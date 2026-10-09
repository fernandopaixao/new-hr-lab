"""Production line: one handler per stage, approvals, debugging controls and the saga.

Each stage reads a case id from its Redis stream, does its work, records an
explanation in the case and in the audit log, and enqueues the next stage (or
parks the case waiting for a human or for the AI agent).
"""
from __future__ import annotations

import asyncio
import copy
import random
import traceback
from typing import Any

from . import agent, clock, engine, logbook as log, shelf
from .contracts import ContractRepo
from .engine import contract_ref
from .context import Ctx
from .domain import (
    AGUARDANDO_AGENTE, AGUARDANDO_APROVACAO, APPROVAL_AUDITORIA, APPROVAL_CONFERENCIA, APPROVAL_EXCECAO, APPROVAL_TYPE_LABELS,
    CANCELADO, CONCLUIDO, CONCLUIDO_COM_RESSALVAS, DUPLICADO, ERRO, FALHOU_COMPENSADO, FINAL_STATUSES, NA_FILA, NAO_ELEGIVEL,
    NEXT_STAGE, PARADO, PERSONAS, PROCESSANDO, REJEITADO, REJEITADO_NA_ENTRADA, REVERTIDO, STAGE_KEYS, STATUS_LABELS,
)
from .expr import ExpressionError, resolve_value, unwrap
from .store import P, Store, new_id, now_ms

WAITING_AGENT_SET = f"{P}:waiting_agent"
MAX_REPLANS = 3


class StageResult:
    def __init__(self, action: str, status: str | None = None, explanation: str = "", next_stage: str | None = None):
        self.action = action  # next | wait | final
        self.status = status
        self.explanation = explanation
        self.next_stage = next_stage


def _get_path(obj: dict, dotted: str) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


class Pipeline:
    def __init__(self, store: Store):
        self.store = store
        self.repo = ContractRepo(store)

    # ------------------------------------------------------------ submission
    async def submit_event(self, event: dict, *, cenario: str | None = None, depuracao: bool = False,
                           breakpoints: list[str] | None = None, pai_id: str | None = None) -> dict:
        event = dict(event)
        event.setdefault("id", new_id("evt"))
        event.setdefault("ocorrido_em", now_ms())
        event.setdefault("origem", "manual")
        event.setdefault("dados", {})
        if not event.get("data_efetiva"):
            event["data_efetiva"] = await clock.today(self.store)
        case = {
            "id": new_id("caso"), "criado_em": now_ms(), "evento": event, "evento_id": event["id"],
            "evento_tipo": event.get("tipo"), "colaborador_id": event.get("colaborador_id"),
            "colaborador_nome": (event.get("dados") or {}).get("nome"), "status": NA_FILA, "estagio": "intake",
            "estagio_parado": None, "depuracao": depuracao, "breakpoints": breakpoints or [], "liberado_para": None,
            "cenario": cenario or (event.get("metadados") or {}).get("cenario"), "pai_id": pai_id, "filhos": [],
            "etapas": {s: {"status": "PENDENTE"} for s in STAGE_KEYS}, "aprovacoes": [], "excecoes_aprovadas": [],
            "replanejamentos": 0, "resumo": "Evento recebido e enfileirado no gatilho.",
        }
        case["etapas"]["intake"]["status"] = "NA_FILA"
        if case["colaborador_id"]:
            emp = await self.store.get_employee(case["colaborador_id"])
            if emp:
                case["colaborador_nome"] = emp.get("nome")
        await self.store.save_case(case)
        await log.write(self.store, log.EVENTO_RECEBIDO, f"Evento {event.get('tipo')} recebido de {event.get('origem')}.",
                        case_id=case["id"], colaborador_id=case["colaborador_id"], estagio="intake", dados={"evento": event})
        await self.store.enqueue("intake", case["id"])
        return case

    # ------------------------------------------------------------ contexts
    async def build_ctx(self, case: dict, receipts: list[dict] | None = None) -> Ctx:
        when = str(case["evento"].get("data_efetiva"))[:10]
        employees = await self.store.list_employees()
        cpfs = {e.get("cpf") for e in employees if e.get("situacao") != "DESLIGADO" and e.get("id") != case.get("colaborador_id")}
        return Ctx(event=case["evento"], norma=await self.repo.norma(when), politica=await self.repo.politica(when),
                   cargos=await self.repo.cargos(when), cpfs_ativos=cpfs, receipts=receipts, employees={e["id"]: e for e in employees})

    async def processo(self, case: dict) -> dict | None:
        when = str(case["evento"].get("data_efetiva"))[:10]
        if case.get("processo_versao"):
            return await self.repo.get(case["processo_codigo"], version=case["processo_versao"])
        return await self.repo.processo_for_event(case["evento"].get("tipo"), when)

    def cargo_alvo(self, processo: dict, ctx: Ctx, emp: dict) -> str | None:
        spec = processo.get("cargo_alvo")
        if not spec:
            return emp.get("cargo") if emp else None
        try:
            return unwrap(resolve_value(spec, ctx.names(emp)))
        except ExpressionError:
            return None

    async def subject(self, case: dict, processo: dict) -> dict:
        """Current employee, or the candidate projection for admission."""
        if (processo.get("evento_schema") or {}).get("colaborador") == "NAO_DEVE_EXISTIR":
            dados = dict(case["evento"].get("dados") or {})
            dados["id"] = case["colaborador_id"]
            return shelf.new_employee_from_admission(dados, str(case["evento"]["data_efetiva"])[:10])
        return await self.store.get_employee(case["colaborador_id"]) or {}

    # ------------------------------------------------------------ dispatcher
    async def should_hold(self, case: dict, stage: str) -> bool:
        if case.get("liberado_para") == stage:
            return False
        ctl = await self.store.control()
        return bool(case.get("depuracao") or stage in (case.get("breakpoints") or []) or stage in ctl.get("breakpoints", []))

    async def run_stage(self, stage: str, case_id: str, worker: str = "worker", recovering: bool = False) -> None:
        case = await self.store.get_case(case_id)
        if not case or case.get("status") in FINAL_STATUSES:
            return
        # a worker that crashed mid-stage gets its pending message back on restart;
        # only then a case left PROCESSANDO by this same worker is resumed
        resumed = (recovering and case.get("estagio") == stage and case.get("status") == PROCESSANDO
                   and (case.get("etapas") or {}).get(stage, {}).get("worker") == worker)
        if resumed:
            await log.write(self.store, log.DEPURACAO, f"Estágio {stage} retomado após queda do worker {worker}.",
                            case_id=case_id, colaborador_id=case.get("colaborador_id"), estagio=stage)
        elif case.get("estagio") != stage or case.get("status") != NA_FILA:
            # stale message: the case moved on, waits for someone, or is being handled elsewhere
            return
        if await self.should_hold(case, stage):
            case.update({"status": PARADO, "estagio": stage, "estagio_parado": stage,
                         "resumo": f"Parado antes de '{stage}' para depuração. Use Avançar para continuar."})
            case["etapas"][stage]["status"] = "PARADO"
            await self.store.save_case(case)
            await log.write(self.store, log.DEPURACAO, f"Caso parado antes do estágio {stage} (ponto de parada).",
                            case_id=case_id, colaborador_id=case.get("colaborador_id"), estagio=stage)
            return
        case["liberado_para"] = None
        case.update({"status": PROCESSANDO, "estagio": stage, "estagio_parado": None})
        etapa = case["etapas"].setdefault(stage, {})
        etapa.update({"status": "PROCESSANDO", "inicio": now_ms(), "worker": worker})
        await self.store.save_case(case)
        settings = await self.store.settings()
        if settings["stage_delay_ms"] > 0:
            await asyncio.sleep(settings["stage_delay_ms"] / 1000)
        handler = getattr(self, f"stage_{stage}")
        try:
            result: StageResult = await handler(case)
        except agent.AgentUnavailable as exc:
            case = await self.store.get_case(case_id) or case
            case.update({"status": AGUARDANDO_AGENTE, "estagio": stage,
                         "resumo": f"Agente de IA indisponível ({exc}). O caso aguarda o provedor de IA voltar; o fallback heurístico está desligado."})
            case["etapas"][stage].update({"status": "AGUARDANDO", "aguardando": "agente"})
            await self.store.save_case(case)
            await self.store.r.hset(WAITING_AGENT_SET, case_id, stage)
            await log.write(self.store, log.AGENTE_INDISPONIVEL, case["resumo"], case_id=case_id,
                            colaborador_id=case.get("colaborador_id"), estagio=stage, dados={"erro": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            case = await self.store.get_case(case_id) or case
            tb = traceback.format_exc(limit=6)
            case.update({"status": ERRO, "resumo": f"Erro inesperado no estágio {stage}: {exc}", "erro": tb})
            case["etapas"][stage].update({"status": "ERRO", "fim": now_ms()})
            await self.store.save_case(case)
            await log.write(self.store, log.DECISAO_FINAL, case["resumo"], case_id=case_id, colaborador_id=case.get("colaborador_id"),
                            estagio=stage, dados={"traceback": tb})
            return
        await self.apply_result(case_id, stage, result)

    async def apply_result(self, case_id: str, stage: str, result: StageResult) -> None:
        case = await self.store.get_case(case_id)
        etapa = case["etapas"].setdefault(stage, {})
        etapa["fim"] = now_ms()
        if etapa.get("inicio"):
            etapa["duracao_ms"] = etapa["fim"] - etapa["inicio"]
        etapa["resumo"] = result.explanation
        if result.action == "next":
            nxt = result.next_stage or NEXT_STAGE[stage]
            etapa["status"] = "OK"
            if nxt is None:
                return
            case["etapas"].setdefault(nxt, {})["status"] = "NA_FILA"
            case.update({"status": NA_FILA, "estagio": nxt, "resumo": result.explanation})
            await self.store.save_case(case)
            await self.store.enqueue(nxt, case_id)
        elif result.action == "wait":
            etapa["status"] = "AGUARDANDO"
            case.update({"status": result.status, "resumo": result.explanation})
            await self.store.save_case(case)
        else:
            etapa["status"] = "OK" if result.status in (CONCLUIDO, CONCLUIDO_COM_RESSALVAS) else "FALHA"
            case.update({"status": result.status, "resumo": result.explanation, "finalizado_em": now_ms(),
                         "decisao_final": {"status": result.status, "rotulo": STATUS_LABELS.get(result.status), "explicacao": result.explanation}})
            await self.store.save_case(case)
            await log.write(self.store, log.DECISAO_FINAL, f"{STATUS_LABELS.get(result.status)}: {result.explanation}",
                            case_id=case_id, colaborador_id=case.get("colaborador_id"), estagio=stage, dados={"status": result.status})

    # ------------------------------------------------------------ stages
    async def stage_intake(self, case: dict) -> StageResult:
        ev = case["evento"]
        cid = case["id"]
        if not ev.get("tipo"):
            return StageResult("final", REJEITADO_NA_ENTRADA, "Evento sem tipo; não é possível identificar o processo.")
        existing = await self.store.claim_event_id(ev["id"], cid)
        if existing and existing != cid:
            await log.write(self.store, log.EVENTO_DUPLICADO, f"Evento {ev['id']} já processado no caso {existing}; ignorado (idempotência).",
                            case_id=cid, colaborador_id=case.get("colaborador_id"), estagio="intake", dados={"caso_original": existing})
            case["caso_original"] = existing
            await self.store.save_case(case)
            return StageResult("final", DUPLICADO, f"Evento duplicado: o mesmo id já foi processado no caso {existing}.")
        processo = await self.processo(case)
        if not processo:
            return StageResult("final", REJEITADO_NA_ENTRADA,
                               f"Não há contrato de processo vigente para o evento {ev['tipo']} na data {ev.get('data_efetiva')}.")
        case.update({"processo": contract_ref(processo), "processo_codigo": processo["codigo"], "processo_versao": processo.get("versao"),
                     "processo_nome": processo.get("nome")})
        schema = processo.get("evento_schema") or {}
        faltando = [f for f in schema.get("obrigatorios") or [] if _get_path(ev, f) in (None, "")]
        if faltando:
            await self.store.save_case(case)
            await log.write(self.store, log.EVENTO_REJEITADO, f"Campos obrigatórios ausentes: {', '.join(faltando)}.", case_id=cid, estagio="intake")
            return StageResult("final", REJEITADO_NA_ENTRADA,
                               f"Evento inválido para {processo['codigo']}: campos obrigatórios ausentes ({', '.join(faltando)}).")
        modo = schema.get("colaborador", "DEVE_EXISTIR")
        if modo == "DEVE_EXISTIR":
            emp = await self.store.get_employee(ev.get("colaborador_id") or "")
            if not emp:
                await self.store.save_case(case)
                return StageResult("final", REJEITADO_NA_ENTRADA, f"Colaborador {ev.get('colaborador_id')} não encontrado no cadastro.")
            case["colaborador_nome"] = emp.get("nome")
        elif modo == "NAO_DEVE_EXISTIR":
            if not ev.get("colaborador_id"):
                ev["colaborador_id"] = await self.next_employee_id()
                case["colaborador_id"] = ev["colaborador_id"]
            elif await self.store.get_employee(ev["colaborador_id"]):
                await self.store.save_case(case)
                return StageResult("final", REJEITADO_NA_ENTRADA, f"Matrícula {ev['colaborador_id']} já existe; admissão exige matrícula nova.")
            case["colaborador_id"] = ev["colaborador_id"]
            case["colaborador_nome"] = (ev.get("dados") or {}).get("nome")
        await self.store.save_case(case)
        if processo.get("coletivo"):
            return await self.fan_out(case, processo)
        return StageResult("next", explanation=f"Evento válido para o processo {contract_ref(processo)}; segue para elegibilidade.")

    async def next_employee_id(self) -> str:
        n = await self.store.r.incr(f"{P}:seq:employee")
        existing = await self.store.r.smembers(f"{P}:employees")
        nums = [int(x[1:]) for x in existing if x[1:].isdigit()]
        base = max(nums) if nums else 0
        if n <= base:
            n = base + 1
            await self.store.r.set(f"{P}:seq:employee", n)
        return f"F{n:05d}"

    async def fan_out(self, case: dict, processo: dict) -> StageResult:
        col = processo["coletivo"]
        ctx = await self.build_ctx(case)
        children = []
        for emp in await self.store.list_employees():
            names = ctx.names(emp)
            try:
                selected = bool(resolve_value("=" + col["selecao"], names))
            except ExpressionError:
                selected = False
            if not selected:
                continue
            dados = unwrap(resolve_value(col.get("dados") or {}, names))
            child_event = {"id": f"{case['evento']['id']}:{emp['id']}", "tipo": col["gera_evento"], "colaborador_id": emp["id"],
                           "data_efetiva": case["evento"]["data_efetiva"], "origem": f"coletivo:{case['id']}", "dados": dados,
                           "correlacao_id": case["evento"]["id"]}
            child = await self.submit_event(child_event, cenario=case.get("cenario"), pai_id=case["id"],
                                            depuracao=False, breakpoints=case.get("breakpoints"))
            children.append(child["id"])
        case = await self.store.get_case(case["id"])
        case["filhos"] = children
        await self.store.save_case(case)
        return StageResult("final", CONCLUIDO, f"Evento coletivo desdobrado em {len(children)} caso(s) individuais ({col['gera_evento']}).")

    async def stage_eligibility(self, case: dict) -> StageResult:
        processo = await self.processo(case)
        ctx = await self.build_ctx(case)
        emp = await self.subject(case, processo)
        alvo = self.cargo_alvo(processo, ctx, emp)
        el = engine.eligibility(processo, ctx, emp, alvo)
        case = await self.store.get_case(case["id"])
        case.update({"elegibilidade": el, "cargo_alvo": alvo})
        await self.store.save_case(case)
        for r in el["regras"]:
            if not r["passou"]:
                await log.write(self.store, log.REGRA, f"[{r['tipo']}] {r['id']} não atendida: {r['explicacao']}", case_id=case["id"],
                                colaborador_id=case.get("colaborador_id"), estagio="eligibility", dados=r)
        await log.write(self.store, log.ELEGIBILIDADE, el["explicacao"], case_id=case["id"], colaborador_id=case.get("colaborador_id"),
                        estagio="eligibility", dados={"decisao": el["decisao"], "resumo": el["resumo"], "regras": el["regras"]})
        if el["decisao"] == "NAO_ELEGIVEL":
            return StageResult("final", NAO_ELEGIVEL, el["explicacao"])
        if el["decisao"] == "EXCECAO_NECESSARIA":
            rules = [r for r in el["regras"] if not r["passou"] and r["tipo"] == "EXCECIONAVEL"]
            for r in rules:
                await self.request_approval(case["id"], APPROVAL_EXCECAO, r["aprovadores"], r["explicacao"], stage="eligibility",
                                            regra=r)
            return StageResult("wait", AGUARDANDO_APROVACAO,
                               f"Aguardando {len(rules)} aprovação(ões) de exceção: " + "; ".join(f"{r['id']} por {'/'.join(r['aprovadores'])}" for r in rules))
        return StageResult("next", explanation=el["explicacao"])

    async def stage_planning(self, case: dict) -> StageResult:
        processo = await self.processo(case)
        ctx = await self.build_ctx(case)
        is_admission = (processo.get("evento_schema") or {}).get("colaborador") == "NAO_DEVE_EXISTIR"
        emp = {} if is_admission else (await self.store.get_employee(case["colaborador_id"]) or {})
        subject = await self.subject(case, processo) if is_admission else emp
        alvo = case.get("cargo_alvo") or self.cargo_alvo(processo, ctx, subject)
        plano = engine.plan(processo, ctx, emp, alvo)
        case = await self.store.get_case(case["id"])
        case.update({"plano": plano, "estado_inicial": emp, "versao_colaborador": emp.get("versao", 0)})
        await self.store.save_case(case)
        for item in plano["operacoes"]:
            await log.write(self.store, log.OPERACAO_ESCOLHIDA,
                            f"{item['seq']}. {item['operacao']} escolhida ({'processo' if item['origem'] == 'PROCESSO' else 'derivada do contrato'}): {item['motivo']}",
                            case_id=case["id"], colaborador_id=case.get("colaborador_id"), estagio="planning", dados=item)
        for item in plano["descartadas"]:
            await log.write(self.store, log.OPERACAO_DESCARTADA, f"{item['operacao']} descartada: {item['motivo_descarte']}",
                            case_id=case["id"], colaborador_id=case.get("colaborador_id"), estagio="planning", dados=item)
        await log.write(self.store, log.PLANO, plano["resumo"], case_id=case["id"], colaborador_id=case.get("colaborador_id"),
                        estagio="planning", dados={"problemas": plano["problemas"], "estado_alvo": plano["estado_alvo"]})
        return StageResult("next", explanation=plano["resumo"])

    async def stage_audit(self, case: dict) -> StageResult:
        """Audit before execution: the gate every plan must pass before any system is touched."""
        processo = await self.processo(case)
        ctx = await self.build_ctx(case)
        plano = case["plano"]
        result = engine.audit_plan(processo, ctx, case.get("estado_inicial") or {}, plano["projetado"], plano, case.get("cargo_alvo"))
        # rules already released by an approved exception (in eligibility) do not ask twice
        liberadas = {e.get("regra_id") for e in case.get("excecoes_aprovadas") or []}
        case["auditoria"] = result
        await self.store.save_case(case)
        for r in result["regras"]:
            if not r["passou"]:
                await log.write(self.store, log.REGRA, f"Auditoria: [{r['tipo']}] {r['id']}: {r['explicacao']}", case_id=case["id"],
                                colaborador_id=case.get("colaborador_id"), estagio="audit", dados=r)
        review = await agent.review(self.store, "AUDITORIA", case, processo, ctx.cargo(case.get("cargo_alvo")))
        case = await self.store.get_case(case["id"])
        case["auditoria"] = result
        case["agente_auditoria"] = review
        case["recomendacao_auditoria"] = review["recomendacao"]
        await self.store.save_case(case)
        await log.write(self.store, log.AGENTE, f"Agente ({review.get('agente')}) recomenda {review['recomendacao']} o plano: {review.get('resumo')}",
                        ator=f"agente:{review.get('modelo')}", case_id=case["id"], colaborador_id=case.get("colaborador_id"), estagio="audit",
                        dados={k: v for k, v in review.items() if k != "prompt"})
        await log.write(self.store, log.AUDITORIA, f"Auditoria antes da execução: {result['decisao']}.", case_id=case["id"],
                        colaborador_id=case.get("colaborador_id"), estagio="audit", dados={"resumo": result["resumo"]})
        settings = await self.store.settings()
        if result["decisao"] == "REPROVADO":
            bloq = [r for r in result["regras"] if not r["passou"] and r["tipo"] == "BLOQUEANTE"]
            return StageResult("final", REJEITADO, "Auditoria reprovou o plano antes da execução; nenhum sistema foi alterado. " +
                               " ".join(r["explicacao"] for r in bloq) + f" Recomendação do agente: {review['recomendacao']}.")
        pending = 0
        for r in [r for r in result["regras"] if not r["passou"] and r["tipo"] == "EXCECIONAVEL" and r["id"] not in liberadas]:
            await self.request_approval(case["id"], APPROVAL_EXCECAO, r["aprovadores"], r["explicacao"], stage="audit", regra=r,
                                        recomendacao=review)
            pending += 1
        if review["recomendacao"] == "REPROVADO" or settings["human_review_mode"] == "SEMPRE":
            motivo = (f"Agente recomenda REPROVADO: {review.get('resumo')}" if review["recomendacao"] == "REPROVADO"
                      else f"Revisão humana obrigatória (modo SEMPRE). Agente recomenda {review['recomendacao']}: {review.get('resumo')}")
            await self.request_approval(case["id"], APPROVAL_AUDITORIA, ["AUDITORIA", "COMPLIANCE"], motivo, stage="audit", recomendacao=review)
            pending += 1
        if pending:
            return StageResult("wait", AGUARDANDO_APROVACAO, f"Auditoria aguarda {pending} decisão(ões) humana(s) antes da execução. "
                                                             f"Recomendação do agente: {review['recomendacao']}.")
        return StageResult("next", explanation=f"Plano auditado e liberado para execução: regras atendidas"
                                               f"{' com ressalvas' if result['decisao'] == 'APROVADO_COM_RESSALVAS' else ''} e agente recomenda "
                                               f"{review['recomendacao']} (confiança {review.get('confianca')}).")

    async def stage_execution(self, case: dict) -> StageResult:
        processo = await self.processo(case)
        is_admission = (processo.get("evento_schema") or {}).get("colaborador") == "NAO_DEVE_EXISTIR"
        emp_id = case["colaborador_id"]
        settings = await self.store.settings()
        ctx = await self.build_ctx(case)
        ectx = shelf.ExecCtx(hoje=ctx.today, norma=dict(ctx.norma.get("parametros") or {}), case_id=case["id"])
        simular = (case["evento"].get("dados") or {}).get("simular_falha_em")
        async with self.store.employee_lock(emp_id):
            emp = await self.store.get_employee(emp_id) or {}
            if not is_admission and int(emp.get("versao", 0)) != int(case.get("versao_colaborador", 0)):
                case["replanejamentos"] = int(case.get("replanejamentos", 0)) + 1
                await self.store.save_case(case)
                msg = (f"O colaborador mudou desde o planejamento (versão {case.get('versao_colaborador')} para {emp.get('versao')}); "
                       f"o plano foi descartado e o caso volta ao planejamento ({case['replanejamentos']}/{MAX_REPLANS}).")
                await log.write(self.store, log.REPLANEJAMENTO, msg, case_id=case["id"], colaborador_id=emp_id, estagio="execution")
                if case["replanejamentos"] > MAX_REPLANS:
                    return StageResult("final", ERRO, "Limite de replanejamentos atingido por concorrência no mesmo colaborador.")
                for s in ("planning", "audit", "execution"):
                    case["etapas"][s] = {"status": "PENDENTE"}
                await self.store.save_case(case)
                return StageResult("next", explanation=msg, next_stage="planning")
            if is_admission and emp:
                return StageResult("final", REJEITADO, f"Matrícula {emp_id} foi criada por outro caso durante o processamento.")
            anterior = copy.deepcopy(emp)
            recibos: list[dict] = []
            snapshots: list[dict] = []
            ops = case["plano"]["operacoes"]
            per_op_delay = settings["stage_delay_ms"] / 1000 / 3
            failure: str | None = None
            for item in ops:
                spec = shelf.SHELF[item["operacao"]]
                recibo = {"id": item["id"], "seq": item["seq"], "operacao": item["operacao"], "sistema": spec.sistema,
                          "parametros": item["parametros"], "inicio": now_ms()}
                try:
                    if simular and simular in (item["operacao"], spec.sistema):
                        raise shelf.OperationError(f"falha simulada no sistema {spec.sistema} (evento pediu simular_falha_em={simular})")
                    if settings["failure_rate_percent"] > 0 and random.random() * 100 < settings["failure_rate_percent"]:
                        raise shelf.OperationError(f"falha aleatória injetada no sistema {spec.sistema} ({settings['failure_rate_percent']}%)")
                    before = copy.deepcopy(emp)
                    descricao, snap = shelf.apply(item["operacao"], emp, item["parametros"], ectx)
                    if emp:
                        emp = await self.store.save_employee(emp)
                    recibo.update({"status": "EXECUTADA", "descricao": descricao, "protocolo": f"{spec.sistema[:3]}-{new_id('p')[2:]}".upper(),
                                   "fim": now_ms(), "alteracoes": engine.state_diff(before, emp)})
                    snapshots.append({"seq": item["seq"], "operacao": item["operacao"], "snapshot": snap, "compensavel": spec.compensavel})
                    recibos.append(recibo)
                    await log.write(self.store, log.OPERACAO_EXECUTADA, f"{item['seq']}. {item['operacao']} em {spec.sistema}: {descricao}",
                                    case_id=case["id"], colaborador_id=emp_id, estagio="execution",
                                    dados={"recibo": recibo, "motivo": item.get("motivo")})
                except Exception as exc:  # noqa: BLE001
                    recibo.update({"status": "FALHOU", "erro": str(exc), "fim": now_ms()})
                    recibos.append(recibo)
                    failure = f"{item['operacao']} falhou: {exc}"
                    await log.write(self.store, log.OPERACAO_FALHOU, f"{item['seq']}. {failure}", case_id=case["id"], colaborador_id=emp_id,
                                    estagio="execution", dados={"recibo": recibo})
                    break
                case_live = await self.store.get_case(case["id"])
                case_live["execucao"] = {"recibos": recibos, "em_andamento": True}
                await self.store.save_case(case_live)
                if per_op_delay > 0:
                    await asyncio.sleep(per_op_delay)
            if failure:
                emp = await self.compensate(case["id"], emp_id, emp, snapshots, recibos, motivo=failure)
                case = await self.store.get_case(case["id"])
                case["execucao"] = {"recibos": recibos, "snapshots": snapshots, "falha": failure, "diff": engine.state_diff(anterior, emp)}
                case["estado_final"] = emp
                await self.store.save_case(case)
                return StageResult("final", FALHOU_COMPENSADO,
                                   f"{failure}. Saga compensou {sum(1 for r in recibos if r['status'] == 'COMPENSADA')} operação(ões) já aplicada(s) "
                                   f"e o colaborador voltou ao estado anterior.")
        case = await self.store.get_case(case["id"])
        case["execucao"] = {"recibos": recibos, "snapshots": snapshots, "diff": engine.state_diff(anterior, emp)}
        case["estado_final"] = emp
        if is_admission:
            case["estado_inicial"] = {}
        await self.store.save_case(case)
        return StageResult("next", explanation=f"{len(recibos)} operação(ões) executada(s) com recibo; segue para a conferência final.")

    async def compensate(self, case_id: str, emp_id: str, emp: dict, snapshots: list[dict], recibos: list[dict], motivo: str) -> dict:
        for snap in reversed(snapshots):
            recibo = next((r for r in recibos if r["seq"] == snap["seq"]), None)
            if not snap.get("compensavel"):
                if recibo:
                    recibo["status"] = "NAO_COMPENSAVEL"
                await log.write(self.store, log.COMPENSACAO, f"{snap['operacao']} não é compensável (ex.: comunicação enviada); registrada para tratamento manual.",
                                case_id=case_id, colaborador_id=emp_id, estagio="execution")
                continue
            shelf.compensate(emp, snap["snapshot"])
            if recibo:
                recibo["status"] = "COMPENSADA"
            await log.write(self.store, log.COMPENSACAO, f"Compensação de {snap['operacao']}: campos restaurados ({motivo}).",
                            case_id=case_id, colaborador_id=emp_id, estagio="execution", dados={"campos": list(snap["snapshot"].keys())})
        if emp:
            emp = await self.store.save_employee(emp)
        else:
            await self.store.r.delete(f"{P}:employee:{emp_id}")
            await self.store.r.srem(f"{P}:employees", emp_id)
        return emp

    async def stage_verification(self, case: dict) -> StageResult:
        """Final check after execution: receipts for every operation and final state equal to the audited one."""
        processo = await self.processo(case)
        recibos = (case.get("execucao") or {}).get("recibos") or []
        # check the state produced by this case's execution; later changes by other cases are reported, not blamed
        final = case.get("estado_final") or {}
        current = await self.store.get_employee(case["colaborador_id"]) or {}
        result = engine.verify_execution(case["plano"]["projetado"], final, recibos)
        if current and int(current.get("versao", 0)) != int(final.get("versao", 0)):
            result["regras"].append({"id": "FIN-CONCORRENCIA", "descricao": "Colaborador alterado por outro caso após esta execução", "tipo": "ALERTA",
                                     "origem": "motor", "passou": False, "aprovadores": [],
                                     "explicacao": f"O cadastro mudou da versão {final.get('versao')} para {current.get('versao')} depois desta execução; "
                                                   "a conferência considerou o estado produzido por este caso."})
            if result["decisao"] == "APROVADO":
                result["decisao"] = "APROVADO_COM_RESSALVAS"
        case["conferencia_final"] = result
        await self.store.save_case(case)
        for r in result["regras"]:
            if not r["passou"]:
                await log.write(self.store, log.REGRA, f"Conferência final: [{r['tipo']}] {r['id']}: {r['explicacao']}", case_id=case["id"],
                                colaborador_id=case.get("colaborador_id"), estagio="verification", dados=r)
        review = await agent.review(self.store, "CONFERENCIA", case, processo)
        case = await self.store.get_case(case["id"])
        case["conferencia_final"] = result
        case["agente_conferencia"] = review
        case["recomendacao_conferencia"] = review["recomendacao"]
        await self.store.save_case(case)
        await log.write(self.store, log.AGENTE, f"Agente ({review.get('agente')}) recomenda {review['recomendacao']} a execução: {review.get('resumo')}",
                        ator=f"agente:{review.get('modelo')}", case_id=case["id"], colaborador_id=case.get("colaborador_id"), estagio="verification",
                        dados={k: v for k, v in review.items() if k != "prompt"})
        await log.write(self.store, log.AUDITORIA, f"Conferência final: {result['decisao']}.", case_id=case["id"],
                        colaborador_id=case.get("colaborador_id"), estagio="verification",
                        dados={"resumo": result["resumo"], "divergencias": result["divergencias"]})
        settings = await self.store.settings()
        if result["decisao"] == "REPROVADO" or review["recomendacao"] == "REPROVADO" or settings["human_review_mode"] == "SEMPRE":
            falhas = [r["explicacao"] for r in result["regras"] if not r["passou"] and r["tipo"] == "BLOQUEANTE"]
            motivo = f"Conferência final {result['decisao']}; agente recomenda {review['recomendacao']}: {review.get('resumo')}"
            if falhas:
                motivo += " Falhas: " + " ".join(falhas)
            await self.request_approval(case["id"], APPROVAL_CONFERENCIA, ["AUDITORIA"], motivo, stage="verification", recomendacao=review)
            return StageResult("wait", AGUARDANDO_APROVACAO, "Execução aguarda decisão da auditoria interna. Rejeitar reverte todas as operações.")
        ressalvas = [r["explicacao"] for r in result["regras"] if not r["passou"]]
        # alerts and exceptions accepted in the audit stay visible as reservations on the final result
        ressalvas += [f"Auditoria: {r['explicacao']}" for r in (case.get("auditoria") or {}).get("regras") or []
                      if not r["passou"] and r["tipo"] != "BLOQUEANTE"]
        if ressalvas:
            return StageResult("final", CONCLUIDO_COM_RESSALVAS, "Execução igual à auditada, com ressalvas: " + " ".join(ressalvas))
        return StageResult("final", CONCLUIDO, f"Execução igual à auditada e com recibos; agente recomenda {review['recomendacao']}.")

    # ------------------------------------------------------------ approvals
    async def direct_manager(self, case: dict) -> dict | None:
        """The real person behind the GESTOR persona for this case: the employee's direct manager.

        Admissions have no record yet, so the manager informed in the event or the head of the unit is used.
        """
        ctx = await self.build_ctx(case)
        emp = ctx.employees.get(case.get("colaborador_id") or "") or {}
        dados = case["evento"].get("dados") or {}
        gid = emp.get("gestor_id") or dados.get("gestor_id") or (None if emp else ctx.unit_manager(dados.get("unidade")))
        gestor = ctx.employees.get(gid or "")
        if not gestor:
            return None
        return {"id": gestor["id"], "nome": gestor.get("nome"), "cargo": gestor.get("cargo"), "unidade": gestor.get("unidade"),
                "situacao": gestor.get("situacao")}

    async def request_approval(self, case_id: str, tipo: str, aprovadores: list[str], explicacao: str, *, stage: str,
                               regra: dict | None = None, recomendacao: dict | None = None) -> dict:
        case = await self.store.get_case(case_id)
        responsavel = await self.direct_manager(case) if "GESTOR" in aprovadores else None
        ap = {
            "id": new_id("apr"), "case_id": case_id, "tipo": tipo, "tipo_rotulo": APPROVAL_TYPE_LABELS[tipo], "estagio": stage,
            "aprovadores": aprovadores, "responsavel": responsavel, "status": "PENDENTE", "explicacao": explicacao, "criado_em": now_ms(),
            "regra": regra, "recomendacao_agente": {k: v for k, v in (recomendacao or {}).items() if k in ("recomendacao", "confianca", "resumo", "achados", "justificativa", "agente", "modelo")} or None,
            "colaborador_id": case.get("colaborador_id"), "colaborador_nome": case.get("colaborador_nome"), "evento_tipo": case.get("evento_tipo"),
        }
        await self.store.save_approval(ap)
        case["aprovacoes"] = (case.get("aprovacoes") or []) + [ap["id"]]
        case["aguardando"] = (case.get("aguardando") or []) + [
            {"id": ap["id"], "tipo_rotulo": ap["tipo_rotulo"], "aprovadores": aprovadores, "responsavel": responsavel}]
        await self.store.save_case(case)
        quem = "/".join(aprovadores) + (f" ({responsavel['nome']}, gestor imediato)" if responsavel else "")
        await log.write(self.store, log.APROVACAO_SOLICITADA, f"{ap['tipo_rotulo']} solicitada a {quem}: {explicacao}",
                        case_id=case_id, colaborador_id=case.get("colaborador_id"), estagio=stage, dados={"aprovacao": ap["id"], "regra": (regra or {}).get("id")})
        return ap

    async def decide(self, ap_id: str, persona: str, decisao: str, justificativa: str) -> dict:
        ap = await self.store.get_approval(ap_id)
        if not ap:
            raise ValueError("aprovação não encontrada")
        if ap["status"] != "PENDENTE":
            raise ValueError(f"aprovação já decidida ({ap['status']})")
        if persona not in ap["aprovadores"]:
            raise PermissionError(f"a persona {persona} não pode decidir; aprovadores: {', '.join(ap['aprovadores'])}")
        if decisao not in ("APROVAR", "REJEITAR"):
            raise ValueError("decisão deve ser APROVAR ou REJEITAR")
        if len((justificativa or "").strip()) < 5:
            raise ValueError("justificativa obrigatória (mínimo 5 caracteres)")
        ap.update({"status": "APROVADA" if decisao == "APROVAR" else "REJEITADA", "decidido_por": {"persona": persona, **PERSONAS.get(persona, {})},
                   "justificativa": justificativa.strip(), "decidido_em": now_ms()})
        await self.store.save_approval(ap)
        case = await self.store.get_case(ap["case_id"])
        case["aguardando"] = [a for a in case.get("aguardando") or [] if a.get("id") != ap_id]
        if ap["status"] == "APROVADA" and ap["tipo"] == APPROVAL_EXCECAO:
            case["excecoes_aprovadas"] = (case.get("excecoes_aprovadas") or []) + [
                {"regra_id": (ap.get("regra") or {}).get("id"), "aprovacao": ap_id, "por": persona, "justificativa": ap["justificativa"]}]
        await self.store.save_case(case)
        await log.write(self.store, log.APROVACAO_DECIDIDA,
                        f"{ap['tipo_rotulo']} {ap['status'].lower()} por {PERSONAS.get(persona, {}).get('pessoa')} ({persona}): {ap['justificativa']}",
                        ator=f"persona:{persona}", case_id=ap["case_id"], colaborador_id=ap.get("colaborador_id"), estagio=ap["estagio"],
                        dados={"aprovacao": ap})
        await self._after_decision(ap)
        return ap

    async def _after_decision(self, ap: dict) -> None:
        case = await self.store.get_case(ap["case_id"])
        if case.get("status") in FINAL_STATUSES:
            return
        same_stage = [await self.store.get_approval(i) for i in case.get("aprovacoes") or []]
        same_stage = [a for a in same_stage if a and a["estagio"] == ap["estagio"]]
        if ap["status"] == "REJEITADA":
            for other in same_stage:
                if other["status"] == "PENDENTE":
                    other.update({"status": "CANCELADA", "decidido_em": now_ms(), "justificativa": "Cancelada: outra decisão do caso foi rejeitada."})
                    await self.store.save_approval(other)
            if ap["tipo"] == APPROVAL_CONFERENCIA:
                await self.revert_after_verification(case, ap)
                return
            await self.apply_result(case["id"], ap["estagio"], StageResult(
                "final", REJEITADO, f"{ap['tipo_rotulo']} rejeitada por {ap['decidido_por'].get('pessoa')} ({ap['decidido_por']['persona']}): {ap['justificativa']}"))
            return
        if any(a["status"] == "PENDENTE" for a in same_stage):
            await self.store.save_case(case)
            return
        if ap["tipo"] == APPROVAL_CONFERENCIA:
            had_issue = (case.get("conferencia_final") or {}).get("decisao") != "APROVADO" or case.get("recomendacao_conferencia") == "REPROVADO"
            status = CONCLUIDO_COM_RESSALVAS if had_issue else CONCLUIDO
            await self.apply_result(case["id"], "verification", StageResult(
                "final", status, f"Execução aceita pela auditoria interna ({ap['decidido_por'].get('pessoa')}): {ap['justificativa']}"))
            return
        await self.apply_result(case["id"], ap["estagio"], StageResult(
            "next", explanation=f"Todas as decisões humanas do estágio foram aprovadas; última por {ap['decidido_por'].get('pessoa')}."))

    async def revert_after_verification(self, case: dict, ap: dict) -> None:
        emp_id = case["colaborador_id"]
        snapshots = (case.get("execucao") or {}).get("snapshots") or []
        recibos = (case.get("execucao") or {}).get("recibos") or []
        async with self.store.employee_lock(emp_id):
            emp = await self.store.get_employee(emp_id) or {}
            emp = await self.compensate(case["id"], emp_id, emp, snapshots, recibos, motivo="conferência final rejeitada")
        case = await self.store.get_case(case["id"])
        case["execucao"]["recibos"] = recibos
        case["estado_final"] = emp
        await self.store.save_case(case)
        await self.apply_result(case["id"], "verification", StageResult(
            "final", REVERTIDO, f"A auditoria interna rejeitou a execução na conferência final ({ap['decidido_por'].get('pessoa')}: {ap['justificativa']}); operações compensadas."))

    # ------------------------------------------------------------ debug controls
    async def release(self, case_id: str, *, continuar: bool = False, actor: str = "OPERADOR") -> dict:
        case = await self.store.get_case(case_id)
        if not case or case.get("status") != PARADO:
            raise ValueError("o caso não está parado")
        stage = case["estagio_parado"]
        case["liberado_para"] = stage
        if continuar:
            case["depuracao"] = False
            case["breakpoints"] = []
        case.update({"status": NA_FILA, "estagio": stage, "estagio_parado": None, "resumo": f"Liberado para executar '{stage}'."})
        case["etapas"][stage]["status"] = "NA_FILA"
        await self.store.save_case(case)
        await log.write(self.store, log.DEPURACAO, f"Caso liberado para o estágio {stage}{' e modo passo a passo desligado' if continuar else ''}.",
                        ator=f"persona:{actor}", case_id=case_id, colaborador_id=case.get("colaborador_id"), estagio=stage)
        await self.store.enqueue(stage, case_id)
        return case

    async def retry_from(self, case_id: str, stage: str, *, event_patch: dict | None = None, depuracao: bool | None = None,
                         actor: str = "OPERADOR") -> dict:
        """Debug: re-run a case from a given stage, optionally editing the event."""
        case = await self.store.get_case(case_id)
        if not case:
            raise ValueError("caso não encontrado")
        if stage not in STAGE_KEYS:
            raise ValueError("estágio inválido")
        if case.get("status") in (PROCESSANDO,):
            raise ValueError("o caso está sendo processado; aguarde")
        if case.get("status") in FINAL_STATUSES and STAGE_KEYS.index(stage) >= STAGE_KEYS.index("execution") and case.get("execucao"):
            raise ValueError("a execução já ocorreu; reprocesse antes da execução ou gere um novo evento")
        if event_patch:
            case["evento"] = event_patch
            case["evento_tipo"] = event_patch.get("tipo")
            if stage == "intake":
                await self.store.r.delete(f"{P}:event:{case['evento']['id']}")
        for i, s in enumerate(STAGE_KEYS):
            if i >= STAGE_KEYS.index(stage):
                case["etapas"][s] = {"status": "PENDENTE"}
        for ap_id in case.get("aprovacoes") or []:
            ap = await self.store.get_approval(ap_id)
            if ap and ap["status"] == "PENDENTE":
                ap.update({"status": "CANCELADA", "decidido_em": now_ms(), "justificativa": "Cancelada por reprocessamento."})
                await self.store.save_approval(ap)
        if stage == "intake":
            await self.store.r.delete(f"{P}:event:{case['evento']['id']}")
        if depuracao is not None:
            case["depuracao"] = depuracao
        case["etapas"][stage]["status"] = "NA_FILA"
        case.update({"status": NA_FILA, "estagio": stage, "estagio_parado": None, "liberado_para": None, "decisao_final": None,
                     "aguardando": [], "resumo": f"Reprocessando a partir de '{stage}'."})
        await self.store.r.hdel(WAITING_AGENT_SET, case_id)
        await self.store.save_case(case)
        await log.write(self.store, log.DEPURACAO, f"Caso reprocessado a partir de {stage}{' com evento editado' if event_patch else ''}.",
                        ator=f"persona:{actor}", case_id=case_id, colaborador_id=case.get("colaborador_id"), estagio=stage,
                        dados={"evento": event_patch} if event_patch else None)
        await self.store.enqueue(stage, case_id)
        return case

    async def cancel(self, case_id: str, actor: str = "OPERADOR") -> dict:
        case = await self.store.get_case(case_id)
        if not case:
            raise ValueError("caso não encontrado")
        if case.get("status") in FINAL_STATUSES:
            raise ValueError("caso já finalizado")
        if case.get("etapas", {}).get("execution", {}).get("status") in ("OK", "PROCESSANDO"):
            raise ValueError("a execução já ocorreu; use a conferência final para reverter")
        for ap_id in case.get("aprovacoes") or []:
            ap = await self.store.get_approval(ap_id)
            if ap and ap["status"] == "PENDENTE":
                ap.update({"status": "CANCELADA", "decidido_em": now_ms(), "justificativa": "Caso cancelado."})
                await self.store.save_approval(ap)
        await self.store.r.hdel(WAITING_AGENT_SET, case_id)
        await self.apply_result(case_id, case.get("estagio") or "intake", StageResult("final", CANCELADO, f"Caso cancelado por {actor}."))
        return await self.store.get_case(case_id)

    async def requeue_waiting_agent(self) -> int:
        waiting = await self.store.r.hgetall(WAITING_AGENT_SET)
        for case_id, stage in waiting.items():
            await self.store.r.hdel(WAITING_AGENT_SET, case_id)
            case = await self.store.get_case(case_id)
            if not case or case.get("status") != AGUARDANDO_AGENTE:
                continue
            case.update({"status": NA_FILA, "resumo": "Agente disponível novamente; caso retomado."})
            case["etapas"][stage]["status"] = "NA_FILA"
            await self.store.save_case(case)
            await self.store.enqueue(stage, case_id)
        return len(waiting)
