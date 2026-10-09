"""Simulated clock.

The lab runs on a business date that operators can move forward, so that
events with a validity period (programs that last a year, for example) can be
demonstrated and tested without waiting. When no date is set, the clock follows
the real calendar. The date lives in Redis and is shared by the API and every
worker.
"""
from __future__ import annotations

from datetime import date, timedelta

from .store import P, Store, now_ms

CLOCK_KEY = f"{P}:clock"


async def state(store: Store) -> dict:
    doc = await store.get_json(CLOCK_KEY) or {}
    real = date.today().isoformat()
    simulated = doc.get("data")
    return {"hoje": simulated or real, "data_real": real, "simulado": bool(simulated),
            "alterado_em": doc.get("alterado_em"), "alterado_por": doc.get("alterado_por")}


async def today(store: Store) -> str:
    return (await state(store))["hoje"]


async def set_date(store: Store, value: str | None, actor: str) -> dict:
    if value:
        value = date.fromisoformat(str(value)[:10]).isoformat()
    await store.set_json(CLOCK_KEY, {"data": value or None, "alterado_em": now_ms(), "alterado_por": actor})
    return await state(store)


async def advance(store: Store, dias: int, actor: str) -> dict:
    current = date.fromisoformat(await today(store))
    return await set_date(store, (current + timedelta(days=int(dias))).isoformat(), actor)
