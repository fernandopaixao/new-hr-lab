"""Natural language agent over the events of the solution.

Answering happens in three steps, all recorded in the answer for debugging:

1. Interpretation: the model turns the question into a structured query
   (intent, filters, grouping, semantic search text), constrained by a JSON
   schema and by the catalog of event types, statuses, rules and personas
   that exist in the lab.
2. Retrieval, deterministic: filters and aggregations run over the case facts
   (exact numbers, never estimated by the model), and a semantic search over
   the embeddings brings the most relevant event narratives.
3. Answer: the model writes the answer only from that evidence and cites the
   cases it used; citations are validated against what was retrieved.

When Ollama is unavailable the agent refuses, unless the simulated fallback is
enabled: then a keyword interpreter and a template answer are used, and the
answer is marked as simulated.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from typing import Any

from . import embeddings as emb
from .agent import AgentUnavailable, chat_json
from .domain import PERSONAS, STATUS_LABELS
from .facts import FILTER_FIELDS, GROUP_FIELDS, apply_filters, group_count, percentile
from .store import P, Store, dumps, now_ms

HISTORY_KEY = f"{P}:ask:history"

INTENTS = ["CONTAGEM", "AGRUPAMENTO", "LISTA", "BUSCA", "EXPLICACAO_CASO", "DESEMPENHO"]

ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "intencao": {"type": "string", "enum": INTENTS},
        "filtros": {
            "type": "object",
            "properties": {
                "evento_tipo": {"type": "string"}, "status": {"type": "string"}, "colaborador_id": {"type": "string"},
                "colaborador_nome": {"type": "string"}, "cargo": {"type": "string"}, "uf": {"type": "string"},
                "regra_falha": {"type": "string"}, "operacao": {"type": "string"}, "persona_aprovadora": {"type": "string"},
                "cenario": {"type": "string"}, "periodo_horas": {"type": "number"},
            },
        },
        "agrupar_por": {"type": "string", "enum": [""] + list(GROUP_FIELDS)},
        "caso_id": {"type": "string"},
        "consulta_semantica": {"type": "string"},
    },
    "required": ["intencao", "filtros", "agrupar_por", "consulta_semantica"],
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "resposta": {"type": "string"},
        "casos_citados": {"type": "array", "items": {"type": "string"}},
        "confianca": {"type": "number"},
        "limitacoes": {"type": "string"},
    },
    "required": ["resposta", "casos_citados", "confianca"],
}

ROUTER_SYSTEM = """Você interpreta perguntas sobre os eventos de um laboratório de RH de um banco brasileiro.
Converta a pergunta em uma consulta estruturada, usando somente os códigos do catálogo fornecido.
- CONTAGEM: quantos casos atendem a um critério.
- AGRUPAMENTO: distribuição por algum campo (use agrupar_por).
- LISTA: listar casos que atendem a um critério.
- BUSCA: perguntas abertas, por assunto ou semelhança ("casos parecidos com", "o que aconteceu com").
- EXPLICACAO_CASO: explicar um caso específico (preencha caso_id).
- DESEMPENHO: tempos, gargalos, filas, agente de IA.
Preencha apenas os filtros que a pergunta pede. Use status e evento_tipo exatamente como no catálogo.
consulta_semantica é uma frase curta em português que descreve o assunto, para busca por similaridade.
Responda apenas com JSON."""

ANSWER_SYSTEM = """Você é o analista de eventos de um laboratório de RH de um banco brasileiro.
Responda em português, de forma direta, somente com base nas evidências fornecidas.
- Números exatos vêm de "estatisticas"; não estime nem invente números.
- Use "documentos" para explicar o que aconteceu e por quê.
- Cite os casos usados pelo id (ex.: caso-1a2b3c) no texto e em casos_citados.
- Se as evidências não bastarem, diga isso em limitacoes.
- Não use emoji. Use no máximo 8 linhas.
Responda apenas com JSON."""

_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0001F900-\U0001F9FF⭐✅❌]")


def strip_emoji(text: str) -> str:
    return _EMOJI.sub("", text or "")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def catalog(facts: list[dict], event_types: list[dict]) -> dict:
    rules: dict[str, str] = {}
    for f in facts:
        for r in f["regras_falhas"]:
            rules.setdefault(r["id"], r["descricao"] or "")
    return {
        "hoje": time.strftime("%Y-%m-%d"),
        "evento_tipo": {e["evento"]: e["nome"] for e in event_types},
        "status": STATUS_LABELS,
        "personas": {k: v["nome"] for k, v in PERSONAS.items()},
        "agrupar_por": list(GROUP_FIELDS),
        "cargos": sorted({f["cargo"] for f in facts if f.get("cargo")}),
        "ufs": sorted({f["uf"] for f in facts if f.get("uf")}),
        "regras_que_ja_falharam": dict(list(rules.items())[:60]),
        "cenarios": sorted({f["cenario"] for f in facts if f.get("cenario")})[:80],
    }


# ---------------------------------------------------------------- heuristic interpretation
EVENT_WORDS = [
    ("promo", "colaborador.promovido"), ("admiss", "colaborador.admitido"), ("contrata", "colaborador.admitido"),
    ("deslig", "colaborador.desligado"), ("demiss", "colaborador.desligado"), ("transfer", "colaborador.transferido"),
    ("afast", "colaborador.afastado"), ("retorno", "colaborador.retornou_afastamento"), ("merito", "colaborador.merito_concedido"),
    ("bonus", "colaborador.bonus_concedido"), ("jornada", "colaborador.jornada_alterada"), ("dependente", "colaborador.dependente_incluido"),
    ("reversao", "colaborador.revertido_cargo_confianca"), ("reajuste individual", "cct.reajuste_individual"),
    ("reajuste", "cct.reajuste_aplicado"), ("conformidade coletiva", "auditoria.conformidade_coletiva"),
    ("conformidade", "auditoria.conformidade_solicitada"),
]
STATUS_WORDS = [
    ("nao eleg", "NAO_ELEGIVEL"), ("inelegiv", "NAO_ELEGIVEL"), ("compensad", "FALHOU_COMPENSADO"), ("falharam na execu", "FALHOU_COMPENSADO"),
    ("revertid", "REVERTIDO"), ("aguardando aprova", "AGUARDANDO_APROVACAO"), ("pendente", "AGUARDANDO_APROVACAO"),
    ("ressalva", "CONCLUIDO_COM_RESSALVAS"), ("na entrada", "REJEITADO_NA_ENTRADA"), ("rejeitad", "REJEITADO"),
    ("duplicad", "DUPLICADO"), ("cancelad", "CANCELADO"), ("aguardando agente", "AGUARDANDO_AGENTE"), ("concluid", "CONCLUIDO"),
]
GROUP_WORDS = [
    ("por status", "status"), ("por situacao", "status"), ("por tipo", "evento_tipo"), ("por evento", "evento_tipo"),
    ("por cargo", "cargo"), ("por uf", "uf"), ("por estado", "uf"), ("por regra", "regra_falha"), ("regras mais", "regra_falha"), ("quais regras", "regra_falha"), ("regras que", "regra_falha"),
    ("por operacao", "operacao"), ("operacoes mais", "operacao"), ("por persona", "persona_aprovadora"), ("quem aprov", "persona_aprovadora"),
    ("por dia", "dia"), ("por hora", "hora"), ("por estagio", "estagio"), ("por cenario", "cenario"),
]


def heuristic_interpret(question: str, cat: dict) -> dict:
    q = _norm(question)
    filtros: dict[str, Any] = {}
    for word, code in EVENT_WORDS:
        if word in q:
            filtros["evento_tipo"] = code
            break
    for word, code in STATUS_WORDS:
        if word in q:
            filtros["status"] = code
            break
    m = re.search(r"\bf\d{5}\b", q)
    if m:
        filtros["colaborador_id"] = m.group(0).upper()
    m = re.search(r"\b([a-z]{2,4}-(?:[a-z]{2,4}-)?\d{2})\b", q)
    if m:
        filtros["regra_falha"] = m.group(1).upper()
    for code, name in cat["personas"].items():
        if code.lower() in q or _norm(name) in q:
            filtros["persona_aprovadora"] = code
    for uf in cat["ufs"]:
        if re.search(rf"\b{uf.lower()}\b", q) and ("uf" in q or "estado" in q or " em " in q):
            filtros["uf"] = uf
    if "ultima hora" in q:
        filtros["periodo_horas"] = 1
    elif "hoje" in q or "ultimas 24" in q:
        filtros["periodo_horas"] = 24
    group = next((g for w, g in GROUP_WORDS if w in q), "")
    caso = re.search(r"caso-[0-9a-f]{6,}", q)
    if caso:
        intent = "EXPLICACAO_CASO"
    elif any(w in q for w in ("tempo", "lento", "gargalo", "demor", "fila", "latencia", "desempenho")):
        intent = "DESEMPENHO"
    elif group:
        intent = "AGRUPAMENTO"
    elif q.startswith("quant") or "quantos" in q or "quantas" in q or "numero de" in q:
        intent = "CONTAGEM"
    elif any(w in q for w in ("liste", "listar", "quais", "mostre")):
        intent = "LISTA"
    else:
        intent = "BUSCA"
    return {"intencao": intent, "filtros": filtros, "agrupar_por": group, "caso_id": caso.group(0) if caso else "",
            "consulta_semantica": question}


def sanitize_query(parsed: dict) -> dict:
    intent = parsed.get("intencao") if parsed.get("intencao") in INTENTS else "BUSCA"
    filtros = {}
    for k, v in (parsed.get("filtros") or {}).items():
        if k in FILTER_FIELDS or k in ("regra_falha", "operacao", "persona_aprovadora", "periodo_horas"):
            if v not in (None, "", 0):
                filtros[k] = v
    if "status" in filtros and str(filtros["status"]).upper() not in STATUS_LABELS:
        filtros.pop("status")
    group = parsed.get("agrupar_por") if parsed.get("agrupar_por") in GROUP_FIELDS else ""
    return {"intencao": intent, "filtros": filtros, "agrupar_por": group, "caso_id": str(parsed.get("caso_id") or ""),
            "consulta_semantica": str(parsed.get("consulta_semantica") or "")}


# ---------------------------------------------------------------- retrieval
def stats_for(query: dict, facts: list[dict]) -> dict:
    sel = apply_filters(facts, query["filtros"])
    out: dict[str, Any] = {"total_casos_no_laboratorio": len(facts), "casos_que_atendem_aos_filtros": len(sel),
                           "filtros_aplicados": query["filtros"], "por_status": group_count(sel, "status", 12)}
    if query["agrupar_por"]:
        linhas = group_count(sel, query["agrupar_por"], 20)
        if query["agrupar_por"] == "regra_falha":
            desc = {r["id"]: f"{r['id']}: {r['descricao']} ({r['tipo']})" for f in sel for r in f["regras_falhas"]}
            for row in linhas:
                row["rotulo"] = desc.get(row["valor"], row["valor"])
        out["agrupamento"] = {"campo": query["agrupar_por"], "linhas": linhas}
    if query["intencao"] == "DESEMPENHO":
        lead = [f["lead_time_ms"] for f in sel if f["lead_time_ms"]]
        out["tempo_total_ms"] = {"p50": percentile(lead, 50), "p95": percentile(lead, 95)}
        per = {}
        for s in ("intake", "eligibility", "planning", "plan_review", "execution", "audit"):
            vals = [f["etapas"][s]["duracao_ms"] for f in sel if f["etapas"][s]["duracao_ms"] is not None]
            per[s] = {"p50": percentile(vals, 50), "p95": percentile(vals, 95)}
        out["tempo_por_estagio_ms"] = per
        agent_ms = [m for f in sel for m in f["agente_ms"]]
        out["agente_ms"] = {"chamadas": len(agent_ms), "p50": percentile(agent_ms, 50), "p95": percentile(agent_ms, 95)}
    recent = sorted(sel, key=lambda f: -(f["criado_em"] or 0))[:12]
    out["exemplos"] = [{"id": f["id"], "evento_tipo": f["evento_tipo"], "colaborador": f["colaborador_nome"], "status": f["status"],
                        "explicacao": (f["explicacao_final"] or "")[:220]} for f in recent]
    return out


def _search_filters(query: dict) -> dict:
    keep = ("evento_tipo", "status", "colaborador_id", "colaborador_nome", "cargo", "uf", "cenario")
    return {k: v for k, v in query["filtros"].items() if k in keep}


def heuristic_answer(question: str, query: dict, stats: dict, docs: list[dict]) -> dict:
    parts = []
    n = stats["casos_que_atendem_aos_filtros"]
    filt = ", ".join(f"{k}={v}" for k, v in query["filtros"].items()) or "sem filtros"
    if query["intencao"] in ("CONTAGEM", "LISTA", "AGRUPAMENTO", "DESEMPENHO"):
        parts.append(f"{n} caso(s) atendem aos critérios ({filt}), de {stats['total_casos_no_laboratorio']} no laboratório.")
    if stats.get("agrupamento"):
        linhas = "; ".join(f"{r['rotulo']}: {r['quantidade']}" for r in stats["agrupamento"]["linhas"][:8])
        parts.append(f"Por {stats['agrupamento']['campo']}: {linhas}.")
    elif stats["por_status"] and query["intencao"] != "BUSCA":
        parts.append("Situação: " + "; ".join(f"{r['rotulo']}: {r['quantidade']}" for r in stats["por_status"][:6]) + ".")
    if stats.get("tempo_por_estagio_ms"):
        slow = max(stats["tempo_por_estagio_ms"].items(), key=lambda kv: kv[1]["p95"] or 0)
        parts.append(f"O estágio mais lento no p95 é {slow[0]} ({slow[1]['p95']} ms).")
    cited = []
    for d in docs[:3]:
        cid = d["meta"].get("case_id")
        first = d["texto"].split("\n")
        expl = next((ln for ln in first if ln.startswith("Decisão final")), first[0])
        parts.append(f"{cid or d['id']}: {expl}")
        if cid:
            cited.append(cid)
    if not parts:
        parts.append("Não encontrei eventos que respondam a essa pergunta.")
    return {"resposta": "\n".join(parts), "casos_citados": cited, "confianca": 0.4,
            "limitacoes": "Resposta montada pelo agente simulado (sem IA), a partir de palavras-chave."}


# ---------------------------------------------------------------- main entry
async def answer(store: Store, question: str, facts: list[dict], event_types: list[dict], persona: str = "") -> dict:
    settings = await store.settings()
    started = time.time()
    model = settings.get("ask_model") or settings["ollama_model"]
    cat = catalog(facts, event_types)
    trace: dict[str, Any] = {"pergunta": question}
    simulated = False

    # 1. interpretation
    try:
        prompt = f"Catálogo:\n{dumps(cat)}\n\nPergunta: {question}"
        parsed, meta = await chat_json(settings, ROUTER_SYSTEM, prompt, ROUTER_SCHEMA, model=model, num_predict=300)
        query = sanitize_query(parsed)
        trace["interpretacao"] = {"agente": "ollama", "modelo": model, "duracao_ms": meta["duracao_ms"], "bruta": meta["resposta_bruta"]}
    except (AgentUnavailable, json.JSONDecodeError) as exc:
        if isinstance(exc, AgentUnavailable) and not settings.get("heuristic_fallback_enabled"):
            raise
        query = heuristic_interpret(question, cat)
        simulated = isinstance(exc, AgentUnavailable)
        trace["interpretacao"] = {"agente": "heuristico", "motivo": str(exc)}
    trace["consulta"] = query

    # 2. retrieval
    stats = stats_for(query, facts)
    docs: list[dict] = []
    search_info: dict[str, Any] = {}
    if query["caso_id"]:
        doc = await store.r.hmget(emb.DOC_KEY + f"caso:{query['caso_id']}", ["text", "meta"])
        if doc[0]:
            docs.append({"id": f"caso:{query['caso_id']}", "score": 1.0, "meta": json.loads(doc[1] or "{}"), "texto": doc[0]})
    try:
        res = await emb.search(store, query["consulta_semantica"] or question, k=int(settings.get("ask_top_k", 8)),
                               filtros=_search_filters(query))
        docs += [d for d in res["resultados"] if d["id"] not in {x["id"] for x in docs}]
        search_info = {k: v for k, v in res.items() if k != "resultados"}
    except AgentUnavailable as exc:
        if not settings.get("heuristic_fallback_enabled"):
            raise
        search_info = {"erro": str(exc)}
    trace["busca"] = search_info
    known_cases = ({d["meta"].get("case_id") for d in docs if d["meta"].get("case_id")} | {e["id"] for e in stats["exemplos"]}
                   | {d["id"] for d in docs if d["meta"].get("fonte") == "log"})

    # 3. answer
    evidence = {"estatisticas": stats, "documentos": [{"id": d["id"] if d["meta"].get("fonte") == "log" else d["meta"].get("case_id"),
                                                        "fonte": d["meta"].get("fonte"),
                                                        "relevancia": d.get("score"), "texto": d["texto"][:1400]} for d in docs[:8]]}
    if simulated:
        result = heuristic_answer(question, query, stats, docs)
        trace["resposta"] = {"agente": "heuristico"}
    else:
        try:
            prompt = f"Pergunta: {question}\n\nEvidências:\n{dumps(evidence)}"
            parsed, meta = await chat_json(settings, ANSWER_SYSTEM, prompt, ANSWER_SCHEMA, model=model, num_predict=700)
            result = {"resposta": str(parsed.get("resposta") or ""), "casos_citados": [str(c) for c in parsed.get("casos_citados") or []],
                      "confianca": parsed.get("confianca"), "limitacoes": str(parsed.get("limitacoes") or "")}
            trace["resposta"] = {"agente": "ollama", "modelo": model, "duracao_ms": meta["duracao_ms"], "bruta": meta["resposta_bruta"]}
        except (AgentUnavailable, json.JSONDecodeError) as exc:
            if isinstance(exc, AgentUnavailable) and not settings.get("heuristic_fallback_enabled"):
                raise
            result = heuristic_answer(question, query, stats, docs)
            simulated = simulated or isinstance(exc, AgentUnavailable)
            trace["resposta"] = {"agente": "heuristico", "motivo": str(exc)}

    invalid = [c for c in result["casos_citados"] if c not in known_cases]
    result["casos_citados"] = [c for c in dict.fromkeys(result["casos_citados"]) if c in known_cases]
    if invalid:
        result["citacoes_descartadas"] = invalid
    result["resposta"] = strip_emoji(result["resposta"]).strip()
    try:
        conf = float(result.get("confianca") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    result["confianca"] = max(0.0, min(1.0, conf / 100 if conf > 1 else conf))
    out = {
        "id": f"perg-{now_ms()}", "pergunta": question, "persona": persona, "criado_em": now_ms(),
        "simulado": simulated, **result,
        "estatisticas": stats, "documentos": [{k: d.get(k) for k in ("id", "score", "similaridade", "meta", "texto")} for d in docs[:8]],
        "rastro": trace, "duracao_ms": int((time.time() - started) * 1000),
    }
    await store.r.lpush(HISTORY_KEY, dumps(out))
    await store.r.ltrim(HISTORY_KEY, 0, 49)
    return out


async def history(store: Store, limit: int = 30) -> list[dict]:
    return [json.loads(x) for x in await store.r.lrange(HISTORY_KEY, 0, limit - 1)]
