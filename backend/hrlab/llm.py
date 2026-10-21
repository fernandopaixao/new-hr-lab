"""LLM providers behind one structured-output call.

The review agent, the natural language agent and the indexer talk to a model
only through this module. Providers:

- ollama:    local or network Ollama (default), `format` with the JSON schema;
- anthropic: Claude Messages API, `output_config.format` with the JSON schema;
- openai:    Chat Completions with `response_format` json_schema; the base URL is
             configurable, so OpenAI-compatible services (Azure OpenAI, OpenRouter,
             Groq, a vLLM or LM Studio server) work too;
- gemini:    Google Gemini `generateContent` with `responseSchema`.

Embeddings: Ollama, OpenAI (or compatible) or Gemini. Claude has no embedding
endpoint, so with Claude the embeddings come from one of the others or from the
simulated hashing model.

Connection, authentication and rate limit errors raise AgentUnavailable (the
case waits, as it always did for Ollama); an answer that is not valid JSON
raises json.JSONDecodeError (the caller retries or sends the case to a person).

External providers are under a spending cap (budget.py): before each call the
ledger checks the cap and raises BudgetExceeded (an AgentUnavailable) without
sending anything; after each call the token usage is priced and charged.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from . import apikeys, budget

PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "nome": "Ollama (local ou na rede)", "chave": False, "setting_modelo": "ollama_model",
        "modelos": ["qwen2.5:7b", "qwen2.5:3b", "qwen2.5:14b", "llama3.1:8b"],
        "descricao": "Roda na sua máquina ou num servidor da rede. Nenhum dado sai do ambiente.",
        "embeddings": True,
    },
    "anthropic": {
        "nome": "Anthropic Claude", "chave": True, "setting_modelo": "anthropic_model",
        "modelos": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
        "descricao": "Modelos Claude pela API da Anthropic. Não oferece embeddings; use Ollama, OpenAI, Gemini ou o simulado.",
        "chave_url": "https://console.anthropic.com/settings/keys", "embeddings": False,
    },
    "openai": {
        "nome": "OpenAI ou compatível", "chave": True, "setting_modelo": "openai_model",
        "modelos": ["gpt-5-mini", "gpt-5", "gpt-4.1-mini"],
        "descricao": "API da OpenAI ou qualquer serviço compatível (Azure OpenAI, OpenRouter, Groq, vLLM) trocando a URL base.",
        "chave_url": "https://platform.openai.com/api-keys", "embeddings": True,
    },
    "gemini": {
        "nome": "Google Gemini", "chave": True, "setting_modelo": "gemini_model",
        "modelos": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"],
        "descricao": "Modelos Gemini pela API do Google AI Studio.",
        "chave_url": "https://aistudio.google.com/apikey", "embeddings": True,
    },
}
EMBEDDING_PROVIDERS = {
    "ollama": {"nome": "Ollama", "setting_modelo": "embedding_model"},
    "openai": {"nome": "OpenAI ou compatível", "setting_modelo": "openai_embedding_model"},
    "gemini": {"nome": "Google Gemini", "setting_modelo": "gemini_embedding_model"},
    "simulado": {"nome": "Simulado (sem IA)", "setting_modelo": None},
}
ANTHROPIC_URL = "https://api.anthropic.com/v1"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
# Claude models that accept the server-side fallback on a refusal.
ANTHROPIC_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")

# Tests replace this with an httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None
# Spend counters of the external providers; set by the API, the workers and the indexer (use_ledger).
# Without a ledger nothing is priced or blocked.
ledger: budget.Ledger | None = None


def use_ledger(store) -> budget.Ledger:
    global ledger
    ledger = budget.Ledger(store)
    return ledger


class AgentUnavailable(Exception):
    pass


class ProviderError(AgentUnavailable):
    """The provider answered with an error (bad key, unknown model, quota)."""


class BudgetExceeded(ProviderError):
    """The spending cap of the external providers is reached; the call was not sent."""


async def guard(settings: dict, prov: str, model: str, *texts: str) -> None:
    """Refuses an external call that would start at or above the spending cap."""
    if ledger is None or not budget.is_external(prov):
        return
    try:
        await ledger.check(settings, prov, model, budget.estimate_tokens(*texts) if texts else 0)
    except budget.BudgetExceeded as exc:
        raise BudgetExceeded(str(exc)) from None


async def charge(settings: dict, prov: str, model: str, tokens_in: int | None, tokens_out: int | None, *, origem: str,
                 estimate_from: tuple[str, str] = ("", "")) -> float | None:
    """Prices one finished external call. Providers that omit the usage are estimated from the texts."""
    if ledger is None or not budget.is_external(prov):
        return None
    estimated = tokens_in is None or tokens_out is None
    if tokens_in is None:
        tokens_in = budget.estimate_tokens(estimate_from[0])
    if tokens_out is None:
        tokens_out = budget.estimate_tokens(estimate_from[1]) if estimate_from[1] else 0
    rec = await ledger.charge(settings, prov, model, tokens_in, tokens_out, origem=origem, estimado=estimated)
    return rec.get("custo_usd")


def provider(settings: dict) -> str:
    p = settings.get("llm_provider") or "ollama"
    return p if p in PROVIDERS else "ollama"


def active_model(settings: dict, prov: str | None = None) -> str:
    return str(settings.get(PROVIDERS[prov or provider(settings)]["setting_modelo"]) or "")


def embedding_provider(settings: dict) -> str:
    p = settings.get("embedding_provider") or "ollama"
    return p if p in EMBEDDING_PROVIDERS else "ollama"


def embedding_model(settings: dict) -> str:
    """Name stored with each vector; vectors of different names are never compared."""
    p = embedding_provider(settings)
    key = EMBEDDING_PROVIDERS[p]["setting_modelo"]
    if not key:
        return ""
    name = str(settings.get(key) or "")
    return name if p == "ollama" else f"{p}:{name}"


def describe(settings: dict) -> str:
    return f"{PROVIDERS[provider(settings)]['nome']}, {active_model(settings)}"


_semaphores: dict[tuple[str, int], asyncio.Semaphore] = {}


def _semaphore(settings: dict, prov: str) -> asyncio.Semaphore:
    size = int(settings["ollama_max_concurrency"] if prov == "ollama" else settings.get("cloud_max_concurrency", 4))
    key = (prov, max(1, size))
    if key not in _semaphores:
        _semaphores[key] = asyncio.Semaphore(key[1])
    return _semaphores[key]


def _client(timeout: float | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=transport)


def _timeout(settings: dict, prov: str) -> float:
    return float(settings["ollama_timeout_s"] if prov == "ollama" else settings.get("cloud_timeout_s", 120))


def _key(settings: dict, prov: str, override: str | None = None) -> str:
    key = override or apikeys.get_key(prov)
    if not key:
        raise ProviderError(f"chave de API de {PROVIDERS[prov]['nome']} não configurada; use o assistente de configuração")
    return key


def _error_text(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text[:300]
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)[:300]
    if isinstance(data, list) and data and isinstance(data[0], dict) and "error" in data[0]:
        return str(data[0]["error"].get("message"))[:300]
    return str(err or data)[:300]


def _raise_for(resp: httpx.Response, prov: str) -> None:
    if resp.status_code < 400:
        return
    detail = _error_text(resp)
    if resp.status_code in (401, 403):
        raise ProviderError(f"{PROVIDERS[prov]['nome']} recusou a chave de API (HTTP {resp.status_code}): {detail}")
    if resp.status_code == 404:
        raise ProviderError(f"{PROVIDERS[prov]['nome']}: modelo ou endereço não encontrado (HTTP 404): {detail}")
    if resp.status_code == 429:
        raise ProviderError(f"{PROVIDERS[prov]['nome']}: limite de uso ou de cota atingido (HTTP 429): {detail}")
    raise ProviderError(f"{PROVIDERS[prov]['nome']} respondeu HTTP {resp.status_code}: {detail}")


def strict_schema(schema: Any) -> Any:
    """JSON schema accepted by the cloud structured outputs: closed objects, no numeric or length limits."""
    if isinstance(schema, list):
        return [strict_schema(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: strict_schema(v) for k, v in schema.items()
           if k not in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength",
                        "maxLength", "minItems", "maxItems", "pattern", "default")}
    if out.get("type") == "object":
        out["additionalProperties"] = False
    return out


def openai_schema(schema: Any) -> Any:
    """OpenAI strict mode also needs every property listed as required; optional ones become nullable."""
    if isinstance(schema, list):
        return [openai_schema(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: openai_schema(v) for k, v in strict_schema(schema).items()}
    if out.get("type") == "object" and "properties" in out:
        required = set(out.get("required") or [])
        for name, prop in out["properties"].items():
            if name not in required and isinstance(prop, dict) and "type" in prop and isinstance(prop["type"], str):
                prop["type"] = [prop["type"], "null"]
                if "enum" in prop:
                    prop["enum"] = [*prop["enum"], None]
        out["required"] = list(out["properties"])
    return out


def gemini_schema(schema: Any) -> Any:
    """Gemini `responseSchema` is an OpenAPI subset: upper case types, no additionalProperties."""
    if isinstance(schema, list):
        return [gemini_schema(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {}
    for k, v in schema.items():
        if k in ("additionalProperties", "minimum", "maximum", "minLength", "maxLength", "pattern", "default"):
            continue
        out[k] = v.upper() if k == "type" and isinstance(v, str) else gemini_schema(v)
    return out


# ------------------------------------------------------------------ chat
async def chat_json(settings: dict, system: str, prompt: str, schema: dict, *, model: str | None = None,
                    max_tokens: int | None = None, prov: str | None = None, api_key: str | None = None,
                    base_url: str | None = None, origem: str = "agente") -> tuple[dict, dict]:
    """One structured call. Returns (parsed JSON, meta with model, duration, tokens, cost and raw answer)."""
    prov = prov or provider(settings)
    model = model or active_model(settings, prov)
    await guard(settings, prov, model, system, prompt)
    started = time.time()
    acquired = started
    try:
        async with _semaphore(settings, prov):
            acquired = time.time()
            if prov == "ollama":
                content, meta = await _ollama(settings, system, prompt, schema, model, max_tokens, base_url)
            elif prov == "anthropic":
                content, meta = await _anthropic(settings, system, prompt, schema, model, max_tokens, _key(settings, prov, api_key))
            elif prov == "openai":
                content, meta = await _openai(settings, system, prompt, schema, model, max_tokens, _key(settings, prov, api_key), base_url)
            else:
                content, meta = await _gemini(settings, system, prompt, schema, model, max_tokens, _key(settings, prov, api_key))
    except (httpx.HTTPError, OSError) as exc:
        raise AgentUnavailable(f"{PROVIDERS[prov]['nome']} indisponível: {type(exc).__name__}: {exc}") from exc
    done = time.time()
    meta["custo_usd"] = await charge(settings, prov, model, meta.get("prompt_eval_count"), meta.get("eval_count"), origem=origem,
                                     estimate_from=(system + prompt, content))
    # duracao_ms includes the wait for a free slot; resposta_ms is the model call alone
    meta.update({"provedor": prov, "modelo": model, "duracao_ms": int((done - started) * 1000), "espera_ms": int((acquired - started) * 1000),
                 "resposta_ms": int((done - acquired) * 1000), "resposta_bruta": content})
    return json.loads(content), meta


async def _ollama(settings, system, prompt, schema, model, max_tokens, base_url):
    url = (base_url or settings["ollama_base_url"]).rstrip("/")
    body = {
        "model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "stream": False, "format": schema, "keep_alive": settings["ollama_keep_alive"],
        "options": {"temperature": settings["ollama_temperature"], "num_ctx": settings["ollama_num_ctx"],
                    "num_predict": max_tokens or settings["ollama_num_predict"], "seed": 42},
    }
    async with _client(_timeout(settings, "ollama")) as client:
        resp = await client.post(f"{url}/api/chat", json=body)
    _raise_for(resp, "ollama")
    data = resp.json()
    meta = {
        "eval_count": data.get("eval_count"), "prompt_eval_count": data.get("prompt_eval_count"),
        "tokens_por_segundo": round(data["eval_count"] / (data["eval_duration"] / 1e9), 1) if data.get("eval_count") and data.get("eval_duration") else None,
    }
    return (data.get("message") or {}).get("content") or "", meta


async def _anthropic(settings, system, prompt, schema, model, max_tokens, key):
    body: dict[str, Any] = {
        "model": model, "max_tokens": max(int(settings.get("cloud_max_tokens", 16000)), max_tokens or 0),
        "system": system, "messages": [{"role": "user", "content": prompt}],
        "output_config": {"format": {"type": "json_schema", "schema": strict_schema(schema)}},
    }
    if settings.get("anthropic_effort"):
        body["output_config"]["effort"] = settings["anthropic_effort"]
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    if model in ANTHROPIC_FALLBACK_MODELS:
        # on a safety refusal the API reruns the request on a fallback model instead of stopping
        body["fallbacks"] = "default"
        headers["anthropic-beta"] = "server-side-fallback-2026-07-01"
    async with _client(_timeout(settings, "anthropic")) as client:
        resp = await client.post(f"{ANTHROPIC_URL}/messages", json=body, headers=headers)
    _raise_for(resp, "anthropic")
    data = resp.json()
    if data.get("stop_reason") == "refusal":
        raise json.JSONDecodeError("o modelo recusou a solicitação", "", 0)
    text = "".join(b.get("text") or "" for b in data.get("content") or [] if b.get("type") == "text")
    usage = data.get("usage") or {}
    return text, {"eval_count": usage.get("output_tokens"), "prompt_eval_count": usage.get("input_tokens"), "modelo_servido": data.get("model")}


async def _openai(settings, system, prompt, schema, model, max_tokens, key, base_url):
    url = (base_url or settings.get("openai_base_url") or "https://api.openai.com/v1").rstrip("/")
    official = "api.openai.com" in url
    body: dict[str, Any] = {
        "model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "resposta", "strict": True, "schema": openai_schema(schema)}},
        ("max_completion_tokens" if official else "max_tokens"): max(int(settings.get("cloud_max_tokens", 16000)), max_tokens or 0),
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {key}"}
    async with _client(_timeout(settings, "openai")) as client:
        resp = await client.post(f"{url}/chat/completions", json=body, headers=headers)
        if resp.status_code == 400 and "temperature" in resp.text:
            # reasoning models accept only the default temperature
            body.pop("temperature")
            resp = await client.post(f"{url}/chat/completions", json=body, headers=headers)
        if resp.status_code == 400 and ("response_format" in resp.text or "json_schema" in resp.text):
            # compatible servers without json_schema: plain JSON mode with the schema in the prompt
            body["response_format"] = {"type": "json_object"}
            body["messages"][-1]["content"] = prompt + "\n\nResponda somente com JSON neste esquema:\n" + json.dumps(schema, ensure_ascii=False)
            resp = await client.post(f"{url}/chat/completions", json=body, headers=headers)
    _raise_for(resp, "openai")
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    if message.get("refusal"):
        raise json.JSONDecodeError(f"o modelo recusou a solicitação: {message['refusal']}", "", 0)
    usage = data.get("usage") or {}
    return message.get("content") or "", {"eval_count": usage.get("completion_tokens"), "prompt_eval_count": usage.get("prompt_tokens"),
                                          "modelo_servido": data.get("model")}


async def _gemini(settings, system, prompt, schema, model, max_tokens, key):
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": max(int(settings.get("cloud_max_tokens", 16000)), max_tokens or 0),
                             "responseMimeType": "application/json", "responseSchema": gemini_schema(schema)},
    }
    async with _client(_timeout(settings, "gemini")) as client:
        resp = await client.post(f"{GEMINI_URL}/models/{model}:generateContent", json=body, headers={"x-goog-api-key": key})
    _raise_for(resp, "gemini")
    data = resp.json()
    cand = (data.get("candidates") or [{}])[0]
    if cand.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
        raise json.JSONDecodeError(f"o modelo recusou a solicitação ({cand['finishReason']})", "", 0)
    text = "".join(p.get("text") or "" for p in (cand.get("content") or {}).get("parts") or [] if not p.get("thought"))
    usage = data.get("usageMetadata") or {}
    return text, {"eval_count": usage.get("candidatesTokenCount"), "prompt_eval_count": usage.get("promptTokenCount"),
                  "modelo_servido": data.get("modelVersion")}


# ------------------------------------------------- JEV-style decision models
JEV_SEMAPHORE_KEY = "jev"


def jev_base_url(settings: dict) -> str:
    return (settings.get("jev_base_url") or settings["ollama_base_url"]).rstrip("/")


async def decide(settings: dict, state: dict[str, str], questions: dict[str, dict], *, model: str | None = None,
                 base_url: str | None = None) -> tuple[dict, dict]:
    """One call to a JEV-style decision model (Ollama 0.35+, POST /v1/systemone).

    `state` holds named texts and `questions` named questions of type `choice` (criteria: option -> description),
    `noul` (yes or no, answered with a probability) or `score` (criteria: ordered labels). Every question is
    answered in the same request, with a probability for each option. There is no free text in the answer.
    Returns (answers by question name, meta with model, durations and tokens).
    """
    model = model or settings["jev_model"]
    url = (base_url or jev_base_url(settings)).rstrip("/")
    started = time.time()
    acquired = started
    sem_key = (JEV_SEMAPHORE_KEY, max(1, int(settings.get("jev_max_concurrency", 2))))
    if sem_key not in _semaphores:
        _semaphores[sem_key] = asyncio.Semaphore(sem_key[1])
    try:
        async with _semaphores[sem_key]:
            acquired = time.time()
            async with _client(float(settings.get("jev_timeout_s", 30))) as client:
                resp = await client.post(f"{url}/v1/systemone", json={"model": model, "state": state, "questions": questions})
    except (httpx.HTTPError, OSError) as exc:
        raise AgentUnavailable(f"Ollama (JEV) indisponível: {type(exc).__name__}: {exc}") from exc
    if resp.status_code == 404:
        detail = _error_text(resp)
        if "model" in detail.lower():
            raise ProviderError(f"modelo de decisão {model} não encontrado no Ollama; use 'Baixar modelo JEV' nas configurações ({detail})")
        raise ProviderError(f"o Ollama em {url} não tem o endpoint /v1/systemone; atualize para a versão 0.35 ou mais nova ({detail})")
    if resp.status_code >= 400:
        raise ProviderError(f"Ollama (JEV) respondeu HTTP {resp.status_code}: {_error_text(resp)}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise json.JSONDecodeError(f"resposta do modelo de decisão não é JSON: {resp.text[:200]}", "", 0) from exc
    answers = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(answers, dict) or any(q not in answers for q in questions):
        raise json.JSONDecodeError(f"resposta do modelo de decisão sem todas as perguntas: {str(data)[:200]}", "", 0)
    done = time.time()
    usage = data.get("usage") or {}
    meta = {"provedor": "ollama-jev", "modelo": model, "modelo_servido": data.get("model"), "url": url,
            "duracao_ms": int((done - started) * 1000), "espera_ms": int((acquired - started) * 1000), "resposta_ms": int((done - acquired) * 1000),
            "eval_count": usage.get("output_tokens"), "prompt_eval_count": usage.get("input_tokens"),
            "resposta_bruta": json.dumps(answers, ensure_ascii=False)}
    return answers, meta


async def jev_health(settings: dict) -> dict:
    """Whether the decision model is installed in the Ollama that serves it."""
    model = settings["jev_model"]
    out: dict[str, Any] = {"modelo": model, "url": jev_base_url(settings)}
    try:
        models = await list_models(settings, "ollama", base_url=out["url"])
    except AgentUnavailable as exc:
        return {**out, "ok": False, "online": False, "modelo_disponivel": False, "erro": str(exc)}
    available = has_model(models, model, "ollama")
    return {**out, "ok": available, "online": True, "modelo_disponivel": available,
            "erro": None if available else f"modelo de decisão {model} não encontrado; use 'Baixar modelo JEV' nas configurações"}


JEV_PING = {"ok": {"type": "noul", "instructions": "O texto diz que o sistema está funcionando?"}}


async def test_jev(settings: dict, model: str | None = None, base_url: str | None = None) -> dict:
    """The wizard's 'Testar JEV': model installed and one tiny decision."""
    s = {**settings, "jev_model": model or settings["jev_model"], "jev_base_url": base_url if base_url is not None else settings.get("jev_base_url", "")}
    health = await jev_health(s)
    out = {"provedor": "jev", "modelo": s["jev_model"], "ok": False}
    if not health["online"]:
        return {**out, "etapa": "conexao", "erro": health["erro"]}
    if not health["modelo_disponivel"]:
        return {**out, "etapa": "modelo", "erro": health["erro"]}
    try:
        _, meta = await decide(s, {"texto": "O sistema está funcionando."}, JEV_PING)
    except AgentUnavailable as exc:
        return {**out, "etapa": "chamada", "erro": str(exc)}
    except json.JSONDecodeError as exc:
        return {**out, "etapa": "chamada", "erro": str(exc)}
    return {**out, "ok": True, "duracao_ms": meta["duracao_ms"]}


# ------------------------------------------------------------- models list
async def list_models(settings: dict, prov: str, *, api_key: str | None = None, base_url: str | None = None) -> list[str]:
    """Models the provider offers to this key. Raises AgentUnavailable (also when the spending cap is reached)."""
    await guard(settings, prov, "")
    try:
        async with _client(10) as client:
            if prov == "ollama":
                resp = await client.get(f"{(base_url or settings['ollama_base_url']).rstrip('/')}/api/tags")
                _raise_for(resp, prov)
                return [m.get("name") for m in resp.json().get("models", [])]
            key = _key(settings, prov, api_key)
            if prov == "anthropic":
                resp = await client.get(f"{ANTHROPIC_URL}/models", params={"limit": 100},
                                        headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
                _raise_for(resp, prov)
                return [m.get("id") for m in resp.json().get("data", [])]
            if prov == "openai":
                url = (base_url or settings.get("openai_base_url") or "https://api.openai.com/v1").rstrip("/")
                resp = await client.get(f"{url}/models", headers={"Authorization": f"Bearer {key}"})
                _raise_for(resp, prov)
                return sorted(m.get("id") for m in resp.json().get("data", []))
            resp = await client.get(f"{GEMINI_URL}/models", params={"pageSize": 200}, headers={"x-goog-api-key": key})
            _raise_for(resp, prov)
            return [m.get("name", "").removeprefix("models/") for m in resp.json().get("models", [])]
    except (httpx.HTTPError, OSError) as exc:
        raise AgentUnavailable(f"{PROVIDERS[prov]['nome']} indisponível: {type(exc).__name__}: {exc}") from exc


def has_model(models: list[str], model: str, prov: str) -> bool:
    if not model:
        return False
    if prov == "ollama":
        return model in models or f"{model}:latest" in models
    # cloud lists may omit aliases or deployments; an empty list proves nothing
    return not models or model in models or any(m.startswith(model) for m in models)


# --------------------------------------------------------------- embeddings
async def embed(settings: dict, texts: list[str], kind: str = "document") -> list[list[float]]:
    """Embeds with the configured embedding provider. Raises AgentUnavailable (also for 'simulado')."""
    prov = embedding_provider(settings)
    if prov == "simulado":
        raise AgentUnavailable("embeddings configurados como simulados")
    if prov == "ollama":
        try:
            return await _ollama_embed(settings, texts, kind)
        except (httpx.HTTPError, OSError, KeyError) as exc:
            raise AgentUnavailable(f"embeddings indisponíveis: {type(exc).__name__}: {exc}") from exc
    model = settings["openai_embedding_model"] if prov == "openai" else settings["gemini_embedding_model"]
    await guard(settings, prov, model, *texts)
    try:
        key = _key(settings, prov)
        async with _client(_timeout(settings, prov)) as client:
            if prov == "openai":
                url = (settings.get("openai_base_url") or "https://api.openai.com/v1").rstrip("/")
                resp = await client.post(f"{url}/embeddings", json={"model": model, "input": texts},
                                         headers={"Authorization": f"Bearer {key}"})
                _raise_for(resp, prov)
                data = resp.json()
                vectors = [d["embedding"] for d in sorted(data["data"], key=lambda d: d.get("index", 0))]
                tokens = (data.get("usage") or {}).get("prompt_tokens")
            else:
                task = "RETRIEVAL_QUERY" if kind == "query" else "RETRIEVAL_DOCUMENT"
                reqs = [{"model": f"models/{model}", "content": {"parts": [{"text": t}]}, "taskType": task} for t in texts]
                resp = await client.post(f"{GEMINI_URL}/models/{model}:batchEmbedContents", json={"requests": reqs},
                                         headers={"x-goog-api-key": key})
                _raise_for(resp, prov)
                vectors = [e["values"] for e in resp.json()["embeddings"]]
                tokens = None  # batchEmbedContents does not return the usage
    except (httpx.HTTPError, OSError, KeyError) as exc:
        raise AgentUnavailable(f"embeddings indisponíveis: {type(exc).__name__}: {exc}") from exc
    await charge(settings, prov, model, tokens, 0, origem="embeddings", estimate_from=("".join(texts), ""))
    return vectors


def _prefix(model: str, kind: str) -> str:
    # nomic-embed-text was trained with task prefixes
    if "nomic" in model:
        return "search_query: " if kind == "query" else "search_document: "
    return ""


async def _ollama_embed(settings: dict, texts: list[str], kind: str) -> list[list[float]]:
    model = settings["embedding_model"]
    url = settings["ollama_base_url"].rstrip("/")
    inputs = [_prefix(model, kind) + t for t in texts]
    async with _client(settings["ollama_timeout_s"]) as client:
        resp = await client.post(f"{url}/api/embed", json={"model": model, "input": inputs, "keep_alive": settings["ollama_keep_alive"],
                                                           "truncate": True})
        if resp.status_code == 404 and "model" not in resp.text:
            # older Ollama: one prompt per call
            out = []
            for t in inputs:
                r = await client.post(f"{url}/api/embeddings", json={"model": model, "prompt": t})
                r.raise_for_status()
                out.append(r.json()["embedding"])
            return out
        resp.raise_for_status()
        return resp.json()["embeddings"]


# ------------------------------------------------------------------ health
async def check_health(settings: dict) -> dict:
    """Reachability of the chat provider and of the embedding provider."""
    prov = provider(settings)
    model = active_model(settings, prov)
    health: dict[str, Any] = {"provedor": prov, "provedor_nome": PROVIDERS[prov]["nome"], "modelo": model,
                              "url": settings["ollama_base_url"].rstrip("/") if prov == "ollama"
                              else (settings.get("openai_base_url") if prov == "openai" else None)}
    try:
        models = await list_models(settings, prov)
        available = has_model(models, model, prov)
        hint = "use 'Baixar modelo' nas configurações" if prov == "ollama" else "confira o nome no assistente de configuração"
        health.update({"ok": available, "online": True, "modelos": models, "modelo_disponivel": available,
                       "erro": None if available else f"modelo {model} não encontrado; {hint}"})
    except AgentUnavailable as exc:
        models = []
        health.update({"ok": False, "online": False, "modelos": [], "modelo_disponivel": False, "erro": str(exc)})

    eprov = embedding_provider(settings)
    emodel_key = EMBEDDING_PROVIDERS[eprov]["setting_modelo"]
    emodel = str(settings.get(emodel_key) or "") if emodel_key else ""
    health.update({"provedor_embedding": eprov, "modelo_embedding": emodel or EMBEDDING_PROVIDERS[eprov]["nome"]})
    if eprov == "simulado":
        health["modelo_embedding_disponivel"] = False
    elif eprov == prov and health["online"]:
        health["modelo_embedding_disponivel"] = has_model(models, emodel, eprov)
    else:
        try:
            health["modelo_embedding_disponivel"] = has_model(await list_models(settings, eprov), emodel, eprov)
        except AgentUnavailable as exc:
            health["modelo_embedding_disponivel"] = False
            health["erro_embedding"] = str(exc)
    return health


PING_SCHEMA = {"type": "object", "properties": {"resposta": {"type": "string"}}, "required": ["resposta"]}


TEST_STAGES = (
    ("chave", "Chave de API"),
    ("teto", "Teto de gastos"),
    ("conexao", "Conexão"),
    ("modelo", "Modelo"),
    ("chamada", "Chamada de teste"),
)


async def test_connection(settings: dict, prov: str, model: str, *, api_key: str | None = None, base_url: str | None = None) -> dict:
    """The setup wizard's 'Testar API': one result per stage, so the interface can draw where it stopped.

    Stages: the key exists (external), the spending cap leaves room (external), the provider answers the
    model list, the model is offered and one tiny structured call comes back as JSON (priced like any call).
    `etapa` names the stage that failed."""
    out: dict[str, Any] = {"provedor": prov, "modelo": model, "ok": False}
    stages = {k: {"id": k, "nome": n, "estado": "PENDENTE", "detalhe": None} for k, n in TEST_STAGES}
    external = budget.is_external(prov)

    def finish(stage: str | None, error: str | None = None) -> dict:
        if stage:
            stages[stage].update(estado="FALHOU", detalhe=error)
            out.update(etapa=stage, erro=error)
        return {**out, "etapas": list(stages.values())}

    if external:
        key = api_key or apikeys.get_key(prov)
        if not key:
            return finish("chave", f"chave de API de {PROVIDERS[prov]['nome']} não informada")
        stages["chave"].update(estado="OK", detalhe=f"chave {'digitada no assistente' if api_key else 'salva'}, termina em {key[-4:]}")
        if ledger is not None:
            try:
                await ledger.check(settings, prov, model, 50, mark=False)
            except budget.BudgetExceeded as exc:
                return finish("teto", str(exc))
            st = await ledger.status(settings)
            stages["teto"].update(estado="OK", detalhe=f"{budget.usd(st['gasto_usd'])} gastos de {budget.usd(st['teto_usd'])} ({st['periodo_rotulo']})")
        else:
            stages["teto"].update(estado="IGNORADO", detalhe="sem controle de gastos neste processo")
    else:
        stages["chave"].update(estado="IGNORADO", detalhe="o Ollama não usa chave")
        stages["teto"].update(estado="IGNORADO", detalhe="o Ollama roda localmente e não tem custo por token")
    started = time.time()
    try:
        models = await list_models(settings, prov, api_key=api_key, base_url=base_url)
    except AgentUnavailable as exc:
        return finish("teto" if isinstance(exc, BudgetExceeded) else "conexao", str(exc))
    out["modelos"] = models
    stages["conexao"].update(estado="OK", detalhe=f"{len(models)} modelo(s) listados em {int((time.time() - started) * 1000)} ms")
    if not has_model(models, model, prov):
        return finish("modelo", f"o modelo {model} não está disponível para esta conta ou servidor")
    stages["modelo"].update(estado="OK", detalhe=f"{model} disponível" if models else f"{model} (a conta não lista modelos; segue para a chamada)")
    try:
        parsed, meta = await chat_json(settings, "Responda em português, só com JSON.", 'Responda {"resposta": "ok"}.', PING_SCHEMA,
                                       model=model, max_tokens=50, prov=prov, api_key=api_key, base_url=base_url, origem="teste")
    except AgentUnavailable as exc:
        return finish("teto" if isinstance(exc, BudgetExceeded) else "chamada", str(exc))
    except json.JSONDecodeError as exc:
        return finish("chamada", f"resposta fora do formato JSON: {exc}")
    tokens = f"{meta.get('prompt_eval_count') or '?'} tokens de entrada, {meta.get('eval_count') or '?'} de saída"
    cost = f", custo {budget.usd(meta['custo_usd'])}" if meta.get("custo_usd") is not None else ""
    stages["chamada"].update(estado="OK", detalhe=f"respondeu {json.dumps(parsed, ensure_ascii=False)} em {meta['duracao_ms']} ms; {tokens}{cost}")
    out.update({"ok": True, "duracao_ms": meta["duracao_ms"], "resposta": parsed.get("resposta"), "tokens_entrada": meta.get("prompt_eval_count"),
                "tokens_saida": meta.get("eval_count"), "custo_usd": meta.get("custo_usd"), "modelo_servido": meta.get("modelo_servido")})
    return finish(None)
