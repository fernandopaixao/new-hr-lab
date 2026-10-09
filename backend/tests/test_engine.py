import random

from hrlab import engine, shelf
from hrlab.expr import resolve_value, unwrap
from hrlab.generators.events import GenCtx, build

from .conftest import TODAY


def _scenario(seeds, team, scenario_id):
    gen = GenCtx(team, seeds["cargos"], TODAY, random.Random(7))
    built = build(scenario_id, team, seeds["cargos"], TODAY, gen=gen)
    assert built, scenario_id
    by_id = {e["id"]: e for e in team}
    for emp_id, patch in (built.get("preparacao") or {}).items():
        by_id[emp_id].update(patch)
    return built["eventos"][0], by_id


def _run(seeds, make_ctx, event, emp):
    processo = seeds["processos"][event["tipo"]]
    ctx = make_ctx(event)
    spec = processo.get("cargo_alvo")
    alvo = unwrap(resolve_value(spec, ctx.names(emp))) if spec else emp.get("cargo")
    return processo, ctx, alvo


def test_generated_team_without_drift_is_compliant(seeds, team, make_ctx):
    ctx = make_ctx({"data_efetiva": TODAY})
    failing = [e["id"] for e in team if not engine.employee_compliance(e, ctx)["conforme"]]
    assert failing == []


def test_team_generation_is_deterministic(seeds):
    from hrlab.generators.team import generate_team
    a = generate_team(size=30, seed=1, today=TODAY, norma=seeds["norma"], cargos=seeds["cargos"])
    b = generate_team(size=30, seed=1, today=TODAY, norma=seeds["norma"], cargos=seeds["cargos"])
    assert a == b


def test_standard_promotion_is_eligible_and_plan_approved(seeds, team, make_ctx):
    event, by_id = _scenario(seeds, team, "promocao_padrao")
    emp = by_id[event["colaborador_id"]]
    processo, ctx, alvo = _run(seeds, make_ctx, event, emp)
    el = engine.eligibility(processo, ctx, emp, alvo)
    assert el["decisao"] == "ELEGIVEL", el["explicacao"]
    plano = engine.plan(processo, ctx, emp, alvo)
    ops = [i["operacao"] for i in plano["operacoes"]]
    assert "ALTERAR_CARGO" in ops and "ALTERAR_SALARIO" in ops
    assert plano["projetado"]["cargo"] == alvo
    check = engine.audit_plan(processo, ctx, emp, plano["projetado"], plano, alvo)
    assert check["decisao"] == "APROVADO", [r for r in check["regras"] if not r.get("passou")]


def test_promotion_with_disciplinary_process_needs_exception(seeds, team, make_ctx):
    event, by_id = _scenario(seeds, team, "promocao_processo_disciplinar")
    emp = by_id[event["colaborador_id"]]
    processo, ctx, alvo = _run(seeds, make_ctx, event, emp)
    assert engine.eligibility(processo, ctx, emp, alvo)["decisao"] == "EXCECAO_NECESSARIA"


def test_promotion_of_employee_on_leave_is_blocked(seeds, team, make_ctx):
    event, by_id = _scenario(seeds, team, "promocao_colaborador_afastado")
    emp = by_id[event["colaborador_id"]]
    processo, ctx, alvo = _run(seeds, make_ctx, event, emp)
    assert engine.eligibility(processo, ctx, emp, alvo)["decisao"] == "NAO_ELEGIVEL"


def test_promotion_without_minimum_time_needs_exception(seeds, team, make_ctx):
    event, by_id = _scenario(seeds, team, "promocao_sem_intersticio")
    emp = by_id[event["colaborador_id"]]
    processo, ctx, alvo = _run(seeds, make_ctx, event, emp)
    assert engine.eligibility(processo, ctx, emp, alvo)["decisao"] == "EXCECAO_NECESSARIA"


def test_shelf_operation_is_compensable(team, seeds):
    emp = team[10]
    before = dict(emp, beneficios=list(emp.get("beneficios") or []))
    ectx = shelf.ExecCtx(hoje=TODAY, norma=seeds["norma"].get("parametros") or {}, case_id="t")
    _, snapshot = shelf.apply("ADICIONAR_BENEFICIO", emp, {"codigo": "GYMPASS", "plano": "BASICO"}, ectx)
    assert any(b["codigo"] == "GYMPASS" for b in emp["beneficios"])
    shelf.compensate(emp, snapshot)
    assert emp["beneficios"] == before["beneficios"]
