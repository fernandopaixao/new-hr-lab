"""Deterministic core: rule evaluation, eligibility, target state, planning and audit.

Everything here is pure (no IO) so it can be tested and explained step by step.
"""
from __future__ import annotations

import copy
from typing import Any

from . import shelf
from .context import Ctx, render
from .expr import ExpressionError, evaluate, resolve_value, unwrap


# --------------------------------------------------------------------- rules
def contract_ref(doc: dict | None) -> str:
    if not doc:
        return "?"
    return f"{doc.get('codigo')} v{doc.get('versao')}"


def eval_rule(rule: dict, names: dict, origem: str) -> dict:
    tipo = rule.get("tipo", "BLOQUEANTE")
    out = {
        "id": rule.get("id"), "descricao": rule.get("descricao"), "tipo": tipo, "origem": origem,
        "expressao": rule.get("expressao"), "base_legal": rule.get("base_legal"),
        "aprovadores": rule.get("aprovadores") or [],
    }
    try:
        ok = bool(evaluate(str(rule.get("expressao", "True")), names))
        out["passou"] = ok
        if ok:
            out["explicacao"] = f"Atende: {rule.get('descricao')}."
        else:
            out["explicacao"] = render(rule.get("explicacao_falha"), names) or f"Não atende: {rule.get('descricao')}."
    except ExpressionError as exc:
        out["passou"] = False
        out["erro"] = str(exc)
        out["explicacao"] = f"Erro ao avaliar a regra ({exc}); tratada como não atendida."
    return out


def eval_rules(rules: list[dict], names: dict, origem: str) -> list[dict]:
    return [eval_rule(r, names, origem) for r in rules or []]


def summarize_rules(results: list[dict]) -> dict:
    bloq = [r for r in results if not r["passou"] and r["tipo"] == "BLOQUEANTE"]
    exc = [r for r in results if not r["passou"] and r["tipo"] == "EXCECIONAVEL"]
    alert = [r for r in results if not r["passou"] and r["tipo"] == "ALERTA"]
    return {"bloqueantes": bloq, "excecionaveis": exc, "alertas": alert, "total": len(results),
            "atendidas": sum(1 for r in results if r["passou"])}


# --------------------------------------------------------------- eligibility
def eligibility(processo: dict, ctx: Ctx, colaborador: dict, cargo_alvo: str | None) -> dict:
    names = ctx.names(colaborador, cargo_alvo=cargo_alvo)
    results = eval_rules((processo.get("elegibilidade") or {}).get("regras") or [], names, contract_ref(processo))
    destino = ctx.cargo(cargo_alvo) if cargo_alvo else None
    if (processo.get("elegibilidade") or {}).get("incluir_entrada_cargo_alvo") and destino:
        results += eval_rules(destino.get("elegibilidade_entrada") or [], names, contract_ref(destino))
    s = summarize_rules(results)
    if s["bloqueantes"]:
        decisao = "NAO_ELEGIVEL"
        explicacao = "Não elegível: " + " ".join(r["explicacao"] for r in s["bloqueantes"])
    elif s["excecionaveis"]:
        decisao = "EXCECAO_NECESSARIA"
        explicacao = "Elegível somente com exceção aprovada: " + " ".join(r["explicacao"] for r in s["excecionaveis"])
    else:
        decisao = "ELEGIVEL"
        explicacao = f"Elegível: todas as {s['total']} regras de elegibilidade foram atendidas."
    if s["alertas"]:
        explicacao += " Alertas: " + " ".join(r["explicacao"] for r in s["alertas"])
    return {"decisao": decisao, "explicacao": explicacao, "regras": results, "resumo": {k: len(v) if isinstance(v, list) else v for k, v in s.items()}}


# ------------------------------------------------------------- target state
def target_state(emp: dict, ctx: Ctx) -> dict:
    """Computes the to-be state demanded by the position contract and the norm."""
    names = ctx.names(emp)
    cargo = ctx.cargo(emp.get("cargo"))
    norma = ctx.norma
    ref_cargo = contract_ref(cargo) if cargo else None
    tobe: dict[str, Any] = {"fontes": {}, "fonte_cargo": ref_cargo}
    ref_norma = contract_ref(norma) if norma else None
    beneficios: list[dict] = []
    verbas: list[dict] = []
    if cargo:
        ea = cargo.get("estado_alvo") or {}
        tobe["regime_jornada"] = ea.get("regime_jornada")
        tobe["jornada_horas"] = ea.get("jornada_horas")
        tobe["faixa_salarial"] = ea.get("faixa_salarial")
        for v in ea.get("verbas") or []:
            verbas.append({"codigo": v["codigo"], "nome": v.get("nome"), "valor": round(float(resolve_value(v.get("valor"), names) or 0), 2),
                           "base_legal": v.get("base_legal"), "fonte": ref_cargo})
        for b in ea.get("beneficios") or []:
            beneficios.append({**{k: b.get(k) for k in ("codigo", "nome", "plano")}, "valor": resolve_value(b.get("valor"), names),
                               "fonte": ref_cargo})
        tobe["acessos"] = [{"codigo": a, "fonte": ref_cargo} for a in ea.get("acessos") or []]
        tobe["equipamentos"] = [{"codigo": e, "fonte": ref_cargo} for e in ea.get("equipamentos") or []]
        tobe["clausulas"] = [{**c, "fonte": ref_cargo} for c in ea.get("clausulas") or []]
        tobe["certificacoes_exigidas"] = ea.get("certificacoes_exigidas") or []
    for b in norma.get("beneficios") or []:
        cond = b.get("quando")
        try:
            applies = bool(resolve_value(cond, names)) if cond else True
        except ExpressionError:
            applies = False
        if applies:
            val = resolve_value(b.get("valor"), names)
            beneficios.append({"codigo": b["codigo"], "nome": b.get("nome"), "plano": b.get("plano"),
                               "valor": round(float(val), 2) if isinstance(val, (int, float)) else val,
                               "base_legal": b.get("base_legal"), "fonte": ref_norma})
    tobe["beneficios"] = beneficios
    tobe["verbas"] = verbas
    if emp.get("uf"):
        try:
            tobe["sindicato"] = names["sindicato_da_uf"](emp["uf"])
        except Exception:  # noqa: BLE001
            tobe["sindicato"] = None
    overrides = (norma.get("estado_por_situacao") or {}).get(emp.get("situacao") or "", {})
    for key, value in overrides.items():
        tobe[key] = [{"codigo": c, "fonte": ref_norma} for c in value] if key in ("acessos", "equipamentos") else list(value)
        tobe["fontes"][key] = f"{ref_norma} (estado por situação {emp.get('situacao')})"
    tobe["_override_verbas"] = "verbas" in overrides
    return tobe


def _item(code: str, params: dict, motivo: str, fonte: str | None, base_legal: str | None = None) -> dict:
    spec = shelf.SHELF[code]
    return {"operacao": code, "nome": spec.nome, "sistema": spec.sistema, "parametros": params, "motivo": motivo,
            "fonte": fonte, "base_legal": base_legal, "origem": "DERIVADO_DO_CONTRATO"}


def diff_to_ops(emp: dict, tobe: dict) -> list[dict]:
    ops: list[dict] = []
    cargo_nome = emp.get("cargo")
    if tobe.get("jornada_horas") is not None and emp.get("situacao") != "DESLIGADO" and (
            tobe["jornada_horas"] != emp.get("jornada_horas") or tobe.get("regime_jornada") != emp.get("regime_jornada")):
        ops.append(_item("ALTERAR_JORNADA", {"horas": tobe["jornada_horas"], "regime": tobe.get("regime_jornada")},
                         f"Contrato do cargo {cargo_nome} define jornada de {tobe['jornada_horas']}h no regime {tobe.get('regime_jornada')}; atual é {emp.get('jornada_horas')}h/{emp.get('regime_jornada')}.",
                         tobe.get("fonte_cargo"), "CLT art. 224 / art. 62"))
    if tobe.get("sindicato") and emp.get("situacao") != "DESLIGADO" and tobe["sindicato"] != emp.get("sindicato"):
        ops.append(_item("ALTERAR_SINDICATO", {"sindicato": tobe["sindicato"]},
                         f"Lotação em {emp.get('uf')} pertence à base do {tobe['sindicato']}; enquadramento atual é {emp.get('sindicato')}.",
                         "NORMA (base territorial)", "CLT art. 511 e 516"))
    faixa = tobe.get("faixa_salarial") or {}
    if faixa.get("min") and emp.get("situacao") in ("ATIVO", "AFASTADO") and float(emp.get("salario_base") or 0) < float(faixa["min"]):
        ops.append(_item("ALTERAR_SALARIO", {"novo_salario": float(faixa["min"]), "motivo": "enquadramento na faixa"},
                         f"Salário R$ {emp.get('salario_base')} abaixo do mínimo da faixa do cargo {cargo_nome} (R$ {faixa['min']}); enquadramento.",
                         tobe.get("fonte_cargo"), "Política de remuneração"))
    # Verbas: only those owned by contracts are managed, unless the situation clears them all.
    current = {v["codigo"]: v for v in emp.get("verbas") or [] if v.get("recorrente", True)}
    wanted = {v["codigo"]: v for v in tobe.get("verbas") or []}
    for code, v in wanted.items():
        if code not in current:
            ops.append(_item("ADICIONAR_VERBA", {"codigo": code, "nome": v.get("nome"), "valor": v["valor"], "recorrente": True, "origem": "CONTRATO"},
                             f"Contrato {v.get('fonte')} exige a verba {code} de R$ {v['valor']} e o colaborador não a possui.",
                             v.get("fonte"), v.get("base_legal")))
        elif abs(float(current[code].get("valor") or 0) - float(v["valor"])) > 0.01:
            ops.append(_item("AJUSTAR_VERBA", {"codigo": code, "valor": v["valor"]},
                             f"Verba {code} deve valer R$ {v['valor']} pelo contrato {v.get('fonte')}; atual R$ {current[code].get('valor')}.",
                             v.get("fonte"), v.get("base_legal")))
    for code, v in current.items():
        if code in wanted:
            continue
        if v.get("origem", "CONTRATO") == "CONTRATO" or tobe.get("_override_verbas"):
            ops.append(_item("REMOVER_VERBA", {"codigo": code},
                             f"Verba {code} não é prevista pelo estado alvo ({'situação ' + str(emp.get('situacao')) if tobe.get('_override_verbas') else 'contrato do cargo ' + str(cargo_nome)}).",
                             tobe.get("fontes", {}).get("verbas"), "CLT art. 468 par. 2" if code in ("GRAT_FUNCAO", "GRAT_GESTAO") else None))
    cur_b = {b["codigo"]: b for b in emp.get("beneficios") or []}
    want_b = {b["codigo"]: b for b in tobe.get("beneficios") or []}
    for code, b in want_b.items():
        if code not in cur_b:
            ops.append(_item("ADICIONAR_BENEFICIO", {"codigo": code, "nome": b.get("nome"), "plano": b.get("plano"), "valor": b.get("valor")},
                             f"Contrato {b.get('fonte')} prevê o benefício {code} (plano {b.get('plano')}) e o colaborador não o possui.",
                             b.get("fonte"), b.get("base_legal")))
        else:
            c = cur_b[code]
            valor_diff = b.get("valor") is not None and c.get("valor") is not None and abs(float(c["valor"]) - float(b["valor"])) > 0.01
            if c.get("plano") != b.get("plano") or valor_diff:
                ops.append(_item("ALTERAR_BENEFICIO", {"codigo": code, "plano": b.get("plano"), "valor": b.get("valor")},
                                 f"Benefício {code} deve ser plano {b.get('plano')}{' valor ' + str(b.get('valor')) if b.get('valor') is not None else ''} pelo contrato {b.get('fonte')}; atual {c.get('plano')}.",
                                 b.get("fonte"), b.get("base_legal")))
    for code in cur_b:
        if code not in want_b:
            ops.append(_item("REMOVER_BENEFICIO", {"codigo": code},
                             f"Benefício {code} não é previsto no estado alvo do cargo {cargo_nome} na situação {emp.get('situacao')}.",
                             tobe.get("fontes", {}).get("beneficios"), None))
    for key, add_op, rm_op, label in (("acessos", "CONCEDER_ACESSO", "REVOGAR_ACESSO", "acesso"),
                                      ("equipamentos", "PROVISIONAR_EQUIPAMENTO", "RECOLHER_EQUIPAMENTO", "equipamento")):
        if key not in tobe:
            continue
        cur = list(emp.get(key) or [])
        want = [x["codigo"] for x in tobe[key]]
        param = "acesso" if key == "acessos" else "equipamento"
        fonte = tobe.get("fontes", {}).get(key) or (tobe[key][0]["fonte"] if tobe[key] else None)
        for code in want:
            if code not in cur:
                ops.append(_item(add_op, {param: code}, f"Estado alvo ({fonte}) prevê o {label} {code}.", fonte))
        for code in cur:
            if code not in want:
                ops.append(_item(rm_op, {param: code}, f"O {label} {code} não é previsto no estado alvo ({fonte}) do cargo {cargo_nome} na situação {emp.get('situacao')}.", fonte,
                                 "Política de segurança da informação" if key == "acessos" else None))
    if "clausulas" in tobe and emp.get("situacao") not in ("DESLIGADO", "GARDEN_LEAVE"):
        cur_c = {c["codigo"] for c in emp.get("clausulas") or []}
        want_c = {c["codigo"]: c for c in tobe["clausulas"]}
        for code, c in want_c.items():
            if code not in cur_c:
                ops.append(_item("INCLUIR_CLAUSULA", {"codigo": code, "nome": c.get("nome"), "parametros": c.get("parametros") or {}},
                                 f"Contrato {c.get('fonte')} exige a cláusula {code} para o cargo {cargo_nome}.", c.get("fonte")))
        for code in cur_c:
            if code not in want_c:
                ops.append(_item("REMOVER_CLAUSULA", {"codigo": code},
                                 f"Cláusula {code} não se aplica ao cargo {cargo_nome}.", None))
    return ops


# ------------------------------------------------------------------- planning
def _key(item: dict) -> tuple:
    p = item.get("parametros") or {}
    return (item["operacao"], p.get("codigo") or p.get("acesso") or p.get("equipamento") or p.get("tipo") or p.get("evento") or "")


def plan(processo: dict, ctx: Ctx, colaborador: dict, cargo_alvo: str | None) -> dict:
    """Builds the execution plan. Returns plan items, discarded items, projection and target state."""
    names = ctx.names(colaborador, cargo_alvo=cargo_alvo)
    orq = processo.get("orquestracao") or {}
    explicit: list[dict] = []
    descartadas: list[dict] = []
    problemas: list[str] = []
    for spec in orq.get("operacoes") or []:
        code = spec.get("operacao")
        quando = spec.get("quando")
        if quando:
            try:
                cond = bool(resolve_value(quando if str(quando).startswith("=") else "=" + str(quando), names))
            except ExpressionError as exc:
                problemas.append(f"{code}: erro na condição ({exc})")
                cond = False
            if not cond:
                descartadas.append({"operacao": code, "motivo_descarte": f"Condição não atendida: {str(quando).lstrip('=')}",
                                    "motivo_contrato": spec.get("motivo")})
                continue
        try:
            params = resolve_value(spec.get("parametros") or {}, names)
        except ExpressionError as exc:
            problemas.append(f"{code}: erro ao resolver parâmetros ({exc})")
            continue
        item = _item(code, unwrap(params), spec.get("motivo") or "", contract_ref(processo), spec.get("base_legal"))
        item["origem"] = "PROCESSO"
        explicit.append(item)

    ectx = shelf.ExecCtx(hoje=ctx.today, norma=dict(ctx.norma.get("parametros") or {}), dry_run=True)
    projected = copy.deepcopy(colaborador) if colaborador else {}
    for item in explicit:
        try:
            shelf.apply(item["operacao"], projected, item["parametros"], ectx)
        except Exception as exc:  # noqa: BLE001
            item["falha_simulada"] = str(exc)
            problemas.append(f"{item['operacao']} falharia na simulação: {exc}")

    tobe: dict = {}
    derived: list[dict] = []
    if orq.get("derivar_estado_alvo", True):
        tobe = target_state(projected, ctx)
        existing = {_key(i) for i in explicit}
        for item in diff_to_ops(projected, tobe):
            if _key(item) in existing or (item["operacao"] == "ALTERAR_SALARIO" and any(e["operacao"] in ("ALTERAR_SALARIO", "APLICAR_REAJUSTE") for e in explicit)):
                descartadas.append({"operacao": item["operacao"], "motivo_descarte": "Já coberta por operação explícita do processo."})
                continue
            derived.append(item)
        # salary changes affect percentage based allowances: recompute after applying derived salary/jornada first
        for item in derived:
            try:
                shelf.apply(item["operacao"], projected, item["parametros"], ectx)
            except Exception as exc:  # noqa: BLE001
                item["falha_simulada"] = str(exc)
                problemas.append(f"{item['operacao']} falharia na simulação: {exc}")
        # second pass: allowances depending on the new salary
        tobe2 = target_state(projected, ctx)
        for item in diff_to_ops(projected, tobe2):
            if item["operacao"] in ("ADICIONAR_VERBA", "AJUSTAR_VERBA"):
                derived.append(item)
                try:
                    shelf.apply(item["operacao"], projected, item["parametros"], ectx)
                except Exception as exc:  # noqa: BLE001
                    problemas.append(f"{item['operacao']} falharia na simulação: {exc}")
        tobe = tobe2

    items = explicit + derived
    items.sort(key=lambda i: shelf.SHELF[i["operacao"]].ordem)
    for seq, item in enumerate(items, start=1):
        item["seq"] = seq
        item["status"] = "PLANEJADA"
        item.setdefault("id", f"op{seq:02d}")
    tobe_public = {k: v for k, v in tobe.items() if not k.startswith("_")}
    return {"operacoes": items, "descartadas": descartadas, "problemas": problemas, "projetado": projected,
            "estado_alvo": tobe_public, "resumo": explain_plan(items, descartadas)}


def explain_plan(items: list[dict], descartadas: list[dict]) -> str:
    if not items:
        return "Nenhuma operação necessária: o estado atual já corresponde ao estado alvo do contrato."
    por_sistema: dict[str, int] = {}
    for i in items:
        por_sistema[i["sistema"]] = por_sistema.get(i["sistema"], 0) + 1
    partes = ", ".join(f"{n} em {s}" for s, n in sorted(por_sistema.items()))
    derivadas = sum(1 for i in items if i["origem"] == "DERIVADO_DO_CONTRATO")
    return (f"{len(items)} operação(ões) planejada(s) ({partes}); {len(items) - derivadas} definida(s) pelo processo e "
            f"{derivadas} derivada(s) da diferença entre o estado atual e o estado alvo do contrato. "
            f"{len(descartadas)} operação(ões) avaliada(s) e descartada(s).")


# ------------------------------------------------------- compliance and audit
def compliance_rules(ctx: Ctx, emp: dict) -> list[tuple[list[dict], str]]:
    out = []
    if ctx.norma:
        out.append((ctx.norma.get("compliance") or [], contract_ref(ctx.norma)))
    cargo = ctx.cargo(emp.get("cargo"))
    if cargo and emp.get("situacao") != "DESLIGADO":
        # position rules describe people holding the position; after dismissal only the norm applies
        out.append((cargo.get("compliance") or [], contract_ref(cargo)))
    return out


def _decide(results: list[dict]) -> tuple[str, dict]:
    s = summarize_rules(results)
    if s["bloqueantes"]:
        decisao = "REPROVADO"
    elif s["excecionaveis"]:
        decisao = "REQUER_APROVACAO"
    elif s["alertas"]:
        decisao = "APROVADO_COM_RESSALVAS"
    else:
        decisao = "APROVADO"
    return decisao, {k: len(v) if isinstance(v, list) else v for k, v in s.items()}


def audit_plan(processo: dict, ctx: Ctx, anterior: dict, projetado: dict, plan_data: dict, cargo_alvo: str | None) -> dict:
    """Pre-execution audit: everything the service contract demands, checked on the projected state.

    Nothing has touched any system yet, so a failure costs nothing to stop. The
    planned operations stand in for receipts, so `operacao_executada(X)` reads
    "X is in the plan" here; the final check later proves each one really ran.
    """
    ctx.receipts = [{"operacao": o["operacao"], "status": "EXECUTADA", "simulado": True} for o in plan_data.get("operacoes") or []]
    names = ctx.names(projetado, anterior=anterior, cargo_alvo=cargo_alvo)
    ref = contract_ref(processo)
    results = eval_rules((processo.get("conferencia_plano") or {}).get("regras") or [], names, ref)
    results += eval_rules((processo.get("auditoria") or {}).get("verificacoes") or [], names, ref)
    for rules, origem in compliance_rules(ctx, projetado):
        results += eval_rules(rules, names, origem)
    for problem in plan_data.get("problemas") or []:
        results.append({"id": "PLANO-SIMULACAO", "descricao": "Simulação do plano", "tipo": "BLOQUEANTE", "origem": "motor",
                        "passou": False, "explicacao": problem, "aprovadores": []})
    pendencias = target_divergences(projetado, ctx)
    results.append({"id": "AUD-ESTADO-ALVO", "descricao": "Estado projetado aderente ao estado alvo dos contratos", "origem": "contrato de serviço",
                    "tipo": "BLOQUEANTE" if (processo.get("orquestracao") or {}).get("derivar_estado_alvo", True) else "ALERTA",
                    "passou": not pendencias, "aprovadores": [],
                    "explicacao": "Estado projetado aderente ao estado alvo." if not pendencias else
                    "Pendências em relação ao estado alvo: " + " ".join(pendencias)})
    decisao, resumo = _decide(results)
    return {"decisao": decisao, "regras": results, "resumo": resumo, "momento": "ANTES_DA_EXECUCAO"}


def verify_execution(projetado: dict, final: dict, receipts: list[dict]) -> dict:
    """Final check after execution: what ran is exactly what the audit approved.

    The audit already proved the projected state compliant, so the final check
    only needs to prove that every planned operation has a receipt and that the
    resulting state equals the projection.
    """
    nao_exec = [r for r in receipts if r.get("status") != "EXECUTADA"]
    results = [{"id": "FIN-RECIBOS", "descricao": "Todas as operações planejadas possuem recibo de execução", "tipo": "BLOQUEANTE",
                "origem": "contrato de serviço", "passou": not nao_exec, "aprovadores": [],
                "explicacao": "Todas as operações têm recibo." if not nao_exec else
                f"{len(nao_exec)} operação(ões) sem execução confirmada: " + ", ".join(r["operacao"] for r in nao_exec)}]
    divergencias = state_divergences(projetado, final)
    results.append({"id": "FIN-PROJECAO", "descricao": "Estado final igual ao estado auditado antes da execução", "tipo": "BLOQUEANTE",
                    "origem": "contrato de serviço", "passou": not divergencias, "aprovadores": [],
                    "explicacao": "Estado final corresponde ao estado auditado." if not divergencias else
                    "Divergências entre o estado auditado e o final: " + "; ".join(divergencias)})
    decisao, resumo = _decide(results)
    return {"decisao": decisao, "regras": results, "resumo": resumo, "divergencias": divergencias, "momento": "DEPOIS_DA_EXECUCAO"}


def target_divergences(emp: dict, ctx: Ctx) -> list[str]:
    """Differences between an employee and the to-be state of the contracts, explained."""
    if not emp:
        return []
    return [i["motivo"] for i in diff_to_ops(emp, target_state(emp, ctx))]


def employee_compliance(emp: dict, ctx: Ctx) -> dict:
    names = ctx.names(emp)
    results: list[dict] = []
    for rules, origem in compliance_rules(ctx, emp):
        results += eval_rules(rules, names, origem)
    pend = target_divergences(emp, ctx)
    falhas = [r for r in results if not r["passou"]]
    return {"conforme": not falhas and not pend, "regras": results, "falhas": falhas, "pendencias_estado_alvo": pend}


AUDITED_FIELDS = ["cargo", "salario_base", "jornada_horas", "regime_jornada", "situacao", "sindicato", "unidade", "uf"]
AUDITED_LISTS = {"beneficios": "codigo", "verbas": "codigo", "clausulas": "codigo"}


def state_divergences(projected: dict, final: dict) -> list[str]:
    out = []
    for f in AUDITED_FIELDS:
        if projected.get(f) != final.get(f):
            out.append(f"{f}: projetado {projected.get(f)}, final {final.get(f)}")
    for f, key in AUDITED_LISTS.items():
        a = sorted(x.get(key) for x in projected.get(f) or [])
        b = sorted(x.get(key) for x in final.get(f) or [])
        if a != b:
            out.append(f"{f}: projetado {a}, final {b}")
    for f in ("acessos", "equipamentos"):
        if sorted(projected.get(f) or []) != sorted(final.get(f) or []):
            out.append(f"{f}: projetado {sorted(projected.get(f) or [])}, final {sorted(final.get(f) or [])}")
    return out


def state_diff(before: dict, after: dict) -> list[dict]:
    """Field level diff used by the interface and by the AI agent prompt."""
    changes = []
    keys = sorted(set(before or {}) | set(after or {}))
    for k in keys:
        if k in ("versao", "atualizado_em", "historico", "historico_salarial", "historico_cargos", "esocial"):
            continue
        a, b = (before or {}).get(k), (after or {}).get(k)
        if a != b:
            changes.append({"campo": k, "antes": a, "depois": b})
    return changes
