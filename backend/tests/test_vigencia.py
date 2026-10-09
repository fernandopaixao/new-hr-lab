"""Events with a validity period: the high-potential program, its agenda and the simulated clock."""
import asyncio
import copy
import random

import pytest

from hrlab import clock, engine, shelf, vigencia
from hrlab.context import add_months
from hrlab.generators.events import GenCtx, build

from .conftest import TODAY

INCLUSAO = "colaborador.programa_alto_potencial_iniciado"
FIM = add_months(TODAY, 12)


def run_process(seeds, make_ctx, team, emp, event):
    """Eligibility, plan, audit and execution of one event, without Redis. Returns (eligibility, plan, audit, final)."""
    processo = seeds["processos"][event["tipo"]]
    ctx = make_ctx(event, team)
    el = engine.eligibility(processo, ctx, emp, emp["cargo"])
    plano = engine.plan(processo, ctx, emp, emp["cargo"])
    audit = engine.audit_plan(processo, make_ctx(event, team), emp, plano["projetado"], plano, emp["cargo"])
    final = copy.deepcopy(emp)
    ectx = shelf.ExecCtx(hoje=event["data_efetiva"], norma=seeds["norma"]["parametros"], case_id="caso-teste")
    for item in plano["operacoes"]:
        shelf.apply(item["operacao"], final, item["parametros"], ectx)
    return el, plano, audit, final


def ops(plano):
    return {(o["operacao"], (o["parametros"].get("codigo") or o["parametros"].get("acesso") or o["parametros"].get("programa"))) for o in plano["operacoes"]}


@pytest.fixture
def hipo(team):
    emp = next(e for e in team if e["cargo"] == "ANALISTA_SR" and not e.get("drift"))
    emp.update({"avaliacao_desempenho": 5, "data_admissao": add_months(TODAY, -40)})
    return emp


@pytest.fixture
def enrolled(seeds, make_ctx, team, hipo):
    event = {"tipo": INCLUSAO, "colaborador_id": hipo["id"], "data_efetiva": TODAY, "dados": {"data_oficial": TODAY}}
    el, plano, audit, final = run_process(seeds, make_ctx, team, hipo, event)
    assert el["decisao"] == "ELEGIVEL", el["explicacao"]
    assert audit["decisao"] in ("APROVADO", "APROVADO_COM_RESSALVAS"), [r for r in audit["regras"] if not r["passou"]]
    hipo.update(final)
    return hipo, plano


def test_inclusion_lasts_one_year_from_the_official_date_and_grants_the_benefits(enrolled):
    emp, plano = enrolled
    prog = vigencia.active_programs(emp)[0]
    assert (prog["inicio"], prog["fim"], prog["status"]) == (TODAY, FIM, "ATIVO")
    # the grants come from the target state: an active program is part of what the contracts demand
    assert {("INCLUIR_PROGRAMA", "ALTO_POTENCIAL"), ("ADICIONAR_VERBA", "BOLSA_ALTO_POTENCIAL"),
            ("ADICIONAR_BENEFICIO", "MENTORIA_EXECUTIVA"), ("CONCEDER_ACESSO", "PLATAFORMA_LIDERANCA")} <= ops(plano)
    assert vigencia.warning_date(prog) == "2027-09-09"
    agenda = vigencia.agenda_for(emp)
    assert [(i["tipo"], i["data"], i["evento"]) for i in agenda] == [
        ("aviso", vigencia.warning_date(prog), "colaborador.programa_a_vencer"),
        ("vencimento", FIM, "colaborador.programa_expirado")]


def test_official_date_in_the_future_or_already_over_is_blocked(seeds, make_ctx, team, hipo):
    processo = seeds["processos"][INCLUSAO]
    for data, regra in ((add_months(TODAY, 1), "APT-03"), (add_months(TODAY, -13), "APT-04")):
        event = {"tipo": INCLUSAO, "colaborador_id": hipo["id"], "data_efetiva": TODAY, "dados": {"data_oficial": data}}
        el = engine.eligibility(processo, make_ctx(event, team), hipo, hipo["cargo"])
        assert el["decisao"] == "NAO_ELEGIVEL" and any(r["id"] == regra and not r["passou"] for r in el["regras"])


def test_expiry_on_the_end_date_undoes_what_the_program_granted(seeds, make_ctx, team, enrolled):
    emp, _ = enrolled
    event = {"tipo": "colaborador.programa_expirado", "colaborador_id": emp["id"], "data_efetiva": FIM, "dados": {"programa": "ALTO_POTENCIAL"}}
    el, plano, audit, final = run_process(seeds, make_ctx, team, emp, event)
    assert el["decisao"] == "ELEGIVEL" and audit["decisao"] in ("APROVADO", "APROVADO_COM_RESSALVAS")
    assert {("ENCERRAR_PROGRAMA", "ALTO_POTENCIAL"), ("REMOVER_VERBA", "BOLSA_ALTO_POTENCIAL"),
            ("REMOVER_BENEFICIO", "MENTORIA_EXECUTIVA"), ("REVOGAR_ACESSO", "PLATAFORMA_LIDERANCA")} <= ops(plano)
    assert final["programas"][0]["status"] == "EXPIRADO" and "PLATAFORMA_LIDERANCA" not in final["acessos"]
    assert vigencia.agenda_for(final) == []


def test_expiry_before_the_end_date_is_not_eligible(seeds, make_ctx, team, enrolled):
    emp, _ = enrolled
    event = {"tipo": "colaborador.programa_expirado", "colaborador_id": emp["id"], "data_efetiva": add_months(TODAY, 6),
             "dados": {"programa": "ALTO_POTENCIAL"}}
    el = engine.eligibility(seeds["processos"][event["tipo"]], make_ctx(event, team), emp, emp["cargo"])
    assert el["decisao"] == "NAO_ELEGIVEL" and any(r["id"] == "VEN-02" and not r["passou"] for r in el["regras"])


def test_renewal_extends_the_period_and_reschedules_the_agenda(seeds, make_ctx, team, enrolled):
    emp, _ = enrolled
    antes = {i["evento_id"] for i in vigencia.agenda_for(emp)}
    event = {"tipo": "colaborador.programa_renovado", "colaborador_id": emp["id"], "data_efetiva": add_months(TODAY, 11),
             "dados": {"programa": "ALTO_POTENCIAL"}}
    el, _, audit, final = run_process(seeds, make_ctx, team, emp, event)
    assert el["decisao"] == "ELEGIVEL" and audit["decisao"] in ("APROVADO", "APROVADO_COM_RESSALVAS")
    prog = vigencia.active_programs(final)[0]
    assert prog["fim"] == add_months(TODAY, 24) and prog["renovacoes"][0]["de"] == FIM
    depois = vigencia.agenda_for(final)
    assert depois[-1]["data"] == add_months(TODAY, 24) and not antes & {i["evento_id"] for i in depois}
    # a second renewal goes beyond the policy limit and needs the committee
    again = dict(event, data_efetiva=add_months(TODAY, 23))
    el2 = engine.eligibility(seeds["processos"][event["tipo"]], make_ctx(again, team), final, final["cargo"])
    assert el2["decisao"] == "EXCECAO_NECESSARIA" and any(r["id"] == "REN-03" and not r["passou"] for r in el2["regras"])


def test_early_termination_removes_grants_and_cancels_the_agenda(seeds, make_ctx, team, enrolled):
    emp, _ = enrolled
    event = {"tipo": "colaborador.programa_encerrado", "colaborador_id": emp["id"], "data_efetiva": add_months(TODAY, 3),
             "dados": {"programa": "ALTO_POTENCIAL", "motivo": "Desistência"}}
    el, _, audit, final = run_process(seeds, make_ctx, team, emp, event)
    assert el["decisao"] == "ELEGIVEL" and audit["decisao"] in ("APROVADO", "APROVADO_COM_RESSALVAS")
    assert final["programas"][0]["status"] == "ENCERRADO" and not any(v["codigo"] == "BOLSA_ALTO_POTENCIAL" for v in final["verbas"])
    assert vigencia.agenda_for(final) == []


def test_other_processes_keep_the_grants_while_the_program_is_active(seeds, make_ctx, team, enrolled):
    emp, _ = enrolled
    event = {"tipo": "auditoria.conformidade_solicitada", "colaborador_id": emp["id"], "data_efetiva": add_months(TODAY, 2), "dados": {}}
    _, plano, _, _ = run_process(seeds, make_ctx, team, emp, event)
    assert not any(o["operacao"] in ("REMOVER_VERBA", "REMOVER_BENEFICIO", "REVOGAR_ACESSO") for o in plano["operacoes"])


def test_dismissal_ends_active_programs(seeds, make_ctx, team, enrolled):
    emp, _ = enrolled
    event = {"tipo": "colaborador.desligado", "colaborador_id": emp["id"], "data_efetiva": add_months(TODAY, 2),
             "dados": {"tipo": "SEM_JUSTA_CAUSA", "aviso": "INDENIZADO"}}
    _, plano, _, final = run_process(seeds, make_ctx, team, emp, event)
    assert ("ENCERRAR_PROGRAMA", "*") in ops(plano)
    assert final["programas"][0]["status"] == "ENCERRADO" and vigencia.agenda_for(final) == []


def test_warning_is_skipped_once_the_end_date_was_reached(enrolled):
    emp, _ = enrolled
    items = vigencia.agenda_for(emp)
    aviso = vigencia.warning_date(emp["programas"][0])
    assert [i["tipo"] for i in vigencia.due(items, TODAY)] == []
    assert [i["tipo"] for i in vigencia.due(items, aviso)] == ["aviso"]
    assert [i["tipo"] for i in vigencia.due(items, FIM)] == ["vencimento"]


# --------------------------------------------------------- clock and agenda tick
class FakeRedis:
    def __init__(self):
        self.h: dict[str, dict] = {}

    async def hsetnx(self, key, field, value):
        if field in self.h.setdefault(key, {}):
            return 0
        self.h[key][field] = value
        return 1

    async def hset(self, key, field, value):
        self.h.setdefault(key, {})[field] = value

    async def hgetall(self, key):
        return dict(self.h.get(key, {}))

    async def xadd(self, *a, **k):
        return "0-0"

    async def lpush(self, *a, **k):
        return 1

    async def ltrim(self, *a, **k):
        return True

    async def publish(self, *a, **k):
        return 0


class FakeStore:
    def __init__(self, employees):
        self.r = FakeRedis()
        self.kv: dict = {}
        self.employees = employees

    async def get_json(self, key):
        return self.kv.get(key)

    async def set_json(self, key, value):
        self.kv[key] = value

    async def list_employees(self):
        return self.employees


class FakePipeline:
    def __init__(self):
        self.events = []

    async def submit_event(self, event, **kw):
        self.events.append(event)
        return {"id": f"caso-{len(self.events)}"}


def test_simulated_clock_emits_each_agenda_event_once(enrolled, monkeypatch):
    emp, _ = enrolled
    store, pipe = FakeStore([emp]), FakePipeline()

    async def no_log(*a, **k):
        return {}
    monkeypatch.setattr(vigencia.log, "write", no_log)

    async def scenario():
        await clock.set_date(store, TODAY, "teste")
        assert await vigencia.tick(store, pipe) == []
        await clock.set_date(store, vigencia.warning_date(emp["programas"][0]), "teste")
        await vigencia.tick(store, pipe)
        await vigencia.tick(store, pipe)  # a second worker or tick does not emit again
        assert [e["tipo"] for e in pipe.events] == ["colaborador.programa_a_vencer"]
        await clock.advance(store, 30, "teste")
        assert (await clock.state(store))["hoje"] == FIM
        await vigencia.tick(store, pipe)
        assert [e["tipo"] for e in pipe.events][-1] == "colaborador.programa_expirado"
        assert pipe.events[-1]["data_efetiva"] == FIM and pipe.events[-1]["origem"] == "agenda:vigencia"
        agenda = await vigencia.agenda(store)
        assert {i["situacao"] for i in agenda["itens"]} == {"EMITIDO"}
        await clock.set_date(store, None, "teste")
        assert not (await clock.state(store))["simulado"]

    asyncio.run(scenario())


def test_suite_scenarios_build_and_reserve_their_agenda_ids(seeds, team):
    gen = GenCtx(team, seeds["cargos"], TODAY, random.Random(7))
    for sid in ("alto_potencial_inclusao", "alto_potencial_vencimento", "alto_potencial_renovacao", "alto_potencial_encerramento"):
        built = build(sid, team, seeds["cargos"], TODAY, gen=gen)
        assert built, sid
        # only the expiry, already due when prepared, is played by the scenario instead of the agenda
        reserved = built["eventos"][0]["metadados"].get("reserva_agenda")
        assert bool(reserved) == (sid == "alto_potencial_vencimento"), sid
