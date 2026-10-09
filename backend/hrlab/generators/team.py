"""Artificial team composition generator.

Builds a plausible bank organization (headquarters plus branches) with names,
positions, dates, union bases, dependents, conduct records and stabilities. The
initial state of each employee is derived from the position contracts, and a
configurable share of employees receives deliberate deviations ("drift") so the
compliance agents have something to find.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from ..context import Ctx, add_months
from ..engine import target_state

FIRST_F = ["Ana", "Beatriz", "Camila", "Daniela", "Eduarda", "Fernanda", "Gabriela", "Helena", "Isabela", "Juliana",
           "Larissa", "Mariana", "Natália", "Patrícia", "Renata", "Sabrina", "Tatiane", "Vanessa", "Yasmin", "Luana",
           "Carolina", "Aline", "Bruna", "Débora", "Priscila", "Lívia", "Rafaela", "Simone", "Cláudia", "Márcia"]
FIRST_M = ["André", "Bruno", "Carlos", "Diego", "Eduardo", "Felipe", "Gustavo", "Henrique", "Igor", "João",
           "Lucas", "Marcelo", "Nelson", "Otávio", "Paulo", "Rafael", "Sérgio", "Thiago", "Vinícius", "Wagner",
           "Rodrigo", "Fábio", "Leonardo", "Mateus", "Ricardo", "Alexandre", "César", "Daniel", "Gilberto", "Roberto"]
LAST = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima", "Gomes",
        "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida", "Lopes", "Soares", "Fernandes", "Vieira", "Barbosa",
        "Rocha", "Dias", "Nascimento", "Andrade", "Moreira", "Nunes", "Marques", "Machado", "Mendes", "Freitas",
        "Cardoso", "Ramos", "Teixeira", "Correia", "Pinto", "Araújo", "Batista", "Moura", "Cavalcanti", "Monteiro"]
CITIES = [("São Paulo", "SP"), ("Campinas", "SP"), ("Rio de Janeiro", "RJ"), ("Belo Horizonte", "MG"),
          ("Porto Alegre", "RS"), ("Curitiba", "PR"), ("Recife", "PE"), ("Salvador", "BA"), ("Brasília", "DF"),
          ("Vitória", "ES"), ("Fortaleza", "CE"), ("Goiânia", "GO")]

DRIFTS = [
    ("SEM_VR", "Vale-refeição ausente"),
    ("JORNADA_8H_SEM_CONFIANCA", "Jornada de 8h em cargo sem confiança"),
    ("GRATIFICACAO_ABAIXO", "Gratificação de função abaixo do mínimo"),
    ("SINDICATO_ERRADO", "Sindicato incompatível com a UF"),
    ("SEM_CELULAR_GESTOR", "Gestor sem celular corporativo"),
    ("ACESSO_EXCEDENTE", "Acesso além do previsto no cargo"),
    ("PLANO_SAUDE_ERRADO", "Plano de saúde diferente do contrato"),
    ("SEM_CRECHE", "Dependente em idade de creche sem auxílio"),
]


def cpf(rng: random.Random) -> str:
    digits = [rng.randint(0, 9) for _ in range(9)]
    for n in (9, 10):
        total = sum(d * w for d, w in zip(digits, range(n + 1, 1, -1)))
        digits.append((total * 10) % 11 % 10)
    return "".join(map(str, digits))


def _rand_date(rng: random.Random, start: date, end: date) -> str:
    if end <= start:
        return start.isoformat()
    return (start + timedelta(days=rng.randint(0, (end - start).days))).isoformat()


def _escolaridade(rng: random.Random, cargo: str) -> str:
    if cargo in ("DIRETOR", "SUPERINTENDENTE"):
        return rng.choice(["POS_GRADUACAO", "POS_GRADUACAO", "MESTRADO", "SUPERIOR"])
    if cargo in ("GERENTE_AGENCIA", "COORDENADOR", "GERENTE_RELACIONAMENTO", "ANALISTA_SR", "ANALISTA_PL"):
        return rng.choice(["SUPERIOR", "SUPERIOR", "POS_GRADUACAO", "SUPERIOR_INCOMPLETO"])
    if cargo == "ANALISTA_JR":
        return rng.choice(["SUPERIOR_INCOMPLETO", "SUPERIOR", "SUPERIOR"])
    return rng.choice(["MEDIO", "MEDIO", "SUPERIOR_INCOMPLETO", "SUPERIOR", "TECNICO"])


def org_slots(size: int, rng: random.Random) -> list[dict]:
    """Returns position slots (cargo, unidade, cidade, uf, manager slot index)."""
    slots: list[dict] = []

    def add(cargo: str, unidade: str, cidade: str, uf: str, gestor: int | None) -> int:
        slots.append({"cargo": cargo, "unidade": unidade, "cidade": cidade, "uf": uf, "gestor": gestor})
        return len(slots) - 1

    diretor = add("DIRETOR", "SEDE", "São Paulo", "SP", None)
    n_sup = max(2, size // 40)
    sups = [add("SUPERINTENDENTE", "SEDE", "São Paulo", "SP", diretor) for _ in range(n_sup)]
    n_coord = max(1, size // 25)
    coords = [add("COORDENADOR", "SEDE", "São Paulo", "SP", rng.choice(sups)) for _ in range(n_coord)]
    n_ag = max(2, size // 14)
    agencies = []
    for i in range(n_ag):
        cidade, uf = CITIES[i % len(CITIES)]
        unidade = f"AG-{1000 + i}"
        ga = add("GERENTE_AGENCIA", unidade, cidade, uf, sups[i % len(sups)])
        agencies.append((unidade, cidade, uf, ga))
    while len(slots) < size:
        roll = rng.random()
        if roll < 0.62:
            unidade, cidade, uf, ga = rng.choice(agencies)
            cargo = rng.choices(["ESCRITURARIO", "CAIXA", "GERENTE_RELACIONAMENTO"], [0.45, 0.25, 0.30])[0]
            add(cargo, unidade, cidade, uf, ga)
        else:
            cargo = rng.choices(["ANALISTA_JR", "ANALISTA_PL", "ANALISTA_SR"], [0.4, 0.35, 0.25])[0]
            add(cargo, "SEDE", "São Paulo", "SP", rng.choice(coords))
    return slots[:size]


def generate_team(*, size: int, seed: int, today: str, norma: dict, cargos: dict[str, dict], drift_percent: float = 15,
                  start_index: int = 1) -> list[dict]:
    rng = random.Random(seed)
    hoje = date.fromisoformat(today)
    slots = org_slots(size, rng)
    ids = [f"F{start_index + i:05d}" for i in range(len(slots))]
    ctx = Ctx(event={"data_efetiva": today}, norma=norma, politica=None, cargos=cargos)
    employees = []
    for i, slot in enumerate(slots):
        cargo = slot["cargo"]
        contract = cargos.get(cargo)
        if contract is None:
            continue
        nivel = int(contract.get("nivel", 1))
        genero = rng.choice(["F", "M"])
        nome = f"{rng.choice(FIRST_F if genero == 'F' else FIRST_M)} {rng.choice(LAST)} {rng.choice(LAST)}"
        idade = rng.randint(max(20, 18 + nivel * 2), min(64, 40 + nivel * 3))
        nascimento = _rand_date(rng, hoje.replace(year=hoje.year - idade - 1), hoje.replace(year=hoje.year - idade))
        max_casa = max(1, min(idade - 18, 30))
        anos_casa = rng.randint(0 if nivel <= 2 else 1, max_casa)
        admissao = _rand_date(rng, hoje - timedelta(days=365 * anos_casa + 300), hoje - timedelta(days=max(40, 365 * anos_casa)))
        adm_d = date.fromisoformat(admissao)
        # a share of people was promoted recently, which makes interstício rules bite
        recent = rng.random() < 0.3
        inicio_cargo = _rand_date(rng, max(adm_d, hoje - timedelta(days=330)), hoje - timedelta(days=30)) if recent \
            else _rand_date(rng, adm_d, max(adm_d, hoje - timedelta(days=400)))
        faixa = (contract.get("estado_alvo") or {}).get("faixa_salarial") or {"min": 4000, "max": 6000}
        salario = round(rng.uniform(float(faixa["min"]), float(faixa["min"]) + (float(faixa["max"]) - float(faixa["min"])) * 0.85) / 10) * 10
        certs: list[str] = []
        if cargo in ("GERENTE_RELACIONAMENTO", "GERENTE_AGENCIA"):
            certs.append("CPA-20")
        elif cargo in ("CAIXA", "ESCRITURARIO", "ANALISTA_JR", "ANALISTA_PL", "ANALISTA_SR", "COORDENADOR"):
            r = rng.random()
            if r < 0.25:
                certs.append("CPA-20")
            elif r < 0.6:
                certs.append("CPA-10")
        if nivel >= 6 and rng.random() < 0.4:
            certs.append("CEA")
        dependentes = []
        for _ in range(rng.choices([0, 1, 2, 3], [0.45, 0.3, 0.2, 0.05])[0]):
            idade_dep_meses = rng.randint(1, 18 * 12)
            dependentes.append({"nome": f"{rng.choice(FIRST_F + FIRST_M)} {nome.split()[-1]}", "parentesco": "FILHO",
                                "data_nascimento": add_months(today, -idade_dep_meses)})
        conduta: dict[str, Any] = {"advertencias": [], "processo_disciplinar_aberto": False, "medida_restritiva_compliance": False}
        if rng.random() < 0.08:
            conduta["advertencias"].append({"data": add_months(today, -rng.randint(1, 20)), "motivo": rng.choice(
                ["Atrasos reiterados", "Descumprimento de procedimento de abertura de conta", "Uso indevido de sistema"])})
        if rng.random() < 0.04:
            conduta["processo_disciplinar_aberto"] = True
        if rng.random() < 0.012:
            conduta["medida_restritiva_compliance"] = True
        estabilidades = []
        if genero == "F" and idade < 42 and rng.random() < 0.04:
            estabilidades.append({"tipo": "GESTANTE", "inicio": add_months(today, -rng.randint(1, 6)), "fim": add_months(today, rng.randint(6, 12)),
                                  "base_legal": "ADCT art. 10 II b"})
        if rng.random() < 0.03:
            estabilidades.append({"tipo": "CIPA", "inicio": add_months(today, -rng.randint(1, 10)), "fim": add_months(today, rng.randint(6, 20)),
                                  "base_legal": "ADCT art. 10 II a"})
        if rng.random() < 0.012 and nivel <= 4:
            estabilidades.append({"tipo": "DIRIGENTE_SINDICAL", "inicio": add_months(today, -rng.randint(1, 20)), "fim": add_months(today, rng.randint(12, 36)),
                                  "base_legal": "CLT art. 543"})
        if rng.random() < 0.012:
            estabilidades.append({"tipo": "ACIDENTE_TRABALHO", "inicio": add_months(today, -rng.randint(1, 8)), "fim": add_months(today, rng.randint(2, 10)),
                                  "base_legal": "Lei 8.213/1991 art. 118"})
        ref = int(norma.get("parametros", {}).get("idade_aposentadoria_referencia", 62))
        if idade >= ref - 2 and anos_casa >= 5:
            fim = add_months(nascimento, ref * 12)
            estabilidades.append({"tipo": "PRE_APOSENTADORIA", "inicio": add_months(fim, -24), "fim": fim, "base_legal": "CCT (ilustrativa)"})
        situacao = "ATIVO"
        afastamento = None
        if rng.random() < 0.025:
            situacao = "AFASTADO"
            afastamento = {"tipo": rng.choice(["DOENCA", "DOENCA", "ACIDENTE_TRABALHO"]),
                           "inicio": add_months(today, -rng.randint(1, 5)), "previsao_retorno": add_months(today, rng.randint(1, 4))}
        emp = {
            "id": ids[i], "nome": nome, "cpf": cpf(rng), "data_nascimento": nascimento, "genero": genero,
            "escolaridade": _escolaridade(rng, cargo), "data_admissao": admissao, "cargo": cargo,
            "data_inicio_cargo": inicio_cargo, "salario_base": float(salario), "regime_jornada": None, "jornada_horas": None,
            "unidade": slot["unidade"], "cidade": slot["cidade"], "uf": slot["uf"],
            "data_inicio_unidade": _rand_date(rng, adm_d, hoje - timedelta(days=20)),
            "centro_custo": f"CC-{slot['unidade']}", "sindicato": None,
            "gestor_id": ids[slot["gestor"]] if slot["gestor"] is not None else None,
            "avaliacao_desempenho": rng.choices([1, 2, 3, 4, 5], [0.04, 0.12, 0.42, 0.30, 0.12])[0],
            "certificacoes": certs, "dependentes": dependentes, "conduta": conduta, "estabilidades": estabilidades,
            "situacao": situacao, "afastamento": afastamento, "beneficios": [], "verbas": [], "acessos": [], "equipamentos": [],
            "clausulas": [], "historico_cargos": [], "licencas": [], "exames": [], "treinamentos": [], "esocial": [],
            "historico_salarial": [{"data": add_months(today, -rng.randint(3, 30)), "de": round(salario * 0.95, 2), "para": float(salario), "motivo": "reajuste anterior"}],
            "historico": [{"data": admissao, "tipo": "ADMISSAO", "descricao": "Admissão (carga inicial gerada)"}],
            "drift": [],
        }
        tobe = target_state(emp, ctx)
        emp["regime_jornada"] = tobe.get("regime_jornada")
        emp["jornada_horas"] = tobe.get("jornada_horas")
        emp["sindicato"] = tobe.get("sindicato")
        emp["verbas"] = [{"codigo": v["codigo"], "nome": v.get("nome"), "valor": v["valor"], "recorrente": True, "origem": "CONTRATO", "desde": inicio_cargo} for v in tobe.get("verbas") or []]
        emp["beneficios"] = [{"codigo": b["codigo"], "nome": b.get("nome"), "plano": b.get("plano"), "valor": b.get("valor"), "desde": admissao} for b in tobe.get("beneficios") or []]
        emp["acessos"] = [a["codigo"] for a in tobe.get("acessos") or []]
        emp["equipamentos"] = [e["codigo"] for e in tobe.get("equipamentos") or []]
        emp["clausulas"] = [{"codigo": c["codigo"], "nome": c.get("nome"), "parametros": c.get("parametros") or {}, "desde": inicio_cargo} for c in tobe.get("clausulas") or []]
        if rng.random() * 100 < drift_percent:
            apply_drift(emp, rng)
        employees.append(emp)
    return employees


def apply_drift(emp: dict, rng: random.Random, kind: str | None = None) -> str | None:
    options = [d for d, _ in DRIFTS]
    rng.shuffle(options)
    for k in ([kind] if kind else options):
        if k == "SEM_VR" and any(b["codigo"] == "VR" for b in emp["beneficios"]):
            emp["beneficios"] = [b for b in emp["beneficios"] if b["codigo"] != "VR"]
        elif k == "JORNADA_8H_SEM_CONFIANCA" and emp.get("regime_jornada") == "NORMAL_224":
            emp["jornada_horas"] = 8
        elif k == "GRATIFICACAO_ABAIXO" and any(v["codigo"] == "GRAT_FUNCAO" for v in emp["verbas"]):
            for v in emp["verbas"]:
                if v["codigo"] == "GRAT_FUNCAO":
                    v["valor"] = round(v["valor"] * 0.7, 2)
        elif k == "SINDICATO_ERRADO":
            emp["sindicato"] = "SEEB-RJ" if emp.get("sindicato") != "SEEB-RJ" else "SEEB-SP"
        elif k == "SEM_CELULAR_GESTOR" and "CELULAR_CORPORATIVO" in emp["equipamentos"]:
            emp["equipamentos"] = [e for e in emp["equipamentos"] if e != "CELULAR_CORPORATIVO"]
        elif k == "ACESSO_EXCEDENTE" and emp["situacao"] == "ATIVO":
            emp["acessos"].append("ADMIN_CORE_BANCARIO")
        elif k == "PLANO_SAUDE_ERRADO" and any(b["codigo"] == "SAUDE" for b in emp["beneficios"]):
            for b in emp["beneficios"]:
                if b["codigo"] == "SAUDE":
                    b["plano"] = "BASICO" if b["plano"] != "BASICO" else "OURO"
        elif k == "SEM_CRECHE" and any(b["codigo"] == "AUXILIO_CRECHE" for b in emp["beneficios"]):
            emp["beneficios"] = [b for b in emp["beneficios"] if b["codigo"] != "AUXILIO_CRECHE"]
        else:
            continue
        emp.setdefault("drift", []).append(k)
        return k
    return None
