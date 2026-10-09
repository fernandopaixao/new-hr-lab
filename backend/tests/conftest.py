import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hrlab.contracts import load_seed_documents  # noqa: E402
from hrlab.context import Ctx  # noqa: E402
from hrlab.generators.team import generate_team  # noqa: E402

TODAY = "2026-10-09"


@pytest.fixture(scope="session")
def seeds():
    docs = load_seed_documents()
    return {
        "norma": next(d for d in docs if d["tipo"] == "NORMA"),
        "politica": next(d for d in docs if d["tipo"] == "POLITICA"),
        "cargos": {d["cargo"]: d for d in docs if d["tipo"] == "CARGO"},
        "processos": {d["evento"]: d for d in docs if d["tipo"] == "PROCESSO"},
        "all": docs,
    }


@pytest.fixture
def team(seeds):
    return generate_team(size=80, seed=42, today=TODAY, norma=seeds["norma"], cargos=seeds["cargos"], drift_percent=0)


@pytest.fixture
def make_ctx(seeds):
    def _make(event):
        return Ctx(event=event, norma=seeds["norma"], politica=seeds["politica"], cargos=seeds["cargos"])
    return _make


@pytest.fixture
def clone():
    return copy.deepcopy
