"""Cloud LLM providers, API keys and settings, against a mocked HTTP transport."""
import asyncio
import json

import httpx
import pytest

from hrlab import apikeys, config, llm
from hrlab.agent import RESPONSE_SCHEMA

ANSWER = {"recomendacao": "APROVADO", "confianca": 0.9, "resumo": "ok", "achados": [], "justificativa": "coerente"}


def settings(**over):
    return {**config.DEFAULT_SETTINGS, **over}


@pytest.fixture
def http(monkeypatch, tmp_path):
    """Captures requests and answers them with the handler set by the test."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    for names in apikeys.ENV_KEYS.values():
        for name in names:
            monkeypatch.delenv(name, raising=False)
    calls = []
    state = {"handler": None}

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return state["handler"](request)

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handle))
    return calls, state


def run(coro):
    return asyncio.run(coro)


def test_keys_come_from_env_first_and_are_never_shown(http, monkeypatch):
    apikeys.set_key("anthropic", "sk-ant-arquivo-123456")
    assert apikeys.get_key("anthropic") == "sk-ant-arquivo-123456"
    st = apikeys.status()["anthropic"]
    assert st == {"configurada": True, "origem": "assistente", "final": "3456"}
    assert "sk-ant" not in json.dumps(apikeys.status())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-ambiente-999999")
    assert apikeys.get_key("anthropic") == "sk-ant-ambiente-999999"
    assert apikeys.status()["anthropic"]["origem"] == "ambiente (.env)"
    apikeys.set_key("anthropic", "")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert apikeys.get_key("anthropic") == "" and not apikeys.status()["anthropic"]["configurada"]


def test_anthropic_uses_structured_output_with_a_closed_schema(http):
    calls, state = http
    apikeys.set_key("anthropic", "sk-ant-teste-0000")
    state["handler"] = lambda r: httpx.Response(200, json={"model": "claude-opus-5-5", "stop_reason": "end_turn",
                                                           "content": [{"type": "text", "text": json.dumps(ANSWER)}],
                                                           "usage": {"input_tokens": 10, "output_tokens": 5}})
    parsed, meta = run(llm.chat_json(settings(llm_provider="anthropic"), "sys", "prompt", RESPONSE_SCHEMA))
    assert parsed == ANSWER and meta["provedor"] == "anthropic" and meta["modelo"] == "claude-opus-5-5"
    req = calls[0]
    body = json.loads(req.content)
    assert str(req.url) == "https://api.anthropic.com/v1/messages" and req.headers["x-api-key"] == "sk-ant-teste-0000"
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False
    assert fmt["schema"]["properties"]["achados"]["items"]["additionalProperties"] is False
    assert "temperature" not in body and "tool_choice" not in body
    assert body["fallbacks"] == "default" and "server-side-fallback" in req.headers["anthropic-beta"]


def test_openai_compatible_base_url_and_temperature_retry(http):
    calls, state = http
    apikeys.set_key("openai", "sk-openai-teste")

    def handler(r):
        body = json.loads(r.content)
        if "temperature" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported value: 'temperature'"}})
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": json.dumps(ANSWER)}}], "usage": {}})
    state["handler"] = handler
    s = settings(llm_provider="openai", openai_base_url="http://vllm.local:8000/v1", openai_model="qwen")
    parsed, _ = run(llm.chat_json(s, "sys", "prompt", RESPONSE_SCHEMA))
    assert parsed == ANSWER and len(calls) == 2
    body = json.loads(calls[1].content)
    assert str(calls[1].url) == "http://vllm.local:8000/v1/chat/completions"
    assert "max_tokens" in body and "max_completion_tokens" not in body
    schema = body["response_format"]["json_schema"]["schema"]
    # strict mode: every property required, optional ones nullable
    item = schema["properties"]["achados"]["items"]
    assert set(item["required"]) == {"severidade", "referencia", "descricao"} and item["properties"]["referencia"]["type"] == ["string", "null"]


def test_gemini_schema_and_errors_mean_unavailable(http):
    calls, state = http
    apikeys.set_key("gemini", "gm-teste")
    state["handler"] = lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(ANSWER)}]}}]})
    parsed, _ = run(llm.chat_json(settings(llm_provider="gemini"), "sys", "prompt", RESPONSE_SCHEMA))
    body = json.loads(calls[0].content)
    assert parsed == ANSWER and calls[0].headers["x-goog-api-key"] == "gm-teste"
    assert body["generationConfig"]["responseSchema"]["type"] == "OBJECT"
    state["handler"] = lambda r: httpx.Response(401, json={"error": {"message": "API key not valid"}})
    with pytest.raises(llm.AgentUnavailable, match="recusou a chave"):
        run(llm.chat_json(settings(llm_provider="gemini"), "sys", "prompt", RESPONSE_SCHEMA))


def test_missing_key_is_unavailable_not_a_crash(http):
    with pytest.raises(llm.AgentUnavailable, match="não configurada"):
        run(llm.chat_json(settings(llm_provider="anthropic"), "sys", "prompt", RESPONSE_SCHEMA))


def test_connection_test_lists_models_and_calls_once(http):
    calls, state = http

    def handler(r):
        if r.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "claude-opus-5-5"}, {"id": "claude-haiku-5-5"}]})
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"resposta": "ok"}'}]})
    state["handler"] = handler
    out = run(llm.test_connection(settings(), "anthropic", "claude-haiku-5-5", api_key="sk-ant-digitada"))
    assert out["ok"] and out["resposta"] == "ok" and "claude-opus-5-5" in out["modelos"]
    assert all(c.headers["x-api-key"] == "sk-ant-digitada" for c in calls)
    assert apikeys.get_key("anthropic") == ""  # testing never stores the key
    bad = run(llm.test_connection(settings(), "anthropic", "claude-inexistente", api_key="sk-ant-digitada"))
    assert not bad["ok"] and bad["etapa"] == "modelo"


def test_embedding_names_and_provider_choices():
    assert llm.embedding_model(settings()) == "nomic-embed-text"
    assert llm.embedding_model(settings(embedding_provider="openai")) == "openai:text-embedding-3-small"
    assert llm.embedding_model(settings(embedding_provider="simulado")) == ""
    assert config.coerce_settings({"llm_provider": "gemini"}) == {"llm_provider": "gemini"}
    with pytest.raises(ValueError):
        config.coerce_settings({"llm_provider": "outro"})
