"""Indexer: keeps the embeddings of every event up to date.

It consumes the audit log stream with its own consumer group (so it never
competes with the stage workers) and marks what changed:
- every entry that belongs to a case marks that case dirty; the case narrative
  is re-embedded after a short debounce, so a case that moves through six
  stages in a second is embedded once, not six times;
- decision entries without their own narrative (approvals, contract and
  employee changes, failures, compensations) become documents on their own.

Run it as its own service (`python -m hrlab.indexer`); docker compose does.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket

import redis.asyncio as aioredis

from . import embeddings as emb
from . import llm
from .llm import AgentUnavailable
from .facts import INDEXED_LOG_KINDS, case_document, log_document
from .logbook import _parse
from .store import LOG_STREAM, Store, now_ms

log = logging.getLogger("hrlab.indexer")
GROUP = "hr-indexer"
DEBOUNCE_MS = int(os.getenv("INDEX_DEBOUNCE_MS", "1500"))
BATCH = int(os.getenv("INDEX_BATCH", "16"))


async def build_docs(store: Store, refs: list[str]) -> list[dict]:
    docs = []
    for ref in refs:
        kind, _, key = ref.partition(":")
        if kind == "caso":
            case = await store.get_case(key)
            if not case:
                continue
            approvals = {}
            for ap_id in case.get("aprovacoes") or []:
                if isinstance(ap_id, str):
                    ap = await store.get_approval(ap_id)
                    if ap:
                        approvals[ap_id] = ap
            employee = await store.get_employee(case["colaborador_id"]) if case.get("colaborador_id") else None
            text, meta = case_document(case, approvals, employee)
        elif kind == "log":
            raw = await store.r.xrange(LOG_STREAM, min=key, max=key, count=1)
            if not raw:
                continue
            text, meta = log_document(_parse(*raw[0]))
        else:
            continue
        docs.append({"id": ref, "ref": ref, "text": text, "meta": meta, "hash": emb.text_hash(text)})
    return docs


async def index_refs(store: Store, refs: list[str]) -> dict:
    """Embeds the given refs (skipping unchanged texts). Raises AgentUnavailable."""
    settings = await store.settings()
    docs = await build_docs(store, refs)
    todo = []
    for d in docs:
        h, model = await emb.existing_hash(store, d["id"])
        if h == d["hash"] and model in (llm.embedding_model(settings), emb.HASH_MODEL) and not (
                model == emb.HASH_MODEL and await _real_model_ok(store, settings)):
            continue
        todo.append(d)
    model = None
    if todo:
        vectors, model = await emb.embed(store, [d["text"] for d in todo])
        await emb.upsert(store, todo, vectors, model)
    return {"lidos": len(refs), "embutidos": len(todo), "modelo": model}


async def _real_model_ok(store: Store, settings: dict) -> bool:
    health = await store.get_json("hr:agent:health") or {}
    return bool(health.get("online") and health.get("modelo_embedding_disponivel"))


async def mark_all(store: Store) -> int:
    """Marks every case and every indexable log entry for (re)indexing."""
    refs: dict[str, int] = {}
    for cid in await store.r.zrange("hr:cases", 0, -1):
        refs[f"caso:{cid}"] = 0
    last = "-"
    while True:
        chunk = await store.r.xrange(LOG_STREAM, min=last, max="+", count=1000)
        if not chunk:
            break
        for entry_id, fields in chunk:
            if fields.get("tipo") in INDEXED_LOG_KINDS:
                refs[f"log:{entry_id}"] = 0
        if len(chunk) < 1000:
            break
        last = "(" + chunk[-1][0]
    await emb.mark_dirty(store, refs)
    return len(refs)


class Indexer:
    def __init__(self, store: Store, name: str | None = None):
        self.store = store
        self.name = name or f"{socket.gethostname()}-{os.getpid()}"
        llm.use_ledger(store)

    async def ensure_group(self) -> None:
        try:
            await self.store.r.xgroup_create(LOG_STREAM, GROUP, id="0", mkstream=True)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def consume_log(self) -> None:
        await self.ensure_group()
        while True:
            try:
                resp = await self.store.r.xreadgroup(GROUP, self.name, {LOG_STREAM: ">"}, count=200, block=1000)
                if not resp:
                    continue
                refs: dict[str, int] = {}
                ids = []
                for entry_id, fields in resp[0][1]:
                    ids.append(entry_id)
                    if fields.get("case_id"):
                        refs[f"caso:{fields['case_id']}"] = now_ms()
                    if fields.get("tipo") in INDEXED_LOG_KINDS:
                        refs[f"log:{entry_id}"] = 0
                await emb.mark_dirty(self.store, refs)
                await self.store.r.xack(LOG_STREAM, GROUP, *ids)
            except aioredis.ResponseError as exc:
                if "NOGROUP" in str(exc):  # the lab was reset and the stream deleted
                    await self.ensure_group()
                    continue
                log.exception("erro lendo o log")
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("erro lendo o log")
                await asyncio.sleep(1)

    async def work(self) -> None:
        while True:
            try:
                settings = await self.store.settings()
                if not settings.get("indexing_enabled", True):
                    await self._status(estado="DESLIGADO", mensagem="Indexação desligada nas configurações.")
                    await asyncio.sleep(3)
                    continue
                # documents embedded with the simulated model go back to the queue once the real model is back
                if await self.store.r.scard(emb.SIMULATED_KEY) and await _real_model_ok(self.store, settings):
                    sims = await self.store.r.smembers(emb.SIMULATED_KEY)
                    await emb.mark_dirty(self.store, {s: 0 for s in sims})
                refs = await self.store.r.zrangebyscore(emb.DIRTY_KEY, 0, now_ms() - DEBOUNCE_MS, start=0, num=BATCH)
                if not refs:
                    await self._status(estado="EM_DIA", mensagem="Índice em dia.")
                    await asyncio.sleep(0.7)
                    continue
                scores = {r: await self.store.r.zscore(emb.DIRTY_KEY, r) for r in refs}
                result = await index_refs(self.store, refs)
                # remove only refs that were not touched again while embedding
                for r, sc in scores.items():
                    if await self.store.r.zscore(emb.DIRTY_KEY, r) == sc:
                        await self.store.r.zrem(emb.DIRTY_KEY, r)
                await self._status(estado="INDEXANDO", mensagem=f"{result['embutidos']} documento(s) embutidos com {result['modelo'] or '-'}.",
                                   ultimo_lote=result)
            except AgentUnavailable as exc:
                await self._status(estado="AGUARDANDO_IA", mensagem=f"Aguardando o provedor de embeddings: {exc}. "
                                   "Os eventos continuam marcados e serão indexados quando ele voltar.")
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("erro indexando")
                await self._status(estado="ERRO", mensagem=f"{type(exc).__name__}: {exc}")
                await asyncio.sleep(3)

    async def _status(self, **kw) -> None:
        current = await self.store.get_json(emb.STATUS_KEY) or {}
        if current.get("estado") == kw.get("estado") and kw.get("estado") in ("EM_DIA", "DESLIGADO"):
            return
        current.update(kw)
        current["atualizado_em"] = now_ms()
        current["indexador"] = self.name
        await self.store.set_json(emb.STATUS_KEY, current)
        await self.store.publish({"tipo": "indice", "estado": current.get("estado")})

    async def run(self) -> None:
        log.info("indexador %s iniciado", self.name)
        await asyncio.gather(self.consume_log(), self.work())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(Indexer(Store()).run())


if __name__ == "__main__":
    main()
