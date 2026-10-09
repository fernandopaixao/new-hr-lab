"""One-off migrations of stored runtime data, run at API start-up.

Each migration is idempotent and guarded by a marker key, so restarting the API
or running several replicas never applies one twice.
"""
from __future__ import annotations

from .domain import APPROVAL_TYPE_LABELS, LEGACY_APPROVAL_RENAMES, LEGACY_STAGE_RENAMES, NA_FILA, PROCESSANDO
from .store import P, Store

AUDIT_BEFORE_EXECUTION = f"{P}:migration:audit_before_execution"

# Case fields renamed when the audit moved ahead of the execution, applied in this order.
CASE_FIELD_RENAMES = [
    ("auditoria", "conferencia_final"), ("agente_auditoria", "agente_conferencia"), ("recomendacao_auditoria", "recomendacao_conferencia"),
    ("conferencia_plano", "auditoria"), ("agente_plano", "agente_auditoria"), ("recomendacao_plano", "recomendacao_auditoria"),
]


def _stage(name: str | None) -> str | None:
    return LEGACY_STAGE_RENAMES.get(name, name) if name else name


def migrate_case(case: dict) -> bool:
    """Rename stages and fields of a case stored before the audit moved ahead. Returns True when changed."""
    if "plan_review" not in (case.get("etapas") or {}):
        return False
    case["etapas"] = {_stage(k): v for k, v in case["etapas"].items()}
    for key in ("estagio", "estagio_parado", "liberado_para"):
        case[key] = _stage(case.get(key))
    case["breakpoints"] = [_stage(b) for b in case.get("breakpoints") or []]
    for old, new in CASE_FIELD_RENAMES:
        if old in case:
            case[new] = case.pop(old)
    return True


def migrate_approval(ap: dict) -> bool:
    if ap.get("estagio") not in LEGACY_STAGE_RENAMES or ap.get("migrado"):
        return False
    ap["estagio"] = _stage(ap["estagio"])
    ap["tipo"] = LEGACY_APPROVAL_RENAMES.get(ap.get("tipo"), ap.get("tipo"))
    ap["tipo_rotulo"] = APPROVAL_TYPE_LABELS.get(ap["tipo"], ap.get("tipo_rotulo"))
    ap["migrado"] = True
    return True


async def audit_before_execution(store: Store) -> int:
    """Stages were intake, ..., plan_review, execution, audit; now intake, ..., audit, execution, verification."""
    if not await store.r.set(AUDIT_BEFORE_EXECUTION, "em_andamento", nx=True):
        return 0
    changed = 0
    pending: dict[str, list[dict]] = {}
    for ap in await store.list_approvals(limit=100000):
        if migrate_approval(ap):
            await store.save_approval(ap)
        if ap.get("status") == "PENDENTE":
            pending.setdefault(ap["case_id"], []).append(
                {"id": ap["id"], "tipo_rotulo": ap.get("tipo_rotulo"), "aprovadores": ap.get("aprovadores") or [], "responsavel": ap.get("responsavel")})
    for case in await store.list_cases(limit=100000):
        if not migrate_case(case):
            continue
        changed += 1
        case["aguardando"] = pending.get(case["id"], [])
        requeue = case.get("status") in (NA_FILA, PROCESSANDO) and case.get("estagio") in ("audit", "verification")
        if requeue:
            # both stages only read and judge, so running them again is safe
            case["status"] = NA_FILA
            case["etapas"].setdefault(case["estagio"], {})["status"] = "NA_FILA"
        await store.save_case(case, publish=False)
        if requeue:
            # messages left in the old streams are ignored by the stage guard; queue again under the new name
            await store.enqueue(case["estagio"], case["id"])
    waiting = await store.r.hgetall(f"{P}:waiting_agent")
    for case_id, stage in waiting.items():
        await store.r.hset(f"{P}:waiting_agent", case_id, _stage(stage))
    ctl = await store.control()
    if any(b in LEGACY_STAGE_RENAMES for b in ctl.get("breakpoints") or []):
        ctl["breakpoints"] = [_stage(b) for b in ctl["breakpoints"]]
        await store.set_control(ctl)
    await store.r.delete(f"{P}:stream:plan_review")
    await store.r.set(AUDIT_BEFORE_EXECUTION, "concluida")
    return changed
