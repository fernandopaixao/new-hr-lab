"""Agenda of events with a validity period (vigência).

A program such as the high-potential program is recorded on the employee
(`programas`) with an official start date, an end date and the events to emit
when it is about to expire and when it expires. The agenda is derived from that
state, so renewing a program (new end date) or ending it early (no longer
active) reschedules or cancels its events without any extra bookkeeping.

`tick` compares the agenda with the simulated clock and submits the events that
are due through the normal production line (intake, eligibility, planning,
audit, execution and final check). Each event has a deterministic id and is
claimed in a Redis hash before submission, so several workers, the API and the
scenario generator never emit the same event twice.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import clock, logbook as log
from .store import P, Store

EMITTED_KEY = f"{P}:vigencia:emitidos"
PREFIX = "vig"
AVISO = "aviso"
VENCIMENTO = "vencimento"


def event_id(emp_id: str, programa: str, fim: str, tipo: str) -> str:
    return f"{PREFIX}-{emp_id}-{programa}-{str(fim)[:10]}-{tipo}"


def active_programs(emp: dict) -> list[dict]:
    return [p for p in emp.get("programas") or [] if p.get("status") == "ATIVO"]


def warning_date(prog: dict) -> str | None:
    dias = int(prog.get("aviso_dias") or 0)
    if not dias or not prog.get("fim") or not prog.get("evento_aviso"):
        return None
    return (date.fromisoformat(str(prog["fim"])[:10]) - timedelta(days=dias)).isoformat()


def remaining_days(prog: dict, hoje: str) -> int | None:
    if not prog.get("fim"):
        return None
    return (date.fromisoformat(str(prog["fim"])[:10]) - date.fromisoformat(hoje[:10])).days


def agenda_for(emp: dict) -> list[dict]:
    """Scheduled events of one employee's active programs, oldest first."""
    items = []
    for prog in active_programs(emp):
        fim = str(prog.get("fim") or "")[:10]
        if not fim:
            continue
        base = {"colaborador_id": emp.get("id"), "colaborador_nome": emp.get("nome"), "programa": prog.get("codigo"),
                "programa_nome": prog.get("nome"), "inicio": prog.get("inicio"), "fim": fim}
        aviso = warning_date(prog)
        if aviso and not prog.get("aviso_em"):
            items.append({**base, "tipo": AVISO, "data": aviso, "evento": prog["evento_aviso"],
                          "evento_id": event_id(emp["id"], prog["codigo"], fim, AVISO)})
        if prog.get("evento_vencimento"):
            items.append({**base, "tipo": VENCIMENTO, "data": fim, "evento": prog["evento_vencimento"],
                          "evento_id": event_id(emp["id"], prog["codigo"], fim, VENCIMENTO)})
    return sorted(items, key=lambda i: (i["data"], i["tipo"] != AVISO))


async def claim(store: Store, evt_id: str, owner: str) -> bool:
    """Reserves an agenda event id. False when someone already emitted it."""
    return bool(await store.r.hsetnx(EMITTED_KEY, evt_id, owner))


async def agenda(store: Store) -> dict:
    hoje = await clock.today(store)
    emitted = await store.r.hgetall(EMITTED_KEY)
    items = []
    for emp in await store.list_employees():
        for item in agenda_for(emp):
            item["vence_em_dias"] = (date.fromisoformat(item["data"]) - date.fromisoformat(hoje)).days
            item["emitido"] = emitted.get(item["evento_id"])
            item["situacao"] = "EMITIDO" if item["emitido"] else ("VENCIDO" if item["data"] <= hoje else "AGENDADO")
            items.append(item)
    items.sort(key=lambda i: (i["data"], i["colaborador_id"] or ""))
    return {"hoje": hoje, "itens": items}


def due(items: list[dict], hoje: str) -> list[dict]:
    """Items due on `hoje`. A warning is skipped once the program has already reached its end date."""
    out = []
    for item in items:
        if item["data"] > hoje:
            continue
        if item["tipo"] == AVISO and item["fim"] <= hoje:
            continue
        out.append(item)
    return out


async def tick(store: Store, pipeline, actor: str = "agenda de vigências") -> list[dict]:
    """Submits every due agenda event that has not been emitted yet. Returns the submitted cases."""
    hoje = await clock.today(store)
    submitted = []
    for emp in await store.list_employees():
        for item in due(agenda_for(emp), hoje):
            if not await claim(store, item["evento_id"], "pendente"):
                continue
            event = {"id": item["evento_id"], "tipo": item["evento"], "colaborador_id": item["colaborador_id"],
                     "data_efetiva": item["data"], "origem": "agenda:vigencia",
                     "dados": {"programa": item["programa"], "fim": item["fim"]},
                     "metadados": {"agenda": item["tipo"], "relogio": hoje}}
            case = await pipeline.submit_event(event)
            await store.r.hset(EMITTED_KEY, item["evento_id"], case["id"])
            rotulo = "Aviso de vencimento" if item["tipo"] == AVISO else "Vencimento"
            await log.write(store, log.AGENDA_VIGENCIA,
                            f"{rotulo} do programa {item['programa']} de {item['colaborador_nome']} emitido pela agenda "
                            f"(previsto para {item['data']}, relógio em {hoje}).",
                            ator=actor, case_id=case["id"], colaborador_id=item["colaborador_id"], dados=item)
            submitted.append(case)
    return submitted
