"""Batch decisions on the approvals screen: each approval is decided and logged on its own."""
import asyncio

import pytest

from hrlab import pipeline as pipeline_mod
from hrlab.pipeline import MAX_BATCH, Pipeline


class FakeStore:
    def __init__(self, approvals):
        self.approvals = {a["id"]: a for a in approvals}

    async def get_approval(self, ap_id):
        return self.approvals.get(ap_id)


class RecordingPipeline(Pipeline):
    """Replaces the single decision with a stub that follows its rules, to look only at the batch."""

    def __init__(self, store, cancels_siblings=False):
        super().__init__(store)
        self.calls = []
        self.cancels_siblings = cancels_siblings

    async def decide(self, ap_id, persona, decisao, justificativa, *, lote=None):
        self.calls.append((ap_id, persona, decisao, justificativa, lote))
        ap = await self.store.get_approval(ap_id)
        if not ap:
            raise ValueError("aprovação não encontrada")
        if ap["status"] != "PENDENTE":
            raise ValueError(f"aprovação já decidida ({ap['status']})")
        if persona not in ap["aprovadores"]:
            raise PermissionError(f"a persona {persona} não pode decidir")
        ap.update({"status": "APROVADA" if decisao == "APROVAR" else "REJEITADA", "lote": lote})
        if self.cancels_siblings and decisao == "REJEITAR":
            for other in self.store.approvals.values():
                if other["case_id"] == ap["case_id"] and other["status"] == "PENDENTE":
                    other["status"] = "CANCELADA"
        return ap


def approval(ap_id, case_id="caso-1", aprovadores=("RH_BP",)):
    return {"id": ap_id, "case_id": case_id, "status": "PENDENTE", "aprovadores": list(aprovadores)}


@pytest.fixture
def logged(monkeypatch):
    entries = []

    async def write(store, tipo, mensagem, **kw):
        entries.append({"tipo": tipo, "mensagem": mensagem, **kw})
        return {}
    monkeypatch.setattr(pipeline_mod.log, "write", write)
    return entries


def test_batch_decides_each_approval_with_the_same_batch_id(logged):
    store = FakeStore([approval("ap-1", "caso-1"), approval("ap-2", "caso-2"), approval("ap-3", "caso-3", ("GESTOR",))])
    pipe = RecordingPipeline(store)
    out = asyncio.run(pipe.decide_batch(["ap-1", "ap-2", "ap-2", "ap-3"], "RH_BP", "APROVAR", "Política revisada pelo comitê"))
    assert [c[0] for c in pipe.calls] == ["ap-1", "ap-2", "ap-3"]  # duplicates removed, order kept
    assert {c[4] for c in pipe.calls} == {out["lote"]} and out["lote"].startswith("lote-")
    assert (out["total"], out["decididas"], out["falhas"], out["ignoradas"]) == (3, 2, 1, 0)
    failed = next(r for r in out["resultados"] if r["id"] == "ap-3")
    assert failed["resultado"] == "FALHOU" and "não pode decidir" in failed["motivo"]
    assert store.approvals["ap-1"]["lote"] == out["lote"]
    summary = [e for e in logged if e["tipo"] == pipeline_mod.log.APROVACAO_LOTE]
    assert len(summary) == 1 and summary[0]["ator"] == "persona:RH_BP" and summary[0]["dados"]["lote"] == out["lote"]


def test_rejection_that_cancels_a_sibling_reports_it_as_ignored(logged):
    store = FakeStore([approval("ap-1", "caso-1"), approval("ap-2", "caso-1")])
    pipe = RecordingPipeline(store, cancels_siblings=True)
    out = asyncio.run(pipe.decide_batch(["ap-1", "ap-2"], "RH_BP", "REJEITAR", "Fora da política vigente"))
    assert (out["decididas"], out["ignoradas"], out["falhas"]) == (1, 1, 0)
    assert out["resultados"][1]["status"] == "CANCELADA"


@pytest.mark.parametrize("ids,decisao,just,msg", [
    ([], "APROVAR", "justificativa ok", "ao menos uma"),
    (["ap-1"], "TALVEZ", "justificativa ok", "APROVAR ou REJEITAR"),
    (["ap-1"], "APROVAR", "ok", "justificativa"),
    ([f"ap-{i}" for i in range(MAX_BATCH + 1)], "APROVAR", "justificativa ok", "no máximo"),
])
def test_batch_is_validated_before_any_decision(logged, ids, decisao, just, msg):
    pipe = RecordingPipeline(FakeStore([approval("ap-1")]))
    with pytest.raises(ValueError, match=msg):
        asyncio.run(pipe.decide_batch(ids, "RH_BP", decisao, just))
    assert pipe.calls == [] and logged == []
