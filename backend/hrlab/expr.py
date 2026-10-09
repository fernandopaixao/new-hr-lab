"""Safe expression evaluator used by contracts.

Contracts express eligibility rules, compliance checks, operation conditions and
parameters as small Python-like expressions, for example:

    colaborador.situacao == 'ATIVO' and meses_no_cargo >= politica.promocao.meses_minimos

Only a whitelisted subset of the Python grammar is accepted (no attribute access
to dunder names, no imports, no lambdas, no assignment). Dicts are wrapped so
that `a.b` and `a['b']` both work.
"""
from __future__ import annotations

import ast
import operator
from datetime import date, datetime
from typing import Any, Callable


class ExpressionError(Exception):
    pass


class Obj(dict):
    """Dict with attribute access. Missing keys resolve to None."""

    def __getattr__(self, item: str) -> Any:
        if item.startswith("_"):
            raise AttributeError(item)
        return wrap(self.get(item))


def wrap(value: Any) -> Any:
    if isinstance(value, Obj):
        return value
    if isinstance(value, dict):
        return Obj(value)
    if isinstance(value, list):
        return [wrap(v) for v in value]
    return value


_BIN_OPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_CMP_OPS: dict[type, Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in (b or []),
    ast.NotIn: lambda a, b: a not in (b or []),
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def months_between(start: Any, end: Any) -> int:
    a, b = _to_date(start), _to_date(end)
    if a is None or b is None:
        return 0
    months = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day < a.day:
        months -= 1
    return months


def days_between(start: Any, end: Any) -> int:
    a, b = _to_date(start), _to_date(end)
    if a is None or b is None:
        return 0
    return (b - a).days


def years_between(start: Any, end: Any) -> int:
    return months_between(start, end) // 12


BASE_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "len": lambda x: len(x or []),
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "sum": lambda x: sum(x or []),
    "any": any,
    "all": all,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "data": _to_date,
    "meses_entre": months_between,
    "dias_entre": days_between,
    "anos_entre": years_between,
    "vazio": lambda x: not x,
}


class _Evaluator:
    def __init__(self, names: dict[str, Any]):
        self.names = names

    def eval(self, node: ast.AST) -> Any:
        method = getattr(self, f"_{type(node).__name__}", None)
        if method is None:
            raise ExpressionError(f"construção não permitida: {type(node).__name__}")
        return method(node)

    def _Expression(self, node: ast.Expression) -> Any:
        return self.eval(node.body)

    def _Constant(self, node: ast.Constant) -> Any:
        return node.value

    def _Name(self, node: ast.Name) -> Any:
        if node.id in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[node.id]
        if node.id not in self.names:
            raise ExpressionError(f"nome desconhecido: {node.id}")
        return wrap(self.names[node.id])

    def _Attribute(self, node: ast.Attribute) -> Any:
        if node.attr.startswith("_"):
            raise ExpressionError("atributo não permitido")
        base = self.eval(node.value)
        if base is None:
            return None
        if isinstance(base, dict):
            return wrap(base.get(node.attr))
        raise ExpressionError(f"atributo '{node.attr}' indisponível em {type(base).__name__}")

    def _Subscript(self, node: ast.Subscript) -> Any:
        base = self.eval(node.value)
        key = self.eval(node.slice)
        if base is None:
            return None
        try:
            return wrap(base[key])
        except (KeyError, IndexError, TypeError):
            return None

    def _List(self, node: ast.List) -> Any:
        return [self.eval(e) for e in node.elts]

    def _Tuple(self, node: ast.Tuple) -> Any:
        return tuple(self.eval(e) for e in node.elts)

    def _Dict(self, node: ast.Dict) -> Any:
        return Obj({self.eval(k): self.eval(v) for k, v in zip(node.keys, node.values)})

    def _BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            result: Any = True
            for v in node.values:
                result = self.eval(v)
                if not result:
                    return result
            return result
        result = False
        for v in node.values:
            result = self.eval(v)
            if result:
                return result
        return result

    def _UnaryOp(self, node: ast.UnaryOp) -> Any:
        val = self.eval(node.operand)
        if isinstance(node.op, ast.Not):
            return not val
        if isinstance(node.op, ast.USub):
            return -val
        if isinstance(node.op, ast.UAdd):
            return +val
        raise ExpressionError("operador unário não permitido")

    def _BinOp(self, node: ast.BinOp) -> Any:
        fn = _BIN_OPS.get(type(node.op))
        if fn is None:
            raise ExpressionError("operador não permitido")
        return fn(self.eval(node.left), self.eval(node.right))

    def _Compare(self, node: ast.Compare) -> Any:
        left = self.eval(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self.eval(comp)
            fn = _CMP_OPS[type(op)]
            try:
                ok = fn(left, right)
            except TypeError:
                # comparisons with None behave as False instead of crashing
                ok = False
            if not ok:
                return False
            left = right
        return True

    def _IfExp(self, node: ast.IfExp) -> Any:
        return self.eval(node.body) if self.eval(node.test) else self.eval(node.orelse)

    def _Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ExpressionError("apenas funções nomeadas são permitidas")
        fn = self.names.get(node.func.id)
        if not callable(fn):
            raise ExpressionError(f"função desconhecida: {node.func.id}")
        args = [self.eval(a) for a in node.args]
        kwargs = {k.arg: self.eval(k.value) for k in node.keywords if k.arg}
        return wrap(fn(*args, **kwargs))

    def _comprehension(self, node: Any, build: Callable[[list], Any]) -> Any:
        if len(node.generators) != 1:
            raise ExpressionError("apenas uma cláusula 'for' é permitida")
        gen = node.generators[0]
        if not isinstance(gen.target, ast.Name):
            raise ExpressionError("alvo de iteração inválido")
        items = self.eval(gen.iter) or []
        out = []
        saved = self.names.get(gen.target.id, _MISSING)
        try:
            for item in items:
                self.names[gen.target.id] = item
                if all(self.eval(cond) for cond in gen.ifs):
                    out.append(self.eval(node.elt))
        finally:
            if saved is _MISSING:
                self.names.pop(gen.target.id, None)
            else:
                self.names[gen.target.id] = saved
        return build(out)

    def _ListComp(self, node: ast.ListComp) -> Any:
        return self._comprehension(node, list)

    def _GeneratorExp(self, node: ast.GeneratorExp) -> Any:
        return self._comprehension(node, list)


_MISSING = object()
_CACHE: dict[str, ast.Expression] = {}


def compile_expression(source: str) -> ast.Expression:
    tree = _CACHE.get(source)
    if tree is None:
        try:
            tree = ast.parse(source.strip(), mode="eval")
        except SyntaxError as exc:
            raise ExpressionError(f"sintaxe inválida: {exc.msg}") from exc
        _CACHE[source] = tree
    return tree


def evaluate(source: str, names: dict[str, Any]) -> Any:
    tree = compile_expression(str(source))
    scope = dict(BASE_FUNCTIONS)
    scope.update(names)
    try:
        return _Evaluator(scope).eval(tree)
    except ExpressionError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any runtime error as a rule error
        raise ExpressionError(f"{type(exc).__name__}: {exc}") from exc


def resolve_value(value: Any, names: dict[str, Any]) -> Any:
    """Resolve a contract parameter: strings starting with '=' are expressions."""
    if isinstance(value, str) and value.startswith("="):
        return unwrap(evaluate(value[1:], names))
    if isinstance(value, dict):
        return {k: resolve_value(v, names) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_value(v, names) for v in value]
    return value


def unwrap(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: unwrap(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [unwrap(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
