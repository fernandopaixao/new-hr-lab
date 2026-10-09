"""Append-only audit log.

Every change and every decision is written with an explanation:
- to the Redis stream `hr:log` (global, filterable in the interface);
- to the case trail and the employee trail (lists);
- to a JSONL file on the data volume, so the log survives outside Redis.
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import config
from .store import LOG_STREAM, P, Store, dumps, now_ms

# Log entry kinds.
EVENTO_RECEBIDO = "EVENTO_RECEBIDO"
EVENTO_REJEITADO = "EVENTO_REJEITADO"
EVENTO_DUPLICADO = "EVENTO_DUPLICADO"
ESTAGIO = "ESTAGIO"
REGRA = "REGRA_AVALIADA"
ELEGIBILIDADE = "DECISAO_ELEGIBILIDADE"
PLANO = "PLANO_GERADO"
OPERACAO_ESCOLHIDA = "OPERACAO_ESCOLHIDA"
OPERACAO_DESCARTADA = "OPERACAO_DESCARTADA"
OPERACAO_EXECUTADA = "OPERACAO_EXECUTADA"
OPERACAO_FALHOU = "OPERACAO_FALHOU"
COMPENSACAO = "COMPENSACAO"
AGENTE = "AGENTE_RECOMENDACAO"
AGENTE_INDISPONIVEL = "AGENTE_INDISPONIVEL"
APROVACAO_SOLICITADA = "APROVACAO_SOLICITADA"
APROVACAO_DECIDIDA = "APROVACAO_DECIDIDA"
AUDITORIA = "AUDITORIA"
DECISAO_FINAL = "DECISAO_FINAL"
COLABORADOR_ALTERADO = "COLABORADOR_ALTERADO"
CONTRATO_ALTERADO = "CONTRATO_ALTERADO"
CONFIG_ALTERADA = "CONFIG_ALTERADA"
CONTROLE = "CONTROLE"
DEPURACAO = "DEPURACAO"
REPLANEJAMENTO = "REPLANEJAMENTO"


async def write(
    store: Store,
    tipo: str,
    mensagem: str,
    *,
    ator: str = "sistema",
    case_id: str | None = None,
    colaborador_id: str | None = None,
    estagio: str | None = None,
    dados: Any = None,
) -> dict:
    entry = {
        "ts": now_ms(),
        "tipo": tipo,
        "ator": ator,
        "case_id": case_id or "",
        "colaborador_id": colaborador_id or "",
        "estagio": estagio or "",
        "mensagem": mensagem,
        "dados": dados if dados is not None else {},
    }
    flat = {k: (dumps(v) if k == "dados" else str(v)) for k, v in entry.items()}
    entry_id = await store.r.xadd(LOG_STREAM, flat, maxlen=200000, approximate=True)
    entry["id"] = entry_id
    serialized = dumps(entry)
    pipe = store.r.pipeline()
    if case_id:
        pipe.rpush(f"{P}:case:{case_id}:log", serialized)
    if colaborador_id:
        pipe.rpush(f"{P}:employee:{colaborador_id}:log", serialized)
    await pipe.execute()
    _append_file(serialized)
    await store.publish({"tipo": "log", "entry": entry})
    return entry


def _append_file(line: str) -> None:
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(config.AUDIT_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _parse(entry_id: str, fields: dict) -> dict:
    out = dict(fields)
    out["id"] = entry_id
    out["ts"] = int(out.get("ts", 0))
    try:
        out["dados"] = json.loads(out.get("dados") or "{}")
    except json.JSONDecodeError:
        pass
    return out


async def query(
    store: Store,
    *,
    limit: int = 300,
    tipo: str | None = None,
    case_id: str | None = None,
    colaborador_id: str | None = None,
    texto: str | None = None,
    before: str | None = None,
) -> list[dict]:
    if case_id:
        raws = await store.r.lrange(f"{P}:case:{case_id}:log", 0, -1)
        items = [json.loads(x) for x in raws]
    elif colaborador_id:
        raws = await store.r.lrange(f"{P}:employee:{colaborador_id}:log", -limit * 3, -1)
        items = [json.loads(x) for x in raws]
    else:
        max_id = f"({before}" if before else "+"
        raw = await store.r.xrevrange(LOG_STREAM, max=max_id, min="-", count=limit * 5 if (tipo or texto) else limit)
        items = [_parse(i, f) for i, f in raw]
        items.reverse()
    if tipo:
        tipos = set(tipo.split(","))
        items = [i for i in items if i.get("tipo") in tipos]
    if texto:
        t = texto.lower()
        items = [i for i in items if t in (i.get("mensagem", "") + dumps(i.get("dados"))).lower()]
    return items[-limit:]
