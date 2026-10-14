"""Qwen and JEV engines, the JEV-style decision client and the agent performance history."""
import asyncio
import json

import httpx
import pytest

from hrlab import agent, config, engines, llm, metrics
from hrlab.store import dumps

QWEN_ANSWER = {"recomendacao": "APROVADO", "confianca": 0.9, "resumo": "ok", "achados": [], "justificativa": "coerente"}


def jev_answers(kind, choice="APROVADO", flags=None):
    flags = flags or {}
    q = engines.QUESTIONS[kind]
    verdict = engines.VERDICT_QUESTION[kind]
    options = list(q[verdict]["criteria"])
    out = {verdict: {"type": "choice", "choice": choice, "probabilities": {o: (0.9 if o == choice else 0.1 / (len(options) - 1)) for o in options},
                     "confidence": 0.9},
           "risco": {"type": "score", "score": 0.1, "legend": {"0": "baixo", "1": "medio", "2": "alto", "3": "critico"},
                     "probabilities": {"0": 0.8, "1": 0.1, "2": 0.05, "3": 0.05}, "confidence": 0.8}}
    for name, spec in q.items():
        if spec["type"] == "noul":
            out[name] = {"type": "noul", "noul": flags.get(name, 0.05)}
    return out


class FakeRedis:
    def __init__(self):
        self.kv, self.streams, self.seq = {}, {}, 0

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, ex=None):
        self.kv[key] = value

    async def xadd(self, key, fields, maxlen=None, approximate=True):
        self.seq += 1
        rec = json.loads(fields["d"])
        sid = f"{rec['ts']}-{self.seq}"
        self.streams.setdefault(key, []).append((sid, fields))
        return sid

    async def xrange(self, key, min="-", max="+"):
        rows = self.streams.get(key, [])
        lo = 0 if min == "-" else int(min)
        hi = float("inf") if max == "+" else int(max)
        return [(i, f) for i, f in rows if lo <= int(i.split("-")[0]) <= hi]

    async def xlen(self, key):
        return len(self.streams.get(key, []))

    async def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
            self.streams.pop(k, None)


class FakeStore:
    def __init__(self, **settings):
        self.r = FakeRedis()
        self._settings = {**config.DEFAULT_SETTINGS, "agent_cache_enabled": False, **settings}

    async def settings(self):
        return dict(self._settings)

    async def get_json(self, key):
        raw = await self.r.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key, value):
        await self.r.set(key, dumps(value))


@pytest.fixture
def http(monkeypatch):
    calls = []
    state = {"jev": None, "chat": None}

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/v1/systemone":
            return state["jev"](request)
        if request.url.path == "/api/chat":
            return state["chat"](request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "tev1:0.8b"}, {"name": "qwen2.5:7b"}]})
        return httpx.Response(404, json={"error": "not found"})

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handle))
    return calls, state


def run(coro):
    return asyncio.run(coro)


CASE = {
    "id": "c-1", "evento": {"tipo": "colaborador.promovido", "data_efetiva": "2026-10-09", "dados": {"cargo_destino": "CAIXA"}},
    "elegibilidade": {"decisao": "ELEGIVEL", "regras": [{"id": "MOV-01", "tipo": "BLOQUEANTE", "descricao": "Tempo mínimo", "passou": True}]},
    "plano": {"operacoes": [{"seq": 1, "operacao": "ALTERAR_CARGO", "parametros": {"cargo": "CAIXA"}, "motivo": "promoção"}], "projetado": {}},
    "auditoria": {"decisao": "APROVADO", "regras": []},
    "estado_inicial": {"id": "E1", "cargo": "ESCRITURARIO", "salario_base": 3800},
}
PROCESSO = {"codigo": "PROMOCAO", "nome": "Promoção"}


def test_decide_posts_typed_questions_to_systemone(http):
    calls, state = http
    state["jev"] = lambda req: httpx.Response(200, json={"model": "tev1:0.8b", "answers": jev_answers("AUDITORIA"),
                                                         "usage": {"input_tokens": 300, "output_tokens": 12}})
    settings = {**config.DEFAULT_SETTINGS}
    answers, meta = run(llm.decide(settings, {"texto": "x"}, engines.AUDIT_QUESTIONS))
    body = json.loads(calls[0].content)
    assert str(calls[0].url) == "http://localhost:11434/v1/systemone"
    assert body["model"] == "tev1:0.8b" and body["state"] == {"texto": "x"}
    assert body["questions"]["recomendacao"]["type"] == "choice" and body["questions"]["risco"]["criteria"] == engines.RISK_LABELS
    assert answers["recomendacao"]["choice"] == "APROVADO"
    assert meta["eval_count"] == 12 and meta["prompt_eval_count"] == 300 and meta["resposta_ms"] >= 0


def test_decide_explains_a_missing_endpoint_or_model(http):
    _, state = http
    state["jev"] = lambda req: httpx.Response(404, text="404 page not found")
    with pytest.raises(llm.ProviderError, match="0.35"):
        run(llm.decide({**config.DEFAULT_SETTINGS}, {"t": "x"}, engines.AUDIT_QUESTIONS))
    state["jev"] = lambda req: httpx.Response(404, json={"error": "model 'tev1:0.8b' not found"})
    with pytest.raises(llm.ProviderError, match="Baixar modelo JEV"):
        run(llm.decide({**config.DEFAULT_SETTINGS}, {"t": "x"}, engines.AUDIT_QUESTIONS))


def test_interpret_turns_probabilities_into_an_explained_review():
    out = engines.interpret("AUDITORIA", jev_answers("AUDITORIA", choice="REPROVADO", flags={"reducao_salarial": 0.82}), "tev1:0.8b")
    assert out["recomendacao"] == "REPROVADO" and out["veredito"] == "REPROVADO" and out["confianca"] == 0.9
    assert any(a["referencia"] == "CLT art. 468" and "82%" in a["descricao"] for a in out["achados"])
    assert "risco baixo" in out["resumo"] and "REPROVADO 90%" in out["justificativa"]
    el = engines.interpret("ELEGIBILIDADE", jev_answers("ELEGIBILIDADE", choice="EXCECAO_NECESSARIA"), "tev1:0.8b")
    assert el["classificacao"] == "EXCECAO_NECESSARIA" and "recomendacao" not in el
    with pytest.raises(ValueError):
        engines.interpret("AUDITORIA", {"recomendacao": {"choice": "TALVEZ"}}, "m")


def test_jev_engine_reviews_and_records_the_call(http):
    _, state = http
    state["jev"] = lambda req: httpx.Response(200, json={"model": "tev1:0.8b", "answers": jev_answers("ELEGIBILIDADE", choice="ELEGIVEL")})
    store = FakeStore(agent_engine="jev")
    review = run(agent.review(store, "ELEGIBILIDADE", CASE, PROCESSO, None, subject=CASE["estado_inicial"]))
    assert review["motor"] == "jev" and review["veredito"] == "ELEGIVEL" and review["processamento_ms"] >= review["resposta_ms"]
    recs = run(metrics.load(store))
    assert len(recs) == 1
    assert recs[0]["motor"] == "jev" and recs[0]["tarefa"] == "ELEGIBILIDADE" and recs[0]["veredito_regras"] == "ELEGIVEL" and recs[0]["ok"]


def test_comparison_runs_the_other_engine_without_deciding(http):
    _, state = http
    state["chat"] = lambda req: httpx.Response(200, json={"message": {"content": json.dumps(QWEN_ANSWER)}, "eval_count": 40, "eval_duration": 1e9})
    state["jev"] = lambda req: httpx.Response(200, json={"answers": jev_answers("AUDITORIA", choice="REPROVADO")})
    store = FakeStore(agent_engine="qwen", agent_compare_enabled=True)
    review = run(agent.review(store, "AUDITORIA", CASE, PROCESSO))
    assert review["motor"] == "qwen" and review["recomendacao"] == "APROVADO"
    assert review["comparacao"]["motor"] == "jev" and review["comparacao"]["veredito"] == "REPROVADO" and review["comparacao"]["concorda"] is False
    recs = run(metrics.load(store))
    assert [(r["motor"], r["papel"]) for r in recs] == [("qwen", "principal"), ("jev", "comparacao")]
    summary = metrics.summarize(recs, desde_ms=0, ate_ms=recs[-1]["ts"] + 1)
    assert summary["concordancia_motores"]["por_tarefa"]["AUDITORIA"] == {"pares": 1, "concordam": 0, "qwen_mais_rigoroso": 0,
                                                                         "jev_mais_rigoroso": 1, "taxa": 0.0}
    assert summary["por_motor"]["jev"]["concordancia_regras"]["agente_mais_rigoroso"] == 1


def test_comparison_engine_down_never_stops_the_case(http):
    _, state = http
    state["chat"] = lambda req: httpx.Response(200, json={"message": {"content": json.dumps(QWEN_ANSWER)}})

    def down(req):
        raise httpx.ConnectError("recusada")
    state["jev"] = down
    store = FakeStore(agent_engine="qwen", agent_compare_enabled=True)
    review = run(agent.review(store, "AUDITORIA", CASE, PROCESSO))
    assert review["recomendacao"] == "APROVADO" and "indisponível" in review["comparacao"]["erro"]
    recs = run(metrics.load(store))
    assert recs[1]["motor"] == "jev" and recs[1]["ok"] is False


def test_main_engine_down_waits_unless_fallback(http):
    _, state = http

    def down(req):
        raise httpx.ConnectError("recusada")
    state["jev"] = down
    with pytest.raises(llm.AgentUnavailable):
        run(agent.review(FakeStore(agent_engine="jev"), "AUDITORIA", CASE, PROCESSO))
    store = FakeStore(agent_engine="jev", heuristic_fallback_enabled=True)
    review = run(agent.review(store, "ELEGIBILIDADE", CASE, PROCESSO, subject={}))
    assert review["motor"] == "heuristico" and review["classificacao"] == "ELEGIVEL"


def test_summary_statistics_and_series():
    base = 1_700_000_000_000
    recs = []
    for i in range(10):
        recs.append({"ts": base + i * 60_000, "motor": "qwen", "papel": "principal", "tarefa": "AUDITORIA", "case_id": f"c{i}", "ok": True,
                     "resposta_ms": 2000 + i * 100, "processamento_ms": 2100 + i * 100, "veredito": "APROVADO", "veredito_regras": "APROVADO"})
        recs.append({"ts": base + i * 60_000 + 1, "motor": "jev", "papel": "comparacao", "tarefa": "AUDITORIA", "case_id": f"c{i}", "ok": True,
                     "resposta_ms": 90, "processamento_ms": 100, "veredito": "APROVADO" if i < 8 else "REPROVADO", "veredito_regras": "APROVADO"})
    recs.append({"ts": base + 1, "motor": "jev", "tarefa": "AUDITORIA", "ok": True, "cache": True, "resposta_ms": 0, "processamento_ms": 1})
    s = metrics.summarize(recs, desde_ms=base, ate_ms=base + 600_000)
    assert s["por_motor"]["qwen"]["processamento_ms"]["media"] == 2550
    assert s["por_motor"]["jev"]["processamento_ms"]["media"] == 100  # cache hits are not timed
    assert s["por_motor"]["jev"]["cache"] == 1
    assert s["comparativo"]["mais_rapido"] == "jev" and s["comparativo"]["vezes"] == 25.5
    assert s["concordancia_motores"]["taxa"] == 0.8 and len(s["concordancia_motores"]["divergencias"]) == 2
    assert s["periodo"]["balde_ms"] == 60_000
    assert sum(b["motores"].get("qwen", {}).get("n", 0) for b in s["serie"]) == 10
