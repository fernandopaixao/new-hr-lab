"""Conference agent (agente de conferência) backed by Ollama.

The deterministic rules decide eligibility and compliance. The agent reviews the
plan and the execution as a second line of defense and ALWAYS returns a clear
recommendation (APROVADO or REPROVADO) with findings and reasoning.

Optimizations for running against a local or network Ollama:
- structured outputs (JSON schema in `format`) so no free text parsing is needed;
- temperature 0 and a fixed seed for reproducible audits;
- compact prompts: only the relevant contract excerpt, the plan and the diff;
- `keep_alive` keeps the model loaded between cases;
- a concurrency semaphore protects a single local GPU from overload;
- a response cache keyed by model and prompt hash (repeated audits in stress tests);
- a health monitor; when Ollama is down the case waits (or, if enabled in the
  settings, a heuristic simulated agent answers and is labelled as such).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

import httpx

from .store import P, Store, dumps, now_ms


class AgentUnavailable(Exception):
    pass


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
Sua função é revisar, como segunda linha de defesa, planos de execução e execuções de operações de RH,
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

_semaphore: asyncio.Semaphore | None = None
_semaphore_size = 0


def _get_semaphore(size: int) -> asyncio.Semaphore:
    global _semaphore, _semaphore_size
    if _semaphore is None or _semaphore_size != size:
        _semaphore = asyncio.Semaphore(max(1, size))
        _semaphore_size = size
    return _semaphore


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


def build_plan_prompt(case: dict, processo: dict, cargo_alvo: dict | None) -> str:
    ctx = {
        "tarefa": "Conferir o PLANO de execução antes de executá-lo.",
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
        "conferencia_deterministica": _rules_digest((case.get("conferencia_plano") or {}).get("regras") or []),
    }
    return "Contexto do caso (JSON):\n" + json.dumps(ctx, ensure_ascii=False, default=str) + \
        "\n\nAvalie se o plano é aderente ao compliance e às regras de negócio e responda no esquema JSON."


def build_audit_prompt(case: dict, processo: dict) -> str:
    ctx = {
        "tarefa": "Auditar a EXECUÇÃO concluída conforme o contrato de serviço.",
        "evento": {"tipo": case["evento"]["tipo"], "data_efetiva": case["evento"].get("data_efetiva"), "dados": case["evento"].get("dados")},
        "processo": {"codigo": processo.get("codigo"), "sla_horas": (processo.get("auditoria") or {}).get("sla_horas")},
        "recibos": [{"operacao": r["operacao"], "status": r["status"], "descricao": r.get("descricao")} for r in (case.get("execucao") or {}).get("recibos") or []],
        "alteracoes": (case.get("execucao") or {}).get("diff"),
        "estado_final": _compact_employee(case.get("estado_final")),
        "auditoria_deterministica": _rules_digest((case.get("auditoria") or {}).get("regras") or []),
        "divergencias_projetado_final": (case.get("auditoria") or {}).get("divergencias"),
    }
    return "Contexto do caso (JSON):\n" + json.dumps(ctx, ensure_ascii=False, default=str) + \
        "\n\nAvalie se a execução foi aplicada corretamente e em conformidade e responda no esquema JSON."


async def check_health(store: Store, settings: dict) -> dict:
    url = settings["ollama_base_url"].rstrip("/")
    model = settings["ollama_model"]
    health: dict[str, Any] = {"url": url, "modelo": model, "verificado_em": now_ms()}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{url}/api/tags")
            resp.raise_for_status()
            models = [m.get("name") for m in resp.json().get("models", [])]
        available = model in models or f"{model}:latest" in models
        emb = settings.get("embedding_model") or ""
        health["modelo_embedding"] = emb
        health["modelo_embedding_disponivel"] = bool(emb) and (emb in models or f"{emb}:latest" in models)
        health.update({"ok": available, "online": True, "modelos": models, "modelo_disponivel": available,
                       "erro": None if available else f"modelo {model} não encontrado; use 'Baixar modelo' nas configurações"})
    except Exception as exc:  # noqa: BLE001
        health.update({"ok": False, "online": False, "modelos": [], "modelo_disponivel": False, "erro": f"{type(exc).__name__}: {exc}"})
    await store.set_json(f"{P}:agent:health", health)
    return health


async def pull_model(settings: dict, model: str | None = None) -> dict:
    url = settings["ollama_base_url"].rstrip("/")
    async with httpx.AsyncClient(timeout=None) as client:
        resp = await client.post(f"{url}/api/pull", json={"model": model or settings["ollama_model"], "stream": False})
        resp.raise_for_status()
        return resp.json()


async def warmup(settings: dict) -> None:
    url = settings["ollama_base_url"].rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings["ollama_timeout_s"]) as client:
            await client.post(f"{url}/api/generate", json={"model": settings["ollama_model"], "prompt": "", "keep_alive": settings["ollama_keep_alive"]})
    except Exception:  # noqa: BLE001 - warmup is best effort
        pass


async def _call_ollama(settings: dict, prompt: str) -> tuple[dict, dict]:
    url = settings["ollama_base_url"].rstrip("/")
    body = {
        "model": settings["ollama_model"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        "stream": False,
        "format": RESPONSE_SCHEMA,
        "keep_alive": settings["ollama_keep_alive"],
        "options": {"temperature": settings["ollama_temperature"], "num_ctx": settings["ollama_num_ctx"],
                    "num_predict": settings["ollama_num_predict"], "seed": 42},
    }
    async with _get_semaphore(int(settings["ollama_max_concurrency"])):
        async with httpx.AsyncClient(timeout=settings["ollama_timeout_s"]) as client:
            resp = await client.post(f"{url}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()
    content = (data.get("message") or {}).get("content") or ""
    meta = {
        "eval_count": data.get("eval_count"), "prompt_eval_count": data.get("prompt_eval_count"),
        "total_duration_ms": int((data.get("total_duration") or 0) / 1e6),
        "tokens_por_segundo": round(data["eval_count"] / (data["eval_duration"] / 1e9), 1) if data.get("eval_count") and data.get("eval_duration") else None,
        "resposta_bruta": content,
    }
    parsed = json.loads(content)
    return parsed, meta


async def chat_json(settings: dict, system: str, prompt: str, schema: dict, *, model: str | None = None,
                    num_predict: int | None = None) -> tuple[dict, dict]:
    """Generic structured call used by the natural language agent.

    Raises AgentUnavailable on connection errors and json.JSONDecodeError on an
    invalid answer, so callers decide between fallback and retry.
    """
    url = settings["ollama_base_url"].rstrip("/")
    body = {
        "model": model or settings["ollama_model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "stream": False,
        "format": schema,
        "keep_alive": settings["ollama_keep_alive"],
        "options": {"temperature": settings["ollama_temperature"], "num_ctx": settings["ollama_num_ctx"],
                    "num_predict": num_predict or settings["ollama_num_predict"], "seed": 42},
    }
    started = time.time()
    try:
        async with _get_semaphore(int(settings["ollama_max_concurrency"])):
            async with httpx.AsyncClient(timeout=settings["ollama_timeout_s"]) as client:
                resp = await client.post(f"{url}/api/chat", json=body)
                resp.raise_for_status()
                data = resp.json()
    except (httpx.HTTPError, OSError) as exc:
        raise AgentUnavailable(f"{type(exc).__name__}: {exc}") from exc
    content = (data.get("message") or {}).get("content") or ""
    meta = {"modelo": body["model"], "duracao_ms": int((time.time() - started) * 1000), "eval_count": data.get("eval_count"),
            "prompt_eval_count": data.get("prompt_eval_count"), "resposta_bruta": content}
    return json.loads(content), meta


def _normalize(parsed: dict) -> dict:
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
        "justificativa": str(parsed.get("justificativa") or ""),
    }


def heuristic_review(kind: str, case: dict) -> dict:
    """Simulated agent used only when enabled in the settings and Ollama is unavailable."""
    if kind == "PLANO":
        rules = (case.get("conferencia_plano") or {}).get("regras") or []
        ops = [o["operacao"] for o in (case.get("plano") or {}).get("operacoes") or []]
    else:
        rules = (case.get("auditoria") or {}).get("regras") or []
        ops = [r["operacao"] for r in (case.get("execucao") or {}).get("recibos") or []]
    achados = []
    for r in rules:
        if not r.get("passou") and r.get("tipo") != "ALERTA":
            achados.append({"severidade": "ALTO" if r["tipo"] == "BLOQUEANTE" else "MEDIO", "referencia": r["id"], "descricao": r["explicacao"]})
    tipo = case["evento"]["tipo"]
    if tipo in ("colaborador.promovido", "colaborador.merito_concedido", "colaborador.transferido", "colaborador.desligado") and "ENVIAR_ESOCIAL" not in ops \
            and not (tipo == "colaborador.desligado" and "INICIAR_GARDEN_LEAVE" in ops):
        achados.append({"severidade": "MEDIO", "referencia": "eSocial", "descricao": "Alteração contratual sem evento eSocial correspondente."})
    if tipo == "colaborador.desligado" and kind == "PLANO" and "CALCULAR_RESCISAO" not in ops:
        achados.append({"severidade": "ALTO", "referencia": "CLT art. 477", "descricao": "Desligamento sem cálculo de rescisão."})
    bloqueia = any(a["severidade"] in ("ALTO", "CRITICO") for a in achados)
    return {
        "recomendacao": "REPROVADO" if bloqueia else "APROVADO",
        "confianca": 0.6,
        "resumo": "Agente simulado (heurístico): " + ("encontrou problemas que impedem a aprovação." if bloqueia else "não encontrou problemas relevantes."),
        "achados": achados,
        "justificativa": "Avaliação heurística baseada nas regras determinísticas e em verificações simples de coerência. Não substitui o agente de IA.",
    }


async def review(store: Store, kind: str, case: dict, processo: dict, cargo_alvo: dict | None = None) -> dict:
    settings = await store.settings()
    prompt = build_plan_prompt(case, processo, cargo_alvo) if kind == "PLANO" else build_audit_prompt(case, processo)
    started = time.time()
    cache_key = f"{P}:agent:cache:" + hashlib.sha256(f"{settings['ollama_model']}|{prompt}".encode()).hexdigest()
    if settings["agent_cache_enabled"]:
        cached = await store.get_json(cache_key)
        if cached:
            cached.update({"cache": True, "duracao_ms": int((time.time() - started) * 1000)})
            return cached
    last_error = None
    for attempt in range(2):
        try:
            parsed, meta = await _call_ollama(settings, prompt if attempt == 0 else prompt + "\n\nResponda apenas com JSON válido.")
            result = _normalize(parsed)
            result.update({
                "agente": "ollama", "modelo": settings["ollama_model"], "url": settings["ollama_base_url"],
                "duracao_ms": int((time.time() - started) * 1000), "prompt": prompt, "cache": False, "tentativas": attempt + 1, **meta,
            })
            if settings["agent_cache_enabled"]:
                await store.r.set(cache_key, dumps(result), ex=86400)
            return result
        except json.JSONDecodeError as exc:
            last_error = f"resposta não é JSON válido: {exc}"
            continue
        except (httpx.HTTPError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            break
    if last_error and "JSON" in last_error:
        return {
            "recomendacao": "REPROVADO", "confianca": 0.0, "resumo": "O agente respondeu em formato inválido; o caso segue para revisão humana.",
            "achados": [{"severidade": "ALTO", "referencia": "agente", "descricao": last_error}], "justificativa": last_error,
            "agente": "ollama", "modelo": settings["ollama_model"], "prompt": prompt, "erro": last_error,
            "duracao_ms": int((time.time() - started) * 1000),
        }
    if settings["heuristic_fallback_enabled"]:
        result = heuristic_review(kind, case)
        result.update({"agente": "heuristico", "modelo": "agente simulado (heurístico)", "motivo_fallback": last_error,
                       "prompt": prompt, "duracao_ms": int((time.time() - started) * 1000)})
        return result
    raise AgentUnavailable(last_error or "Ollama indisponível")
