"""JEV engine: eligibility classification and audits with a JEV-style decision model.

A decision model (tev1:0.8b by default, served by Ollama 0.35+ at /v1/systemone)
does not write text: it receives named texts (`state`) and named questions, and
answers every question in one request with a probability for each option. So the
JEV engine is shaped differently from the generative (Qwen) engine:

- the context is a few short texts instead of one large JSON prompt;
- the verdict is a `choice` question with the same options the pipeline uses
  (ELEGIVEL, EXCECAO_NECESSARIA, NAO_ELEGIVEL or APROVADO, REPROVADO);
- each compliance check the generative agent would write as a finding is a `noul`
  (yes or no) question; a probability of 0.5 or more becomes a finding;
- the risk is a `score` question over four ordered labels;
- the summary and the reasoning are written here from the probabilities, so every
  decision stays explained in the log, as with the generative agent.

The deterministic rules still decide (ADR 0006); this engine, like Qwen, recommends.
"""
from __future__ import annotations

import json
from typing import Any

RISK_LABELS = ["baixo", "medio", "alto", "critico"]
FINDING_THRESHOLD = 0.5


def _compact(obj: Any, limit: int = 1800) -> str:
    text = json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
    return text if len(text) <= limit else text[:limit] + "..."


def _rules_text(rules: list[dict]) -> str:
    lines = []
    for r in rules:
        state = "atendida" if r.get("passou") else "NAO ATENDIDA"
        lines.append(f"[{r.get('tipo')}] {r.get('id')}: {r.get('descricao') or ''} -> {state}"
                     + ("" if r.get("passou") else f": {r.get('explicacao') or ''}"))
    return "\n".join(lines) or "nenhuma regra avaliada"


ELIGIBILITY_QUESTIONS: dict[str, dict] = {
    "classificacao": {
        "type": "choice",
        "instructions": "Classifique a elegibilidade do colaborador para este evento de RH, segundo a política, a CLT e a convenção dos bancários.",
        "criteria": {
            "ELEGIVEL": "Todas as regras bloqueantes e excecionáveis estão atendidas; o movimento pode seguir.",
            "EXCECAO_NECESSARIA": "Só regras excecionáveis não foram atendidas; o movimento depende de aprovação de exceção.",
            "NAO_ELEGIVEL": "Alguma regra bloqueante não foi atendida ou há impedimento legal; o movimento não pode seguir.",
        },
    },
    "restricao_conduta": {"type": "noul", "instructions": "Há restrição de conduta ou de compliance (processo disciplinar aberto, medida restritiva) que impede o movimento?"},
    "impedimento_legal": {"type": "noul", "instructions": "O movimento viola a CLT, a convenção coletiva ou uma estabilidade do colaborador?"},
    "risco": {"type": "score", "instructions": "Qual o risco de aprovar este movimento?", "criteria": RISK_LABELS},
}

AUDIT_QUESTIONS: dict[str, dict] = {
    "recomendacao": {
        "type": "choice",
        "instructions": "Audite o plano de execução antes de qualquer sistema ser alterado: ele é aderente ao compliance e às regras de negócio?",
        "criteria": {
            "APROVADO": "O plano é coerente com o evento e com os contratos e pode ser executado, mesmo com observações menores.",
            "REPROVADO": "O plano tem violação legal, regra bloqueante não atendida, operação obrigatória ausente, redução salarial ou acesso indevido.",
        },
    },
    "violacao_legal": {"type": "noul", "instructions": "O plano viola a CLT ou a convenção coletiva dos bancários?"},
    "operacao_obrigatoria_ausente": {"type": "noul", "instructions": "Falta no plano alguma operação obrigatória para este evento (por exemplo eSocial ou cálculo de rescisão)?"},
    "reducao_salarial": {"type": "noul", "instructions": "O plano reduz o salário do colaborador sem base legal?"},
    "acesso_indevido": {"type": "noul", "instructions": "O estado projetado mantém acesso, benefício ou equipamento que o novo cargo não deveria ter?"},
    "risco": {"type": "score", "instructions": "Qual o risco de executar este plano?", "criteria": RISK_LABELS},
}

VERIFICATION_QUESTIONS: dict[str, dict] = {
    "recomendacao": {
        "type": "choice",
        "instructions": "Confira a execução concluída: ela foi aplicada igual ao plano auditado e em conformidade?",
        "criteria": {
            "APROVADO": "Todas as operações têm recibo e o estado final é igual ao auditado.",
            "REPROVADO": "Falta recibo, alguma operação falhou ou o estado final diverge do auditado.",
        },
    },
    "recibo_ausente": {"type": "noul", "instructions": "Alguma operação do plano está sem recibo ou falhou?"},
    "estado_divergente": {"type": "noul", "instructions": "O estado final do colaborador diverge do estado auditado antes da execução?"},
    "violacao_legal": {"type": "noul", "instructions": "O estado final viola a CLT ou a convenção coletiva dos bancários?"},
    "risco": {"type": "score", "instructions": "Qual o risco de manter esta execução?", "criteria": RISK_LABELS},
}

QUESTIONS = {"ELEGIBILIDADE": ELIGIBILITY_QUESTIONS, "AUDITORIA": AUDIT_QUESTIONS, "CONFERENCIA": VERIFICATION_QUESTIONS}
VERDICT_QUESTION = {"ELEGIBILIDADE": "classificacao", "AUDITORIA": "recomendacao", "CONFERENCIA": "recomendacao"}

# finding written when a yes or no check crosses the threshold: (severity, reference, description)
FINDINGS: dict[str, tuple[str, str, str]] = {
    "restricao_conduta": ("CRITICO", "Política de movimentação", "Restrição de conduta ou de compliance impede o movimento."),
    "impedimento_legal": ("CRITICO", "CLT / CCT", "O movimento viola a lei, a convenção ou uma estabilidade."),
    "violacao_legal": ("CRITICO", "CLT / CCT", "Violação da CLT ou da convenção coletiva dos bancários."),
    "operacao_obrigatoria_ausente": ("ALTO", "Contrato do processo", "Falta operação obrigatória para o evento."),
    "reducao_salarial": ("CRITICO", "CLT art. 468", "Redução salarial sem base legal."),
    "acesso_indevido": ("ALTO", "Contrato do cargo", "Estado projetado mantém acesso, benefício ou equipamento indevido."),
    "recibo_ausente": ("ALTO", "Contrato de serviço", "Operação sem recibo ou com falha."),
    "estado_divergente": ("ALTO", "Conferência final", "Estado final diverge do auditado."),
}


def build_state(kind: str, case: dict, processo: dict, cargo_alvo: dict | None, compact_employee, subject: dict | None = None) -> dict[str, str]:
    """Short named texts: only what the questions of this task need."""
    ev = case.get("evento") or {}
    state = {"evento": f"{ev.get('tipo')} em {ev.get('data_efetiva')}: {_compact(ev.get('dados'), 700)}",
             "processo": f"{processo.get('codigo')}: {processo.get('nome')}"}
    if kind == "ELEGIBILIDADE":
        state["colaborador"] = _compact(compact_employee(subject))
        state["cargo_alvo"] = _compact({"cargo": (cargo_alvo or {}).get("cargo"), "nome": (cargo_alvo or {}).get("nome")}, 300)
        state["regras"] = _rules_text((case.get("elegibilidade") or {}).get("regras") or [])
    elif kind == "AUDITORIA":
        plano = case.get("plano") or {}
        state["colaborador_atual"] = _compact(compact_employee(case.get("estado_inicial")))
        state["plano"] = "\n".join(f"{o['seq']}. {o['operacao']} {_compact(o.get('parametros'), 200)}: {o.get('motivo')}"
                                   for o in plano.get("operacoes") or []) or "plano vazio"
        state["estado_projetado"] = _compact(compact_employee(plano.get("projetado")))
        state["regras"] = _rules_text((case.get("auditoria") or {}).get("regras") or [])
    else:
        execucao = case.get("execucao") or {}
        state["recibos"] = "\n".join(f"{r['operacao']}: {r['status']}" for r in execucao.get("recibos") or []) or "sem recibos"
        state["alteracoes"] = _compact(execucao.get("diff"), 1200)
        state["regras"] = _rules_text((case.get("conferencia_final") or {}).get("regras") or [])
        state["divergencias"] = _compact((case.get("conferencia_final") or {}).get("divergencias"), 600)
    return state


def _prob(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v > 1:
        v = v / 100
    return max(0.0, min(1.0, v))


def _risk(answer: dict | None) -> tuple[str | None, float | None]:
    if not isinstance(answer, dict):
        return None, None
    probs = answer.get("probabilities") or {}
    legend = answer.get("legend") or {str(i): label for i, label in enumerate(RISK_LABELS)}
    if probs:
        key = max(probs, key=lambda k: _prob(probs[k]))
        return legend.get(str(key), str(key)), _prob(probs[key])
    score = answer.get("score")
    if isinstance(score, (int, float)):
        idx = max(0, min(len(RISK_LABELS) - 1, round(score * (len(RISK_LABELS) - 1)) if score <= 1 else int(score)))
        return RISK_LABELS[idx], None
    return None, None


def interpret(kind: str, answers: dict, model: str) -> dict:
    """Maps the probabilities to the review the pipeline expects (same fields as the generative agent)."""
    q = VERDICT_QUESTION[kind]
    verdict_answer = answers.get(q) or {}
    options = list(QUESTIONS[kind][q]["criteria"])
    probs = {k: _prob(v) for k, v in (verdict_answer.get("probabilities") or {}).items() if k in options}
    choice = verdict_answer.get("choice")
    if choice not in options:
        choice = max(probs, key=probs.get) if probs else None
    if choice is None:
        raise ValueError(f"o modelo de decisão não escolheu uma opção válida para {q}: {verdict_answer}")
    conf = verdict_answer.get("confidence")
    conf = _prob(conf) if conf is not None else probs.get(choice, 0.5)
    achados = []
    for name, spec in QUESTIONS[kind].items():
        if spec["type"] != "noul" or name not in FINDINGS:
            continue
        p = _prob((answers.get(name) or {}).get("noul"))
        if p >= FINDING_THRESHOLD:
            sev, ref, desc = FINDINGS[name]
            achados.append({"severidade": sev, "referencia": ref, "descricao": f"{desc} (probabilidade {round(p * 100)}%)"})
    risco, risco_p = _risk(answers.get("risco"))
    if risco:
        achados.append({"severidade": "INFO", "referencia": "risco", "descricao": f"Risco estimado: {risco}"
                        + (f" ({round(risco_p * 100)}%)" if risco_p is not None else "") + "."})
    dist = ", ".join(f"{k} {round(v * 100)}%" for k, v in sorted(probs.items(), key=lambda kv: -kv[1])) or "sem distribuição"
    checks = "; ".join(f"{n} {round(_prob((answers.get(n) or {}).get('noul')) * 100)}%"
                       for n, s in QUESTIONS[kind].items() if s["type"] == "noul")
    label = "classifica" if kind == "ELEGIBILIDADE" else "recomenda"
    out = {
        "confianca": round(conf, 3), "achados": achados,
        "resumo": f"Motor JEV ({model}) {label} {choice} com {round(conf * 100)}% de confiança" + (f"; risco {risco}." if risco else "."),
        "justificativa": f"Distribuição da decisão: {dist}. Verificações (probabilidade de sim): {checks or 'nenhuma'}. "
                         f"Achados entram quando a probabilidade passa de {round(FINDING_THRESHOLD * 100)}%.",
        "probabilidades": probs, "risco": risco, "veredito": choice,
    }
    out["classificacao" if kind == "ELEGIBILIDADE" else "recomendacao"] = choice
    return out
