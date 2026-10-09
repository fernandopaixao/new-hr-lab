from hrlab.contracts import from_yaml, is_valid_on, to_yaml, validate


def test_all_seed_contracts_are_valid(seeds):
    for doc in seeds["all"]:
        assert validate(doc) == [], doc["codigo"]


def test_yaml_round_trip(seeds):
    doc = seeds["processos"]["colaborador.promovido"]
    assert from_yaml(to_yaml(doc)) == doc


def test_vigencia(seeds):
    doc = dict(seeds["processos"]["colaborador.promovido"], vigencia={"inicio": "2027-01-01", "fim": None})
    assert not is_valid_on(doc, "2026-10-09")
    assert is_valid_on(doc, "2027-02-01")


def test_invalid_rule_expression_is_reported(seeds):
    doc = dict(seeds["processos"]["colaborador.promovido"])
    doc["elegibilidade"] = {"regras": [{"id": "X-1", "tipo": "BLOQUEANTE", "descricao": "quebrada", "expressao": "colaborador.("}]}
    assert validate(doc)
