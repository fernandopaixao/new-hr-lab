"""Contract repository: versions, validity periods (vigência) and lookups.

Contracts are YAML documents. Each code keeps a list of versions; the version used
for an event is the one whose vigência contains the event's effective date.
"""
from __future__ import annotations

import copy
import glob
import os
from datetime import date
from typing import Any

import yaml

from . import expr
from .store import Store, now_ms

SEED_DIR = os.path.join(os.path.dirname(__file__), "seeds", "contracts")
KINDS = ("NORMA", "POLITICA", "CARGO", "PROCESSO")
RULE_TYPES = ("BLOQUEANTE", "EXCECIONAVEL", "ALERTA")


class ContractError(ValueError):
    pass


def load_seed_documents() -> list[dict]:
    docs: list[dict] = []
    for path in sorted(glob.glob(os.path.join(SEED_DIR, "*.yaml"))):
        with open(path, encoding="utf-8") as fh:
            for doc in yaml.safe_load_all(fh):
                if doc:
                    docs.append(doc)
    return docs


def _iter_rules(doc: dict) -> list[tuple[str, dict]]:
    rules: list[tuple[str, dict]] = []
    for r in doc.get("compliance") or []:
        rules.append(("compliance", r))
    for r in doc.get("elegibilidade_entrada") or []:
        rules.append(("elegibilidade_entrada", r))
    for section in ("elegibilidade", "conferencia_plano"):
        for r in (doc.get(section) or {}).get("regras") or []:
            rules.append((section, r))
    for r in (doc.get("auditoria") or {}).get("verificacoes") or []:
        rules.append(("auditoria", r))
    return rules


def validate(doc: dict) -> list[str]:
    """Structural validation. Returns a list of problems (empty when valid)."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["o contrato deve ser um objeto"]
    for key in ("codigo", "tipo", "nome", "vigencia"):
        if not doc.get(key):
            problems.append(f"campo obrigatório ausente: {key}")
    if doc.get("tipo") not in KINDS:
        problems.append(f"tipo deve ser um de {KINDS}")
    vig = doc.get("vigencia") or {}
    try:
        start = date.fromisoformat(str(vig.get("inicio")))
        if vig.get("fim"):
            if date.fromisoformat(str(vig["fim"])) < start:
                problems.append("vigência termina antes de começar")
    except (TypeError, ValueError):
        problems.append("vigencia.inicio deve ser uma data AAAA-MM-DD")
    if doc.get("tipo") == "CARGO":
        if not doc.get("cargo"):
            problems.append("contrato de cargo precisa do campo 'cargo'")
        if not isinstance(doc.get("estado_alvo"), dict):
            problems.append("contrato de cargo precisa de 'estado_alvo'")
    if doc.get("tipo") == "PROCESSO":
        if not doc.get("evento"):
            problems.append("contrato de processo precisa do campo 'evento'")
    seen: set[str] = set()
    for section, rule in _iter_rules(doc):
        rid = rule.get("id")
        if not rid:
            problems.append(f"regra sem id em {section}")
            continue
        if rid in seen:
            problems.append(f"id de regra duplicado: {rid}")
        seen.add(rid)
        if rule.get("tipo", "BLOQUEANTE") not in RULE_TYPES:
            problems.append(f"{rid}: tipo deve ser um de {RULE_TYPES}")
        if rule.get("tipo") == "EXCECIONAVEL" and not rule.get("aprovadores"):
            problems.append(f"{rid}: regra excecionável precisa de aprovadores")
        try:
            expr.compile_expression(str(rule.get("expressao", "")))
        except expr.ExpressionError as exc:
            problems.append(f"{rid}: {exc}")
    from .shelf import SHELF  # local import to avoid a cycle

    for op in ((doc.get("orquestracao") or {}).get("operacoes") or []):
        code = op.get("operacao")
        if code not in SHELF:
            problems.append(f"operação desconhecida na prateleira: {code}")
        if op.get("quando"):
            try:
                expr.compile_expression(str(op["quando"]).lstrip("="))
            except expr.ExpressionError as exc:
                problems.append(f"{code}.quando: {exc}")
    return problems


def is_valid_on(doc: dict, when: str) -> bool:
    vig = doc.get("vigencia") or {}
    start = str(vig.get("inicio") or "0000-01-01")
    end = vig.get("fim")
    return start <= when[:10] and (not end or when[:10] <= str(end))


class ContractRepo:
    def __init__(self, store: Store):
        self.store = store

    async def seed(self, force: bool = False) -> int:
        count = 0
        for doc in load_seed_documents():
            existing = await self.store.get_contract_versions(doc["codigo"])
            if existing and not force:
                continue
            doc = copy.deepcopy(doc)
            doc.setdefault("versao", 1)
            doc["salvo_em"] = now_ms()
            doc["salvo_por"] = "seed"
            await self.store.save_contract_versions(doc["codigo"], [doc])
            count += 1
        return count

    async def all_versions(self) -> dict[str, list[dict]]:
        out = {}
        for code in await self.store.list_contract_codes():
            out[code] = await self.store.get_contract_versions(code)
        return out

    async def latest(self) -> list[dict]:
        return [versions[-1] for versions in (await self.all_versions()).values() if versions]

    async def get(self, code: str, when: str | None = None, version: int | None = None) -> dict | None:
        versions = await self.store.get_contract_versions(code)
        if not versions:
            return None
        if version is not None:
            return next((v for v in versions if int(v.get("versao", 0)) == int(version)), None)
        if when is None:
            return versions[-1]
        valid = [v for v in versions if is_valid_on(v, when)]
        return max(valid, key=lambda v: int(v.get("versao", 0))) if valid else None

    async def save(self, doc: dict, author: str, as_new_version: bool = True) -> dict:
        problems = validate(doc)
        if problems:
            raise ContractError("; ".join(problems))
        code = doc["codigo"]
        versions = await self.store.get_contract_versions(code)
        doc = copy.deepcopy(doc)
        doc["salvo_em"] = now_ms()
        doc["salvo_por"] = author
        if as_new_version or not versions:
            doc["versao"] = (max(int(v.get("versao", 0)) for v in versions) + 1) if versions else 1
            versions.append(doc)
        else:
            target = int(doc.get("versao") or versions[-1].get("versao", 1))
            idx = next((i for i, v in enumerate(versions) if int(v.get("versao", 0)) == target), None)
            if idx is None:
                raise ContractError(f"versão {target} não existe")
            doc["versao"] = target
            versions[idx] = doc
        await self.store.save_contract_versions(code, versions)
        return doc

    async def delete_version(self, code: str, version: int) -> None:
        versions = [v for v in await self.store.get_contract_versions(code) if int(v.get("versao", 0)) != int(version)]
        if versions:
            await self.store.save_contract_versions(code, versions)
        else:
            await self.store.delete_contract(code)

    # ---------------------------------------------------------- domain lookups
    async def _valid_of_kind(self, kind: str, when: str) -> list[dict]:
        out = []
        for code, versions in (await self.all_versions()).items():
            valid = [v for v in versions if v.get("tipo") == kind and is_valid_on(v, when)]
            if valid:
                out.append(max(valid, key=lambda v: int(v.get("versao", 0))))
        return out

    async def norma(self, when: str) -> dict | None:
        items = await self._valid_of_kind("NORMA", when)
        return items[0] if items else None

    async def politica(self, when: str) -> dict | None:
        items = await self._valid_of_kind("POLITICA", when)
        return items[0] if items else None

    async def cargos(self, when: str) -> dict[str, dict]:
        return {c["cargo"]: c for c in await self._valid_of_kind("CARGO", when)}

    async def processo_for_event(self, event_type: str, when: str) -> dict | None:
        for doc in await self._valid_of_kind("PROCESSO", when):
            if doc.get("evento") == event_type:
                return doc
        return None

    async def event_types(self) -> list[dict]:
        out = []
        for doc in await self.latest():
            if doc.get("tipo") == "PROCESSO":
                out.append({
                    "evento": doc["evento"], "processo": doc["codigo"], "nome": doc.get("nome"),
                    "descricao": doc.get("descricao"), "schema": doc.get("evento_schema") or {},
                    "coletivo": bool(doc.get("coletivo")),
                })
        return sorted(out, key=lambda x: x["evento"])


def to_yaml(doc: dict) -> str:
    clean = {k: v for k, v in doc.items() if k not in ("salvo_em", "salvo_por")}
    return yaml.safe_dump(clean, allow_unicode=True, sort_keys=False, width=120)


def from_yaml(text: str) -> dict:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ContractError(f"YAML inválido: {exc}") from exc
    if not isinstance(doc, dict):
        raise ContractError("o YAML deve descrever um objeto")
    return doc


def resolve_any(value: Any, names: dict) -> Any:
    return expr.resolve_value(value, names)
