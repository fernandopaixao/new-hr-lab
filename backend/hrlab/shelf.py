"""Shelf of services (prateleira de serviços).

Each operation is a small, parameterized and decoupled service. Processes do not
know how an operation works: contracts only name the operation and give its
parameters. Every operation:
- declares the target system (FOLHA, BENEFICIOS, IAM...);
- declares its parameters (validated before execution);
- declares the employee fields it touches, so the saga can compensate it by
  restoring a snapshot of those fields;
- returns a receipt with a protocol number and a human readable description.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from .context import add_months
from .expr import months_between


class OperationError(Exception):
    pass


@dataclass
class Param:
    nome: str
    tipo: str = "texto"
    obrigatorio: bool = True
    descricao: str = ""


@dataclass
class Operation:
    codigo: str
    nome: str
    sistema: str
    descricao: str
    parametros: list[Param]
    toca: list[str]
    ordem: int
    fn: Callable[[dict, dict, "ExecCtx"], str]
    compensavel: bool = True
    tags: list[str] = field(default_factory=list)

    def describe(self) -> dict:
        return {
            "codigo": self.codigo, "nome": self.nome, "sistema": self.sistema, "descricao": self.descricao,
            "parametros": [p.__dict__ for p in self.parametros], "campos_afetados": self.toca,
            "ordem": self.ordem, "compensavel": self.compensavel,
        }


@dataclass
class ExecCtx:
    hoje: str
    norma: dict
    case_id: str = ""
    dry_run: bool = False


SHELF: dict[str, Operation] = {}


def op(codigo: str, nome: str, sistema: str, descricao: str, params: list[Param], toca: list[str], ordem: int,
       compensavel: bool = True):
    def deco(fn: Callable[[dict, dict, ExecCtx], str]):
        SHELF[codigo] = Operation(codigo, nome, sistema, descricao, params, toca, ordem, fn, compensavel)
        return fn
    return deco


def _hist(emp: dict, ctx: ExecCtx, tipo: str, descricao: str) -> None:
    emp.setdefault("historico", []).append({"data": ctx.hoje, "tipo": tipo, "descricao": descricao, "caso": ctx.case_id})


def _remove_code(items: list, code: str) -> tuple[list, bool]:
    kept = [i for i in items if (i.get("codigo") if isinstance(i, dict) else i) != code]
    return kept, len(kept) != len(items)


def _money(v: Any) -> str:
    return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ----------------------------------------------------------------- cadastro
@op("CRIAR_CADASTRO", "Criar cadastro", "CADASTRO", "Cria o registro do colaborador a partir dos dados de admissão.",
    [Param("colaborador_id", descricao="Matrícula atribuída"), Param("dados", "objeto", True, "Dados do candidato: nome, cpf, cargo, salário, lotação...")],
    ["*"], 10, compensavel=True)
def _criar_cadastro(emp: dict, p: dict, ctx: ExecCtx) -> str:
    d = dict(p["dados"] or {})
    d["id"] = p["colaborador_id"]
    emp.clear()
    emp.update(new_employee_from_admission(d, ctx.hoje))
    return f"Cadastro criado para {emp['nome']} no cargo {emp['cargo']} com salário {_money(emp['salario_base'])}."


@op("ALTERAR_SITUACAO", "Alterar situação do vínculo", "CADASTRO",
    "Altera a situação (ATIVO, AFASTADO, GARDEN_LEAVE, DESLIGADO) e registra o afastamento.",
    [Param("situacao"), Param("motivo", obrigatorio=False), Param("inicio", "data", False), Param("previsao_retorno", "data", False)],
    ["situacao", "afastamento", "historico_afastamentos", "historico"], 15)
def _alterar_situacao(emp: dict, p: dict, ctx: ExecCtx) -> str:
    nova = p["situacao"]
    if nova not in ("ATIVO", "AFASTADO", "GARDEN_LEAVE", "DESLIGADO"):
        raise OperationError(f"situação inválida: {nova}")
    anterior = emp.get("situacao")
    if nova == "AFASTADO":
        emp["afastamento"] = {"tipo": p.get("motivo"), "inicio": p.get("inicio") or ctx.hoje, "previsao_retorno": p.get("previsao_retorno")}
    elif anterior == "AFASTADO" and emp.get("afastamento"):
        fim = dict(emp["afastamento"], fim=ctx.hoje)
        emp.setdefault("historico_afastamentos", []).append(fim)
        emp["afastamento"] = None
    emp["situacao"] = nova
    _hist(emp, ctx, "SITUACAO", f"{anterior} para {nova} ({p.get('motivo') or 'sem motivo'})")
    return f"Situação alterada de {anterior} para {nova}."


@op("ALTERAR_LOTACAO", "Alterar lotação", "CADASTRO", "Altera unidade, município, UF e centro de custo.",
    [Param("unidade"), Param("cidade"), Param("uf"), Param("centro_custo", obrigatorio=False)],
    ["unidade", "cidade", "uf", "centro_custo", "data_inicio_unidade", "historico"], 20)
def _alterar_lotacao(emp: dict, p: dict, ctx: ExecCtx) -> str:
    antes = f"{emp.get('unidade')} ({emp.get('cidade')}/{emp.get('uf')})"
    emp.update({"unidade": p["unidade"], "cidade": p["cidade"], "uf": p["uf"], "data_inicio_unidade": ctx.hoje})
    if p.get("centro_custo"):
        emp["centro_custo"] = p["centro_custo"]
    _hist(emp, ctx, "LOTACAO", f"{antes} para {p['unidade']} ({p['cidade']}/{p['uf']})")
    return f"Lotação alterada de {antes} para {p['unidade']} ({p['cidade']}/{p['uf']})."


@op("ALTERAR_SINDICATO", "Alterar enquadramento sindical", "CADASTRO",
    "Altera o sindicato conforme a base territorial da lotação.", [Param("sindicato")], ["sindicato", "historico"], 22)
def _alterar_sindicato(emp: dict, p: dict, ctx: ExecCtx) -> str:
    antes = emp.get("sindicato")
    emp["sindicato"] = p["sindicato"]
    _hist(emp, ctx, "SINDICATO", f"{antes} para {p['sindicato']}")
    return f"Sindicato alterado de {antes} para {p['sindicato']}; contribuições passam a ser repassadas à nova entidade."


@op("ALTERAR_GESTOR", "Alterar gestor imediato", "CADASTRO", "Altera o gestor imediato.", [Param("gestor_id")],
    ["gestor_id"], 24)
def _alterar_gestor(emp: dict, p: dict, ctx: ExecCtx) -> str:
    antes = emp.get("gestor_id")
    emp["gestor_id"] = p["gestor_id"]
    return f"Gestor alterado de {antes} para {p['gestor_id']}."


@op("INCLUIR_DEPENDENTE", "Incluir dependente", "CADASTRO", "Inclui dependente no cadastro.",
    [Param("nome"), Param("parentesco"), Param("data_nascimento", "data")], ["dependentes"], 26)
def _incluir_dependente(emp: dict, p: dict, ctx: ExecCtx) -> str:
    emp.setdefault("dependentes", []).append({"nome": p["nome"], "parentesco": p["parentesco"], "data_nascimento": p["data_nascimento"]})
    return f"Dependente {p['nome']} ({p['parentesco']}) incluído."


# ---------------------------------------------------------------------- folha
@op("ALTERAR_CARGO", "Alterar cargo", "FOLHA", "Altera o cargo e reinicia a contagem de tempo no cargo.",
    [Param("cargo")], ["cargo", "data_inicio_cargo", "historico_cargos", "historico"], 30)
def _alterar_cargo(emp: dict, p: dict, ctx: ExecCtx) -> str:
    antes = emp.get("cargo")
    if antes == p["cargo"]:
        raise OperationError(f"colaborador já está no cargo {antes}")
    emp.setdefault("historico_cargos", []).append({"cargo": antes, "inicio": emp.get("data_inicio_cargo"), "fim": ctx.hoje})
    emp["cargo"] = p["cargo"]
    emp["data_inicio_cargo"] = ctx.hoje
    _hist(emp, ctx, "CARGO", f"{antes} para {p['cargo']}")
    return f"Cargo alterado de {antes} para {p['cargo']}."


@op("ALTERAR_SALARIO", "Alterar salário", "FOLHA", "Altera o salário base e registra no histórico salarial.",
    [Param("novo_salario", "numero"), Param("motivo", obrigatorio=False)], ["salario_base", "historico_salarial"], 32)
def _alterar_salario(emp: dict, p: dict, ctx: ExecCtx) -> str:
    novo = round(float(p["novo_salario"]), 2)
    if novo <= 0:
        raise OperationError("salário deve ser positivo")
    antes = float(emp.get("salario_base") or 0)
    emp["salario_base"] = novo
    emp.setdefault("historico_salarial", []).append({"data": ctx.hoje, "de": antes, "para": novo, "motivo": p.get("motivo") or "evento"})
    return f"Salário alterado de {_money(antes)} para {_money(novo)}."


@op("APLICAR_REAJUSTE", "Aplicar reajuste percentual", "FOLHA", "Aplica reajuste percentual ao salário base (ex.: CCT).",
    [Param("percentual", "numero")], ["salario_base", "historico_salarial"], 33)
def _aplicar_reajuste(emp: dict, p: dict, ctx: ExecCtx) -> str:
    pct = float(p["percentual"])
    antes = float(emp.get("salario_base") or 0)
    novo = round(antes * (1 + pct / 100), 2)
    emp["salario_base"] = novo
    emp.setdefault("historico_salarial", []).append({"data": ctx.hoje, "de": antes, "para": novo, "motivo": f"reajuste {pct}%"})
    return f"Reajuste de {pct}% aplicado: {_money(antes)} para {_money(novo)}."


@op("ALTERAR_JORNADA", "Alterar jornada", "PONTO", "Altera a jornada diária e o regime de controle.",
    [Param("horas", "numero"), Param("regime", obrigatorio=False)], ["jornada_horas", "regime_jornada"], 35)
def _alterar_jornada(emp: dict, p: dict, ctx: ExecCtx) -> str:
    antes = f"{emp.get('jornada_horas')}h/{emp.get('regime_jornada')}"
    emp["jornada_horas"] = int(p["horas"])
    if p.get("regime"):
        emp["regime_jornada"] = p["regime"]
    return f"Jornada alterada de {antes} para {emp['jornada_horas']}h/{emp.get('regime_jornada')}."


@op("ADICIONAR_VERBA", "Adicionar verba", "FOLHA", "Inclui uma verba de folha (gratificação, adicional, bônus).",
    [Param("codigo"), Param("nome", obrigatorio=False), Param("valor", "numero"), Param("recorrente", "booleano", False),
     Param("origem", obrigatorio=False, descricao="CONTRATO ou EVENTO"), Param("competencia", "data", False)],
    ["verbas"], 40)
def _adicionar_verba(emp: dict, p: dict, ctx: ExecCtx) -> str:
    recorrente = p.get("recorrente")
    recorrente = True if recorrente is None else bool(recorrente)
    if recorrente and any(v.get("codigo") == p["codigo"] for v in emp.get("verbas") or []):
        raise OperationError(f"verba recorrente {p['codigo']} já existe; use AJUSTAR_VERBA")
    emp.setdefault("verbas", []).append({
        "codigo": p["codigo"], "nome": p.get("nome") or p["codigo"], "valor": round(float(p["valor"]), 2),
        "recorrente": recorrente, "origem": p.get("origem") or "CONTRATO", "desde": ctx.hoje,
        "competencia": p.get("competencia"),
    })
    return f"Verba {p['codigo']} incluída: {_money(p['valor'])} ({'recorrente' if recorrente else 'pontual'})."


@op("AJUSTAR_VERBA", "Ajustar valor de verba", "FOLHA", "Ajusta o valor de uma verba recorrente existente.",
    [Param("codigo"), Param("valor", "numero")], ["verbas"], 41)
def _ajustar_verba(emp: dict, p: dict, ctx: ExecCtx) -> str:
    for v in emp.get("verbas") or []:
        if v.get("codigo") == p["codigo"]:
            antes = v.get("valor")
            v["valor"] = round(float(p["valor"]), 2)
            return f"Verba {p['codigo']} ajustada de {_money(antes)} para {_money(v['valor'])}."
    raise OperationError(f"verba {p['codigo']} não encontrada")


@op("REMOVER_VERBA", "Remover verba", "FOLHA", "Remove uma verba da folha.", [Param("codigo")], ["verbas"], 42)
def _remover_verba(emp: dict, p: dict, ctx: ExecCtx) -> str:
    emp["verbas"], removed = _remove_code(emp.get("verbas") or [], p["codigo"])
    if not removed:
        raise OperationError(f"verba {p['codigo']} não encontrada")
    return f"Verba {p['codigo']} removida."


@op("CALCULAR_RESCISAO", "Calcular rescisão", "FOLHA",
    "Calcula verbas rescisórias (valores ilustrativos): saldo, aviso prévio proporcional, 13º, férias e multa do FGTS.",
    [Param("tipo"), Param("aviso", obrigatorio=False)], ["rescisao"], 60)
def _calcular_rescisao(emp: dict, p: dict, ctx: ExecCtx) -> str:
    n = ctx.norma
    tipo = p["tipo"]
    hoje = date.fromisoformat(ctx.hoje)
    meses = months_between(emp.get("data_admissao"), ctx.hoje)
    anos = meses // 12
    rem = float(emp.get("salario_base") or 0) + sum(float(v.get("valor") or 0) for v in emp.get("verbas") or [] if v.get("recorrente"))
    dias_aviso = min(n.get("aviso_previo_base_dias", 30) + n.get("aviso_previo_dias_por_ano", 3) * anos, n.get("aviso_previo_max_dias", 90))
    saldo = rem / 30 * hoje.day
    decimo = 0.0 if tipo == "JUSTA_CAUSA" else rem / 12 * hoje.month
    ferias = 0.0 if tipo == "JUSTA_CAUSA" else rem / 12 * (meses % 12) * 4 / 3
    aviso = 0.0
    multa_pct = 0
    if tipo == "SEM_JUSTA_CAUSA":
        aviso = rem / 30 * dias_aviso if (p.get("aviso") or "INDENIZADO") == "INDENIZADO" else 0.0
        multa_pct = n.get("multa_fgts_sem_justa_causa", 40)
    elif tipo == "ACORDO_484A":
        aviso = rem / 30 * dias_aviso / 2
        multa_pct = n.get("multa_fgts_acordo", 20)
    fgts = rem * n.get("fgts_percentual", 8) / 100 * meses
    multa = fgts * multa_pct / 100
    total = saldo + decimo + ferias + aviso
    emp["rescisao"] = {
        "tipo": tipo, "data": ctx.hoje, "remuneracao_base": round(rem, 2), "dias_aviso_previo": dias_aviso,
        "saldo_salario": round(saldo, 2), "decimo_terceiro_proporcional": round(decimo, 2),
        "ferias_proporcionais_com_terco": round(ferias, 2), "aviso_previo_indenizado": round(aviso, 2),
        "fgts_saldo_estimado": round(fgts, 2), "multa_fgts": round(multa, 2), "total_bruto": round(total, 2),
        "aviso": "Valores ilustrativos, sem descontos legais.",
    }
    return f"Rescisão {tipo} calculada: total bruto {_money(total)}, multa FGTS {_money(multa)}, aviso prévio de {dias_aviso} dias."


# ------------------------------------------------------------------ benefícios
@op("ADICIONAR_BENEFICIO", "Adicionar benefício", "BENEFICIOS", "Provisiona benefício junto à operadora.",
    [Param("codigo"), Param("nome", obrigatorio=False), Param("plano", obrigatorio=False), Param("valor", "numero", False)],
    ["beneficios"], 50)
def _adicionar_beneficio(emp: dict, p: dict, ctx: ExecCtx) -> str:
    if any(b.get("codigo") == p["codigo"] for b in emp.get("beneficios") or []):
        raise OperationError(f"benefício {p['codigo']} já existe")
    emp.setdefault("beneficios", []).append({"codigo": p["codigo"], "nome": p.get("nome") or p["codigo"], "plano": p.get("plano"),
                                             "valor": p.get("valor"), "desde": ctx.hoje})
    extra = f", {_money(p['valor'])}" if p.get("valor") else ""
    return f"Benefício {p['codigo']} provisionado (plano {p.get('plano')}{extra})."


@op("ALTERAR_BENEFICIO", "Alterar plano de benefício", "BENEFICIOS", "Altera plano ou valor de um benefício existente.",
    [Param("codigo"), Param("plano", obrigatorio=False), Param("valor", "numero", False)], ["beneficios"], 51)
def _alterar_beneficio(emp: dict, p: dict, ctx: ExecCtx) -> str:
    for b in emp.get("beneficios") or []:
        if b.get("codigo") == p["codigo"]:
            antes = f"{b.get('plano')}/{b.get('valor')}"
            b["plano"] = p.get("plano") or b.get("plano")
            if p.get("valor") is not None:
                b["valor"] = p["valor"]
            return f"Benefício {p['codigo']} alterado de {antes} para {b.get('plano')}/{b.get('valor')}."
    raise OperationError(f"benefício {p['codigo']} não encontrado")


@op("REMOVER_BENEFICIO", "Remover benefício", "BENEFICIOS", "Cancela benefício junto à operadora.", [Param("codigo")],
    ["beneficios"], 52)
def _remover_beneficio(emp: dict, p: dict, ctx: ExecCtx) -> str:
    emp["beneficios"], removed = _remove_code(emp.get("beneficios") or [], p["codigo"])
    if not removed:
        raise OperationError(f"benefício {p['codigo']} não encontrado")
    return f"Benefício {p['codigo']} cancelado."


# ------------------------------------------------------------------------ IAM
@op("CONCEDER_ACESSO", "Conceder acesso", "IAM", "Concede perfil de acesso em sistema.", [Param("acesso")], ["acessos"], 70)
def _conceder_acesso(emp: dict, p: dict, ctx: ExecCtx) -> str:
    if p["acesso"] in (emp.get("acessos") or []):
        raise OperationError(f"acesso {p['acesso']} já concedido")
    emp.setdefault("acessos", []).append(p["acesso"])
    return f"Acesso {p['acesso']} concedido."


@op("REVOGAR_ACESSO", "Revogar acesso", "IAM", "Revoga perfil de acesso em sistema.", [Param("acesso")], ["acessos"], 71)
def _revogar_acesso(emp: dict, p: dict, ctx: ExecCtx) -> str:
    if p["acesso"] not in (emp.get("acessos") or []):
        raise OperationError(f"acesso {p['acesso']} não existe")
    emp["acessos"] = [a for a in emp["acessos"] if a != p["acesso"]]
    return f"Acesso {p['acesso']} revogado."


# ----------------------------------------------------------------- patrimônio
@op("PROVISIONAR_EQUIPAMENTO", "Provisionar equipamento", "PATRIMONIO", "Entrega equipamento ao colaborador.",
    [Param("equipamento")], ["equipamentos"], 75)
def _provisionar_equip(emp: dict, p: dict, ctx: ExecCtx) -> str:
    if p["equipamento"] in (emp.get("equipamentos") or []):
        raise OperationError(f"equipamento {p['equipamento']} já entregue")
    emp.setdefault("equipamentos", []).append(p["equipamento"])
    return f"Equipamento {p['equipamento']} provisionado (termo de responsabilidade emitido)."


@op("RECOLHER_EQUIPAMENTO", "Recolher equipamento", "PATRIMONIO", "Recolhe equipamento do colaborador.",
    [Param("equipamento")], ["equipamentos"], 76)
def _recolher_equip(emp: dict, p: dict, ctx: ExecCtx) -> str:
    if p["equipamento"] not in (emp.get("equipamentos") or []):
        raise OperationError(f"equipamento {p['equipamento']} não está com o colaborador")
    emp["equipamentos"] = [e for e in emp["equipamentos"] if e != p["equipamento"]]
    return f"Equipamento {p['equipamento']} recolhido."


# -------------------------------------------------------------------- jurídico
@op("INCLUIR_CLAUSULA", "Incluir cláusula contratual", "JURIDICO", "Inclui cláusula (garden leave, não concorrência).",
    [Param("codigo"), Param("nome", obrigatorio=False), Param("parametros", "objeto", False)], ["clausulas"], 80)
def _incluir_clausula(emp: dict, p: dict, ctx: ExecCtx) -> str:
    if any(c.get("codigo") == p["codigo"] for c in emp.get("clausulas") or []):
        raise OperationError(f"cláusula {p['codigo']} já existe")
    emp.setdefault("clausulas", []).append({"codigo": p["codigo"], "nome": p.get("nome") or p["codigo"],
                                            "parametros": p.get("parametros") or {}, "desde": ctx.hoje})
    return f"Cláusula {p['codigo']} incluída por aditivo contratual {p.get('parametros') or ''}."


@op("REMOVER_CLAUSULA", "Remover cláusula contratual", "JURIDICO", "Remove cláusula contratual por aditivo.",
    [Param("codigo")], ["clausulas"], 81)
def _remover_clausula(emp: dict, p: dict, ctx: ExecCtx) -> str:
    emp["clausulas"], removed = _remove_code(emp.get("clausulas") or [], p["codigo"])
    if not removed:
        raise OperationError(f"cláusula {p['codigo']} não encontrada")
    return f"Cláusula {p['codigo']} removida por aditivo contratual."


@op("REGISTRAR_ESTABILIDADE", "Registrar estabilidade", "JURIDICO", "Registra período de estabilidade provisória.",
    [Param("tipo"), Param("inicio", "data"), Param("fim", "data", False), Param("base_legal", obrigatorio=False)],
    ["estabilidades"], 82)
def _registrar_estabilidade(emp: dict, p: dict, ctx: ExecCtx) -> str:
    emp.setdefault("estabilidades", []).append({"tipo": p["tipo"], "inicio": p["inicio"], "fim": p.get("fim"), "base_legal": p.get("base_legal")})
    return f"Estabilidade {p['tipo']} registrada de {p['inicio']} até {p.get('fim') or 'indeterminado'}."


@op("INICIAR_GARDEN_LEAVE", "Iniciar garden leave", "JURIDICO", "Inicia período de garden leave remunerado.",
    [Param("dias", "numero")], ["garden_leave"], 84)
def _garden_leave(emp: dict, p: dict, ctx: ExecCtx) -> str:
    dias = int(p.get("dias") or 90)
    fim = date.fromordinal(date.fromisoformat(ctx.hoje).toordinal() + dias).isoformat()
    emp["garden_leave"] = {"inicio": ctx.hoje, "fim": fim, "dias": dias}
    return f"Garden leave de {dias} dias iniciado; término e rescisão previstos para {fim}."


@op("ENCERRAR_VINCULO", "Encerrar vínculo", "CADASTRO", "Registra o encerramento do contrato de trabalho.",
    [Param("tipo")], ["desligamento"], 90)
def _encerrar_vinculo(emp: dict, p: dict, ctx: ExecCtx) -> str:
    emp["desligamento"] = {"data": ctx.hoje, "tipo": p["tipo"]}
    return f"Vínculo encerrado em {ctx.hoje} ({p['tipo']})."


# ------------------------------------------------------------- ponto e SST
@op("CONCEDER_LICENCA", "Conceder licença", "PONTO", "Registra licença remunerada (maternidade, paternidade).",
    [Param("tipo"), Param("dias", "numero")], ["licencas"], 37)
def _conceder_licenca(emp: dict, p: dict, ctx: ExecCtx) -> str:
    dias = int(p["dias"])
    emp.setdefault("licencas", []).append({"tipo": p["tipo"], "inicio": ctx.hoje, "dias": dias})
    return f"Licença {p['tipo']} de {dias} dias registrada a partir de {ctx.hoje}."


@op("AGENDAR_EXAME", "Agendar exame ocupacional", "SST", "Agenda exame ocupacional (ASO) conforme o PCMSO.",
    [Param("tipo", descricao="ADMISSIONAL, DEMISSIONAL, MUDANCA_FUNCAO, RETORNO_TRABALHO, PERIODICO")], ["exames"], 85)
def _agendar_exame(emp: dict, p: dict, ctx: ExecCtx) -> str:
    emp.setdefault("exames", []).append({"tipo": p["tipo"], "agendado_para": ctx.hoje, "status": "AGENDADO"})
    return f"Exame {p['tipo']} agendado na clínica credenciada."


@op("REGISTRAR_TREINAMENTO", "Registrar treinamento obrigatório", "TREINAMENTO", "Matricula em trilha obrigatória.",
    [Param("curso")], ["treinamentos"], 86)
def _registrar_treinamento(emp: dict, p: dict, ctx: ExecCtx) -> str:
    emp.setdefault("treinamentos", []).append({"curso": p["curso"], "matricula": ctx.hoje, "status": "MATRICULADO"})
    return f"Matrícula na trilha {p['curso']} realizada."


# ------------------------------------------------------- eSocial e comunicação
@op("ENVIAR_ESOCIAL", "Enviar evento eSocial", "ESOCIAL", "Transmite evento ao eSocial (simulado).",
    [Param("evento"), Param("descricao", obrigatorio=False)], ["esocial"], 95)
def _enviar_esocial(emp: dict, p: dict, ctx: ExecCtx) -> str:
    recibo = "1." + hashlib.sha1(f"{emp.get('id')}{p['evento']}{ctx.case_id}".encode()).hexdigest()[:16]
    emp.setdefault("esocial", []).append({"evento": p["evento"], "descricao": p.get("descricao"), "data": ctx.hoje, "recibo": recibo})
    return f"Evento {p['evento']} transmitido ao eSocial, recibo {recibo}."


@op("NOTIFICAR", "Notificar", "COMUNICACAO", "Envia comunicação a colaborador, gestor e áreas.",
    [Param("destinatarios", "lista"), Param("assunto"), Param("mensagem", obrigatorio=False)], [], 99, compensavel=False)
def _notificar(emp: dict, p: dict, ctx: ExecCtx) -> str:
    dest = ", ".join(p.get("destinatarios") or [])
    return f"Comunicação '{p['assunto']}' enviada para {dest}."


# --------------------------------------------------------------------- helpers
def validate_params(code: str, params: dict) -> list[str]:
    spec = SHELF.get(code)
    if spec is None:
        return [f"operação {code} não existe na prateleira"]
    problems = []
    for p in spec.parametros:
        if p.obrigatorio and (params.get(p.nome) is None or params.get(p.nome) == ""):
            problems.append(f"parâmetro obrigatório ausente: {p.nome}")
    return problems


def apply(code: str, emp: dict, params: dict, ctx: ExecCtx) -> tuple[str, dict]:
    """Applies an operation in place. Returns (description, snapshot for compensation)."""
    spec = SHELF[code]
    problems = validate_params(code, params)
    if problems:
        raise OperationError("; ".join(problems))
    if spec.toca == ["*"]:
        snapshot = {"*": copy.deepcopy(emp)}
    else:
        snapshot = {k: copy.deepcopy(emp.get(k)) for k in spec.toca}
    description = spec.fn(emp, params, ctx)
    return description, snapshot


def compensate(emp: dict, snapshot: dict) -> None:
    if "*" in snapshot:
        emp.clear()
        emp.update(snapshot["*"])
        return
    for key, value in snapshot.items():
        emp[key] = value


def catalog() -> list[dict]:
    return [o.describe() for o in sorted(SHELF.values(), key=lambda o: o.ordem)]


def new_employee_from_admission(d: dict, hoje: str) -> dict:
    data_inicio = d.get("data_admissao") or hoje
    return {
        "id": d.get("id"),
        "nome": d.get("nome"),
        "cpf": "".join(c for c in str(d.get("cpf") or "") if c.isdigit()),
        "data_nascimento": d.get("data_nascimento"),
        "genero": d.get("genero") or "F",
        "escolaridade": d.get("escolaridade") or "SUPERIOR",
        "data_admissao": data_inicio,
        "cargo": d.get("cargo"),
        "data_inicio_cargo": data_inicio,
        "salario_base": round(float(d.get("salario") or 0), 2),
        "regime_jornada": "NORMAL_224",
        "jornada_horas": 6,
        "unidade": d.get("unidade") or "SEDE",
        "cidade": d.get("cidade"),
        "uf": d.get("uf"),
        "data_inicio_unidade": data_inicio,
        "centro_custo": d.get("centro_custo") or "CC-0000",
        "sindicato": d.get("sindicato"),
        "gestor_id": d.get("gestor_id"),
        "avaliacao_desempenho": 3,
        "certificacoes": list(d.get("certificacoes") or []),
        "dependentes": list(d.get("dependentes") or []),
        "conduta": {"advertencias": [], "processo_disciplinar_aberto": False, "medida_restritiva_compliance": False},
        "estabilidades": [],
        "situacao": "ATIVO",
        "afastamento": None,
        "beneficios": [],
        "verbas": [],
        "acessos": [],
        "equipamentos": [],
        "clausulas": [],
        "historico_cargos": [],
        "historico_salarial": [{"data": data_inicio, "de": 0, "para": round(float(d.get("salario") or 0), 2), "motivo": "admissão"}],
        "historico": [{"data": hoje, "tipo": "ADMISSAO", "descricao": "Admissão"}],
    }


__all__ = ["SHELF", "ExecCtx", "OperationError", "apply", "compensate", "catalog", "validate_params", "add_months"]
