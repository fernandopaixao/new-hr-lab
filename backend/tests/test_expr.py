import pytest

from hrlab.expr import ExpressionError, evaluate, resolve_value, unwrap, wrap


def test_attribute_access_and_arithmetic():
    names = {"colaborador": wrap({"salario_base": 5000, "cargo": "CAIXA"})}
    assert evaluate("colaborador.salario_base * 1.1 > 5400", names) is True
    assert evaluate("colaborador.cargo in ['CAIXA', 'ESCRITURARIO']", names) is True


def test_missing_attribute_is_none():
    names = {"colaborador": wrap({})}
    assert evaluate("colaborador.inexistente is None", names) is True


def test_parameter_strings_starting_with_equals_are_expressions():
    names = {"x": 2}
    assert unwrap(resolve_value("=x + 3", names)) == 5
    assert resolve_value("literal", names) == "literal"


@pytest.mark.parametrize("source", [
    "__import__('os')",
    "colaborador.__class__",
    "(lambda: 1)()",
    "open('/etc/passwd')",
])
def test_unsafe_constructs_are_rejected(source):
    with pytest.raises(ExpressionError):
        evaluate(source, {"colaborador": wrap({})})
