"""Stage workers: Redis Streams consumers, one loop per stage.

Several worker processes can run in parallel (docker compose --scale worker=N);
consumer groups guarantee each message is delivered to one consumer. Global and
per-stage pauses stop consumption, so messages accumulate visibly in the queues.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket

from . import agent
from .contracts import ContractRepo
from .domain import STAGE_KEYS
from .pipeline import Pipeline
from .store import GROUP, Store, stream_key

log = logging.getLogger("hrlab.worker")
STAGE_CONCURRENCY = int(os.getenv("STAGE_CONCURRENCY", "4"))


class Worker:
    def __init__(self, store: Store, name: str | None = None):
        self.store = store
        self.pipeline = Pipeline(store)
        self.name = name or f"{socket.gethostname()}-{os.getpid()}"
        self.stopping = False

    async def stage_loop(self, stage: str) -> None:
        sem = asyncio.Semaphore(STAGE_CONCURRENCY)
        key = stream_key(stage)
        # first deliver messages left pending by a crashed consumer of this name
        last_id = "0"
        while not self.stopping:
            try:
                ctl = await self.store.control()
                if ctl.get("paused") or stage in ctl.get("paused_stages", []):
                    await asyncio.sleep(0.5)
                    continue
                if sem.locked():
                    await asyncio.sleep(0.05)
                    continue
                resp = await self.store.r.xreadgroup(GROUP, self.name, {key: last_id}, count=1, block=1000)
                if not resp:
                    last_id = ">"
                    continue
                _, messages = resp[0]
                if not messages:
                    last_id = ">"
                    continue
                for msg_id, fields in messages:
                    await sem.acquire()
                    asyncio.create_task(self._handle(stage, msg_id, fields, sem))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("erro no loop do estágio %s: %s", stage, exc)
                await asyncio.sleep(1)

    async def _handle(self, stage: str, msg_id: str, fields: dict, sem: asyncio.Semaphore) -> None:
        try:
            await self.pipeline.run_stage(stage, fields.get("case_id", ""), worker=self.name)
        except Exception:  # noqa: BLE001
            log.exception("falha ao processar %s em %s", fields, stage)
        finally:
            await self.store.r.xack(stream_key(stage), GROUP, msg_id)
            sem.release()

    async def agent_monitor(self) -> None:
        warmed = False
        while not self.stopping:
            try:
                settings = await self.store.settings()
                health = await agent.check_health(self.store, settings)
                if health.get("ok"):
                    if not warmed:
                        asyncio.create_task(agent.warmup(settings))
                        warmed = True
                    await self.pipeline.requeue_waiting_agent()
                elif settings.get("heuristic_fallback_enabled"):
                    await self.pipeline.requeue_waiting_agent()
                else:
                    warmed = False
            except Exception:  # noqa: BLE001
                log.exception("erro no monitor do agente")
            await asyncio.sleep(10)

    async def run(self) -> None:
        await self.store.ensure_groups(STAGE_KEYS)
        await ContractRepo(self.store).seed()
        log.info("worker %s iniciado para os estágios %s", self.name, STAGE_KEYS)
        tasks = [asyncio.create_task(self.stage_loop(s)) for s in STAGE_KEYS]
        tasks.append(asyncio.create_task(self.agent_monitor()))
        await asyncio.gather(*tasks)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store = Store()
    asyncio.run(Worker(store).run())


if __name__ == "__main__":
    main()
