"""Spending cap of the external providers, against a real Redis (skipped when redis-server is missing)."""
import asyncio
import json
import shutil
import socket
import subprocess
import time

import httpx
import pytest

from hrlab import apikeys, budget, config, llm
from hrlab.store import LOG_STREAM, Store

PING = {"type": "object", "properties": {"resposta": {"type": "string"}}, "required": ["resposta"]}


def settings(**over):
    return {**config.DEFAULT_SETTINGS, "llm_provider": "anthropic", "anthropic_model": "claude-opus-5-5", **over}


@pytest.fixture(scope="module")
def redis_url(tmp_path_factory):
    exe = shutil.which("redis-server")
    if not exe:
        pytest.skip("redis-server não instalado")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([exe, "--port", str(port), "--save", "", "--appendonly", "no", "--dir", str(tmp_path_factory.mktemp("redis"))],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    yield f"redis://127.0.0.1:{port}/0"
    proc.terminate()
    proc.wait()


@pytest.fixture
def env(redis_url, monkeypatch, tmp_path):
    """A clean Redis, a ledger, an API key and a mocked provider that counts the requests it receives."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "AUDIT_LOG_FILE", str(tmp_path / "audit-log.jsonl"))
    for names in apikeys.ENV_KEYS.values():
        for name in names:
            monkeypatch.delenv(name, raising=False)
    apikeys.set_key("anthropic", "sk-ant-teste-0000")
    apikeys.set_key("openai", "sk-openai-teste-0000")
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "claude-opus-5-5"}]})
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}], "usage": {"prompt_tokens": 1_000_000}})
        return httpx.Response(200, json={"model": "claude-opus-5-5", "stop_reason": "end_turn",
                                         "content": [{"type": "text", "text": json.dumps({"resposta": "ok"})}],
                                         "usage": {"input_tokens": 100_000, "output_tokens": 20_000}})

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handle))
    monkeypatch.setattr(llm, "ledger", None)

    def run(fn):
        async def main():
            store = Store(redis_url)
            await store.r.flushdb()
            llm.use_ledger(store)
            try:
                return await fn(store)
            finally:
                await store.close()
        return asyncio.run(main())

    return run, calls


def test_prices_come_from_the_table_overrides_or_the_most_expensive_model():
    assert budget.price_for("anthropic", "claude-opus-5-5") == {"entrada": 4.0, "saida": 20.0, "origem": "tabela"}
    assert budget.price_for("openai", "gpt-5-mini-2025-08-07")["entrada"] == 0.25
    assert budget.price_for("gemini", "models/gemini-2.5-flash")["saida"] == 2.5
    unknown = budget.price_for("anthropic", "claude-futuro")
    assert unknown["origem"] == "desconhecido" and unknown["entrada"] == 10.0
    custom = budget.price_for("openai", "llama-local", {"openai:llama-local": {"entrada": 0, "saida": 0}})
    assert custom == {"entrada": 0.0, "saida": 0.0, "origem": "editado"}
    assert budget.cost({"entrada": 4.0, "saida": 20.0}, 100_000, 20_000) == pytest.approx(0.8)


def test_each_call_is_priced_from_the_usage_and_survives_in_redis(env):
    run, calls = env

    async def scenario(store):
        s = settings(spend_cap_usd=10)
        _, meta = await llm.chat_json(s, "sys", "prompt", PING)
        st = await llm.ledger.status(s, recent=5)
        return meta, st

    meta, st = run(scenario)
    assert meta["custo_usd"] == pytest.approx(0.8)  # 100k in at US$ 4 + 20k out at US$ 20 per million
    assert st["gasto_usd"] == pytest.approx(0.8) and st["chamadas"] == 1 and not st["bloqueado"]
    assert st["por_modelo"] == [{"provedor": "anthropic", "modelo": "claude-opus-5-5", "custo_usd": pytest.approx(0.8)}]
    assert st["recentes"][0]["origem"] == "agente" and st["recentes"][0]["tokens_saida"] == 20_000
    assert len(calls) == 1


def test_reaching_the_cap_blocks_new_calls_before_they_are_sent(env):
    run, calls = env

    async def scenario(store):
        s = settings(spend_cap_usd=1.5)
        await llm.chat_json(s, "sys", "prompt", PING)   # 0.80
        await llm.chat_json(s, "sys", "prompt", PING)   # 1.60: passes the cap while in flight
        sent = len(calls)
        errors = []
        for _ in range(3):
            with pytest.raises(llm.BudgetExceeded) as exc:
                await llm.chat_json(s, "sys", "prompt", PING)
            errors.append(str(exc.value))
        with pytest.raises(llm.AgentUnavailable):
            await llm.list_models(s, "anthropic")
        logs = [f["mensagem"] for _, f in await store.r.xrange(LOG_STREAM)]
        st = await llm.ledger.status(s)
        # raising the cap lets calls through again
        await llm.chat_json(settings(spend_cap_usd=5), "sys", "prompt", PING)
        after = await llm.ledger.status(settings(spend_cap_usd=5))
        return sent, errors, logs, st, after

    sent, errors, logs, st, after = run(scenario)
    assert sent == 2 and len(calls) == 3  # nothing was sent while blocked
    assert "teto de gastos atingido" in errors[0] and "US$ 1,60" in errors[0]
    assert sum("bloqueadas" in m for m in logs) == 1  # one log entry per blocking episode
    assert any("80% do teto" in m for m in logs)
    assert st["bloqueado"] and st["restante_usd"] == 0
    assert not after["bloqueado"] and after["gasto_usd"] == pytest.approx(2.4)


def test_a_zero_cap_blocks_every_external_call_but_never_ollama(env):
    run, calls = env

    async def scenario(store):
        with pytest.raises(llm.BudgetExceeded, match="nenhum teto"):
            await llm.chat_json(settings(spend_cap_usd=0), "sys", "prompt", PING)
        await llm.ledger.check(settings(spend_cap_usd=0), "ollama", "qwen2.5:7b", 10**9)

    run(scenario)
    assert calls == []


def test_embeddings_are_priced_and_blocked_too(env):
    run, calls = env

    async def scenario(store):
        s = settings(spend_cap_usd=0.03, embedding_provider="openai")
        await llm.embed(s, ["texto"])  # 1M tokens at US$ 0.02
        await llm.embed(s, ["texto"])  # 0.04
        with pytest.raises(llm.BudgetExceeded):
            await llm.embed(s, ["texto"])
        return await llm.ledger.status(s, recent=1)

    st = run(scenario)
    assert st["gasto_usd"] == pytest.approx(0.04) and st["recentes"][0]["origem"] == "embeddings"
    assert len(calls) == 2


def test_period_reset_and_monthly_counter(env):
    run, _ = env

    async def scenario(store):
        s = settings(spend_cap_usd=0.5)
        await llm.chat_json(s, "sys", "prompt", PING)
        blocked = (await llm.ledger.status(s))["bloqueado"]
        before = await llm.ledger.reset_period(s)
        st = await llm.ledger.status(s)
        total = (await llm.ledger.status(settings(spend_period="TOTAL")))["gasto_usd"]
        return blocked, before, st, total

    blocked, before, st, total = run(scenario)
    assert blocked and before == pytest.approx(0.8)
    assert st["gasto_usd"] == 0 and not st["bloqueado"]
    assert total == pytest.approx(0.8)  # zeroing the month keeps the all-time counter


def test_api_test_reports_each_stage(env):
    run, calls = env

    async def scenario(store):
        ok = await llm.test_connection(settings(spend_cap_usd=10), "anthropic", "claude-opus-5-5")
        await llm.chat_json(settings(spend_cap_usd=10), "sys", "prompt", PING)
        blocked = await llm.test_connection(settings(spend_cap_usd=1), "anthropic", "claude-opus-5-5")
        no_key = await llm.test_connection(settings(), "gemini", "gemini-2.5-flash")
        return ok, blocked, no_key, await store.r.exists(budget.BLOCK_KEY)

    ok, blocked, no_key, marked = run(scenario)
    assert ok["ok"] and [e["estado"] for e in ok["etapas"]] == ["OK"] * 5 and ok["custo_usd"] > 0
    assert blocked["etapa"] == "teto" and [e["estado"] for e in blocked["etapas"]] == ["OK", "FALHOU", "PENDENTE", "PENDENTE", "PENDENTE"]
    assert no_key["etapa"] == "chave"
    assert not marked  # a wizard test with unsaved values does not block the lab
