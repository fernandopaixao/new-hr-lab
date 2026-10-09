"""Evaluation context shared by eligibility, planning, plan review and audit.

`build_names` returns the variables and helper functions available to contract
expressions. Helpers are bound to a subject employee ("colaborador").
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from .expr import days_between, evaluate, months_between, unwrap, wrap

ESCOLARIDADE = ["FUNDAMENTAL", "MEDIO", "TECNICO", "SUPERIOR_INCOMPLETO", "SUPERIOR", "POS_GRADUACAO", "MESTRADO", "DOUTORADO"]


def cpf_valido(cpf: Any) -> bool:
    digits = [int(c) for c in str(cpf or "") if c.isdigit()]
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for n in (9, 10):
        total = sum(d * w for d, w in zip(digits[:n], range(n + 1, 1, -1)))
        check = (total * 10) % 11 % 10
        if check != digits[n]:
            return False
    return True


def add_months(value: Any, months: int) -> str:
    d = date.fromisoformat(str(value)[:10])
    m = d.month - 1 + int(months)
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day).isoformat()


class Ctx:
    """Static data needed to build evaluation names for one case."""

    def __init__(self, *, event: dict, norma: dict | None, politica: dict | None, cargos: dict[str, dict],
                 cpfs_ativos: set[str] | None = None, receipts: list[dict] | None = None):
        self.event = event
        self.norma = norma or {}
        self.politica = politica or {}
        self.cargos = cargos
        self.cpfs_ativos = cpfs_ativos or set()
        self.receipts = receipts or []

    @property
    def today(self) -> str:
        return str(self.event.get("data_efetiva") or self.event.get("ocorrido_em") or date.today().isoformat())[:10]

    def cargo(self, code: Any) -> dict | None:
        return self.cargos.get(str(code)) if code else None

    def names(self, colaborador: dict | None, *, anterior: dict | None = None, cargo_alvo: str | None = None,
              extra: dict | None = None) -> dict[str, Any]:
        emp = colaborador or {}
        hoje = self.today
        norma_params = dict(self.norma.get("parametros") or {})
        politica_params = dict(self.politica.get("parametros") or {})

        def lst(key: str) -> list:
            return emp.get(key) or []

        def possui_beneficio(code: str) -> bool:
            return any(b.get("codigo") == code for b in lst("beneficios"))

        def plano_beneficio(code: str) -> Any:
            return next((b.get("plano") for b in lst("beneficios") if b.get("codigo") == code), None)

        def possui_verba(code: str) -> bool:
            return any(v.get("codigo") == code for v in lst("verbas"))

        def valor_verba(code: str) -> float:
            return round(sum(float(v.get("valor") or 0) for v in lst("verbas") if v.get("codigo") == code), 2)

        def possui_certificacao(code: str) -> bool:
            return code in lst("certificacoes")

        def possui_acesso(code: str) -> bool:
            return code in lst("acessos")

        def possui_equipamento(code: str) -> bool:
            return code in lst("equipamentos")

        def possui_clausula(code: str) -> bool:
            return any(c.get("codigo") == code for c in lst("clausulas"))

        def parametro_clausula(code: str, param: str) -> Any:
            for c in lst("clausulas"):
                if c.get("codigo") == code:
                    return (c.get("parametros") or {}).get(param)
            return None

        def estabilidade_ativa(tipo: str | None = None) -> bool:
            for e in lst("estabilidades"):
                if tipo and e.get("tipo") != tipo:
                    continue
                if str(e.get("inicio") or "0000")[:10] <= hoje and (not e.get("fim") or str(e["fim"])[:10] >= hoje):
                    return True
            return False

        def dependentes_menores_de(meses: int) -> int:
            return sum(1 for d in lst("dependentes") if 0 <= months_between(d.get("data_nascimento"), hoje) <= int(meses))

        def escolaridade_ao_menos(nivel: str) -> bool:
            cur = emp.get("escolaridade")
            if cur not in ESCOLARIDADE or nivel not in ESCOLARIDADE:
                return False
            return ESCOLARIDADE.index(cur) >= ESCOLARIDADE.index(nivel)

        def sindicato_da_uf(uf: str) -> str | None:
            for s in norma_params.get("sindicatos") or []:
                if uf in (s.get("ufs") or []):
                    return s.get("codigo")
            return None

        def advertencias_ultimos_meses(meses: int) -> int:
            return sum(1 for a in (emp.get("conduta") or {}).get("advertencias") or []
                       if 0 <= months_between(a.get("data"), hoje) < int(meses))

        def operacao_executada(code: str) -> bool:
            return any(r.get("operacao") == code and r.get("status") == "EXECUTADA" for r in self.receipts)

        def cpf_em_uso(cpf: str) -> bool:
            return "".join(c for c in str(cpf) if c.isdigit()) in self.cpfs_ativos

        afast = emp.get("afastamento") or {}
        ultimos_aumentos = [h.get("data") for h in lst("historico_salarial") if h.get("data")]
        ultimo_aumento = max(ultimos_aumentos) if ultimos_aumentos else emp.get("data_admissao")

        cargo_atual = self.cargo(emp.get("cargo"))
        names: dict[str, Any] = {
            "colaborador": emp,
            "anterior": anterior or {},
            "evento": self.event,
            "hoje": hoje,
            "norma": norma_params,
            "politica": politica_params,
            "cargo_atual": cargo_atual,
            "cargo_destino": self.cargo(cargo_alvo) if cargo_alvo else cargo_atual,
            "idade": months_between(emp.get("data_nascimento"), hoje) // 12 if emp.get("data_nascimento") else 0,
            "meses_de_casa": months_between(emp.get("data_admissao"), hoje),
            "anos_de_casa": months_between(emp.get("data_admissao"), hoje) // 12,
            "meses_no_cargo": months_between(emp.get("data_inicio_cargo") or emp.get("data_admissao"), hoje),
            "meses_na_unidade": months_between(emp.get("data_inicio_unidade") or emp.get("data_admissao"), hoje),
            "meses_desde_ultimo_aumento": months_between(ultimo_aumento, hoje) if ultimo_aumento else 999,
            "dias_afastado": days_between(afast.get("inicio"), hoje) if afast else 0,
            "possui_beneficio": possui_beneficio,
            "plano_beneficio": plano_beneficio,
            "possui_verba": possui_verba,
            "valor_verba": valor_verba,
            "possui_certificacao": possui_certificacao,
            "possui_acesso": possui_acesso,
            "possui_equipamento": possui_equipamento,
            "possui_clausula": possui_clausula,
            "parametro_clausula": parametro_clausula,
            "estabilidade_ativa": estabilidade_ativa,
            "dependentes_menores_de": dependentes_menores_de,
            "escolaridade_ao_menos": escolaridade_ao_menos,
            "sindicato_da_uf": sindicato_da_uf,
            "advertencias_ultimos_meses": advertencias_ultimos_meses,
            "operacao_executada": operacao_executada,
            "cpf_valido": cpf_valido,
            "cpf_em_uso": cpf_em_uso,
            "somar_meses": add_months,
            "cargo": lambda code: self.cargo(code),
        }
        if extra:
            names.update(extra)
        return names


def render(template: str | None, names: dict[str, Any]) -> str:
    """Render '{expression}' placeholders inside explanation templates."""
    if not template:
        return ""
    out = []
    i = 0
    text = str(template)
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth = 1
            j = i + 1
            while j < len(text) and depth:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            source = text[i + 1:j - 1]
            try:
                value = unwrap(evaluate(source, names))
                if isinstance(value, float):
                    value = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                out.append(str(value))
            except Exception:  # noqa: BLE001 - explanation must never break the flow
                out.append("?")
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


__all__ = ["Ctx", "render", "cpf_valido", "add_months", "wrap"]
