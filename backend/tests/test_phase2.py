
import numpy as np

from hrlab import embeddings as emb
from hrlab.ask import heuristic_interpret, sanitize_query, stats_for, strip_emoji
from hrlab.facts import apply_filters, case_document, case_fact, group_count, insights, percentile

from .conftest import TODAY


def _case(cid, status, tipo="colaborador.promovido", failed=None, created=1_000_000, finished=1_005_000):
    return {
        "id": cid, "evento_tipo": tipo, "status": status, "estagio": "audit", "criado_em": created, "finalizado_em": finished,
        "colaborador_id": "F00001", "colaborador_nome": "Ana", "evento": {"tipo": tipo, "data_efetiva": TODAY, "dados": {}},
        "etapas": {s: {"status": "OK", "duracao_ms": 10} for s in ("intake", "eligibility", "planning", "plan_review", "execution", "audit")},
        "elegibilidade": {"decisao": "NAO_ELEGIVEL" if failed else "ELEGIVEL", "explicacao": "x",
                          "regras": [{"id": failed, "tipo": "BLOQUEANTE", "passou": False, "descricao": "d", "explicacao": "e"}] if failed else []},
        "estado_inicial": {"cargo": "CAIXA", "uf": "SP"}, "aprovacoes": [],
    }


def test_facts_filters_and_groups():
    facts = [case_fact(_case("c1", "CONCLUIDO")), case_fact(_case("c2", "NAO_ELEGIVEL", failed="PRM-05")),
             case_fact(_case("c3", "NAO_ELEGIVEL", tipo="colaborador.transferido", failed="TRF-02"))]
    assert len(apply_filters(facts, {"status": "NAO_ELEGIVEL"})) == 2
    assert len(apply_filters(facts, {"status": "nao_elegivel", "evento_tipo": "colaborador.promovido"})) == 1
    assert [r["valor"] for r in group_count(facts, "regra_falha")] == ["PRM-05", "TRF-02"]
    assert percentile([1, 2, 3, 4, 100], 50) == 3


def test_case_document_mentions_failed_rule():
    text, meta = case_document(_case("c2", "NAO_ELEGIVEL", failed="PRM-05"))
    assert "PRM-05" in text and meta["case_id"] == "c2" and meta["fonte"] == "caso"


def test_insights_shape_and_alerts():
    facts = [case_fact(_case(f"c{i}", "FALHOU_COMPENSADO" if i % 2 else "CONCLUIDO", finished=10_000_000 - i)) for i in range(12)]
    out = insights(facts, now_ms=10_000_000 + 1000)
    assert out["kpis"]["casos"] == 12
    assert any("falharam" in a["texto"] for a in out["alertas"])
    assert [f["estagio"] for f in out["funil"]][0] == "intake"


def test_hash_embedding_groups_portuguese_word_forms():
    a = np.array(emb.hash_embed("desligamento do superintendente com garden leave"))
    b = np.array(emb.hash_embed("superintendente desligado, garden leave iniciado"))
    c = np.array(emb.hash_embed("inclusão de dependente no plano odontológico"))
    assert float(a @ b) > float(a @ c)


def test_heuristic_interpretation():
    cat = {"personas": {"HRBP": "HR Business Partner"}, "ufs": ["SP", "RJ"]}
    q = heuristic_interpret("Quantas promoções ficaram não elegíveis?", cat)
    assert q["intencao"] == "CONTAGEM" and q["filtros"] == {"evento_tipo": "colaborador.promovido", "status": "NAO_ELEGIVEL"}
    assert heuristic_interpret("Quais regras mais barraram eventos?", cat)["agrupar_por"] == "regra_falha"
    assert heuristic_interpret("explique o caso-0a1b2c3d4e", cat)["caso_id"] == "caso-0a1b2c3d4e"


def test_sanitize_drops_unknown_values():
    q = sanitize_query({"intencao": "INVENTADA", "filtros": {"status": "QUALQUER", "hackeado": 1, "uf": "SP"}, "agrupar_por": "x"})
    assert q["intencao"] == "BUSCA" and q["filtros"] == {"uf": "SP"} and q["agrupar_por"] == ""


def test_stats_are_exact():
    facts = [case_fact(_case(f"c{i}", "CONCLUIDO" if i < 7 else "NAO_ELEGIVEL")) for i in range(10)]
    st = stats_for({"intencao": "CONTAGEM", "filtros": {"status": "NAO_ELEGIVEL"}, "agrupar_por": "", "caso_id": "", "consulta_semantica": ""}, facts)
    assert st["casos_que_atendem_aos_filtros"] == 3


def test_strip_emoji():
    assert strip_emoji("Pronto \U0001F680 ok \u2705") == "Pronto  ok "


def test_receipts_feed_operation_facts():
    case = _case("c9", "FALHOU_COMPENSADO")
    case["execucao"] = {"recibos": [{"operacao": "ALTERAR_CARGO", "status": "COMPENSADA"},
                                    {"operacao": "ALTERAR_BENEFICIO", "status": "FALHOU", "erro": "falha simulada"}]}
    f = case_fact(case)
    assert f["operacoes_executadas"] == ["ALTERAR_CARGO"] and f["operacoes_falhas"] == ["ALTERAR_BENEFICIO"] and f["compensado"]
    text, _ = case_document(case)
    assert "ALTERAR_BENEFICIO: FALHOU falha simulada" in text
