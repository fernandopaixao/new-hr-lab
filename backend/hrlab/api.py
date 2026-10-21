"""HTTP API used by the interface (FastAPI)."""
from __future__ import annotations

import asyncio
import copy
import json
import random
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from . import agent, apikeys, ask, budget, clock, embeddings as emb, engine, facts as factsmod, indexer, llm, logbook as log, metrics as agent_metrics, migrations, shelf, vigencia
from .config import DEFAULT_SETTINGS, REDIS_URL, coerce_settings
from .context import Ctx
from .contracts import ContractError, ContractRepo, from_yaml, to_yaml, validate
from .domain import (
    APPROVAL_OUTCOMES, APPROVAL_TYPE_LABELS, FINAL_STATUSES, NA_FILA, PERSONAS, PROCESSANDO, STAGE_OUTCOMES, STAGES, STAGE_KEYS,
    STATUS_LABELS, next_step,
)
from .generators import events as evgen
from .generators.team import DRIFTS, apply_drift, generate_team
from .pipeline import Pipeline
from .store import LOG_STREAM, P, UPDATES_CHANNEL, Store, case_summary, new_id, now_ms

store = Store()
pipeline = Pipeline(store)
repo = ContractRepo(store)
ledger = llm.use_ledger(store)
BACKGROUND: set[asyncio.Task] = set()

EVENT_TEMPLATES: dict[str, dict] = {
    "colaborador.admitido": {"nome": "Nome Sobrenome", "cpf": "52998224725", "data_nascimento": "1995-04-10", "genero": "F", "escolaridade": "SUPERIOR",
                             "cargo": "ESCRITURARIO", "salario": 3800, "unidade": "AG-1000", "cidade": "São Paulo", "uf": "SP", "centro_custo": "CC-AG-1000",
                             "certificacoes": [], "dependentes": []},
    "colaborador.promovido": {"cargo_destino": "CAIXA", "novo_salario": 4600, "justificativa": "Ciclo de carreira"},
    "colaborador.merito_concedido": {"percentual": 5},
    "colaborador.revertido_cargo_confianca": {"cargo_destino": "ANALISTA_PL", "motivo": "Reestruturação da carteira"},
    "colaborador.transferido": {"unidade": "AG-2001", "cidade": "Rio de Janeiro", "uf": "RJ", "anuencia_colaborador": True, "provisoria": False},
    "colaborador.desligado": {"tipo": "SEM_JUSTA_CAUSA", "motivo": "Reestruturação", "aviso": "INDENIZADO", "falta_grave_registrada": False},
    "colaborador.afastado": {"tipo": "DOENCA", "inicio": "", "previsao_retorno": ""},
    "colaborador.retornou_afastamento": {"data_retorno": ""},
    "cct.reajuste_aplicado": {"percentual": 5.5, "sindicatos": ["SEEB-SP"]},
    "cct.reajuste_individual": {"percentual": 5.5},
    "colaborador.dependente_incluido": {"nome": "Nome do dependente", "parentesco": "FILHO", "data_nascimento": "", "certidao_apresentada": True},
    "colaborador.bonus_concedido": {"valor": 5000, "motivo": "Metas do semestre"},
    "colaborador.jornada_alterada": {"horas": 6},
    "auditoria.conformidade_solicitada": {"motivo": "Conferência pontual"},
    "auditoria.conformidade_coletiva": {"cargo": "", "motivo": "Varredura"},
    "colaborador.programa_alto_potencial_iniciado": {"data_oficial": "", "justificativa": "Indicação do comitê de talentos"},
    "colaborador.programa_renovado": {"programa": "ALTO_POTENCIAL", "meses": 12, "justificativa": "Renovação aprovada pelo comitê"},
    "colaborador.programa_encerrado": {"programa": "ALTO_POTENCIAL", "motivo": "Desistência do colaborador"},
    "colaborador.programa_a_vencer": {"programa": "ALTO_POTENCIAL"},
    "colaborador.programa_expirado": {"programa": "ALTO_POTENCIAL"},
}


async def today() -> str:
    """Business date: the simulated clock when set, else the real calendar."""
    return await clock.today(store)


async def bootstrap() -> None:
    await store.ensure_groups(STAGE_KEYS)
    await migrations.audit_before_execution(store)
    await repo.seed()
    if not await store.r.smembers(f"{P}:employees"):
        await _generate(80, 42, 15, replace=True, actor="sistema (carga inicial)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    for attempt in range(30):
        try:
            await bootstrap()
            break
        except Exception:  # noqa: BLE001 - redis may still be starting
            await asyncio.sleep(1)
    yield
    await store.close()


app = FastAPI(title="Novo RH - laboratório de arquitetura orientada a eventos", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def http_error(exc: Exception) -> HTTPException:
    code = 403 if isinstance(exc, PermissionError) else 400
    return HTTPException(status_code=code, detail=str(exc))


# ------------------------------------------------------------------ meta
@app.get("/api/health")
async def health() -> dict:
    await store.r.ping()
    return {"ok": True}


@app.get("/api/meta")
async def meta() -> dict:
    return {
        "estagios": [{"id": k, "nome": n, "descricao": d, "saida": STAGE_OUTCOMES.get(k)} for k, n, d in STAGES],
        "resultado_aprovacao": {k: {"aprovar": a, "rejeitar": r} for k, (a, r) in APPROVAL_OUTCOMES.items()},
        "status": STATUS_LABELS, "finais": sorted(FINAL_STATUSES), "personas": PERSONAS,
        "tipos_aprovacao": APPROVAL_TYPE_LABELS, "tipos_evento": await repo.event_types(),
        "templates_evento": EVENT_TEMPLATES, "cenarios": [s.describe() for s in evgen.SCENARIOS],
        "prateleira": shelf.catalog(), "desvios": [{"id": k, "nome": n} for k, n in DRIFTS], "hoje": await today(), "relogio": await clock.state(store),
    }


# ------------------------------------------------------------- control
@app.get("/api/control")
async def get_control() -> dict:
    return await store.control()


@app.post("/api/control")
async def set_control(patch: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    ctl = await store.control()
    for key in ("paused", "paused_stages", "breakpoints"):
        if key in patch:
            ctl[key] = patch[key]
    await store.set_control(ctl)
    await log.write(store, log.CONTROLE, f"Controle da linha alterado: pausa geral {'ligada' if ctl['paused'] else 'desligada'}; "
                    f"estágios pausados {ctl['paused_stages'] or 'nenhum'}; pontos de parada {ctl['breakpoints'] or 'nenhum'}.",
                    ator=f"persona:{x_persona}", dados=ctl)
    await store.publish({"tipo": "control", "control": ctl})
    return ctl


@app.get("/api/settings")
async def get_settings() -> dict:
    return {"valores": await store.settings(), "padroes": DEFAULT_SETTINGS}


async def apply_settings(patch: dict, persona: str, motivo: str = "Configurações alteradas") -> dict:
    before = await store.settings()
    try:
        after = await store.update_settings(patch)
    except ValueError as exc:
        raise http_error(exc) from exc
    changes = {k: {"antes": before.get(k), "depois": v} for k, v in after.items() if before.get(k) != v}
    if changes:
        await log.write(store, log.CONFIG_ALTERADA, f"{motivo}: " + ", ".join(f"{k}={v['depois']}" for k, v in changes.items()),
                        ator=f"persona:{persona}", dados=changes)
    if llm.embedding_model(before) != llm.embedding_model(after):
        # vectors of different models are not comparable: re-embed everything
        await indexer.mark_all(store)
    if changes:
        await agent.check_health(store, after)
    return after


@app.put("/api/settings")
async def put_settings(patch: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    return {"valores": await apply_settings(patch, x_persona), "padroes": DEFAULT_SETTINGS}


# ---------------------------------------------------------------- setup
SETUP_KEY = f"{P}:setup"


def _redis_label() -> str:
    # never show a password that may be part of the URL
    url = REDIS_URL
    if "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://***@{rest.split('@', 1)[1]}"
    return url


@app.get("/api/setup")
async def get_setup() -> dict:
    info = await store.r.info("server")
    return {
        "estado": await store.get_json(SETUP_KEY) or {"concluido": False},
        "provedores": llm.PROVIDERS, "provedores_embedding": llm.EMBEDDING_PROVIDERS, "chaves": apikeys.status(), "motores": ENGINES,
        "valores": await store.settings(), "padroes": DEFAULT_SETTINGS,
        "gastos": await ledger.status(await store.settings()), "precos": budget.price_table(await ledger.overrides()),
        "ambiente": {"redis": _redis_label(), "redis_versao": info.get("redis_version"),
                     "colaboradores": await store.r.scard(f"{P}:employees"), "casos": await store.r.zcard(f"{P}:cases")},
    }


@app.post("/api/setup/test")
async def setup_test(body: dict = Body(...)) -> dict:
    """Tests a provider with the values typed in the wizard, before anything is saved."""
    prov = str(body.get("provedor") or "")
    if prov not in llm.PROVIDERS:
        raise HTTPException(400, f"provedor desconhecido: {prov}")
    try:
        typed = coerce_settings({k: v for k, v in (body.get("valores") or {}).items() if k in DEFAULT_SETTINGS})
    except (TypeError, ValueError) as exc:
        raise http_error(exc) from exc
    settings = {**await store.settings(), **typed}
    base_url = settings["ollama_base_url"] if prov == "ollama" else (settings["openai_base_url"] if prov == "openai" else None)
    model = str(body.get("modelo") or llm.active_model(settings, prov))
    return await llm.test_connection(settings, prov, model, api_key=(body.get("chave") or None), base_url=base_url)


# ------------------------------------------------- spending cap (external LLMs)
@app.get("/api/gastos")
async def get_spend(recentes: int = 30) -> dict:
    settings = await store.settings()
    return {**await ledger.status(settings, recent=max(0, min(recentes, 500))), "precos": budget.price_table(await ledger.overrides()),
            "provedor": llm.provider(settings), "modelo": llm.active_model(settings),
            "preco_modelo": budget.price_for(llm.provider(settings), llm.active_model(settings), await ledger.overrides())
            if budget.is_external(llm.provider(settings)) else None}


@app.put("/api/gastos/teto")
async def put_spend_cap(body: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    patch = {k: body[k] for k in ("spend_cap_usd", "spend_period", "spend_alert_percent") if k in body}
    await apply_settings(patch, x_persona, "Teto de gastos alterado")
    return await get_spend()


@app.put("/api/gastos/precos")
async def put_spend_price(body: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    """Edits (or, without values, restores) the price of one model, in US$ per million tokens."""
    prov, model = str(body.get("provedor") or ""), str(body.get("modelo") or "").strip()
    if prov not in budget.EXTERNAL or not model:
        raise HTTPException(400, "informe um provedor externo (anthropic, openai ou gemini) e o modelo")
    try:
        entrada = None if body.get("entrada") in (None, "") else float(body["entrada"])
        saida = None if body.get("saida") in (None, "") else float(body["saida"])
        await ledger.set_price(prov, model, entrada, saida)
    except (TypeError, ValueError) as exc:
        raise http_error(exc) from exc
    what = f"US$ {entrada:g} entrada e US$ {saida:g} saída por milhão de tokens" if entrada is not None and saida is not None else "preço da tabela restaurado"
    await log.write(store, log.GASTOS, f"Preço de {prov} {model}: {what}.", ator=f"persona:{x_persona}",
                    dados={"provedor": prov, "modelo": model, "entrada": entrada, "saida": saida})
    return await get_spend()


@app.post("/api/gastos/zerar")
async def reset_spend(x_persona: str = Header("OPERADOR")) -> dict:
    settings = await store.settings()
    before = await ledger.reset_period(settings)
    await log.write(store, log.GASTOS, f"Contador de gastos zerado ({budget.period_label(settings)}); estava em {budget.usd(before)}.",
                    ator=f"persona:{x_persona}", dados={"gasto_anterior_usd": before})
    await agent.check_health(store, settings)
    return await get_spend()


@app.post("/api/setup/test-jev")
async def setup_test_jev(body: dict = Body(default={})) -> dict:
    """Tests the JEV decision model with the values typed in the wizard, before anything is saved."""
    settings = {**await store.settings(), **{k: v for k, v in (body.get("valores") or {}).items() if k in DEFAULT_SETTINGS}}
    return await llm.test_jev(settings, body.get("modelo") or None)


@app.put("/api/setup/key")
async def setup_key(body: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    prov = str(body.get("provedor") or "")
    try:
        apikeys.set_key(prov, body.get("chave"))
    except ValueError as exc:
        raise http_error(exc) from exc
    what = "configurada" if body.get("chave") else "removida"
    await log.write(store, log.CONFIG_ALTERADA, f"Chave de API de {llm.PROVIDERS[prov]['nome']} {what} pelo assistente (o valor não é registrado).",
                    ator=f"persona:{x_persona}", dados={"provedor": prov, "acao": what})
    await agent.check_health(store, await store.settings())
    return apikeys.status()


@app.post("/api/setup/complete")
async def setup_complete(body: dict = Body(default={}), x_persona: str = Header("OPERADOR")) -> dict:
    after = await apply_settings(body.get("valores") or {}, x_persona, "Configuração inicial concluída")
    state = {"concluido": True, "concluido_em": now_ms(), "persona": x_persona, "pulado": bool(body.get("pulado"))}
    await store.set_json(SETUP_KEY, state)
    return {"estado": state, "valores": after}


@app.get("/api/agent/health")
async def agent_health() -> dict:
    return await store.get_json(f"{P}:agent:health") or {"ok": False, "erro": "ainda não verificado"}


@app.post("/api/agent/check")
async def agent_check() -> dict:
    return await agent.check_health(store, await store.settings())


@app.post("/api/agent/pull")
async def agent_pull(body: dict = Body(default={})) -> dict:
    settings = await store.settings()
    try:
        if body.get("motor") == "jev":
            return await agent.pull_model(settings, body.get("modelo") or settings["jev_model"], llm.jev_base_url(settings))
        return await agent.pull_model(settings, body.get("modelo"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"falha ao baixar o modelo: {exc}") from exc


@app.post("/api/agent/cache/clear")
async def agent_cache_clear() -> dict:
    n = 0
    async for key in store.r.scan_iter(match=f"{P}:agent:cache:*", count=500):
        await store.r.delete(key)
        n += 1
    return {"removidos": n}


# ------------------------------------------------- agent performance (Qwen x JEV)
ENGINES = {
    "qwen": {"nome": "Qwen (generativo)", "descricao": "Modelo generativo do provedor configurado (qwen2.5:7b no Ollama por padrão). "
             "Lê o caso inteiro em JSON e escreve resumo, achados e justificativa."},
    "jev": {"nome": "JEV (modelo de decisão)", "descricao": "Modelo de decisão no estilo JEV servido pelo Ollama 0.35+ (tev1:0.8b por padrão). "
            "Responde perguntas tipadas com probabilidades, numa só chamada, sem texto livre."},
}


@app.get("/api/metrics/agentes")
async def agent_performance(periodo_horas: float = 24, balde_min: int = 0, ate: int | None = None) -> dict:
    """History of agent response and processing times, per engine and task, with Qwen x JEV comparison."""
    fim = ate or now_ms()
    desde = int(fim - periodo_horas * 3_600_000) if periodo_horas else 0
    recs = await agent_metrics.load(store, desde, fim)
    out = agent_metrics.summarize(recs, desde_ms=desde, ate_ms=fim, bucket_ms=balde_min * 60_000 if balde_min else None)
    settings = await store.settings()
    out["config"] = {"motor": settings["agent_engine"], "comparacao": settings["agent_compare_enabled"],
                     "elegibilidade": settings["agent_eligibility_enabled"], "modelo_qwen": llm.active_model(settings),
                     "provedor_qwen": llm.PROVIDERS[llm.provider(settings)]["nome"], "modelo_jev": settings["jev_model"]}
    return out


@app.delete("/api/metrics/agentes")
async def agent_performance_clear(x_persona: str = Header("OPERADOR")) -> dict:
    n = await agent_metrics.clear(store)
    await log.write(store, log.CONTROLE, f"Histórico de desempenho dos agentes limpo ({n} registros).", ator=f"persona:{x_persona}")
    return {"removidos": n}


# ------------------------------------------------------------ employees
def employee_summary(e: dict, conf: dict | None = None) -> dict:
    out = {k: e.get(k) for k in ("id", "nome", "cargo", "situacao", "salario_base", "unidade", "cidade", "uf", "sindicato", "data_admissao",
                                 "data_inicio_cargo", "jornada_horas", "regime_jornada", "genero", "avaliacao_desempenho", "drift", "versao")}
    out["estabilidades"] = [s.get("tipo") for s in e.get("estabilidades") or []]
    out["programas"] = [{"codigo": p.get("codigo"), "fim": p.get("fim")} for p in vigencia.active_programs(e)]
    out["alertas_conduta"] = bool((e.get("conduta") or {}).get("processo_disciplinar_aberto") or (e.get("conduta") or {}).get("medida_restritiva_compliance"))
    if conf is not None:
        out["conforme"] = conf["conforme"]
        out["pendencias"] = len(conf["falhas"]) + len(conf["pendencias_estado_alvo"])
    return out


async def compliance_ctx(employees: list[dict] | None = None) -> Ctx:
    t = await today()
    employees = employees if employees is not None else await store.list_employees()
    return Ctx(event={"data_efetiva": t, "dados": {}}, norma=await repo.norma(t), politica=await repo.politica(t), cargos=await repo.cargos(t),
               employees={e["id"]: e for e in employees})


def person_ref(e: dict, ctx: Ctx) -> dict:
    """Short reference to a person, used by the hierarchy views."""
    return {"id": e.get("id"), "nome": e.get("nome"), "cargo": e.get("cargo"), "cargo_nome": (ctx.cargo(e.get("cargo")) or {}).get("nome"),
            "unidade": e.get("unidade"), "cidade": e.get("cidade"), "uf": e.get("uf"), "situacao": e.get("situacao")}


@app.get("/api/employees")
async def list_employees() -> list[dict]:
    employees = await store.list_employees()
    ctx = await compliance_ctx(employees)
    reports: dict[str, int] = {}
    for e in employees:
        if e.get("gestor_id") and e.get("situacao") != "DESLIGADO":
            reports[e["gestor_id"]] = reports.get(e["gestor_id"], 0) + 1
    out = []
    for e in employees:
        row = employee_summary(e, engine.employee_compliance(e, ctx))
        row.update({"gestor_id": e.get("gestor_id"), "gestor_nome": ctx.manager(e).get("nome"), "subordinados": reports.get(e["id"], 0),
                    "cargo_nome": (ctx.cargo(e.get("cargo")) or {}).get("nome"), "nivel": (ctx.cargo(e.get("cargo")) or {}).get("nivel")})
        out.append(row)
    return out


@app.get("/api/employees/{emp_id}")
async def get_employee(emp_id: str) -> dict:
    emp = await store.get_employee(emp_id)
    if not emp:
        raise HTTPException(404, "colaborador não encontrado")
    ctx = await compliance_ctx()
    conf = engine.employee_compliance(emp, ctx)
    tobe = engine.target_state(emp, ctx)
    cases = [case_summary(c) for c in await store.list_cases(limit=500) if c.get("colaborador_id") == emp_id]
    hierarquia = {"cadeia": [person_ref(m, ctx) for m in ctx.management_chain(emp)],
                  "subordinados": sorted((person_ref(r, ctx) for r in ctx.direct_reports(emp_id)), key=lambda r: (r["cargo"] or "", r["nome"] or "")),
                  "pares": len([p for p in ctx.direct_reports(emp.get("gestor_id")) if p["id"] != emp_id]) if emp.get("gestor_id") else 0}
    hoje = await today()
    emitted = await store.r.hgetall(vigencia.EMITTED_KEY)
    programas = [{**p, "dias_restantes": vigencia.remaining_days(p, hoje) if p.get("status") == "ATIVO" else None,
                  "aviso_previsto": vigencia.warning_date(p)} for p in emp.get("programas") or []]
    agenda = [{**i, "emitido": emitted.get(i["evento_id"])} for i in vigencia.agenda_for(emp)]
    return {"colaborador": emp, "programas": programas, "agenda": agenda, "hoje": hoje, "cargo_contrato": {k: (ctx.cargo(emp.get("cargo")) or {}).get(k) for k in ("nome", "nivel", "segmento", "descricao")},
            "conformidade": conf, "estado_alvo": {k: v for k, v in tobe.items() if not k.startswith("_")}, "hierarquia": hierarquia,
            "casos": cases[:50], "log": await log.query(store, colaborador_id=emp_id, limit=200)}


@app.put("/api/employees/{emp_id}")
async def update_employee(emp_id: str, patch: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    async with store.employee_lock(emp_id):
        emp = await store.get_employee(emp_id)
        if not emp:
            raise HTTPException(404, "colaborador não encontrado")
        before = copy.deepcopy(emp)
        for k, v in patch.items():
            if k in ("id", "versao"):
                continue
            emp[k] = v
        emp = await store.save_employee(emp)
    diff = engine.state_diff(before, emp)
    await log.write(store, log.COLABORADOR_ALTERADO, f"Cadastro alterado manualmente: {', '.join(d['campo'] for d in diff) or 'sem mudanças'}.",
                    ator=f"persona:{x_persona}", colaborador_id=emp_id, dados={"alteracoes": diff})
    await store.publish({"tipo": "employee", "id": emp_id})
    return emp


@app.post("/api/employees/generate")
async def generate_employees(body: dict = Body(default={}), x_persona: str = Header("OPERADOR")) -> dict:
    n = await _generate(int(body.get("tamanho", 80)), int(body.get("semente", random.randint(1, 99999))), float(body.get("desvio_percentual", 15)),
                        replace=bool(body.get("substituir", True)), actor=f"persona:{x_persona}")
    return {"gerados": n}


async def _generate(size: int, seed: int, drift: float, *, replace: bool, actor: str) -> int:
    t = await today()
    if replace:
        await store.delete_all_employees()
        await store.r.delete(f"{P}:seq:employee")
        start = 1
    else:
        existing = await store.r.smembers(f"{P}:employees")
        start = max([int(x[1:]) for x in existing if x[1:].isdigit()] or [0]) + 1
    team = generate_team(size=size, seed=seed, today=t, norma=await repo.norma(t), cargos=await repo.cargos(t), drift_percent=drift, start_index=start)
    for emp in team:
        emp["versao"] = 0
        await store.save_employee(emp)
    await log.write(store, log.COLABORADOR_ALTERADO, f"Time artificial gerado: {len(team)} colaboradores (semente {seed}, {drift}% com desvios).",
                    ator=actor, dados={"tamanho": size, "semente": seed, "desvio_percentual": drift, "substituir": replace})
    await store.publish({"tipo": "employees"})
    return len(team)


@app.post("/api/employees/{emp_id}/drift")
async def drift_employee(emp_id: str, body: dict = Body(default={}), x_persona: str = Header("OPERADOR")) -> dict:
    async with store.employee_lock(emp_id):
        emp = await store.get_employee(emp_id)
        if not emp:
            raise HTTPException(404, "colaborador não encontrado")
        before = copy.deepcopy(emp)
        kind = apply_drift(emp, random.Random(), body.get("tipo"))
        if not kind:
            raise HTTPException(400, "nenhum desvio aplicável a este colaborador")
        emp = await store.save_employee(emp)
    await log.write(store, log.COLABORADOR_ALTERADO, f"Desvio de conformidade injetado: {kind}.", ator=f"persona:{x_persona}", colaborador_id=emp_id,
                    dados={"alteracoes": engine.state_diff(before, emp)})
    return emp


# ------------------------------------------------------------ contracts
@app.get("/api/contracts")
async def list_contracts() -> list[dict]:
    out = []
    for code, versions in (await repo.all_versions()).items():
        latest = versions[-1]
        out.append({"codigo": code, "tipo": latest.get("tipo"), "nome": latest.get("nome"), "versao": latest.get("versao"),
                    "vigencia": latest.get("vigencia"), "evento": latest.get("evento"), "cargo": latest.get("cargo"),
                    "versoes": [{"versao": v.get("versao"), "vigencia": v.get("vigencia"), "salvo_em": v.get("salvo_em"), "salvo_por": v.get("salvo_por")} for v in versions]})
    order = {"NORMA": 0, "POLITICA": 1, "CARGO": 2, "PROCESSO": 3}
    return sorted(out, key=lambda c: (order.get(c["tipo"], 9), c.get("nivel") or 0, c["codigo"]))


@app.get("/api/contracts/{code}")
async def get_contract(code: str, versao: int | None = None) -> dict:
    doc = await repo.get(code, version=versao)
    if not doc:
        raise HTTPException(404, "contrato não encontrado")
    return {"contrato": doc, "yaml": to_yaml(doc), "versoes": [v.get("versao") for v in await store.get_contract_versions(code)]}


@app.post("/api/contracts/validate")
async def validate_contract(body: dict = Body(...)) -> dict:
    try:
        doc = from_yaml(body["yaml"]) if "yaml" in body else body["contrato"]
    except ContractError as exc:
        return {"valido": False, "problemas": [str(exc)]}
    problems = validate(doc)
    return {"valido": not problems, "problemas": problems, "contrato": doc, "yaml": to_yaml(doc)}


@app.post("/api/contracts")
async def save_contract(body: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    try:
        doc = from_yaml(body["yaml"]) if "yaml" in body else body["contrato"]
        before = await repo.get(doc.get("codigo", ""))
        saved = await repo.save(doc, author=x_persona, as_new_version=bool(body.get("nova_versao", True)))
    except ContractError as exc:
        raise http_error(exc) from exc
    await log.write(store, log.CONTRATO_ALTERADO,
                    f"Contrato {saved['codigo']} salvo como versão {saved['versao']} (vigência {saved['vigencia'].get('inicio')} a {saved['vigencia'].get('fim') or 'indeterminado'})"
                    f"{': ' + body['comentario'] if body.get('comentario') else ''}.",
                    ator=f"persona:{x_persona}", dados={"codigo": saved["codigo"], "versao": saved["versao"],
                                                         "versao_anterior": (before or {}).get("versao"), "nova_versao": bool(body.get("nova_versao", True))})
    return saved


@app.delete("/api/contracts/{code}/versions/{version}")
async def delete_contract_version(code: str, version: int, x_persona: str = Header("OPERADOR")) -> dict:
    await repo.delete_version(code, version)
    await log.write(store, log.CONTRATO_ALTERADO, f"Versão {version} do contrato {code} removida.", ator=f"persona:{x_persona}", dados={"codigo": code, "versao": version})
    return {"ok": True}


@app.post("/api/contracts/reset")
async def reset_contracts(x_persona: str = Header("OPERADOR")) -> dict:
    for code in await store.list_contract_codes():
        await store.delete_contract(code)
    n = await repo.seed(force=True)
    await log.write(store, log.CONTRATO_ALTERADO, f"Contratos restaurados para os exemplos originais ({n}).", ator=f"persona:{x_persona}")
    return {"restaurados": n}


# ------------------------------------------------------------------ shelf
@app.get("/api/shelf")
async def get_shelf() -> list[dict]:
    return shelf.catalog()


@app.post("/api/shelf/{code}/invoke")
async def invoke_operation(code: str, body: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    """Calls a shelf operation directly, outside any process (decoupled use)."""
    if code not in shelf.SHELF:
        raise HTTPException(404, "operação não existe")
    emp_id = body.get("colaborador_id")
    params = body.get("parametros") or {}
    simular = bool(body.get("simular", True))
    t = await today()
    ectx = shelf.ExecCtx(hoje=t, norma=((await repo.norma(t)) or {}).get("parametros") or {}, case_id="avulso")
    async with store.employee_lock(emp_id):
        emp = await store.get_employee(emp_id)
        if not emp:
            raise HTTPException(404, "colaborador não encontrado")
        work = copy.deepcopy(emp)
        try:
            descricao, _ = shelf.apply(code, work, params, ectx)
        except Exception as exc:  # noqa: BLE001
            raise http_error(exc) from exc
        diff = engine.state_diff(emp, work)
        conf = engine.employee_compliance(work, await compliance_ctx())
        if not simular:
            await store.save_employee(work)
            await log.write(store, log.OPERACAO_EXECUTADA, f"Operação avulsa {code}: {descricao}", ator=f"persona:{x_persona}", colaborador_id=emp_id,
                            dados={"parametros": params, "alteracoes": diff})
    return {"descricao": descricao, "simulado": simular, "alteracoes": diff, "conformidade_apos": conf}


# ----------------------------------------------------------------- events
@app.post("/api/events")
async def post_event(body: dict = Body(...)) -> dict:
    event = body.get("evento") or body
    case = await pipeline.submit_event(event, depuracao=bool(body.get("depuracao", False)), breakpoints=body.get("breakpoints") or [])
    return case_summary(case)


# ------------------------------------------------- clock and validity agenda
@app.get("/api/clock")
async def get_clock() -> dict:
    return await clock.state(store)


async def _clock_changed(state: dict, actor: str, mensagem: str) -> dict:
    await log.write(store, log.RELOGIO, mensagem, ator=actor, dados=state)
    emitted = await vigencia.tick(store, pipeline)
    await store.publish({"tipo": "clock", "relogio": state})
    return {**state, "emitidos": [case_summary(c) for c in emitted]}


@app.post("/api/clock/advance")
async def advance_clock(body: dict = Body(default={}), x_persona: str = Header("OPERADOR")) -> dict:
    """Moves the simulated date forward and immediately emits the agenda events that became due."""
    dias = int(body.get("dias", 1))
    if dias <= 0:
        raise HTTPException(400, "informe um número positivo de dias")
    antes = await today()
    state = await clock.advance(store, dias, f"persona:{x_persona}")
    return await _clock_changed(state, f"persona:{x_persona}", f"Relógio simulado avançado {dias} dia(s): de {antes} para {state['hoje']}.")


@app.put("/api/clock")
async def set_clock(body: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    """Sets the simulated date; `data: null` returns to the real calendar."""
    antes = await today()
    try:
        state = await clock.set_date(store, body.get("data"), f"persona:{x_persona}")
    except ValueError as exc:
        raise HTTPException(400, "data inválida; use AAAA-MM-DD") from exc
    destino = state["hoje"] + ("" if state["simulado"] else " (calendário real)")
    return await _clock_changed(state, f"persona:{x_persona}", f"Relógio simulado alterado de {antes} para {destino}.")


@app.get("/api/vigencias")
async def get_agenda() -> dict:
    """Upcoming warning and expiry events of every active program."""
    return await vigencia.agenda(store)


@app.post("/api/vigencias/tick")
async def run_agenda(x_persona: str = Header("OPERADOR")) -> dict:
    """Emits the due agenda events now (the worker also does it periodically)."""
    emitted = await vigencia.tick(store, pipeline, actor=f"persona:{x_persona}")
    return {"emitidos": [case_summary(c) for c in emitted]}


@app.get("/api/scenarios")
async def list_scenarios() -> list[dict]:
    return [s.describe() for s in evgen.SCENARIOS]


async def apply_preparation(prep: dict, cenario: str) -> None:
    for emp_id, patch in (prep or {}).items():
        async with store.employee_lock(emp_id):
            emp = await store.get_employee(emp_id)
            if not emp:
                continue
            before = copy.deepcopy(emp)
            emp.update(patch)
            await store.save_employee(emp)
        await log.write(store, log.COLABORADOR_ALTERADO, f"Preparação do cenário '{cenario}': {', '.join(patch.keys())}.", ator="gerador de cenários",
                        colaborador_id=emp_id, dados={"alteracoes": engine.state_diff(before, emp)})


async def launch_built(built: dict, *, depuracao: bool, breakpoints: list[str], intervalo_ms: int = 0) -> list[dict]:
    # a scenario that plays an agenda event (an expiry, for example) reserves its id
    # before preparing the employee, so the agenda never emits the same event too
    for ev in built["eventos"]:
        for evt_id in (ev.get("metadados") or {}).get("reserva_agenda") or []:
            await store.r.hset(vigencia.EMITTED_KEY, evt_id, f"cenario:{built['cenario']['id']}")
    await apply_preparation(built.get("preparacao") or {}, built["cenario"]["id"])
    cases = []
    for ev in built["eventos"]:
        cases.append(await pipeline.submit_event(copy.deepcopy(ev), cenario=built["cenario"]["id"], depuracao=depuracao, breakpoints=breakpoints))
        if intervalo_ms:
            await asyncio.sleep(intervalo_ms / 1000)
    return cases


@app.post("/api/scenarios/{scenario_id}/generate")
async def generate_scenario(scenario_id: str, body: dict = Body(default={})) -> dict:
    if scenario_id not in evgen.SCENARIO_BY_ID:
        raise HTTPException(404, "cenário não existe")
    t = await today()
    built = evgen.build(scenario_id, await store.list_employees(), await repo.cargos(t), t, seed=body.get("semente"))
    if not built:
        raise HTTPException(409, "nenhum colaborador adequado para este cenário; gere um time maior")
    if not body.get("enviar", True):
        return {"previa": built}
    cases = await launch_built(built, depuracao=bool(body.get("depuracao")), breakpoints=body.get("breakpoints") or [])
    return {"casos": [case_summary(c) for c in cases], "eventos": built["eventos"], "preparacao": built.get("preparacao")}


@app.post("/api/scenarios/burst")
async def burst(body: dict = Body(default={})) -> dict:
    n = min(int(body.get("quantidade", 20)), 2000)
    t = await today()
    items = evgen.random_burst(n, await store.list_employees(), await repo.cargos(t), t, seed=body.get("semente"), categorias=body.get("categorias"))
    intervalo = int(body.get("intervalo_ms", 0))

    async def run() -> None:
        for built in items:
            await launch_built(built, depuracao=False, breakpoints=[], intervalo_ms=0)
            if intervalo:
                await asyncio.sleep(intervalo / 1000)

    task = asyncio.create_task(run())
    BACKGROUND.add(task)
    task.add_done_callback(BACKGROUND.discard)
    return {"agendados": len(items), "cenarios": [b["cenario"]["id"] for b in items]}


@app.post("/api/scenarios/suite")
async def run_suite(body: dict = Body(default={})) -> dict:
    ids = body.get("cenarios") or [s.id for s in evgen.SCENARIOS]
    run_id = new_id("suite")
    doc = {"id": run_id, "criado_em": now_ms(), "status": "EXECUTANDO", "cenarios": ids, "resultados": [], "timeout_s": int(body.get("timeout_s", 1800))}
    await store.set_json(f"{P}:scenario_run:{run_id}", doc)
    await store.r.zadd(f"{P}:scenario_runs", {run_id: now_ms()})
    task = asyncio.create_task(_suite(run_id, ids, body.get("semente", 7), doc["timeout_s"]))
    BACKGROUND.add(task)
    task.add_done_callback(BACKGROUND.discard)
    return doc


async def _suite(run_id: str, ids: list[str], seed: int, timeout_s: int) -> None:
    t = await today()
    gen = evgen.GenCtx(await store.list_employees(), await repo.cargos(t), t, random.Random(seed))
    results = []
    for sid in ids:
        sc = evgen.SCENARIO_BY_ID.get(sid)
        if not sc:
            continue
        built = evgen.build(sid, gen.employees, gen.cargos, t, gen=gen)
        if not built:
            results.append({"cenario": sc.describe(), "resultado": "SEM_CANDIDATO", "casos": []})
            continue
        cases = await launch_built(built, depuracao=False, breakpoints=[])
        results.append({"cenario": sc.describe(), "casos": [c["id"] for c in cases], "resultado": "EXECUTANDO"})
    doc = await store.get_json(f"{P}:scenario_run:{run_id}")
    doc["resultados"] = results
    await store.set_json(f"{P}:scenario_run:{run_id}", doc)
    deadline = time.time() + timeout_s
    while True:
        pending = False
        for r in results:
            if r["resultado"] == "SEM_CANDIDATO":
                continue
            statuses = []
            agent_only = True
            for cid in r["casos"]:
                c = await store.get_case(cid) or {}
                statuses.append(c.get("status"))
                for ap_id in c.get("aprovacoes") or []:
                    ap = await store.get_approval(ap_id) or {}
                    if ap.get("status") == "PENDENTE" and ap.get("tipo") == "EXCECAO_ELEGIBILIDADE":
                        agent_only = False
            r["status_casos"] = statuses
            r["status_rotulos"] = [STATUS_LABELS.get(s, s) for s in statuses]
            if any(s in (NA_FILA, PROCESSANDO) for s in statuses):
                r["resultado"] = "EXECUTANDO"
                pending = True
            elif all(s in r["cenario"]["esperado"] for s in statuses):
                r["resultado"] = "OK"
            elif any(s == "AGUARDANDO_APROVACAO" for s in statuses) and agent_only and set(r["cenario"]["esperado"]) & {"CONCLUIDO", "CONCLUIDO_COM_RESSALVAS"}:
                r["resultado"] = "DIVERGENCIA_AGENTE"
            elif any(s == "AGUARDANDO_AGENTE" for s in statuses):
                r["resultado"] = "AGUARDANDO_AGENTE"
                pending = True
            else:
                r["resultado"] = "DIVERGENTE"
        doc["resultados"] = results
        doc["resumo"] = {k: sum(1 for r in results if r["resultado"] == k) for k in
                         ("OK", "DIVERGENTE", "DIVERGENCIA_AGENTE", "EXECUTANDO", "AGUARDANDO_AGENTE", "SEM_CANDIDATO")}
        if not pending or time.time() > deadline:
            doc["status"] = "CONCLUIDA" if not pending else "TEMPO_ESGOTADO"
            doc["finalizado_em"] = now_ms()
            await store.set_json(f"{P}:scenario_run:{run_id}", doc)
            await store.publish({"tipo": "suite", "id": run_id})
            return
        await store.set_json(f"{P}:scenario_run:{run_id}", doc)
        await store.publish({"tipo": "suite", "id": run_id})
        await asyncio.sleep(2)


@app.get("/api/scenarios/suite")
async def list_suites() -> list[dict]:
    ids = await store.r.zrevrange(f"{P}:scenario_runs", 0, 19)
    out = []
    for i in ids:
        d = await store.get_json(f"{P}:scenario_run:{i}")
        if d:
            out.append({k: d.get(k) for k in ("id", "criado_em", "status", "resumo", "finalizado_em")})
    return out


@app.get("/api/scenarios/suite/{run_id}")
async def get_suite(run_id: str) -> dict:
    d = await store.get_json(f"{P}:scenario_run:{run_id}")
    if not d:
        raise HTTPException(404, "execução não encontrada")
    return d


# ------------------------------------------------------------------ cases
@app.get("/api/cases")
async def list_cases(limit: int = 300, status: str | None = None) -> list[dict]:
    cases = [case_summary(c) for c in await store.list_cases(limit=limit)]
    if status:
        wanted = set(status.split(","))
        cases = [c for c in cases if c["status"] in wanted]
    return cases


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    case = await store.get_case(case_id)
    if not case:
        raise HTTPException(404, "caso não encontrado")
    approvals = [await store.get_approval(a) for a in case.get("aprovacoes") or []]
    case["proximo_passo"] = case.get("proximo_passo") or next_step(case)
    return {"caso": case, "aprovacoes": [a for a in approvals if a], "log": await log.query(store, case_id=case_id, limit=1000)}


@app.post("/api/cases/{case_id}/release")
async def release_case(case_id: str, body: dict = Body(default={}), x_persona: str = Header("OPERADOR")) -> dict:
    try:
        return case_summary(await pipeline.release(case_id, continuar=bool(body.get("continuar")), actor=x_persona))
    except ValueError as exc:
        raise http_error(exc) from exc


@app.post("/api/cases/{case_id}/retry")
async def retry_case(case_id: str, body: dict = Body(default={}), x_persona: str = Header("OPERADOR")) -> dict:
    try:
        return case_summary(await pipeline.retry_from(case_id, body.get("estagio", "intake"), event_patch=body.get("evento"),
                                                      depuracao=body.get("depuracao"), actor=x_persona))
    except ValueError as exc:
        raise http_error(exc) from exc


@app.post("/api/cases/{case_id}/cancel")
async def cancel_case(case_id: str, x_persona: str = Header("OPERADOR")) -> dict:
    try:
        return case_summary(await pipeline.cancel(case_id, actor=x_persona))
    except ValueError as exc:
        raise http_error(exc) from exc


@app.post("/api/cases/{case_id}/debug")
async def debug_case(case_id: str, body: dict = Body(default={})) -> dict:
    case = await store.get_case(case_id)
    if not case:
        raise HTTPException(404, "caso não encontrado")
    if "depuracao" in body:
        case["depuracao"] = bool(body["depuracao"])
    if "breakpoints" in body:
        case["breakpoints"] = body["breakpoints"]
    await store.save_case(case)
    return case_summary(case)


# -------------------------------------------------------------- approvals
@app.get("/api/approvals")
async def list_approvals(pendentes: bool = False, limit: int = 300) -> list[dict]:
    return await store.list_approvals(pending_only=pendentes, limit=limit)


@app.post("/api/approvals/{ap_id}/decide")
async def decide(ap_id: str, body: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    try:
        return await pipeline.decide(ap_id, body.get("persona") or x_persona, body.get("decisao", ""), body.get("justificativa", ""))
    except (ValueError, PermissionError) as exc:
        raise http_error(exc) from exc


# ------------------------------------------------------------------- logs
@app.get("/api/logs")
async def get_logs(limit: int = 300, tipo: str | None = None, case_id: str | None = None, colaborador_id: str | None = None,
                   texto: str | None = None, antes: str | None = None) -> list[dict]:
    return await log.query(store, limit=limit, tipo=tipo, case_id=case_id, colaborador_id=colaborador_id, texto=texto, before=antes)


@app.get("/api/logs/export", response_class=PlainTextResponse)
async def export_logs(limite: int = Query(20000)) -> PlainTextResponse:
    raw = await store.r.xrange(LOG_STREAM, count=limite)
    lines = []
    for i, f in raw:
        entry = dict(f, id=i)
        try:
            entry["dados"] = json.loads(entry.get("dados") or "{}")
        except json.JSONDecodeError:
            pass
        lines.append(json.dumps(entry, ensure_ascii=False))
    return PlainTextResponse("\n".join(lines), headers={"Content-Disposition": "attachment; filename=audit-log.jsonl"})


# ------------------------------------------------------------------ stats
@app.get("/api/stats")
async def stats() -> dict:
    cases = await store.list_cases(limit=2000)
    by_status: dict[str, int] = {}
    by_stage: dict[str, dict[str, int]] = {s: {} for s in STAGE_KEYS}
    durations: dict[str, list[int]] = {s: [] for s in STAGE_KEYS}
    agent_ms: list[int] = []
    agent_rec = {"APROVADO": 0, "REPROVADO": 0}
    by_type: dict[str, int] = {}
    for c in cases:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1
        by_type[c.get("evento_tipo") or "?"] = by_type.get(c.get("evento_tipo") or "?", 0) + 1
        if c["status"] not in FINAL_STATUSES:
            st = c.get("estagio") or "intake"
            by_stage.setdefault(st, {})[c["status"]] = by_stage.setdefault(st, {}).get(c["status"], 0) + 1
        for s, e in (c.get("etapas") or {}).items():
            if e.get("duracao_ms") is not None and s in durations:
                durations[s].append(e["duracao_ms"])
        for k in ("agente_auditoria", "agente_conferencia"):
            a = c.get(k)
            if a:
                if a.get("duracao_ms") is not None and not a.get("cache"):
                    agent_ms.append(a["duracao_ms"])
                agent_rec[a.get("recomendacao", "REPROVADO")] = agent_rec.get(a.get("recomendacao", "REPROVADO"), 0) + 1
    now = now_ms()
    last_min = sum(1 for c in cases if c.get("finalizado_em") and now - c["finalizado_em"] < 60000)
    return {
        "total_casos": await store.count_cases(), "por_status": by_status, "por_estagio": by_stage, "por_tipo": by_type,
        "filas": await store.queue_stats(STAGE_KEYS),
        "duracao_media_ms": {s: (sum(v) // len(v) if v else None) for s, v in durations.items()},
        "agente": {"chamadas": len(agent_ms), "duracao_media_ms": (sum(agent_ms) // len(agent_ms)) if agent_ms else None, "recomendacoes": agent_rec,
                   "saude": await store.get_json(f"{P}:agent:health")},
        "aprovacoes_pendentes": await store.r.scard(f"{P}:approvals:pending"),
        "finalizados_ultimo_minuto": last_min,
        "controle": await store.control(),
        "relogio": await clock.state(store),
        "gastos": await ledger.status(await store.settings()),
    }


@app.post("/api/reset")
async def reset(body: dict = Body(default={}), x_persona: str = Header("OPERADOR")) -> dict:
    await store.reset_runtime()
    await emb.clear(store)
    await store.ensure_groups(STAGE_KEYS)
    if body.get("colaboradores"):
        await _generate(int(body.get("tamanho", 80)), int(body.get("semente", 42)), float(body.get("desvio_percentual", 15)), replace=True,
                        actor=f"persona:{x_persona}")
    await log.write(store, log.CONTROLE, "Laboratório reiniciado: casos, aprovações, filas e log limpos.", ator=f"persona:{x_persona}")
    await store.publish({"tipo": "reset"})
    return {"ok": True}


# ------------------------------------------------------------- phase 2: visibility, embeddings, questions
async def load_facts(limit: int = 5000) -> list[dict]:
    cases = await store.list_cases(limit=limit)
    ap_ids = {a for c in cases for a in (c.get("aprovacoes") or []) if isinstance(a, str)}
    approvals = {}
    if ap_ids:
        raws = await store.r.mget([f"{P}:approval:{a}" for a in ap_ids])
        approvals = {json.loads(x)["id"]: json.loads(x) for x in raws if x}
    employees = {e["id"]: e for e in await store.list_employees()}
    return [factsmod.case_fact(c, approvals, employees.get(c.get("colaborador_id"))) for c in cases]


@app.get("/api/insights")
async def insights(periodo_horas: float = 0, balde_min: int = 5, baldes: int = 24) -> dict:
    facts = await load_facts()
    if periodo_horas:
        facts = factsmod.apply_filters(facts, {"periodo_horas": periodo_horas})
    ctx = await compliance_ctx()
    comp = [engine.employee_compliance(e, ctx) for e in await store.list_employees()]
    result = factsmod.insights(facts, queues=await store.queue_stats(STAGE_KEYS),
                               pending_approvals=await store.list_approvals(pending_only=True), employees_compliance=comp,
                               bucket_min=max(1, balde_min), buckets=max(4, min(baldes, 96)))
    result["indice"] = await emb.status(store)
    result["agente_saude"] = await store.get_json(f"{P}:agent:health")
    return result


@app.get("/api/facts")
async def list_facts(evento_tipo: str | None = None, status: str | None = None, colaborador_id: str | None = None,
                     regra_falha: str | None = None, periodo_horas: float = 0, agrupar_por: str | None = None, limite: int = 200) -> dict:
    facts = await load_facts()
    filtros = {"evento_tipo": evento_tipo, "status": status, "colaborador_id": colaborador_id, "regra_falha": regra_falha,
               "periodo_horas": periodo_horas}
    sel = factsmod.apply_filters(facts, filtros)
    out = {"total": len(sel), "fatos": sel[:limite]}
    if agrupar_por:
        if agrupar_por not in factsmod.GROUP_FIELDS:
            raise HTTPException(400, f"agrupar_por deve ser um de {factsmod.GROUP_FIELDS}")
        out["agrupamento"] = factsmod.group_count(sel, agrupar_por, 50)
    return out


@app.get("/api/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    """Prometheus exposition, for Grafana or any scraper."""
    facts = await load_facts()
    lines = ["# HELP hrlab_cases Casos por status", "# TYPE hrlab_cases gauge"]
    for row in factsmod.group_count(facts, "status", 100):
        lines.append(f'hrlab_cases{{status="{row["valor"]}"}} {row["quantidade"]}')
    lines += ["# HELP hrlab_cases_by_event Casos por tipo de evento", "# TYPE hrlab_cases_by_event gauge"]
    for row in factsmod.group_count(facts, "evento_tipo", 100):
        lines.append(f'hrlab_cases_by_event{{evento="{row["valor"]}"}} {row["quantidade"]}')
    lines += ["# HELP hrlab_queue_messages Mensagens por fila", "# TYPE hrlab_queue_messages gauge"]
    for stage, q in (await store.queue_stats(STAGE_KEYS)).items():
        lines.append(f'hrlab_queue_messages{{estagio="{stage}",tipo="pendentes"}} {q.get("pendentes", 0)}')
        lines.append(f'hrlab_queue_messages{{estagio="{stage}",tipo="atraso"}} {q.get("atraso") or 0}')
        lines.append(f'hrlab_queue_consumers{{estagio="{stage}"}} {q.get("consumidores", 0)}')
    lines += ["# HELP hrlab_stage_duration_ms Duração por estágio", "# TYPE hrlab_stage_duration_ms summary"]
    for s in STAGE_KEYS:
        vals = [f["etapas"][s]["duracao_ms"] for f in facts if f["etapas"][s]["duracao_ms"] is not None]
        for qn in (50, 95):
            v = factsmod.percentile(vals, qn)
            if v is not None:
                lines.append(f'hrlab_stage_duration_ms{{estagio="{s}",quantile="{qn / 100}"}} {v}')
        lines.append(f'hrlab_stage_duration_ms_count{{estagio="{s}"}} {len(vals)}')
    perf = agent_metrics.summarize(await agent_metrics.load(store, now_ms() - 86_400_000), desde_ms=now_ms() - 86_400_000, ate_ms=now_ms())
    lines += ["# HELP hrlab_agent_processing_ms Tempo de processamento dos agentes nas últimas 24 horas",
              "# TYPE hrlab_agent_processing_ms summary"]
    for motor, row in perf["por_motor"].items():
        for qn in ("p50", "p95"):
            if row["processamento_ms"][qn] is not None:
                lines.append(f'hrlab_agent_processing_ms{{motor="{motor}",quantile="0.{qn[1:]}"}} {row["processamento_ms"][qn]}')
            if row["resposta_ms"][qn] is not None:
                lines.append(f'hrlab_agent_response_ms{{motor="{motor}",quantile="0.{qn[1:]}"}} {row["resposta_ms"][qn]}')
        lines.append(f'hrlab_agent_calls{{motor="{motor}"}} {row["chamadas"]}')
        lines.append(f'hrlab_agent_errors{{motor="{motor}"}} {row["erros"]}')
    health = await store.get_json(f"{P}:agent:health") or {}
    st = await emb.status(store)
    lines += [
        f"hrlab_approvals_pending {await store.r.scard(f'{P}:approvals:pending')}",
        f"hrlab_agent_up {1 if health.get('ok') else 0}",
        f"hrlab_index_documents {st['documentos']}",
        f"hrlab_index_dirty {st['pendentes']}",
        f"hrlab_index_simulated {st['simulados']}",
    ]
    return "\n".join(lines) + "\n"


@app.get("/api/index/status")
async def index_status() -> dict:
    return await emb.status(store)


@app.post("/api/index/rebuild")
async def index_rebuild(body: dict = Body(default={}), x_persona: str = Header("OPERADOR")) -> dict:
    if body.get("limpar"):
        await emb.clear(store)
    n = await indexer.mark_all(store)
    await log.write(store, log.CONTROLE, f"Reindexação de embeddings solicitada: {n} documento(s) marcados.", ator=f"persona:{x_persona}")
    return {"marcados": n}


@app.post("/api/search")
async def semantic_search(body: dict = Body(...)) -> dict:
    texto = str(body.get("texto") or "").strip()
    if not texto:
        raise HTTPException(400, "informe o texto da busca")
    try:
        return await emb.search(store, texto, k=int(body.get("k", 10)), filtros=body.get("filtros") or {})
    except agent.AgentUnavailable as exc:
        raise HTTPException(503, f"Provedor de embeddings indisponível para a busca ({exc}). "
                                 "Ative o modo simulado nas configurações para buscar sem IA.") from exc


@app.post("/api/ask")
async def ask_question(body: dict = Body(...), x_persona: str = Header("OPERADOR")) -> dict:
    pergunta = str(body.get("pergunta") or "").strip()
    if len(pergunta) < 3:
        raise HTTPException(400, "escreva uma pergunta")
    try:
        return await ask.answer(store, pergunta, await load_facts(), await repo.event_types(), persona=x_persona)
    except agent.AgentUnavailable as exc:
        raise HTTPException(503, f"IA indisponível ({exc}). Ative o modo simulado nas configurações para responder sem IA.") from exc


@app.get("/api/ask/history")
async def ask_history(limite: int = 30) -> list[dict]:
    return await ask.history(store, limite)


# ----------------------------------------------------------------- stream
@app.get("/api/stream")
async def stream() -> StreamingResponse:
    async def gen():
        pubsub = store.r.pubsub()
        await pubsub.subscribe(UPDATES_CHANNEL)
        try:
            yield "retry: 2000\n\n"
            last_ping = time.time()
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    yield f"data: {msg['data']}\n\n"
                if time.time() - last_ping > 15:
                    yield ": ping\n\n"
                    last_ping = time.time()
        finally:
            await pubsub.unsubscribe(UPDATES_CHANNEL)
            await pubsub.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
