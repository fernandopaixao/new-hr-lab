"""Performance history of the agents: one record per agent call, kept across lab resets.

Every call of the eligibility, audit and final check agents (main engine or the
comparison engine) is appended to the Redis stream `hr:metrics:agent` with the
engine, model, task, response time, processing time, tokens and verdict. The
performance panel reads a time window of that stream and aggregates it here:
averages and percentiles per engine and task, a time series, the agreement of
each engine with the deterministic rules, and the agreement between Qwen and
JEV on the same case and task.

Times:
- resposta_ms: the model call alone (request sent until answer received);
- espera_ms: waiting for a free slot of the provider (concurrency limit);
- processamento_ms: the whole agent task (prompt, wait, retries, parsing and normalization).
"""
from __future__ import annotations

import json
from typing import Any

from .facts import percentile
from .store import P, Store, dumps, now_ms

STREAM = f"{P}:metrics:agent"
MAX_RECORDS = 200_000
ENGINES = ("qwen", "jev")
ENGINE_LABELS = {"qwen": "Qwen (generativo)", "jev": "JEV (decisor)", "heuristico": "Agente simulado"}
TASKS = ("ELEGIBILIDADE", "AUDITORIA", "CONFERENCIA")
TASK_LABELS = {"ELEGIBILIDADE": "Classificação de elegibilidade", "AUDITORIA": "Auditoria do plano", "CONFERENCIA": "Conferência da execução"}
STRICTNESS = {"APROVADO": 0, "ELEGIVEL": 0, "EXCECAO_NECESSARIA": 1, "REPROVADO": 2, "NAO_ELEGIVEL": 2}


def rules_verdict(kind: str, case: dict) -> str | None:
    """Decision of the deterministic rules in the same terms as the agent's verdict."""
    if kind == "ELEGIBILIDADE":
        return (case.get("elegibilidade") or {}).get("decisao")
    decisao = (case.get("auditoria" if kind == "AUDITORIA" else "conferencia_final") or {}).get("decisao")
    if not decisao:
        return None
    return "REPROVADO" if decisao == "REPROVADO" else "APROVADO"


def build_record(*, motor: str, papel: str, kind: str, case: dict, result: dict | None, started_ms: int,
                 erro: str | None = None) -> dict:
    result = result or {}
    return {
        "ts": now_ms(), "motor": motor, "papel": papel, "tarefa": kind, "case_id": case.get("id"),
        "evento_tipo": (case.get("evento") or {}).get("tipo"), "modelo": result.get("modelo"), "provedor": result.get("provedor"),
        "resposta_ms": result.get("resposta_ms"), "espera_ms": result.get("espera_ms"),
        "processamento_ms": result.get("processamento_ms") if result.get("processamento_ms") is not None else now_ms() - started_ms,
        "tokens_entrada": result.get("prompt_eval_count"), "tokens_saida": result.get("eval_count"),
        "tentativas": result.get("tentativas"), "cache": bool(result.get("cache")), "simulado": result.get("agente") == "heuristico",
        "ok": erro is None and not result.get("erro"), "erro": erro or result.get("erro"),
        "veredito": result.get("veredito"), "confianca": result.get("confianca"), "veredito_regras": rules_verdict(kind, case),
    }


async def record(store: Store, rec: dict) -> None:
    await store.r.xadd(STREAM, {"d": dumps(rec)}, maxlen=MAX_RECORDS, approximate=True)


async def load(store: Store, desde_ms: int = 0, ate_ms: int | None = None) -> list[dict]:
    rows = await store.r.xrange(STREAM, min=str(desde_ms) if desde_ms else "-", max=str(ate_ms) if ate_ms else "+")
    out = []
    for _, fields in rows:
        try:
            out.append(json.loads(fields["d"]))
        except (KeyError, ValueError):
            continue
    return out


async def clear(store: Store) -> int:
    n = await store.r.xlen(STREAM)
    await store.r.delete(STREAM)
    return n


# ------------------------------------------------------------------ aggregation
def _stats(values: list[Any]) -> dict:
    vals = [int(v) for v in values if v is not None]
    if not vals:
        return {"n": 0, "media": None, "p50": None, "p95": None, "max": None, "min": None}
    return {"n": len(vals), "media": round(sum(vals) / len(vals)), "p50": percentile(vals, 50), "p95": percentile(vals, 95),
            "max": max(vals), "min": min(vals)}


def _timed(recs: list[dict]) -> list[dict]:
    """Calls that really reached a model: no cache hits, no simulated agent, no failures."""
    return [r for r in recs if r.get("ok") and not r.get("cache") and not r.get("simulado")]


def _group(recs: list[dict]) -> dict:
    timed = _timed(recs)
    tok_in = [r.get("tokens_entrada") for r in timed if r.get("tokens_entrada") is not None]
    tok_out = [r.get("tokens_saida") for r in timed if r.get("tokens_saida") is not None]
    return {
        "chamadas": len(recs), "medidas": len(timed), "erros": sum(1 for r in recs if not r.get("ok")),
        "cache": sum(1 for r in recs if r.get("cache")), "simuladas": sum(1 for r in recs if r.get("simulado")),
        "resposta_ms": _stats([r.get("resposta_ms") for r in timed]),
        "espera_ms": _stats([r.get("espera_ms") for r in timed]),
        "processamento_ms": _stats([r.get("processamento_ms") for r in timed]),
        "tokens_entrada_media": round(sum(tok_in) / len(tok_in)) if tok_in else None,
        "tokens_saida_media": round(sum(tok_out) / len(tok_out)) if tok_out else None,
        "confianca_media": _avg_float([r.get("confianca") for r in recs if r.get("ok") and not r.get("simulado")]),
        "modelos": sorted({r.get("modelo") for r in recs if r.get("modelo")}),
    }


def _avg_float(values: list[Any]) -> float | None:
    vals = [float(v) for v in values if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 3) if vals else None


def _rules_agreement(recs: list[dict]) -> dict:
    out = {"concordam": 0, "agente_mais_rigoroso": 0, "regras_mais_rigorosas": 0, "total": 0}
    for r in recs:
        a, b = r.get("veredito"), r.get("veredito_regras")
        if not r.get("ok") or r.get("simulado") or a not in STRICTNESS or b not in STRICTNESS:
            continue
        out["total"] += 1
        if a == b:
            out["concordam"] += 1
        elif STRICTNESS[a] > STRICTNESS[b]:
            out["agente_mais_rigoroso"] += 1
        else:
            out["regras_mais_rigorosas"] += 1
    out["taxa"] = round(out["concordam"] / out["total"], 3) if out["total"] else None
    return out


def _engine_agreement(recs: list[dict]) -> dict:
    """Qwen and JEV on the same case and task: the latest valid verdict of each."""
    latest: dict[tuple[str, str], dict[str, dict]] = {}
    for r in recs:
        if not r.get("ok") or r.get("simulado") or not r.get("case_id") or r.get("motor") not in ENGINES:
            continue
        slot = latest.setdefault((r["case_id"], r["tarefa"]), {})
        if r["motor"] not in slot or r["ts"] >= slot[r["motor"]]["ts"]:
            slot[r["motor"]] = r
    by_task = {t: {"pares": 0, "concordam": 0, "qwen_mais_rigoroso": 0, "jev_mais_rigoroso": 0} for t in TASKS}
    divergencias = []
    for (case_id, task), slot in latest.items():
        if len(slot) < 2 or task not in by_task:
            continue
        q, j = slot["qwen"], slot["jev"]
        row = by_task[task]
        row["pares"] += 1
        if q["veredito"] == j["veredito"]:
            row["concordam"] += 1
        else:
            if STRICTNESS.get(q["veredito"], 0) >= STRICTNESS.get(j["veredito"], 0):
                row["qwen_mais_rigoroso"] += 1
            else:
                row["jev_mais_rigoroso"] += 1
            divergencias.append({"case_id": case_id, "tarefa": task, "evento_tipo": q.get("evento_tipo"), "ts": max(q["ts"], j["ts"]),
                                 "qwen": q["veredito"], "jev": j["veredito"], "regras": q.get("veredito_regras")})
    pares = sum(r["pares"] for r in by_task.values())
    conc = sum(r["concordam"] for r in by_task.values())
    for row in by_task.values():
        row["taxa"] = round(row["concordam"] / row["pares"], 3) if row["pares"] else None
    divergencias.sort(key=lambda d: d["ts"], reverse=True)
    return {"pares": pares, "concordam": conc, "taxa": round(conc / pares, 3) if pares else None, "por_tarefa": by_task,
            "divergencias": divergencias[:20]}


def auto_bucket_ms(span_ms: int) -> int:
    """About 30 to 60 points on the chart, rounded to a readable step."""
    for step in (60_000, 5 * 60_000, 15 * 60_000, 3_600_000, 6 * 3_600_000, 86_400_000, 7 * 86_400_000):
        if span_ms / step <= 60:
            return step
    return 30 * 86_400_000


def _series(recs: list[dict], desde_ms: int, ate_ms: int, bucket_ms: int) -> list[dict]:
    timed = _timed(recs)
    start = desde_ms - desde_ms % bucket_ms
    n = max(1, min(400, (ate_ms - start) // bucket_ms + 1))
    buckets: list[dict[str, Any]] = [{"inicio": start + i * bucket_ms, "motores": {}} for i in range(n)]
    acc: dict[tuple[int, str], dict[str, list]] = {}
    for r in timed:
        i = (r["ts"] - start) // bucket_ms
        if 0 <= i < n:
            a = acc.setdefault((i, r["motor"]), {"resposta": [], "processamento": []})
            a["resposta"].append(r.get("resposta_ms"))
            a["processamento"].append(r.get("processamento_ms"))
    for (i, motor), a in acc.items():
        resp, proc = [v for v in a["resposta"] if v is not None], [v for v in a["processamento"] if v is not None]
        buckets[i]["motores"][motor] = {
            "n": len(proc), "resposta_media_ms": round(sum(resp) / len(resp)) if resp else None,
            "processamento_media_ms": round(sum(proc) / len(proc)) if proc else None,
            "processamento_p95_ms": percentile(proc, 95),
        }
    return buckets


def summarize(recs: list[dict], *, desde_ms: int, ate_ms: int, bucket_ms: int | None = None, recentes: int = 30) -> dict:
    """Everything the performance panel shows for a time window."""
    if recs and not desde_ms:
        desde_ms = min(r["ts"] for r in recs)
    desde_ms = desde_ms or ate_ms - 3_600_000
    bucket_ms = bucket_ms or auto_bucket_ms(max(1, ate_ms - desde_ms))
    motores = sorted({r.get("motor") for r in recs if r.get("motor")}, key=lambda m: (m not in ENGINES, m))
    for m in ENGINES:
        if m not in motores:
            motores.insert(ENGINES.index(m), m)
    por_motor = {}
    for m in motores:
        mine = [r for r in recs if r.get("motor") == m]
        por_motor[m] = {"motor": m, "nome": ENGINE_LABELS.get(m, m), **_group(mine),
                        "por_tarefa": {t: _group([r for r in mine if r.get("tarefa") == t]) for t in TASKS},
                        "concordancia_regras": _rules_agreement(mine),
                        "principal": sum(1 for r in mine if r.get("papel") == "principal"),
                        "comparacao": sum(1 for r in mine if r.get("papel") == "comparacao")}
    q, j = por_motor.get("qwen"), por_motor.get("jev")
    comparativo = None
    if q and j and q["processamento_ms"]["media"] and j["processamento_ms"]["media"]:
        faster = "jev" if j["processamento_ms"]["media"] < q["processamento_ms"]["media"] else "qwen"
        slow, fast = (q, j) if faster == "jev" else (j, q)
        comparativo = {"mais_rapido": faster, "nome": ENGINE_LABELS[faster],
                       "vezes": round(slow["processamento_ms"]["media"] / max(1, fast["processamento_ms"]["media"]), 1),
                       "diferenca_media_ms": slow["processamento_ms"]["media"] - fast["processamento_ms"]["media"]}
    erros = [r for r in recs if not r.get("ok")]
    return {
        "periodo": {"desde": desde_ms, "ate": ate_ms, "balde_ms": bucket_ms}, "total": len(recs),
        "motores": motores, "nomes": ENGINE_LABELS, "tarefas": TASK_LABELS,
        "por_motor": por_motor, "comparativo": comparativo,
        "serie": _series(recs, desde_ms, ate_ms, bucket_ms),
        "concordancia_motores": _engine_agreement(recs),
        "erros_recentes": [{k: r.get(k) for k in ("ts", "motor", "tarefa", "case_id", "erro", "modelo")} for r in erros[-10:]][::-1],
        "recentes": [{k: r.get(k) for k in ("ts", "motor", "papel", "tarefa", "case_id", "evento_tipo", "modelo", "resposta_ms",
                                             "espera_ms", "processamento_ms", "veredito", "veredito_regras", "confianca", "cache", "ok", "erro")}
                     for r in recs[-recentes:]][::-1],
    }
