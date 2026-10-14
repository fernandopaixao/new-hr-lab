"""Conference agent (agente de conferência) with two engines: Qwen and JEV.

The deterministic rules decide eligibility and compliance. The agent classifies
eligibility (kind ELEGIBILIDADE, advisory), audits the plan before execution
(kind AUDITORIA) and checks the execution afterwards (kind CONFERENCIA) as a
second line of defense and ALWAYS returns a clear verdict with findings and
reasoning.

Engines (setting agent_engine):
- qwen: the generative model of the configured provider (llm.py), qwen2.5:7b on
  Ollama by default, answering a JSON schema;
- jev: a JEV-style decision model on Ollama (engines.py), tev1:0.8b by default,
  answering typed questions with probabilities.
With agent_compare_enabled the other engine answers the same task right after,
for comparison only. Every call of both engines is recorded in metrics.py.

Optimizations (most matter for a local or network Ollama):
- structured outputs (JSON schema in `format`) so no free text parsing is needed;
- temperature 0 and a fixed seed for reproducible audits;
- compact prompts: only the relevant contract excerpt, the plan and the diff;
- `keep_alive` keeps the model loaded between cases;
- a concurrency semaphore protects a single local GPU from overload;
- a response cache keyed by model and prompt hash (repeated audits in stress tests);
- a health monitor; when the provider is down the case waits (or, if enabled in the
  settings, a heuristic simulated agent answers and is labelled as such).
"""
from __future__ import annotations

import hashlib
import json
import time

import httpx

from . import engines, llm, metrics
from .llm import AgentUnavailable, chat_json  # noqa: F401 - re-exported for the pipeline and the ask agent
from .store import P, Store, dumps, now_ms


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "recomendacao": {"type": "string", "enum": ["APROVADO", "REPROVADO"]},
        "confianca": {"type": "number"},
        "resumo": {"type": "string"},
        "achados": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severidade": {"type": "string", "enum": ["CRITICO", "ALTO", "MEDIO", "BAIXO", "INFO"]},
                    "referencia": {"type": "string"},
                    "descricao": {"type": "string"},
                },
                "required": ["severidade", "descricao"],
            },
        },
        "justificativa": {"type": "string"},
    },
    "required": ["recomendacao", "confianca", "resumo", "achados", "justificativa"],
}

SYSTEM_PROMPT = """Você é o agente de conferência de um sistema de RH de um banco brasileiro.
Sua função é auditar, como segunda linha de defesa, planos de execução antes que qualquer sistema seja alterado
e conferir as execuções concluídas de operações de RH,
verificando aderência à CLT, à convenção coletiva dos bancários (valores ilustrativos), à política interna
e ao contrato de serviço do processo.

Regras de trabalho:
- Responda SEMPRE em português do Brasil, somente com JSON válido no esquema pedido.
- Dê sempre uma recomendação clara: APROVADO ou REPROVADO.
- REPROVE quando houver violação legal, regra bloqueante não atendida, operação sem justificativa,
  operação obrigatória ausente, redução salarial, acesso indevido mantido ou estado final divergente.
- APROVE quando o plano ou a execução estiver coerente com o evento e com os contratos, mesmo com
  observações menores (registre-as como achados BAIXO ou INFO).
- As regras determinísticas já foram avaliadas e vêm no contexto; não as contradiga sem motivo explícito.
- Seja objetivo: cada achado cita a referência (regra, artigo ou cláusula) e descreve o problema em uma frase.
- Não invente fatos que não estejam no contexto."""

def _compact_employee(emp: dict | None) -> dict:
    if not emp:
        return {}
    return {
        "id": emp.get("id"), "cargo": emp.get("cargo"), "situacao": emp.get("situacao"),
        "salario_base": emp.get("salario_base"), "jornada": f"{emp.get('jornada_horas')}h {emp.get('regime_jornada')}",
        "lotacao": f"{emp.get('unidade')} {emp.get('cidade')}/{emp.get('uf')}", "sindicato": emp.get("sindicato"),
        "beneficios": [f"{b.get('codigo')}:{b.get('plano')}" for b in emp.get("beneficios") or []],
        "verbas": [f"{v.get('codigo')}:{v.get('valor')}" for v in emp.get("verbas") or []],
        "acessos": emp.get("acessos") or [], "equipamentos": emp.get("equipamentos") or [],
        "clausulas": [c.get("codigo") for c in emp.get("clausulas") or []],
        "estabilidades": [f"{e.get('tipo')} ate {e.get('fim')}" for e in emp.get("estabilidades") or []],
        "certificacoes": emp.get("certificacoes") or [],
        "conduta": {k: v for k, v in (emp.get("conduta") or {}).items() if k != "advertencias"},
    }


def _rules_digest(rules: list[dict]) -> dict:
    failed = [f"[{r['tipo']}] {r['id']}: {r['explicacao']}" for r in rules if not r.get("passou")]
    return {"avaliadas": len(rules), "nao_atendidas": failed}


def build_audit_prompt(case: dict, processo: dict, cargo_alvo: dict | None) -> str:
    ctx = {
        "tarefa": "Auditar o PLANO antes da execução: nenhum sistema foi alterado ainda; aprove só o que pode ser executado.",
        "evento": {"tipo": case["evento"]["tipo"], "data_efetiva": case["evento"].get("data_efetiva"), "dados": case["evento"].get("dados")},
        "processo": {"codigo": processo.get("codigo"), "nome": processo.get("nome"), "descricao": processo.get("descricao")},
        "elegibilidade": {"decisao": (case.get("elegibilidade") or {}).get("decisao"),
                          "excecoes_aprovadas": [a.get("regra_id") for a in case.get("excecoes_aprovadas") or []]},
        "colaborador_atual": _compact_employee(case.get("estado_inicial")),
        "estado_alvo_do_cargo": (cargo_alvo or {}).get("estado_alvo"),
        "plano": [{"seq": o["seq"], "operacao": o["operacao"], "parametros": o["parametros"], "motivo": o["motivo"]}
                  for o in (case.get("plano") or {}).get("operacoes") or []],
        "operacoes_descartadas": (case.get("plano") or {}).get("descartadas"),
        "estado_projetado": _compact_employee((case.get("plano") or {}).get("projetado")),
        "auditoria_deterministica": _rules_digest((case.get("auditoria") or {}).get("regras") or []),
    }
    return "Contexto do caso (JSON):\n" + json.dumps(ctx, ensure_ascii=False, default=str) + \
        "\n\nAvalie se o plano é aderente ao compliance e às regras de negócio e responda no esquema JSON."


ELIGIBILITY_SCHEMA = {
    "type": "object",
    "properties": {
        "classificacao": {"type": "string", "enum": ["ELEGIVEL", "EXCECAO_NECESSARIA", "NAO_ELEGIVEL"]},
        "confianca": {"type": "number"},
        "resumo": {"type": "string"},
        "achados": RESPONSE_SCHEMA["properties"]["achados"],
        "justificativa": {"type": "string"},
    },
    "required": ["classificacao", "confianca", "resumo", "achados", "justificativa"],
}

ELIGIBILITY_SYSTEM_PROMPT = """Você é o agente de elegibilidade de um sistema de RH de um banco brasileiro.
Classifique se o colaborador é elegível ao evento de RH, segundo a política de movimentação interna, a CLT e a
convenção coletiva dos bancários (valores ilustrativos).

Regras de trabalho:
- Responda SEMPRE em português do Brasil, somente com JSON válido no esquema pedido.
- ELEGIVEL: todas as regras bloqueantes e excecionáveis atendidas.
- EXCECAO_NECESSARIA: só regras excecionáveis não atendidas; depende de aprovação de exceção.
- NAO_ELEGIVEL: alguma regra bloqueante não atendida, restrição de conduta ou impedimento legal.
- As regras determinísticas já foram avaliadas e vêm no contexto; não as contradiga sem motivo explícito.
- Cada achado cita a referência (regra, artigo ou cláusula) e descreve o problema em uma frase.
- Não invente fatos que não estejam no contexto."""


def build_eligibility_prompt(case: dict, processo: dict, subject: dict | None, cargo_alvo: dict | None) -> str:
    el = case.get("elegibilidade") or {}
    ctx = {
        "tarefa": "Classificar a ELEGIBILIDADE do colaborador ao evento, antes de qualquer plano.",
        "evento": {"tipo": case["evento"]["tipo"], "data_efetiva": case["evento"].get("data_efetiva"), "dados": case["evento"].get("dados")},
        "processo": {"codigo": processo.get("codigo"), "nome": processo.get("nome"), "descricao": processo.get("descricao")},
        "colaborador": _compact_employee(subject),
        "cargo_alvo": {"cargo": (cargo_alvo or {}).get("cargo"), "nome": (cargo_alvo or {}).get("nome")},
        "regras": [{"id": r.get("id"), "tipo": r.get("tipo"), "descricao": r.get("descricao"), "passou": r.get("passou"),
                    "explicacao": r.get("explicacao")} for r in el.get("regras") or []],
    }
    return "Contexto do caso (JSON):\n" + json.dumps(ctx, ensure_ascii=False, default=str) + \
        "\n\nClassifique a elegibilidade e responda no esquema JSON."


def build_verification_prompt(case: dict, processo: dict) -> str:
    ctx = {
        "tarefa": "Conferir a EXECUÇÃO concluída: ela deve ser igual ao plano auditado antes da execução.",
        "evento": {"tipo": case["evento"]["tipo"], "data_efetiva": case["evento"].get("data_efetiva"), "dados": case["evento"].get("dados")},
        "processo": {"codigo": processo.get("codigo"), "sla_horas": (processo.get("auditoria") or {}).get("sla_horas")},
        "recibos": [{"operacao": r["operacao"], "status": r["status"], "descricao": r.get("descricao")} for r in (case.get("execucao") or {}).get("recibos") or []],
        "alteracoes": (case.get("execucao") or {}).get("diff"),
        "estado_final": _compact_employee(case.get("estado_final")),
        "conferencia_deterministica": _rules_digest((case.get("conferencia_final") or {}).get("regras") or []),
        "divergencias_auditado_final": (case.get("conferencia_final") or {}).get("divergencias"),
    }
    return "Contexto do caso (JSON):\n" + json.dumps(ctx, ensure_ascii=False, default=str) + \
        "\n\nAvalie se a execução foi aplicada corretamente e em conformidade e responda no esquema JSON."


async def check_health(store: Store, settings: dict) -> dict:
    """Health of the generative provider plus, when JEV is the engine or the comparison is on, of the decision model.

    `ok` follows the engine of the eligibility and audit agents, so cases waiting for the agent resume
    when that engine is back."""
    health = await llm.check_health(settings)
    engine = settings.get("agent_engine", "qwen")
    health["motor"] = engine
    health["ok_qwen"] = health["ok"]
    if engine == "jev" or settings.get("agent_compare_enabled"):
        health["jev"] = await llm.jev_health(settings)
    health["erro_qwen"] = health.get("erro")
    if engine == "jev":
        health["ok"] = health["jev"]["ok"]
        if not health["ok"]:
            health["erro"] = health["jev"]["erro"]
    health["verificado_em"] = now_ms()
    await store.set_json(f"{P}:agent:health", health)
    return health


async def pull_model(settings: dict, model: str | None = None, base_url: str | None = None) -> dict:
    """Downloads a model into Ollama (only Ollama installs models)."""
    url = (base_url or settings["ollama_base_url"]).rstrip("/")
    async with httpx.AsyncClient(timeout=None) as client:
        resp = await client.post(f"{url}/api/pull", json={"model": model or settings["ollama_model"], "stream": False})
        resp.raise_for_status()
        return resp.json()


async def warmup(settings: dict) -> None:
    if settings.get("agent_engine") == "jev" or llm.provider(settings) != "ollama":
        return
    url = settings["ollama_base_url"].rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings["ollama_timeout_s"]) as client:
            await client.post(f"{url}/api/generate", json={"model": settings["ollama_model"], "prompt": "", "keep_alive": settings["ollama_keep_alive"]})
    except Exception:  # noqa: BLE001 - warmup is best effort
        pass


ELIGIBILITY_CLASSES = ("ELEGIVEL", "EXCECAO_NECESSARIA", "NAO_ELEGIVEL")


def _normalize(parsed: dict, kind: str = "AUDITORIA") -> dict:
    if kind == "ELEGIBILIDADE":
        cls = str(parsed.get("classificacao", "")).upper()
        out = _normalize({**parsed, "recomendacao": "APROVADO"})
        out.pop("recomendacao")
        cls = cls if cls in ELIGIBILITY_CLASSES else "NAO_ELEGIVEL"
        return {**out, "classificacao": cls, "veredito": cls}
    rec = str(parsed.get("recomendacao", "")).upper()
    if rec not in ("APROVADO", "REPROVADO"):
        rec = "REPROVADO"
    try:
        conf = float(parsed.get("confianca", 0.5))
    except (TypeError, ValueError):
        conf = 0.5
    if conf > 1:
        conf = conf / 100
    return {
        "recomendacao": rec, "confianca": max(0.0, min(1.0, conf)), "resumo": str(parsed.get("resumo") or ""),
        "achados": [a for a in parsed.get("achados") or [] if isinstance(a, dict)],
        "justificativa": str(parsed.get("justificativa") or ""), "veredito": rec,
    }


def heuristic_review(kind: str, case: dict) -> dict:
    """Simulated agent used only when enabled in the settings and the LLM is unavailable."""
    if kind == "ELEGIBILIDADE":
        el = case.get("elegibilidade") or {}
        cls = el.get("decisao") if el.get("decisao") in ELIGIBILITY_CLASSES else "NAO_ELEGIVEL"
        return {"classificacao": cls, "veredito": cls, "confianca": 0.6, "achados": [],
                "resumo": f"Agente simulado (heurístico): repete a decisão das regras ({cls}).",
                "justificativa": "Avaliação heurística baseada nas regras determinísticas. Não substitui o agente de IA."}
    if kind == "AUDITORIA":
        rules = (case.get("auditoria") or {}).get("regras") or []
        ops = [o["operacao"] for o in (case.get("plano") or {}).get("operacoes") or []]
    else:
        rules = (case.get("conferencia_final") or {}).get("regras") or []
        ops = [r["operacao"] for r in (case.get("execucao") or {}).get("recibos") or []]
    achados = []
    for r in rules:
        if not r.get("passou") and r.get("tipo") != "ALERTA":
            achados.append({"severidade": "ALTO" if r["tipo"] == "BLOQUEANTE" else "MEDIO", "referencia": r["id"], "descricao": r["explicacao"]})
    tipo = case["evento"]["tipo"]
    if tipo in ("colaborador.promovido", "colaborador.merito_concedido", "colaborador.transferido", "colaborador.desligado") and "ENVIAR_ESOCIAL" not in ops \
            and not (tipo == "colaborador.desligado" and "INICIAR_GARDEN_LEAVE" in ops):
        achados.append({"severidade": "MEDIO", "referencia": "eSocial", "descricao": "Alteração contratual sem evento eSocial correspondente."})
    if tipo == "colaborador.desligado" and kind == "AUDITORIA" and "CALCULAR_RESCISAO" not in ops:
        achados.append({"severidade": "ALTO", "referencia": "CLT art. 477", "descricao": "Desligamento sem cálculo de rescisão."})
    bloqueia = any(a["severidade"] in ("ALTO", "CRITICO") for a in achados)
    return {
        "recomendacao": "REPROVADO" if bloqueia else "APROVADO", "veredito": "REPROVADO" if bloqueia else "APROVADO",
        "confianca": 0.6,
        "resumo": "Agente simulado (heurístico): " + ("encontrou problemas que impedem a aprovação." if bloqueia else "não encontrou problemas relevantes."),
        "achados": achados,
        "justificativa": "Avaliação heurística baseada nas regras determinísticas e em verificações simples de coerência. Não substitui o agente de IA.",
    }


OTHER_ENGINE = {"qwen": "jev", "jev": "qwen"}
COMPARISON_KEYS = ("motor", "modelo", "veredito", "recomendacao", "classificacao", "confianca", "resumo", "achados", "resposta_ms",
                   "processamento_ms", "cache", "erro", "risco", "probabilidades")


def _invalid(kind: str, error: str) -> dict:
    """Verdict when the engine answered out of format: the strictest one, so a person looks at the case."""
    out = {"confianca": 0.0, "achados": [{"severidade": "ALTO", "referencia": "agente", "descricao": error}], "justificativa": error, "erro": error}
    if kind == "ELEGIBILIDADE":
        return {**out, "classificacao": "NAO_ELEGIVEL", "veredito": "NAO_ELEGIVEL",
                "resumo": "O agente respondeu em formato inválido; a decisão fica com as regras."}
    return {**out, "recomendacao": "REPROVADO", "veredito": "REPROVADO",
            "resumo": "O agente respondeu em formato inválido; o caso segue para revisão humana."}


async def _call_qwen(settings: dict, kind: str, case: dict, processo: dict, cargo_alvo: dict | None, subject: dict | None,
                     attempt: int) -> tuple[dict, dict, str]:
    if kind == "ELEGIBILIDADE":
        prompt, system, schema = build_eligibility_prompt(case, processo, subject, cargo_alvo), ELIGIBILITY_SYSTEM_PROMPT, ELIGIBILITY_SCHEMA
    elif kind == "AUDITORIA":
        prompt, system, schema = build_audit_prompt(case, processo, cargo_alvo), SYSTEM_PROMPT, RESPONSE_SCHEMA
    else:
        prompt, system, schema = build_verification_prompt(case, processo), SYSTEM_PROMPT, RESPONSE_SCHEMA
    parsed, meta = await chat_json(settings, system, prompt if attempt == 0 else prompt + "\n\nResponda apenas com JSON válido.", schema)
    result = _normalize(parsed, kind)
    result.update({**meta, "agente": llm.provider(settings), "url": settings["ollama_base_url"] if llm.provider(settings) == "ollama" else None})
    return result, meta, prompt


async def _call_jev(settings: dict, kind: str, case: dict, processo: dict, cargo_alvo: dict | None, subject: dict | None,
                    attempt: int) -> tuple[dict, dict, str]:
    state = engines.build_state(kind, case, processo, cargo_alvo, _compact_employee, subject)
    answers, meta = await llm.decide(settings, state, engines.QUESTIONS[kind])
    result = engines.interpret(kind, answers, meta["modelo"])
    result.update({**meta, "agente": "jev", "respostas": answers})
    return result, meta, json.dumps({"state": state, "questions": engines.QUESTIONS[kind]}, ensure_ascii=False)


def _identity(settings: dict, engine: str) -> tuple[str, str]:
    if engine == "jev":
        return "ollama-jev", settings["jev_model"]
    return llm.provider(settings), llm.active_model(settings)


async def run_engine(store: Store, settings: dict, engine: str, kind: str, case: dict, processo: dict, cargo_alvo: dict | None = None,
                     subject: dict | None = None, *, papel: str = "principal") -> dict:
    """One task on one engine, with cache, one retry on an invalid answer and the heuristic fallback (main engine only).

    Records the call in the performance history. Raises AgentUnavailable when the engine is down and the
    heuristic fallback is off (or for the comparison engine, always)."""
    started = time.time()
    started_ms = now_ms()
    prov, model = _identity(settings, engine)
    call = _call_jev if engine == "jev" else _call_qwen
    if engine == "jev":
        fingerprint = json.dumps(engines.build_state(kind, case, processo, cargo_alvo, _compact_employee, subject), ensure_ascii=False, sort_keys=True)
    elif kind == "ELEGIBILIDADE":
        fingerprint = build_eligibility_prompt(case, processo, subject, cargo_alvo)
    elif kind == "AUDITORIA":
        fingerprint = build_audit_prompt(case, processo, cargo_alvo)
    else:
        fingerprint = build_verification_prompt(case, processo)
    # the old key shape (provider|model|prompt) still serves the generative audits cached before the engines
    raw_key = f"{prov}|{model}|{fingerprint}" if engine == "qwen" and kind != "ELEGIBILIDADE" else f"{engine}|{prov}|{model}|{kind}|{fingerprint}"
    cache_key = f"{P}:agent:cache:" + hashlib.sha256(raw_key.encode()).hexdigest()

    def finish(result: dict) -> dict:
        result.update({"motor": engine, "papel": papel, "processamento_ms": int((time.time() - started) * 1000)})
        result.setdefault("modelo", model)
        result["duracao_ms"] = result["processamento_ms"]
        return result

    async def save_metric(result: dict | None, error: str | None = None) -> None:
        try:
            await metrics.record(store, metrics.build_record(motor=(result or {}).get("motor", engine), papel=papel, kind=kind, case=case,
                                                             result=result, started_ms=started_ms, erro=error))
        except Exception:  # noqa: BLE001 - metrics never stop a case
            pass

    if settings["agent_cache_enabled"]:
        cached = await store.get_json(cache_key)
        if cached:
            cached.update({"cache": True, "resposta_ms": 0, "espera_ms": 0})
            cached.setdefault("veredito", cached.get("classificacao") or cached.get("recomendacao"))
            result = finish(cached)
            await save_metric(result)
            return result
    last_error, invalid_answer = None, False
    for attempt in range(2):
        try:
            result, _meta, prompt = await call(settings, kind, case, processo, cargo_alvo, subject, attempt)
            result.update({"prompt": prompt, "cache": False, "tentativas": attempt + 1, "modelo": model})
            result = finish(result)
            if settings["agent_cache_enabled"]:
                await store.r.set(cache_key, dumps(result), ex=86400)
            await save_metric(result)
            return result
        except ValueError as exc:  # json.JSONDecodeError included
            last_error, invalid_answer = f"resposta fora do formato: {exc}", True
            continue
        except AgentUnavailable as exc:
            last_error, invalid_answer = str(exc), False
            break
    if invalid_answer:
        result = finish({**_invalid(kind, last_error), "agente": engine, "modelo": model, "provedor": prov})
        await save_metric(result)
        return result
    await save_metric({"motor": engine, "modelo": model, "provedor": prov}, last_error)
    if papel == "principal" and settings["heuristic_fallback_enabled"]:
        result = heuristic_review(kind, case)
        result.update({"agente": "heuristico", "modelo": "agente simulado (heurístico)", "motivo_fallback": last_error})
        result = finish(result)
        result["motor"] = "heuristico"
        await save_metric(result)
        return result
    name = "JEV" if engine == "jev" else llm.PROVIDERS[prov]["nome"]
    raise AgentUnavailable(last_error or f"{name} indisponível")


async def review(store: Store, kind: str, case: dict, processo: dict, cargo_alvo: dict | None = None, subject: dict | None = None) -> dict:
    """Runs the task on the configured engine and, when enabled, on the other one for comparison."""
    settings = await store.settings()
    engine = settings.get("agent_engine") or "qwen"
    result = await run_engine(store, settings, engine, kind, case, processo, cargo_alvo, subject)
    if settings.get("agent_compare_enabled"):
        other = OTHER_ENGINE.get(engine, "qwen")
        try:
            shadow = await run_engine(store, settings, other, kind, case, processo, cargo_alvo, subject, papel="comparacao")
        except Exception as exc:  # noqa: BLE001 - the comparison never stops a case
            shadow = {"motor": other, "erro": str(exc)}
        comp = {k: shadow.get(k) for k in COMPARISON_KEYS if k in shadow}
        comp["concorda"] = shadow.get("veredito") == result.get("veredito") if shadow.get("veredito") and not shadow.get("erro") else None
        result["comparacao"] = comp
    return result
