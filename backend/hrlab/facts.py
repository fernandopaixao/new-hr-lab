"""Read model over cases: flat facts, narrative documents and aggregations.

Cases are the system of record of every event that entered the line. This
module turns them into:
- facts: one flat row per case, used by dashboards and by the natural language
  agent to answer counting and aggregation questions deterministically;
- documents: one narrative text per case (and per relevant log entry), which
  is what gets embedded for semantic search;
- insights: the visibility dashboard (funnel, lead times, bottlenecks, top
  failing rules, operations, approvals, agent agreement and alerts).

Everything here is pure: no Redis, no network.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Iterable

from .domain import ACTIVE_STATUSES, FINAL_STATUSES, PERSONAS, STAGE_KEYS, STAGES, STATUS_LABELS

STAGE_NAMES = {k: n for k, n, _ in STAGES}
AGENT_KEYS = ("agente_auditoria", "agente_conferencia")

# Log kinds that become searchable documents on their own (the rest is already
# part of the case narrative).
# Lab controls (pause, settings, reindex) are left out on purpose: they are not
# HR events and would only add noise to the answers.
INDEXED_LOG_KINDS = {
    "APROVACAO_DECIDIDA", "CONTRATO_ALTERADO", "COLABORADOR_ALTERADO",
    "OPERACAO_FALHOU", "COMPENSACAO", "EVENTO_REJEITADO", "REPLANEJAMENTO",
}

# Fields that the natural language agent may filter and group by.
FILTER_FIELDS = ("evento_tipo", "status", "colaborador_id", "colaborador_nome", "cargo", "cargo_alvo", "uf", "unidade",
                 "processo", "cenario", "estagio", "recomendacao_auditoria", "recomendacao_conferencia", "gestor_id")
GROUP_FIELDS = ("status", "evento_tipo", "processo", "estagio", "cargo", "cargo_alvo", "uf", "unidade", "cenario",
                "regra_falha", "operacao", "operacao_falha", "persona_aprovadora", "recomendacao_auditoria",
                "recomendacao_conferencia", "gestor_id", "dia", "hora")


def _int(v: Any, default: int | None = None) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def iso(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def failed_rules(section: dict | None) -> list[dict]:
    return [r for r in (section or {}).get("regras") or [] if not r.get("passou")]


# ---------------------------------------------------------------- facts
def case_fact(case: dict, approvals: dict[str, dict] | None = None, employee: dict | None = None) -> dict:
    """Flat, analysis-friendly view of one case.

    The employee snapshot taken by the case is preferred; cases that stopped
    before planning have none, so the current employee record fills the gaps.
    """
    approvals = approvals or {}
    ev = case.get("evento") or {}
    emp = case.get("estado_inicial") or case.get("estado_final") or employee or {}
    etapas = case.get("etapas") or {}
    plano = case.get("plano") or {}
    recibos = (case.get("execucao") or {}).get("recibos") or []
    aps = [approvals.get(a) or {"id": a} for a in case.get("aprovacoes") or [] if isinstance(a, str)]
    aps += [a for a in case.get("aprovacoes") or [] if isinstance(a, dict)]
    regras_falhas = []
    for key in ("elegibilidade", "auditoria", "conferencia_final"):
        for r in failed_rules(case.get(key)):
            regras_falhas.append({"id": r.get("id"), "tipo": r.get("tipo"), "secao": key, "descricao": r.get("descricao"),
                                  "explicacao": r.get("explicacao")})
    criado = _int(case.get("criado_em"), 0) or 0
    fim = _int(case.get("finalizado_em"))
    return {
        "id": case.get("id"),
        "evento_id": case.get("evento_id"),
        "evento_tipo": case.get("evento_tipo"),
        "processo": case.get("processo_nome") or case.get("processo_codigo"),
        "status": case.get("status"),
        "status_rotulo": STATUS_LABELS.get(case.get("status"), case.get("status")),
        "final": case.get("status") in FINAL_STATUSES,
        "estagio": case.get("estagio"),
        "colaborador_id": case.get("colaborador_id"),
        "colaborador_nome": case.get("colaborador_nome") or emp.get("nome"),
        "cargo": emp.get("cargo") or (ev.get("dados") or {}).get("cargo"),
        "cargo_alvo": case.get("cargo_alvo"),
        "gestor_id": emp.get("gestor_id"),
        "uf": emp.get("uf") or (ev.get("dados") or {}).get("uf"),
        "unidade": emp.get("unidade") or (ev.get("dados") or {}).get("unidade"),
        "cenario": case.get("cenario"),
        "pai_id": case.get("pai_id"),
        "data_efetiva": ev.get("data_efetiva"),
        "criado_em": criado,
        "finalizado_em": fim,
        "lead_time_ms": (fim - criado) if fim and criado else None,
        "dia": (iso(criado) or "")[:10],
        "hora": (iso(criado) or "")[:13],
        "etapas": {s: {"status": (etapas.get(s) or {}).get("status"), "duracao_ms": _int((etapas.get(s) or {}).get("duracao_ms"))}
                   for s in STAGE_KEYS},
        "elegibilidade": (case.get("elegibilidade") or {}).get("decisao"),
        "auditoria": (case.get("auditoria") or {}).get("decisao"),
        "conferencia_final": (case.get("conferencia_final") or {}).get("decisao"),
        "recomendacao_auditoria": case.get("recomendacao_auditoria") or (case.get("agente_auditoria") or {}).get("recomendacao"),
        "recomendacao_conferencia": case.get("recomendacao_conferencia") or (case.get("agente_conferencia") or {}).get("recomendacao"),
        "agente_simulado": any((case.get(k) or {}).get("agente") == "heuristico" for k in AGENT_KEYS),
        "agente_ms": [m for m in (_int((case.get(k) or {}).get("duracao_ms")) for k in AGENT_KEYS
                                  if case.get(k) and not (case.get(k) or {}).get("cache")) if m is not None],
        "regras_falhas": regras_falhas,
        "operacoes": [o.get("operacao") for o in plano.get("operacoes") or []],
        "operacoes_descartadas": [o.get("operacao") for o in plano.get("descartadas") or []],
        "operacoes_executadas": [r.get("operacao") for r in recibos if r.get("status") in ("EXECUTADA", "COMPENSADA")],
        "operacoes_falhas": [r.get("operacao") for r in recibos if r.get("status") == "FALHOU"],
        "compensado": case.get("status") == "FALHOU_COMPENSADO" or any(r.get("status") == "COMPENSADA" for r in recibos),
        "replanejamentos": _int(case.get("replanejamentos"), 0),
        "aprovacoes": [{"id": a.get("id"), "tipo": a.get("tipo"), "status": a.get("status"),
                        "persona": (a.get("decidido_por") or {}).get("persona"), "aprovadores": a.get("aprovadores") or [],
                        "justificativa": a.get("justificativa"), "criado_em": _int(a.get("criado_em")),
                        "decidido_em": _int(a.get("decidido_em"))} for a in aps],
        "explicacao_final": (case.get("decisao_final") or {}).get("explicacao") or case.get("resumo"),
    }


def _values(fact: dict, field: str) -> list[Any]:
    """Values of a (possibly multi-valued) field for grouping."""
    if field == "regra_falha":
        return [r["id"] for r in fact["regras_falhas"]] or []
    if field == "operacao":
        return fact["operacoes_executadas"] or fact["operacoes"]
    if field == "operacao_falha":
        return fact["operacoes_falhas"]
    if field == "persona_aprovadora":
        return [a["persona"] for a in fact["aprovacoes"] if a.get("persona")]
    return [fact.get(field)]


def apply_filters(facts: Iterable[dict], filtros: dict | None, now_ms: int | None = None) -> list[dict]:
    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "", [], 0) or k == "final"}
    now_ms = now_ms or int(time.time() * 1000)
    out = []
    for f in facts:
        ok = True
        for key, want in filtros.items():
            if key == "periodo_horas":
                ok = f["criado_em"] >= now_ms - float(want) * 3600_000
            elif key == "desde":
                ok = (f.get("dia") or "") >= str(want)[:10]
            elif key == "ate":
                ok = (f.get("dia") or "") <= str(want)[:10]
            elif key == "final":
                ok = f["final"] == bool(want)
            elif key == "regra_falha":
                ok = any(str(want).upper() in (r["id"] or "").upper() for r in f["regras_falhas"])
            elif key == "operacao":
                ok = str(want).upper() in [o.upper() for o in f["operacoes"] + f["operacoes_falhas"]]
            elif key == "persona_aprovadora":
                ok = any((a.get("persona") or "") == str(want).upper() for a in f["aprovacoes"])
            elif key == "colaborador_nome":
                ok = str(want).lower() in (f.get("colaborador_nome") or "").lower()
            elif key in FILTER_FIELDS:
                vals = want if isinstance(want, list) else [want]
                ok = str(f.get(key) or "").upper() in [str(v).upper() for v in vals]
            if not ok:
                break
        if ok:
            out.append(f)
    return out


def group_count(facts: list[dict], field: str, top: int = 25) -> list[dict]:
    counts: dict[str, int] = {}
    for f in facts:
        for v in _values(f, field):
            if v is None or v == "":
                continue
            counts[str(v)] = counts.get(str(v), 0) + 1
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    return [{"valor": k, "rotulo": STATUS_LABELS.get(k, PERSONAS.get(k, {}).get("nome", k)), "quantidade": n} for k, n in rows]


def percentile(values: list[int], p: float) -> int | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = max(0, min(len(vals) - 1, int(round((p / 100) * (len(vals) - 1)))))
    return vals[k]


# ---------------------------------------------------------------- documents
def case_document(case: dict, approvals: dict[str, dict] | None = None, employee: dict | None = None) -> tuple[str, dict]:
    """Narrative text of a case, used for embeddings, plus its metadata."""
    f = case_fact(case, approvals, employee)
    ev = case.get("evento") or {}
    dados = ev.get("dados") or {}
    lines = [
        f"Caso {f['id']} do evento {f['evento_tipo']} ({f['processo'] or 'sem processo'}).",
        f"Colaborador {f['colaborador_nome'] or '-'} ({f['colaborador_id'] or '-'}), cargo {f['cargo'] or '-'}"
        + (f", cargo alvo {f['cargo_alvo']}" if f["cargo_alvo"] and f["cargo_alvo"] != f["cargo"] else "")
        + (f", unidade {f['unidade']} {f['uf'] or ''}" if f["unidade"] else "") + ".",
        f"Data efetiva {f['data_efetiva']}; situação final: {f['status_rotulo']}.",
    ]
    if dados:
        resumo_dados = ", ".join(f"{k}={v}" for k, v in list(dados.items())[:10] if not isinstance(v, (dict, list)))
        if resumo_dados:
            lines.append(f"Dados do evento: {resumo_dados}.")
    if case.get("cenario"):
        lines.append(f"Cenário de teste: {case['cenario']}.")
    el = case.get("elegibilidade") or {}
    if el:
        lines.append(f"Elegibilidade: {el.get('explicacao') or el.get('decisao')}")
    for r in f["regras_falhas"]:
        lines.append(f"Regra {r['id']} ({r['tipo']}, {r['secao']}) não atendida: {r['explicacao'] or r['descricao']}")
    plano = case.get("plano") or {}
    if plano.get("resumo"):
        lines.append(f"Plano: {plano['resumo']}")
    for o in (plano.get("operacoes") or [])[:20]:
        lines.append(f"Operação {o.get('operacao')} em {o.get('sistema')}: {o.get('motivo')}")
    for o in (plano.get("descartadas") or [])[:10]:
        lines.append(f"Operação {o.get('operacao')} descartada: {o.get('motivo_descarte')}")
    for k, label in (("agente_auditoria", "Agente na auditoria antes da execução"), ("agente_conferencia", "Agente na conferência final")):
        a = case.get(k)
        if a:
            achados = "; ".join(str(x.get("descricao")) for x in (a.get("achados") or [])[:5])
            lines.append(f"{label}: recomenda {a.get('recomendacao')} (confiança {a.get('confianca')}). {a.get('resumo') or ''} "
                         f"{('Achados: ' + achados) if achados else ''}".strip())
    for r in (case.get("execucao") or {}).get("recibos") or []:
        if r.get("status") != "EXECUTADA":
            lines.append(f"Execução de {r.get('operacao')}: {r.get('status')} {r.get('erro') or ''}".strip())
    for a in f["aprovacoes"]:
        if a.get("persona"):
            lines.append(f"Aprovação {a['tipo']} {(a['status'] or '').lower()} por {a['persona']}: {a.get('justificativa') or ''}")
        else:
            lines.append(f"Aprovação {a['tipo']} {(a['status'] or 'pendente').lower()}, aguardando {', '.join(a['aprovadores'])}.")
    for k, label in (("auditoria", "Auditoria antes da execução"), ("conferencia_final", "Conferência final")):
        if (case.get(k) or {}).get("decisao"):
            lines.append(f"{label}: {case[k]['decisao']}.")
    if f["explicacao_final"]:
        lines.append(f"Decisão final: {f['explicacao_final']}")
    meta = {k: f.get(k) for k in ("id", "evento_tipo", "status", "colaborador_id", "colaborador_nome", "cargo", "cargo_alvo",
                                  "uf", "unidade", "processo", "cenario", "criado_em", "dia", "final")}
    meta["fonte"] = "caso"
    meta["case_id"] = f["id"]
    return "\n".join(x for x in lines if x), meta


def log_document(entry: dict) -> tuple[str, dict]:
    text = f"{entry.get('tipo')} por {entry.get('ator')}: {entry.get('mensagem')}"
    if entry.get("colaborador_id"):
        text += f" Colaborador {entry['colaborador_id']}."
    if entry.get("case_id"):
        text += f" Caso {entry['case_id']}."
    meta = {"fonte": "log", "tipo": entry.get("tipo"), "case_id": entry.get("case_id") or None,
            "colaborador_id": entry.get("colaborador_id") or None, "criado_em": _int(entry.get("ts"), 0),
            "dia": (iso(_int(entry.get("ts"), 0)) or "")[:10], "ator": entry.get("ator")}
    return text, meta


# ---------------------------------------------------------------- insights
def insights(facts: list[dict], *, queues: dict | None = None, pending_approvals: list[dict] | None = None,
             employees_compliance: list[dict] | None = None, now_ms: int | None = None, bucket_min: int = 5,
             buckets: int = 24) -> dict:
    """Visibility dashboard computed from facts."""
    now_ms = now_ms or int(time.time() * 1000)
    total = len(facts)
    finals = [f for f in facts if f["final"]]

    # funnel: how many cases reached each stage, and where the non-finished ones are
    funnel = []
    for s in STAGE_KEYS:
        reached = sum(1 for f in facts if f["etapas"][s]["status"] not in (None, "PENDENTE"))
        ok = sum(1 for f in facts if f["etapas"][s]["status"] == "OK")
        here = sum(1 for f in facts if not f["final"] and f["estagio"] == s)
        funnel.append({"estagio": s, "nome": STAGE_NAMES[s], "alcancaram": reached, "concluiram": ok, "em_andamento": here})

    # lead times per stage
    tempos = []
    for s in STAGE_KEYS:
        vals = [f["etapas"][s]["duracao_ms"] for f in facts if f["etapas"][s]["duracao_ms"] is not None]
        tempos.append({"estagio": s, "nome": STAGE_NAMES[s], "n": len(vals), "p50_ms": percentile(vals, 50),
                       "p95_ms": percentile(vals, 95), "max_ms": max(vals) if vals else None})
    lead = [f["lead_time_ms"] for f in finals if f["lead_time_ms"] is not None]

    # throughput timeline
    size = bucket_min * 60_000
    start = now_ms - buckets * size
    timeline = [{"inicio": start + i * size, "entradas": 0, "finalizados": 0, "problemas": 0} for i in range(buckets)]
    for f in facts:
        i = (f["criado_em"] - start) // size if f["criado_em"] else -1
        if 0 <= i < buckets:
            timeline[i]["entradas"] += 1
        if f["finalizado_em"]:
            j = (f["finalizado_em"] - start) // size
            if 0 <= j < buckets:
                timeline[j]["finalizados"] += 1
                if f["status"] not in ("CONCLUIDO", "CONCLUIDO_COM_RESSALVAS"):
                    timeline[j]["problemas"] += 1

    # matrix event type x status
    matrix: dict[str, dict[str, int]] = {}
    for f in facts:
        row = matrix.setdefault(f["evento_tipo"] or "?", {})
        row[f["status"]] = row.get(f["status"], 0) + 1

    # rules
    rules: dict[str, dict] = {}
    for f in facts:
        for r in f["regras_falhas"]:
            item = rules.setdefault(r["id"], {"id": r["id"], "descricao": r["descricao"], "tipo": r["tipo"], "secao": r["secao"], "quantidade": 0,
                                              "exemplos": []})
            item["quantidade"] += 1
            if len(item["exemplos"]) < 3:
                item["exemplos"].append(f["id"])
    top_rules = sorted(rules.values(), key=lambda r: -r["quantidade"])[:15]

    # operations
    ops: dict[str, dict] = {}
    for f in facts:
        for o in f["operacoes_executadas"]:
            ops.setdefault(o, {"operacao": o, "executadas": 0, "falhas": 0, "descartadas": 0})["executadas"] += 1
        for o in f["operacoes_falhas"]:
            ops.setdefault(o, {"operacao": o, "executadas": 0, "falhas": 0, "descartadas": 0})["falhas"] += 1
        for o in f["operacoes_descartadas"]:
            ops.setdefault(o, {"operacao": o, "executadas": 0, "falhas": 0, "descartadas": 0})["descartadas"] += 1
    operations = sorted(ops.values(), key=lambda o: -(o["executadas"] + o["falhas"]))

    # approvals
    decided = [a for f in facts for a in f["aprovacoes"] if a.get("decidido_em")]
    by_persona: dict[str, dict] = {}
    for a in decided:
        p = by_persona.setdefault(a["persona"], {"persona": a["persona"], "nome": PERSONAS.get(a["persona"], {}).get("nome"),
                                                 "aprovadas": 0, "rejeitadas": 0, "tempos": []})
        p["aprovadas" if a["status"] == "APROVADA" else "rejeitadas"] += 1
        if a.get("criado_em"):
            p["tempos"].append(a["decidido_em"] - a["criado_em"])
    for p in by_persona.values():
        p["tempo_mediano_ms"] = percentile(p.pop("tempos"), 50)
    pend = pending_approvals or []
    pend_by: dict[str, int] = {}
    oldest = None
    for a in pend:
        for who in a.get("aprovadores") or []:
            pend_by[who] = pend_by.get(who, 0) + 1
        c = _int(a.get("criado_em"))
        if c and (oldest is None or c < oldest):
            oldest = c

    # agent vs rules agreement
    agreement = {"concordam": 0, "agente_mais_rigoroso": 0, "regras_mais_rigorosas": 0, "simulado": 0}
    for f in facts:
        for rule_dec, rec in ((f["auditoria"], f["recomendacao_auditoria"]), (f["conferencia_final"], f["recomendacao_conferencia"])):
            if not rule_dec or not rec:
                continue
            rules_ok = rule_dec in ("APROVADO", "APROVADO_COM_RESSALVAS")
            agent_ok = rec == "APROVADO"
            if rules_ok == agent_ok:
                agreement["concordam"] += 1
            elif rules_ok:
                agreement["agente_mais_rigoroso"] += 1
            else:
                agreement["regras_mais_rigorosas"] += 1
        if f["agente_simulado"]:
            agreement["simulado"] += 1
    agent_ms = [m for f in facts for m in f["agente_ms"]]

    # alerts
    alerts = []
    for stage, q in (queues or {}).items():
        backlog = int((q or {}).get("atraso") or 0) + int((q or {}).get("pendentes") or 0)
        if backlog >= 20:
            alerts.append({"nivel": "ALTO", "texto": f"Fila de {STAGE_NAMES.get(stage, stage)} acumulada: {backlog} mensagens aguardando."})
    waiting_agent = sum(1 for f in facts if f["status"] == "AGUARDANDO_AGENTE")
    if waiting_agent:
        alerts.append({"nivel": "ALTO", "texto": f"{waiting_agent} caso(s) aguardando o agente de IA: verifique o Ollama."})
    if oldest and now_ms - oldest > 30 * 60_000:
        alerts.append({"nivel": "MEDIO", "texto": f"Há aprovação pendente há {int((now_ms - oldest) / 60_000)} minutos."})
    recent = [f for f in finals if f["finalizado_em"] and now_ms - f["finalizado_em"] < 3600_000]
    if len(recent) >= 10:
        failed = sum(1 for f in recent if f["status"] in ("FALHOU_COMPENSADO", "ERRO", "REVERTIDO"))
        if failed / len(recent) > 0.2:
            alerts.append({"nivel": "ALTO", "texto": f"{failed} de {len(recent)} casos da última hora falharam, foram compensados ou revertidos."})
    if agreement["agente_mais_rigoroso"] >= 3:
        alerts.append({"nivel": "MEDIO", "texto": f"O agente reprovou {agreement['agente_mais_rigoroso']} vez(es) o que as regras aprovaram: "
                                                  "vale revisar contratos ou o prompt."})
    nonconf = [e for e in employees_compliance or [] if not e.get("conforme")]
    if nonconf:
        alerts.append({"nivel": "BAIXO", "texto": f"{len(nonconf)} colaborador(es) fora do estado alvo ou do compliance do cargo."})

    status_counts = group_count(facts, "status", top=50)
    concluded = sum(1 for f in finals if f["status"] in ("CONCLUIDO", "CONCLUIDO_COM_RESSALVAS"))
    return {
        "gerado_em": now_ms,
        "kpis": {
            "casos": total, "em_andamento": sum(1 for f in facts if f["status"] in ACTIVE_STATUSES), "finalizados": len(finals),
            "taxa_conclusao": round(concluded / len(finals), 3) if finals else None,
            "lead_time_p50_ms": percentile(lead, 50), "lead_time_p95_ms": percentile(lead, 95),
            "aprovacoes_pendentes": len(pend), "compensacoes": sum(1 for f in facts if f["compensado"]),
            "replanejamentos": sum(f["replanejamentos"] or 0 for f in facts),
            "agente_p50_ms": percentile(agent_ms, 50), "agente_p95_ms": percentile(agent_ms, 95),
        },
        "funil": funnel,
        "tempos_por_estagio": tempos,
        "linha_do_tempo": {"balde_min": bucket_min, "pontos": timeline},
        "por_status": status_counts,
        "matriz_evento_status": matrix,
        "regras_mais_falhas": top_rules,
        "operacoes": operations,
        "aprovacoes": {"pendentes_por_persona": pend_by, "decisoes_por_persona": sorted(by_persona.values(), key=lambda p: p["persona"] or ""),
                       "pendente_mais_antiga_em": oldest},
        "agente": {"concordancia": agreement, "chamadas": len(agent_ms)},
        "conformidade_colaboradores": {"total": len(employees_compliance or []), "fora": len(nonconf)},
        "alertas": alerts,
    }
