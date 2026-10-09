"""Redis-backed storage: documents, indexes, streams, pub/sub and locks.

Redis is the single state store of the lab (persisted with AOF in docker):
- JSON documents for employees, contracts, cases, approvals and settings;
- one stream per production-line stage, consumed through consumer groups;
- an append-only audit log stream;
- a pub/sub channel that feeds the live interface.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import redis.asyncio as aioredis

from . import config
from .domain import next_step

P = "hr"
UPDATES_CHANNEL = f"{P}:updates"
LOG_STREAM = f"{P}:log"
GROUP = "hr-workers"


def stream_key(stage: str) -> str:
    return f"{P}:stream:{stage}"


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class Store:
    def __init__(self, url: str | None = None):
        self.r: aioredis.Redis = aioredis.from_url(url or config.REDIS_URL, decode_responses=True)

    async def close(self) -> None:
        await self.r.aclose()

    # ---------------------------------------------------------------- generic
    async def get_json(self, key: str) -> Any:
        raw = await self.r.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any) -> None:
        await self.r.set(key, dumps(value))

    # --------------------------------------------------------------- settings
    async def settings(self) -> dict[str, Any]:
        stored = await self.get_json(f"{P}:settings") or {}
        merged = dict(config.DEFAULT_SETTINGS)
        merged.update({k: v for k, v in stored.items() if k in merged})
        return merged

    async def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        stored = await self.get_json(f"{P}:settings") or {}
        stored.update(config.coerce_settings(patch))
        await self.set_json(f"{P}:settings", stored)
        return await self.settings()

    async def control(self) -> dict[str, Any]:
        ctl = await self.get_json(f"{P}:control") or {}
        ctl.setdefault("paused", False)
        ctl.setdefault("paused_stages", [])
        ctl.setdefault("breakpoints", [])
        return ctl

    async def set_control(self, ctl: dict[str, Any]) -> None:
        await self.set_json(f"{P}:control", ctl)

    # -------------------------------------------------------------- employees
    async def get_employee(self, emp_id: str) -> dict | None:
        return await self.get_json(f"{P}:employee:{emp_id}")

    async def save_employee(self, emp: dict) -> dict:
        emp["versao"] = int(emp.get("versao", 0)) + 1
        emp["atualizado_em"] = now_ms()
        await self.set_json(f"{P}:employee:{emp['id']}", emp)
        await self.r.sadd(f"{P}:employees", emp["id"])
        return emp

    async def list_employees(self) -> list[dict]:
        ids = sorted(await self.r.smembers(f"{P}:employees"))
        if not ids:
            return []
        raws = await self.r.mget([f"{P}:employee:{i}" for i in ids])
        return [json.loads(x) for x in raws if x]

    async def delete_all_employees(self) -> None:
        ids = await self.r.smembers(f"{P}:employees")
        if ids:
            await self.r.delete(*[f"{P}:employee:{i}" for i in ids], *[f"{P}:employee:{i}:log" for i in ids])
        await self.r.delete(f"{P}:employees")

    @asynccontextmanager
    async def employee_lock(self, emp_id: str, timeout: int = 30) -> AsyncIterator[None]:
        lock = self.r.lock(f"{P}:lock:employee:{emp_id}", timeout=timeout, blocking_timeout=timeout)
        acquired = await lock.acquire()
        if not acquired:
            raise TimeoutError(f"não foi possível obter trava do colaborador {emp_id}")
        try:
            yield
        finally:
            try:
                await lock.release()
            except Exception:  # noqa: BLE001 - lock may have expired
                pass

    # -------------------------------------------------------------- contracts
    async def get_contract_versions(self, code: str) -> list[dict]:
        return await self.get_json(f"{P}:contract:{code}") or []

    async def save_contract_versions(self, code: str, versions: list[dict]) -> None:
        await self.set_json(f"{P}:contract:{code}", versions)
        await self.r.sadd(f"{P}:contracts", code)

    async def delete_contract(self, code: str) -> None:
        await self.r.delete(f"{P}:contract:{code}")
        await self.r.srem(f"{P}:contracts", code)

    async def list_contract_codes(self) -> list[str]:
        return sorted(await self.r.smembers(f"{P}:contracts"))

    # ------------------------------------------------------------------ cases
    async def get_case(self, case_id: str) -> dict | None:
        return await self.get_json(f"{P}:case:{case_id}")

    async def save_case(self, case: dict, publish: bool = True) -> dict:
        case["atualizado_em"] = now_ms()
        case["proximo_passo"] = next_step(case)
        await self.set_json(f"{P}:case:{case['id']}", case)
        await self.r.zadd(f"{P}:cases", {case["id"]: case.get("criado_em", now_ms())})
        if publish:
            await self.publish({"tipo": "case", "case": case_summary(case)})
        return case

    async def list_cases(self, limit: int = 300, offset: int = 0) -> list[dict]:
        ids = await self.r.zrevrange(f"{P}:cases", offset, offset + limit - 1)
        if not ids:
            return []
        raws = await self.r.mget([f"{P}:case:{i}" for i in ids])
        return [json.loads(x) for x in raws if x]

    async def count_cases(self) -> int:
        return await self.r.zcard(f"{P}:cases")

    async def claim_event_id(self, event_id: str, case_id: str) -> str | None:
        """Idempotency: returns the existing case id if the event was already seen."""
        ok = await self.r.set(f"{P}:event:{event_id}", case_id, nx=True)
        if ok:
            return None
        return await self.r.get(f"{P}:event:{event_id}")

    # -------------------------------------------------------------- approvals
    async def get_approval(self, ap_id: str) -> dict | None:
        return await self.get_json(f"{P}:approval:{ap_id}")

    async def save_approval(self, ap: dict) -> dict:
        await self.set_json(f"{P}:approval:{ap['id']}", ap)
        await self.r.zadd(f"{P}:approvals", {ap["id"]: ap.get("criado_em", now_ms())})
        if ap.get("status") == "PENDENTE":
            await self.r.sadd(f"{P}:approvals:pending", ap["id"])
        else:
            await self.r.srem(f"{P}:approvals:pending", ap["id"])
        await self.publish({"tipo": "approval", "approval": ap})
        return ap

    async def list_approvals(self, pending_only: bool = False, limit: int = 300) -> list[dict]:
        if pending_only:
            ids = list(await self.r.smembers(f"{P}:approvals:pending"))
        else:
            ids = await self.r.zrevrange(f"{P}:approvals", 0, limit - 1)
        if not ids:
            return []
        raws = await self.r.mget([f"{P}:approval:{i}" for i in ids])
        items = [json.loads(x) for x in raws if x]
        return sorted(items, key=lambda a: a.get("criado_em", 0), reverse=True)

    # ---------------------------------------------------------------- streams
    async def ensure_groups(self, stages: list[str]) -> None:
        for stage in stages:
            try:
                await self.r.xgroup_create(stream_key(stage), GROUP, id="0", mkstream=True)
            except aioredis.ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

    async def enqueue(self, stage: str, case_id: str, extra: dict | None = None) -> str:
        fields = {"case_id": case_id}
        if extra:
            fields.update({k: dumps(v) for k, v in extra.items()})
        return await self.r.xadd(stream_key(stage), fields, maxlen=50000, approximate=True)

    async def queue_stats(self, stages: list[str]) -> dict[str, dict]:
        out = {}
        for stage in stages:
            key = stream_key(stage)
            info = {"tamanho": 0, "pendentes": 0, "atraso": 0, "consumidores": 0}
            try:
                info["tamanho"] = await self.r.xlen(key)
                for g in await self.r.xinfo_groups(key):
                    if g.get("name") == GROUP:
                        info["pendentes"] = g.get("pending", 0)
                        info["atraso"] = g.get("lag") or 0
                        info["consumidores"] = g.get("consumers", 0)
            except aioredis.ResponseError:
                pass
            out[stage] = info
        return out

    # ---------------------------------------------------------------- pub/sub
    async def publish(self, message: dict) -> None:
        await self.r.publish(UPDATES_CHANNEL, dumps(message))

    # ------------------------------------------------------------------ reset
    async def reset_runtime(self) -> None:
        """Drop cases, approvals, logs and queues (keeps employees and contracts)."""
        patterns = [f"{P}:case:*", f"{P}:approval:*", f"{P}:event:*", f"{P}:stream:*", f"{P}:lock:*", f"{P}:scenario_run:*"]
        for pattern in patterns:
            async for key in self.r.scan_iter(match=pattern, count=500):
                await self.r.delete(key)
        await self.r.delete(f"{P}:cases", f"{P}:approvals", f"{P}:approvals:pending", LOG_STREAM, f"{P}:scenario_runs",
                          f"{P}:vigencia:emitidos")
        async for key in self.r.scan_iter(match=f"{P}:employee:*:log", count=500):
            await self.r.delete(key)


def case_summary(case: dict) -> dict:
    keys = [
        "id", "evento_tipo", "evento_id", "colaborador_id", "colaborador_nome", "status", "estagio",
        "estagio_parado", "criado_em", "atualizado_em", "resumo", "cenario", "depuracao", "pai_id",
        "recomendacao_auditoria", "recomendacao_conferencia", "processo", "proximo_passo",
    ]
    out = {k: case.get(k) for k in keys}
    out["proximo_passo"] = case.get("proximo_passo") or next_step(case)
    return out
