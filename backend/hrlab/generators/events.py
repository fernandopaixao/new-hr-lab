"""Artificial event generator: a catalog of realistic and adversarial scenarios.

Each scenario picks (or prepares) a suitable employee and builds one or more
events that are sufficient to trigger and feed the whole flow. Every scenario
declares the expected outcome, which the scenario runner compares with the real
outcome to produce a test report.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from ..context import add_months
from ..expr import months_between
from .team import FIRST_F, FIRST_M, LAST, cpf

Builder = Callable[["GenCtx"], "dict | None"]


@dataclass
class Scenario:
    id: str
    nome: str
    categoria: str  # PADRAO, EXCECAO, BLOQUEIO, ESTRESSE, COLETIVO
    descricao: str
    esperado: list[str]
    builder: Builder

    def describe(self) -> dict:
        return {"id": self.id, "nome": self.nome, "categoria": self.categoria, "descricao": self.descricao, "esperado": self.esperado}


class GenCtx:
    def __init__(self, employees: list[dict], cargos: dict[str, dict], today: str, rng: random.Random):
        self.employees = employees
        self.cargos = cargos
        self.today = today
        self.rng = rng
        self.used: set[str] = set()

    def active(self) -> list[dict]:
        return [e for e in self.employees if e.get("situacao") == "ATIVO" and e["id"] not in self.used]

    def pick(self, pred: Callable[[dict], bool], prefer_clean: bool = True) -> dict | None:
        cands = [e for e in self.active() if pred(e)]
        if prefer_clean:
            clean = [e for e in cands if not e.get("drift") and not (e.get("conduta") or {}).get("processo_disciplinar_aberto")
                     and not (e.get("conduta") or {}).get("medida_restritiva_compliance") and not e.get("estabilidades")
                     and not (e.get("conduta") or {}).get("advertencias")]
            cands = clean or cands
        if not cands:
            return None
        emp = self.rng.choice(cands)
        self.used.add(emp["id"])
        return emp

    def faixa(self, cargo: str) -> dict:
        return (self.cargos.get(cargo, {}).get("estado_alvo") or {}).get("faixa_salarial") or {"min": 0, "max": 0}

    def months_in_role(self, e: dict) -> int:
        return months_between(e.get("data_inicio_cargo") or e.get("data_admissao"), self.today)


def evt(tipo: str, colaborador_id: str | None, dados: dict, ctx: GenCtx, cenario: str, **extra: Any) -> dict:
    e = {"id": f"evt-{uuid.uuid4().hex[:12]}", "tipo": tipo, "colaborador_id": colaborador_id, "data_efetiva": ctx.today,
         "origem": "gerador", "dados": dados, "metadados": {"cenario": cenario, "gerado_por": "gerador-de-eventos"}}
    e.update(extra)
    return e


def ready_for_promotion(ctx: GenCtx, e: dict) -> dict:
    """Patch that makes an employee meet the generic promotion policy."""
    return {"data_inicio_cargo": add_months(ctx.today, -18), "avaliacao_desempenho": 4,
            "conduta": {"advertencias": [], "processo_disciplinar_aberto": False, "medida_restritiva_compliance": False}}


def _promo(ctx: GenCtx, origem: str, destino: str, cenario: str, patch: dict | None = None, salario: float | None = None, **dados: Any) -> dict | None:
    e = ctx.pick(lambda x: x["cargo"] == origem)
    if not e:
        return None
    prep = ready_for_promotion(ctx, e)
    prep.update(patch or {})
    novo = salario if salario is not None else round(e["salario_base"] * 1.15 / 10) * 10
    d = {"cargo_destino": destino, "novo_salario": novo, "justificativa": "Promoção prevista no ciclo de carreira", "solicitante": e.get("gestor_id")}
    d.update(dados)
    return {"eventos": [evt("colaborador.promovido", e["id"], d, ctx, cenario)], "preparacao": {e["id"]: prep}}


def _candidate(ctx: GenCtx, cargo: str, salario: float, uf: str = "SP", cidade: str = "São Paulo", idade: int = 28, **extra: Any) -> dict:
    genero = ctx.rng.choice(["F", "M"])
    nome = f"{ctx.rng.choice(FIRST_F if genero == 'F' else FIRST_M)} {ctx.rng.choice(LAST)} {ctx.rng.choice(LAST)}"
    d = {"nome": nome, "cpf": cpf(ctx.rng), "data_nascimento": add_months(ctx.today, -idade * 12 - 3), "genero": genero,
         "escolaridade": "SUPERIOR", "cargo": cargo, "salario": salario, "unidade": "AG-1000" if uf == "SP" else "SEDE",
         "cidade": cidade, "uf": uf, "centro_custo": "CC-AG-1000", "certificacoes": [], "dependentes": []}
    d.update(extra)
    return d


# ------------------------------------------------------------------ builders
def s_promocao_padrao(c: GenCtx):
    return _promo(c, "ANALISTA_JR", "ANALISTA_PL", "promocao_padrao", {"escolaridade": "SUPERIOR"})


def s_promocao_sem_intersticio(c: GenCtx):
    r = _promo(c, "ESCRITURARIO", "CAIXA", "promocao_sem_intersticio")
    if r:
        emp_id = next(iter(r["preparacao"]))
        r["preparacao"][emp_id]["data_inicio_cargo"] = add_months(c.today, -5)
        r["preparacao"][emp_id]["data_admissao"] = add_months(c.today, -30)
    return r


def s_promocao_processo_disciplinar(c: GenCtx):
    return _promo(c, "ANALISTA_PL", "ANALISTA_SR", "promocao_processo_disciplinar",
                  {"escolaridade": "SUPERIOR", "conduta": {"advertencias": [], "processo_disciplinar_aberto": True, "medida_restritiva_compliance": False}})


def s_promocao_sem_cpa20(c: GenCtx):
    return _promo(c, "ANALISTA_SR", "GERENTE_RELACIONAMENTO", "promocao_sem_cpa20", {"certificacoes": ["CPA-10"], "escolaridade": "SUPERIOR"},
                  salario=None)


def s_promocao_media_gestao(c: GenCtx):
    return _promo(c, "ANALISTA_SR", "COORDENADOR", "promocao_media_gestao", {"escolaridade": "POS_GRADUACAO", "avaliacao_desempenho": 5})


def s_promocao_diretor(c: GenCtx):
    return _promo(c, "SUPERINTENDENTE", "DIRETOR", "promocao_diretor_sem_comite",
                  {"escolaridade": "POS_GRADUACAO", "data_inicio_cargo": add_months(c.today, -36)}, aprovado_comite=False)


def s_promocao_salto(c: GenCtx):
    return _promo(c, "ESCRITURARIO", "ANALISTA_PL", "promocao_salto_de_nivel", {"escolaridade": "SUPERIOR"})


def s_promocao_reducao(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] == "ANALISTA_PL")
    if not e:
        return None
    return {"eventos": [evt("colaborador.promovido", e["id"], {"cargo_destino": "ANALISTA_SR", "novo_salario": round(e["salario_base"] * 0.9, 2)}, c, "promocao_com_reducao")],
            "preparacao": {e["id"]: ready_for_promotion(c, e) | {"escolaridade": "SUPERIOR"}}}


def s_promocao_afastado(c: GenCtx):
    r = _promo(c, "CAIXA", "GERENTE_RELACIONAMENTO", "promocao_colaborador_afastado", {"certificacoes": ["CPA-20"], "escolaridade": "SUPERIOR"})
    if r:
        emp_id = next(iter(r["preparacao"]))
        r["preparacao"][emp_id].update({"situacao": "AFASTADO", "afastamento": {"tipo": "DOENCA", "inicio": add_months(c.today, -1), "previsao_retorno": add_months(c.today, 1)}})
    return r


def s_admissao_padrao(c: GenCtx):
    return {"eventos": [evt("colaborador.admitido", None, _candidate(c, "ESCRITURARIO", 3800), c, "admissao_padrao")]}


def s_admissao_abaixo_piso(c: GenCtx):
    return {"eventos": [evt("colaborador.admitido", None, _candidate(c, "ESCRITURARIO", 3000), c, "admissao_abaixo_do_piso")]}


def s_admissao_menor(c: GenCtx):
    return {"eventos": [evt("colaborador.admitido", None, _candidate(c, "ESCRITURARIO", 3700, idade=17), c, "admissao_menor_de_idade")]}


def s_admissao_cpf_invalido(c: GenCtx):
    d = _candidate(c, "CAIXA", 4600)
    d["cpf"] = "12345678900"
    return {"eventos": [evt("colaborador.admitido", None, d, c, "admissao_cpf_invalido")]}


def s_admissao_gerente_sem_cpa(c: GenCtx):
    return {"eventos": [evt("colaborador.admitido", None, _candidate(c, "GERENTE_RELACIONAMENTO", 9000, idade=33), c, "admissao_gerente_sem_cpa20")]}


def s_admissao_gerente_acima_faixa(c: GenCtx):
    d = _candidate(c, "GERENTE_RELACIONAMENTO", 15000, idade=38, certificacoes=["CPA-20"], uf="RJ", cidade="Rio de Janeiro")
    d["dependentes"] = [{"nome": "Pedro", "parentesco": "FILHO", "data_nascimento": add_months(c.today, -20)}]
    return {"eventos": [evt("colaborador.admitido", None, d, c, "admissao_gerente_acima_da_faixa")]}


def s_transferencia_mesma_cidade(c: GenCtx):
    e = c.pick(lambda x: x["cidade"] == "São Paulo" and x["cargo"] in ("ESCRITURARIO", "CAIXA"))
    if not e:
        return None
    return {"eventos": [evt("colaborador.transferido", e["id"], {"unidade": "AG-2001", "cidade": "São Paulo", "uf": "SP", "centro_custo": "CC-AG-2001"}, c, "transferencia_mesma_cidade")],
            "preparacao": {e["id"]: {"data_inicio_unidade": add_months(c.today, -12)}}}


def s_transferencia_sem_anuencia(c: GenCtx):
    e = c.pick(lambda x: x["uf"] == "SP" and x["cargo"] in ("ESCRITURARIO", "CAIXA"))
    if not e:
        return None
    return {"eventos": [evt("colaborador.transferido", e["id"], {"unidade": "AG-3001", "cidade": "Rio de Janeiro", "uf": "RJ", "anuencia_colaborador": False}, c, "transferencia_outra_base_sem_anuencia")],
            "preparacao": {e["id"]: {"data_inicio_unidade": add_months(c.today, -12)}}}


def s_transferencia_com_anuencia(c: GenCtx):
    e = c.pick(lambda x: x["uf"] == "SP" and x["cargo"] in ("ESCRITURARIO", "CAIXA", "ANALISTA_JR"))
    if not e:
        return None
    return {"eventos": [evt("colaborador.transferido", e["id"], {"unidade": "AG-4001", "cidade": "Belo Horizonte", "uf": "MG", "anuencia_colaborador": True, "centro_custo": "CC-AG-4001"}, c, "transferencia_outra_base_com_anuencia")],
            "preparacao": {e["id"]: {"data_inicio_unidade": add_months(c.today, -12)}}}


def s_transferencia_provisoria_confianca(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] == "GERENTE_RELACIONAMENTO" and x["cidade"] != "Recife")
    if not e:
        return None
    return {"eventos": [evt("colaborador.transferido", e["id"], {"unidade": "AG-5001", "cidade": "Recife", "uf": "PE", "provisoria": True, "anuencia_colaborador": False}, c, "transferencia_provisoria_cargo_confianca")],
            "preparacao": {e["id"]: {"data_inicio_unidade": add_months(c.today, -12)}}}


def s_transferencia_dirigente(c: GenCtx):
    e = c.pick(lambda x: x["uf"] == "SP" and x["cargo"] in ("ESCRITURARIO", "CAIXA"))
    if not e:
        return None
    est = (e.get("estabilidades") or []) + [{"tipo": "DIRIGENTE_SINDICAL", "inicio": add_months(c.today, -6), "fim": add_months(c.today, 30), "base_legal": "CLT art. 543"}]
    return {"eventos": [evt("colaborador.transferido", e["id"], {"unidade": "AG-6001", "cidade": "Porto Alegre", "uf": "RS", "anuencia_colaborador": True}, c, "transferencia_dirigente_sindical")],
            "preparacao": {e["id"]: {"estabilidades": est, "data_inicio_unidade": add_months(c.today, -12)}}}


def s_reversao(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] == "GERENTE_RELACIONAMENTO")
    if not e:
        return None
    return {"eventos": [evt("colaborador.revertido_cargo_confianca", e["id"], {"cargo_destino": "ANALISTA_PL", "motivo": "Reestruturação da carteira de varejo da agência"}, c, "reversao_cargo_confianca")]}


def _deslig(c: GenCtx, pred, cenario: str, tipo: str = "SEM_JUSTA_CAUSA", patch: dict | None = None, **dados):
    e = c.pick(pred)
    if not e:
        return None
    d = {"tipo": tipo, "motivo": "Reestruturação", "aviso": "INDENIZADO"}
    d.update(dados)
    out = {"eventos": [evt("colaborador.desligado", e["id"], d, c, cenario)]}
    if patch is not None:
        out["preparacao"] = {e["id"]: patch(e) if callable(patch) else patch}
    return out


def s_deslig_padrao(c: GenCtx):
    return _deslig(c, lambda x: x["cargo"] in ("ESCRITURARIO", "CAIXA", "ANALISTA_JR"), "desligamento_sem_justa_causa", patch={"estabilidades": []})


def s_deslig_gestante(c: GenCtx):
    return _deslig(c, lambda x: x["genero"] == "F" and x["cargo"] in ("ESCRITURARIO", "CAIXA", "ANALISTA_PL"), "desligamento_gestante",
                   patch={"estabilidades": [{"tipo": "GESTANTE", "inicio": add_months(c.today, -3), "fim": add_months(c.today, 9), "base_legal": "ADCT art. 10 II b"}]})


def s_deslig_pre_aposentadoria(c: GenCtx):
    return _deslig(c, lambda x: x["cargo"] in ("CAIXA", "ESCRITURARIO", "ANALISTA_SR"), "desligamento_pre_aposentadoria",
                   patch={"estabilidades": [{"tipo": "PRE_APOSENTADORIA", "inicio": add_months(c.today, -4), "fim": add_months(c.today, 20), "base_legal": "CCT"}],
                          "data_admissao": add_months(c.today, -12 * 22)})


def s_deslig_executivo(c: GenCtx):
    return _deslig(c, lambda x: x["cargo"] in ("SUPERINTENDENTE", "DIRETOR"), "desligamento_executivo_garden_leave", patch={"estabilidades": []})


def s_deslig_justa_causa(c: GenCtx):
    return _deslig(c, lambda x: x["cargo"] in ("ESCRITURARIO", "CAIXA"), "desligamento_justa_causa_sem_registro", tipo="JUSTA_CAUSA",
                   falta_grave_registrada=False, patch={"estabilidades": []})


def s_deslig_cipa(c: GenCtx):
    return _deslig(c, lambda x: x["cargo"] in ("ESCRITURARIO", "CAIXA", "ANALISTA_JR"), "desligamento_membro_cipa",
                   patch={"estabilidades": [{"tipo": "CIPA", "inicio": add_months(c.today, -5), "fim": add_months(c.today, 14), "base_legal": "ADCT art. 10 II a"}]})


def s_afastamento_doenca(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] in ("ESCRITURARIO", "CAIXA", "ANALISTA_PL"))
    if not e:
        return None
    return {"eventos": [evt("colaborador.afastado", e["id"], {"tipo": "DOENCA", "inicio": c.today, "previsao_retorno": add_months(c.today, 2), "cid": "M54.5"}, c, "afastamento_doenca")]}


def s_licenca_maternidade(c: GenCtx):
    e = c.pick(lambda x: x["genero"] == "F")
    if not e:
        return None
    return {"eventos": [evt("colaborador.afastado", e["id"], {"tipo": "MATERNIDADE", "inicio": c.today, "previsao_retorno": add_months(c.today, 6)}, c, "licenca_maternidade")]}


def s_retorno_acidente(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] in ("CAIXA", "ESCRITURARIO"))
    if not e:
        return None
    prep = {"situacao": "AFASTADO", "afastamento": {"tipo": "ACIDENTE_TRABALHO", "inicio": add_months(c.today, -3), "previsao_retorno": c.today},
            "acessos": ["EMAIL"]}
    return {"eventos": [evt("colaborador.retornou_afastamento", e["id"], {"data_retorno": c.today}, c, "retorno_de_acidente_de_trabalho")], "preparacao": {e["id"]: prep}}


def s_nascimento(c: GenCtx):
    e = c.pick(lambda x: x["genero"] == "M")
    if not e:
        return None
    return {"eventos": [evt("colaborador.dependente_incluido", e["id"], {"nome": f"{c.rng.choice(FIRST_F + FIRST_M)} {e['nome'].split()[-1]}", "parentesco": "FILHO",
                                                                         "data_nascimento": add_months(c.today, 0), "certidao_apresentada": True}, c, "nascimento_de_filho")]}


def s_bonus(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] in ("GERENTE_RELACIONAMENTO", "ANALISTA_SR", "COORDENADOR"))
    if not e:
        return None
    return {"eventos": [evt("colaborador.bonus_concedido", e["id"], {"valor": round(e["salario_base"] * 1.5, 2), "motivo": "Atingimento de metas do semestre"}, c, "bonus_padrao")],
            "preparacao": {e["id"]: {"avaliacao_desempenho": 4}}}


def s_bonus_comite(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] in ("GERENTE_AGENCIA", "SUPERINTENDENTE"))
    if not e:
        return None
    return {"eventos": [evt("colaborador.bonus_concedido", e["id"], {"valor": round(e["salario_base"] * 5, 2), "motivo": "Resultado excepcional"}, c, "bonus_acima_do_limite")],
            "preparacao": {e["id"]: {"avaliacao_desempenho": 5}}}


def s_bonus_malus(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] in ("GERENTE_RELACIONAMENTO", "GERENTE_AGENCIA"))
    if not e:
        return None
    return {"eventos": [evt("colaborador.bonus_concedido", e["id"], {"valor": round(e["salario_base"], 2), "motivo": "Campanha de vendas"}, c, "bonus_com_medida_restritiva")],
            "preparacao": {e["id"]: {"conduta": {"advertencias": [], "processo_disciplinar_aberto": False, "medida_restritiva_compliance": True}}}}


def s_merito(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] == "GERENTE_RELACIONAMENTO")
    if not e:
        return None
    return {"eventos": [evt("colaborador.merito_concedido", e["id"], {"percentual": 6}, c, "merito_com_recalculo_de_gratificacao")],
            "preparacao": {e["id"]: {"avaliacao_desempenho": 5, "historico_salarial": [{"data": add_months(c.today, -14), "de": 0, "para": e["salario_base"], "motivo": "anterior"}],
                                     "salario_base": round(c.faixa("GERENTE_RELACIONAMENTO")["min"] * 1.05, 2)}}}


def s_merito_acima(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] in ("ANALISTA_PL", "ANALISTA_SR"))
    if not e:
        return None
    return {"eventos": [evt("colaborador.merito_concedido", e["id"], {"percentual": 15}, c, "merito_acima_do_limite")],
            "preparacao": {e["id"]: {"avaliacao_desempenho": 5, "historico_salarial": [{"data": add_months(c.today, -14), "de": 0, "para": e["salario_base"], "motivo": "anterior"}]}}}


def s_jornada_8h(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] in ("ESCRITURARIO", "CAIXA"))
    if not e:
        return None
    return {"eventos": [evt("colaborador.jornada_alterada", e["id"], {"horas": 8}, c, "jornada_8h_sem_cargo_de_confianca")]}


def s_reajuste_cct(c: GenCtx):
    return {"eventos": [evt("cct.reajuste_aplicado", None, {"percentual": 5.5, "sindicatos": ["SEEB-SP"], "data_base": c.today}, c, "reajuste_cct_coletivo")]}


def s_conformidade_coletiva(c: GenCtx):
    return {"eventos": [evt("auditoria.conformidade_coletiva", None, {"motivo": "Varredura de conformidade"}, c, "conformidade_coletiva")]}


def s_conformidade_drift(c: GenCtx):
    cands = [e for e in c.active() if e.get("drift")]
    if not cands:
        return None
    e = c.rng.choice(cands)
    c.used.add(e["id"])
    return {"eventos": [evt("auditoria.conformidade_solicitada", e["id"], {"motivo": f"Divergência conhecida: {', '.join(e['drift'])}"}, c, "conformidade_com_divergencia")]}


def s_duplicado(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] in ("ANALISTA_PL", "GERENTE_RELACIONAMENTO", "COORDENADOR"))
    if not e:
        return None
    ev = evt("colaborador.bonus_concedido", e["id"], {"valor": 1000.0, "motivo": "Campanha"}, c, "evento_duplicado")
    return {"eventos": [ev, dict(ev, metadados={"cenario": "evento_duplicado", "copia": True})], "preparacao": {e["id"]: {"avaliacao_desempenho": 4}}}


def s_invalido(c: GenCtx):
    e = c.pick(lambda x: True)
    if not e:
        return None
    return {"eventos": [evt("colaborador.promovido", e["id"], {"novo_salario": 9000}, c, "evento_invalido_sem_cargo_destino")]}


def s_inexistente(c: GenCtx):
    return {"eventos": [evt("colaborador.promovido", "F99999", {"cargo_destino": "CAIXA"}, c, "colaborador_inexistente")]}


def s_tipo_desconhecido(c: GenCtx):
    e = c.pick(lambda x: True)
    return {"eventos": [evt("colaborador.teletransportado", e["id"] if e else None, {"destino": "Marte"}, c, "tipo_de_evento_desconhecido")]}


def s_sem_contrato_vigente(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] == "ESCRITURARIO")
    if not e:
        return None
    ev = evt("colaborador.promovido", e["id"], {"cargo_destino": "CAIXA"}, c, "data_sem_contrato_vigente")
    ev["data_efetiva"] = "2019-03-01"
    return {"eventos": [ev]}


def s_falha_beneficios(c: GenCtx):
    r = _promo(c, "ANALISTA_PL", "ANALISTA_SR", "falha_no_sistema_de_beneficios", {"escolaridade": "SUPERIOR"}, simular_falha_em="BENEFICIOS")
    return r


def s_concorrentes(c: GenCtx):
    e = c.pick(lambda x: x["cargo"] == "GERENTE_RELACIONAMENTO")
    if not e:
        return None
    prep = {"avaliacao_desempenho": 5, "historico_salarial": [{"data": add_months(c.today, -14), "de": 0, "para": e["salario_base"], "motivo": "anterior"}]}
    return {"eventos": [
        evt("colaborador.merito_concedido", e["id"], {"percentual": 4}, c, "eventos_concorrentes"),
        evt("colaborador.bonus_concedido", e["id"], {"valor": 2000.0, "motivo": "Campanha"}, c, "eventos_concorrentes"),
        evt("colaborador.transferido", e["id"], {"unidade": "AG-7001", "cidade": e["cidade"], "uf": e["uf"]}, c, "eventos_concorrentes"),
    ], "preparacao": {e["id"]: prep | {"data_inicio_unidade": add_months(c.today, -12)}}}


FINAL_OK = ["CONCLUIDO", "CONCLUIDO_COM_RESSALVAS"]
SCENARIOS: list[Scenario] = [
    Scenario("promocao_padrao", "Promoção padrão", "PADRAO", "Analista júnior elegível promovido a pleno.", FINAL_OK, s_promocao_padrao),
    Scenario("promocao_media_gestao", "Promoção para média gerência", "PADRAO", "Analista sênior vira coordenador: gratificação de 55%, 8h, celular corporativo e trilha de liderança.", FINAL_OK, s_promocao_media_gestao),
    Scenario("promocao_sem_intersticio", "Promoção sem interstício", "EXCECAO", "Escriturário com 5 meses no cargo; exige exceção do HRBP.", ["AGUARDANDO_APROVACAO"], s_promocao_sem_intersticio),
    Scenario("promocao_processo_disciplinar", "Promoção com processo disciplinar", "EXCECAO", "Processo disciplinar aberto exige exceção de compliance.", ["AGUARDANDO_APROVACAO"], s_promocao_processo_disciplinar),
    Scenario("promocao_salto_de_nivel", "Promoção com salto de níveis", "EXCECAO", "Escriturário promovido direto a analista pleno.", ["AGUARDANDO_APROVACAO"], s_promocao_salto),
    Scenario("promocao_diretor_sem_comite", "Nomeação de diretor sem comitê", "EXCECAO", "Superintendente a diretor sem aprovação do comitê de remuneração.", ["AGUARDANDO_APROVACAO"], s_promocao_diretor),
    Scenario("promocao_sem_cpa20", "Promoção a gerente sem CPA-20", "BLOQUEIO", "Cargo que distribui investimentos exige CPA-20 (bloqueante).", ["NAO_ELEGIVEL"], s_promocao_sem_cpa20),
    Scenario("promocao_com_reducao", "Promoção com redução salarial", "BLOQUEIO", "Novo salário menor que o atual viola a irredutibilidade.", ["NAO_ELEGIVEL"], s_promocao_reducao),
    Scenario("promocao_colaborador_afastado", "Promoção de colaborador afastado", "BLOQUEIO", "Colaborador afastado não pode ser promovido.", ["NAO_ELEGIVEL"], s_promocao_afastado),
    Scenario("admissao_padrao", "Admissão padrão", "PADRAO", "Escriturário admitido com VR, VA, saúde, acessos, ASO e S-2200.", FINAL_OK, s_admissao_padrao),
    Scenario("admissao_abaixo_do_piso", "Admissão abaixo do piso", "BLOQUEIO", "Salário abaixo do piso da CCT.", ["NAO_ELEGIVEL"], s_admissao_abaixo_piso),
    Scenario("admissao_menor_de_idade", "Admissão de menor de 18 anos", "BLOQUEIO", "Contratação CLT regular de menor de idade.", ["NAO_ELEGIVEL"], s_admissao_menor),
    Scenario("admissao_cpf_invalido", "Admissão com CPF inválido", "BLOQUEIO", "CPF com dígitos verificadores inválidos.", ["NAO_ELEGIVEL"], s_admissao_cpf_invalido),
    Scenario("admissao_gerente_sem_cpa20", "Admissão de gerente sem CPA-20", "BLOQUEIO", "Gerente de relacionamento sem certificação.", ["NAO_ELEGIVEL"], s_admissao_gerente_sem_cpa),
    Scenario("admissao_gerente_acima_da_faixa", "Admissão de gerente acima da faixa", "EXCECAO", "Salário acima da faixa exige HRBP; filho pequeno gera auxílio-creche.", ["AGUARDANDO_APROVACAO"], s_admissao_gerente_acima_faixa),
    Scenario("transferencia_mesma_cidade", "Transferência na mesma cidade", "PADRAO", "Mudança de agência sem mudança de domicílio.", FINAL_OK, s_transferencia_mesma_cidade),
    Scenario("transferencia_outra_base_com_anuencia", "Transferência para outra base sindical", "PADRAO", "SP para MG com anuência: troca de sindicato.", FINAL_OK, s_transferencia_com_anuencia),
    Scenario("transferencia_outra_base_sem_anuencia", "Transferência sem anuência", "BLOQUEIO", "Mudança de domicílio sem anuência de cargo sem confiança (art. 469).", ["NAO_ELEGIVEL"], s_transferencia_sem_anuencia),
    Scenario("transferencia_provisoria_cargo_confianca", "Transferência provisória de cargo de confiança", "PADRAO", "Sem anuência, com adicional de transferência de 25%.", FINAL_OK, s_transferencia_provisoria_confianca),
    Scenario("transferencia_dirigente_sindical", "Transferência de dirigente sindical", "BLOQUEIO", "Dirigente não pode sair da base (art. 543).", ["NAO_ELEGIVEL"], s_transferencia_dirigente),
    Scenario("reversao_cargo_confianca", "Reversão de cargo de confiança", "PADRAO", "Gerente volta a analista: remove gratificação, volta a 6h, revoga acessos.", FINAL_OK, s_reversao),
    Scenario("desligamento_sem_justa_causa", "Desligamento sem justa causa", "PADRAO", "Rescisão, ASO demissional, revogação de acessos, S-2299.", FINAL_OK, s_deslig_padrao),
    Scenario("desligamento_executivo_garden_leave", "Desligamento de executivo", "PADRAO", "Superintendente entra em garden leave de 90 dias.", FINAL_OK, s_deslig_executivo),
    Scenario("desligamento_gestante", "Desligamento de gestante", "BLOQUEIO", "Estabilidade da gestante impede a dispensa.", ["NAO_ELEGIVEL"], s_deslig_gestante),
    Scenario("desligamento_membro_cipa", "Desligamento de membro da CIPA", "BLOQUEIO", "Estabilidade de cipeiro.", ["NAO_ELEGIVEL"], s_deslig_cipa),
    Scenario("desligamento_pre_aposentadoria", "Desligamento em pré-aposentadoria", "EXCECAO", "Estabilidade da CCT; exige parecer jurídico.", ["AGUARDANDO_APROVACAO"], s_deslig_pre_aposentadoria),
    Scenario("desligamento_justa_causa_sem_registro", "Justa causa sem registro de falta", "EXCECAO", "Exige parecer jurídico.", ["AGUARDANDO_APROVACAO"], s_deslig_justa_causa),
    Scenario("afastamento_doenca", "Afastamento por doença", "PADRAO", "Acessos reduzidos, VR mantido, S-2230.", FINAL_OK, s_afastamento_doenca),
    Scenario("licenca_maternidade", "Licença-maternidade", "PADRAO", "180 dias e estabilidade da gestante.", FINAL_OK, s_licenca_maternidade),
    Scenario("retorno_de_acidente_de_trabalho", "Retorno de acidente de trabalho", "PADRAO", "Exame de retorno e estabilidade de 12 meses.", FINAL_OK, s_retorno_acidente),
    Scenario("nascimento_de_filho", "Nascimento de filho", "PADRAO", "Dependente, licença-paternidade e auxílio-creche.", FINAL_OK, s_nascimento),
    Scenario("bonus_padrao", "Bônus padrão", "PADRAO", "Verba pontual de bônus.", FINAL_OK, s_bonus),
    Scenario("bonus_acima_do_limite", "Bônus acima de 3 salários", "EXCECAO", "Exige comitê de remuneração.", ["AGUARDANDO_APROVACAO"], s_bonus_comite),
    Scenario("bonus_com_medida_restritiva", "Bônus com medida restritiva", "BLOQUEIO", "Malus de compliance impede bônus.", ["NAO_ELEGIVEL"], s_bonus_malus),
    Scenario("merito_com_recalculo_de_gratificacao", "Mérito com recálculo de gratificação", "PADRAO", "Aumento de 6% recalcula a gratificação de 55%.", FINAL_OK, s_merito),
    Scenario("merito_acima_do_limite", "Mérito acima do limite", "EXCECAO", "15% exige comitê.", ["AGUARDANDO_APROVACAO"], s_merito_acima),
    Scenario("jornada_8h_sem_cargo_de_confianca", "Jornada de 8h sem confiança", "BLOQUEIO", "Viola o art. 224 da CLT.", ["NAO_ELEGIVEL"], s_jornada_8h),
    Scenario("reajuste_cct_coletivo", "Reajuste coletivo da CCT", "COLETIVO", "Data-base: um caso por colaborador da base SEEB-SP.", ["CONCLUIDO"], s_reajuste_cct),
    Scenario("conformidade_com_divergencia", "Conformidade com divergência", "PADRAO", "Colaborador com desvio gerado; o plano remedia.", FINAL_OK, s_conformidade_drift),
    Scenario("conformidade_coletiva", "Conformidade coletiva", "COLETIVO", "Varredura de todos os colaboradores contra os contratos.", ["CONCLUIDO"], s_conformidade_coletiva),
    Scenario("evento_duplicado", "Evento duplicado", "ESTRESSE", "Mesmo id enviado duas vezes; o segundo é descartado.", ["CONCLUIDO", "CONCLUIDO_COM_RESSALVAS", "DUPLICADO"], s_duplicado),
    Scenario("evento_invalido_sem_cargo_destino", "Evento inválido", "ESTRESSE", "Promoção sem cargo de destino.", ["REJEITADO_NA_ENTRADA"], s_invalido),
    Scenario("colaborador_inexistente", "Colaborador inexistente", "ESTRESSE", "Matrícula que não existe.", ["REJEITADO_NA_ENTRADA"], s_inexistente),
    Scenario("tipo_de_evento_desconhecido", "Tipo de evento desconhecido", "ESTRESSE", "Nenhum contrato de processo atende o evento.", ["REJEITADO_NA_ENTRADA"], s_tipo_desconhecido),
    Scenario("data_sem_contrato_vigente", "Data sem contrato vigente", "ESTRESSE", "Data efetiva anterior à vigência dos contratos.", ["REJEITADO_NA_ENTRADA"], s_sem_contrato_vigente),
    Scenario("falha_no_sistema_de_beneficios", "Falha no sistema de benefícios", "ESTRESSE", "A operadora falha no meio da execução; a saga compensa.", ["FALHOU_COMPENSADO"], s_falha_beneficios),
    Scenario("eventos_concorrentes", "Eventos concorrentes", "ESTRESSE", "Mérito, bônus e transferência simultâneos para a mesma pessoa; trava e replanejamento.", FINAL_OK + ["AGUARDANDO_APROVACAO"], s_concorrentes),
]
SCENARIO_BY_ID = {s.id: s for s in SCENARIOS}


def build(scenario_id: str, employees: list[dict], cargos: dict[str, dict], today: str, seed: int | None = None,
          gen: GenCtx | None = None) -> dict | None:
    sc = SCENARIO_BY_ID[scenario_id]
    ctx = gen or GenCtx(employees, cargos, today, random.Random(seed))
    out = sc.builder(ctx)
    if out:
        out["cenario"] = sc.describe()
    return out


def random_burst(n: int, employees: list[dict], cargos: dict[str, dict], today: str, seed: int | None = None,
                 categorias: list[str] | None = None) -> list[dict]:
    rng = random.Random(seed)
    ctx = GenCtx(employees, cargos, today, rng)
    pool = [s for s in SCENARIOS if s.categoria != "COLETIVO" and (not categorias or s.categoria in categorias)]
    out = []
    for _ in range(n):
        sc = rng.choice(pool)
        built = sc.builder(ctx)
        if built:
            built["cenario"] = sc.describe()
            out.append(built)
    return out
