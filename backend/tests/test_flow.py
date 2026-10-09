"""Audit before execution, final check, hierarchy and next step."""
import copy
import random

from hrlab import engine
from hrlab.domain import STAGE_KEYS, next_step
from hrlab.generators.events import GenCtx, build
from hrlab.migrations import migrate_approval, migrate_case

from .conftest import TODAY


def _prepare(seeds, team, scenario_id):
    gen = GenCtx(team, seeds["cargos"], TODAY, random.Random(7))
    built = build(scenario_id, team, seeds["cargos"], TODAY, gen=gen)
    by_id = {e["id"]: e for e in team}
    for emp_id, patch in (built.get("preparacao") or {}).items():
        by_id[emp_id].update(patch)
    return built["eventos"][0], by_id


def test_audit_comes_before_execution():
    assert STAGE_KEYS == ["intake", "eligibility", "planning", "audit", "execution", "verification"]
    assert STAGE_KEYS.index("audit") < STAGE_KEYS.index("execution") < STAGE_KEYS.index("verification")


def test_audit_blocks_plan_missing_a_required_operation(seeds, team, make_ctx):
    event, by_id = _prepare(seeds, team, "desligamento_sem_justa_causa")
    emp = by_id[event["colaborador_id"]]
    processo = seeds["processos"][event["tipo"]]
    ctx = make_ctx(event, team)
    plano = engine.plan(processo, ctx, emp, emp["cargo"])
    assert engine.audit_plan(processo, ctx, emp, plano["projetado"], plano, emp["cargo"])["decisao"] in ("APROVADO", "APROVADO_COM_RESSALVAS")
    # the audit verifications of the service contract now run before anything is executed
    sem_rescisao = dict(plano, operacoes=[o for o in plano["operacoes"] if o["operacao"] != "CALCULAR_RESCISAO"])
    result = engine.audit_plan(processo, make_ctx(event, team), emp, plano["projetado"], sem_rescisao, emp["cargo"])
    assert result["decisao"] == "REPROVADO"
    assert result["momento"] == "ANTES_DA_EXECUCAO"
    assert any(not r["passou"] and r["tipo"] == "BLOQUEANTE" for r in result["regras"])


def test_final_check_compares_execution_with_the_audited_projection(team):
    projetado = copy.deepcopy(team[5])
    recibos = [{"operacao": "ALTERAR_SALARIO", "status": "EXECUTADA"}]
    assert engine.verify_execution(projetado, copy.deepcopy(projetado), recibos)["decisao"] == "APROVADO"
    divergente = dict(copy.deepcopy(projetado), salario_base=projetado["salario_base"] + 100)
    out = engine.verify_execution(projetado, divergente, recibos)
    assert out["decisao"] == "REPROVADO" and out["divergencias"]
    falhou = engine.verify_execution(projetado, projetado, [{"operacao": "ALTERAR_SALARIO", "status": "FALHOU"}])
    assert next(r for r in falhou["regras"] if r["id"] == "FIN-RECIBOS")["passou"] is False


def test_generated_team_forms_a_single_hierarchy(team, make_ctx):
    ctx = make_ctx({"data_efetiva": TODAY}, team)
    diretores = [e for e in team if not e.get("gestor_id")]
    assert [e["cargo"] for e in diretores] == ["DIRETOR"]
    for e in team:
        chain = ctx.management_chain(e)
        assert e["cargo"] == "DIRETOR" or chain[-1]["id"] == diretores[0]["id"]
        if e.get("gestor_id"):
            assert ctx.level(ctx.manager(e)) >= ctx.level(e)


def test_transfer_to_existing_agency_assigns_its_manager(seeds, team, make_ctx):
    event, by_id = _prepare(seeds, team, "transferencia_outra_base_com_anuencia")
    emp = by_id[event["colaborador_id"]]
    ctx = make_ctx(event, team)
    head = ctx.unit_manager(event["dados"]["unidade"], acima_de=emp)
    assert head and by_id[head]["cargo"] == "GERENTE_AGENCIA"
    plano = engine.plan(seeds["processos"][event["tipo"]], ctx, emp, emp["cargo"])
    assert plano["projetado"]["gestor_id"] == head


def test_dismissing_a_manager_warns_about_the_team(seeds, team, make_ctx):
    gerente = next(e for e in team if e["cargo"] == "GERENTE_AGENCIA")
    event = {"tipo": "colaborador.desligado", "colaborador_id": gerente["id"], "data_efetiva": TODAY,
             "dados": {"tipo": "SEM_JUSTA_CAUSA", "aviso": "INDENIZADO"}}
    el = engine.eligibility(seeds["processos"][event["tipo"]], make_ctx(event, team), gerente, gerente["cargo"])
    alerta = next(r for r in el["regras"] if r["id"] == "DSL-HIER")
    assert not alerta["passou"] and "defina o novo gestor" in alerta["explicacao"]


def test_next_step_names_who_acts_and_what_follows():
    waiting = {"status": "AGUARDANDO_APROVACAO", "estagio": "audit", "aguardando": [
        {"tipo_rotulo": "Exceção de regra", "aprovadores": ["GESTOR"], "responsavel": {"nome": "Ana Lima"}}]}
    step = next_step(waiting)
    assert step["quem"] == "GESTOR" and "Gestor imediato (Ana Lima)" in step["texto"] and "o plano é executado" in step["texto"]
    assert "reverte" in next_step({"status": "NA_FILA", "estagio": "verification"})["texto"]
    assert next_step({"status": "REVERTIDO", "estagio": "verification"})["encerrado"] is True
    assert next_step({"status": "PARADO", "estagio": "audit", "estagio_parado": "audit"})["quem"] == "OPERADOR"


def test_cases_stored_before_the_change_are_migrated():
    legacy = {"id": "c1", "status": "AGUARDANDO_APROVACAO", "estagio": "audit", "breakpoints": ["plan_review"],
              "etapas": {s: {"status": "OK"} for s in ("intake", "eligibility", "planning", "plan_review", "execution", "audit")},
              "conferencia_plano": {"decisao": "APROVADO"}, "agente_plano": {"recomendacao": "APROVADO"}, "recomendacao_plano": "APROVADO",
              "auditoria": {"decisao": "REPROVADO"}, "agente_auditoria": {"recomendacao": "REPROVADO"}, "recomendacao_auditoria": "REPROVADO"}
    assert migrate_case(legacy)
    assert list(legacy["etapas"]) == ["intake", "eligibility", "planning", "audit", "execution", "verification"]
    assert legacy["estagio"] == "verification" and legacy["breakpoints"] == ["audit"]
    assert legacy["auditoria"]["decisao"] == "APROVADO" and legacy["conferencia_final"]["decisao"] == "REPROVADO"
    assert legacy["recomendacao_auditoria"] == "APROVADO" and legacy["recomendacao_conferencia"] == "REPROVADO"
    assert not migrate_case(legacy)
    ap = {"id": "a1", "estagio": "audit", "tipo": "REVISAO_AUDITORIA"}
    assert migrate_approval(ap) and ap["estagio"] == "verification" and ap["tipo"] == "REVISAO_CONFERENCIA_FINAL"
    ap2 = {"id": "a2", "estagio": "plan_review", "tipo": "REVISAO_PLANO"}
    assert migrate_approval(ap2) and ap2["estagio"] == "audit" and ap2["tipo"] == "REVISAO_AUDITORIA"
    assert not migrate_approval(ap)
