"""Shared vocabulary: pipeline stages, case statuses, personas, event types."""
from __future__ import annotations

# Production line stages, in order.
STAGES = [
    ("intake", "Gatilho", "Recebe e valida o evento, garante idempotência e abre o caso."),
    ("eligibility", "Elegibilidade", "Avalia regras de política, conduta, CLT e CCT do contrato do processo e do cargo."),
    ("planning", "Planejamento", "Calcula o estado alvo pelo contrato, escolhe operações da prateleira e projeta o resultado."),
    ("audit", "Auditoria", "Antes de qualquer sistema ser alterado: regras e agente de IA auditam o plano e o estado projetado."),
    ("execution", "Execução", "Executa as operações auditadas em saga, com compensação em caso de falha."),
    ("verification", "Conferência final", "Prova que o executado é igual ao auditado: recibos de todas as operações e estado final igual ao projetado."),
]
# Stage keys used before the audit moved ahead of the execution (kept to migrate stored cases).
LEGACY_STAGE_RENAMES = {"audit": "verification", "plan_review": "audit"}
STAGE_KEYS = [s[0] for s in STAGES]
NEXT_STAGE = {STAGE_KEYS[i]: (STAGE_KEYS[i + 1] if i + 1 < len(STAGE_KEYS) else None) for i in range(len(STAGE_KEYS))}

# Case statuses.
NA_FILA = "NA_FILA"
PROCESSANDO = "PROCESSANDO"
PARADO = "PARADO"  # held by a breakpoint / debug step
AGUARDANDO_APROVACAO = "AGUARDANDO_APROVACAO"
AGUARDANDO_AGENTE = "AGUARDANDO_AGENTE"
CONCLUIDO = "CONCLUIDO"
CONCLUIDO_COM_RESSALVAS = "CONCLUIDO_COM_RESSALVAS"
NAO_ELEGIVEL = "NAO_ELEGIVEL"
REJEITADO = "REJEITADO"
REJEITADO_NA_ENTRADA = "REJEITADO_NA_ENTRADA"
DUPLICADO = "DUPLICADO"
FALHOU_COMPENSADO = "FALHOU_COMPENSADO"
ERRO = "ERRO"
CANCELADO = "CANCELADO"
REVERTIDO = "REVERTIDO"

ACTIVE_STATUSES = {NA_FILA, PROCESSANDO, PARADO, AGUARDANDO_APROVACAO, AGUARDANDO_AGENTE}
FINAL_STATUSES = {
    CONCLUIDO, CONCLUIDO_COM_RESSALVAS, NAO_ELEGIVEL, REJEITADO, REJEITADO_NA_ENTRADA,
    DUPLICADO, FALHOU_COMPENSADO, ERRO, CANCELADO, REVERTIDO,
}

STATUS_LABELS = {
    NA_FILA: "Na fila",
    PROCESSANDO: "Processando",
    PARADO: "Parado (depuração)",
    AGUARDANDO_APROVACAO: "Aguardando aprovação",
    AGUARDANDO_AGENTE: "Aguardando agente de IA",
    CONCLUIDO: "Concluído",
    CONCLUIDO_COM_RESSALVAS: "Concluído com ressalvas",
    NAO_ELEGIVEL: "Não elegível",
    REJEITADO: "Rejeitado",
    REJEITADO_NA_ENTRADA: "Rejeitado na entrada",
    DUPLICADO: "Duplicado",
    FALHOU_COMPENSADO: "Falhou e compensado",
    ERRO: "Erro",
    CANCELADO: "Cancelado",
    REVERTIDO: "Revertido após a conferência final",
}

# Personas that can decide approvals. There is no real authentication: the
# interface switches persona and every decision records who decided.
PERSONAS = {
    "OPERADOR": {"nome": "Operador de RH", "pessoa": "Lúcia Andrade"},
    "GESTOR": {"nome": "Gestor imediato", "pessoa": "Marcos Teixeira"},
    "HRBP": {"nome": "HR Business Partner", "pessoa": "Renata Moura"},
    "JURIDICO": {"nome": "Jurídico trabalhista", "pessoa": "Dr. Paulo Siqueira"},
    "COMPLIANCE": {"nome": "Compliance", "pessoa": "Helena Prado"},
    "AUDITORIA": {"nome": "Auditoria interna", "pessoa": "Ricardo Lemos"},
    "COMITE": {"nome": "Comitê de remuneração", "pessoa": "Comitê (colegiado)"},
}

APPROVAL_EXCECAO = "EXCECAO_ELEGIBILIDADE"
APPROVAL_AUDITORIA = "REVISAO_AUDITORIA"
APPROVAL_CONFERENCIA = "REVISAO_CONFERENCIA_FINAL"
APPROVAL_TYPE_LABELS = {
    APPROVAL_EXCECAO: "Exceção de regra",
    APPROVAL_AUDITORIA: "Revisão humana da auditoria",
    APPROVAL_CONFERENCIA: "Revisão humana da conferência final",
}
# Approval types used before the audit moved ahead of the execution.
LEGACY_APPROVAL_RENAMES = {"REVISAO_AUDITORIA": APPROVAL_CONFERENCIA, "REVISAO_PLANO": APPROVAL_AUDITORIA}

# What leaves each stage and where it goes: shown in the interface so every phase says what comes next.
STAGE_OUTCOMES = {
    "intake": "Evento válido segue para a elegibilidade. Evento inválido, duplicado ou sem contrato vigente encerra o caso.",
    "eligibility": "Elegível segue para o planejamento. Regra excecionável espera a pessoa indicada; regra bloqueante encerra como não elegível.",
    "planning": "O plano e o estado projetado seguem para a auditoria. Nenhum sistema é alterado nesta fase.",
    "audit": "Aprovado segue para a execução. Exceção ou parecer contrário do agente espera uma pessoa; falha bloqueante rejeita sem alterar nada.",
    "execution": "Com todos os recibos, segue para a conferência final. Falha em uma operação compensa as anteriores e encerra o caso.",
    "verification": "Igual ao auditado conclui o caso. Divergência ou parecer contrário do agente vai à auditoria interna, que pode reverter tudo.",
}

# What a pending decision unblocks, by the stage that asked for it.
APPROVAL_OUTCOMES = {
    "eligibility": ("o caso segue para o planejamento", "o caso é rejeitado sem alterar nenhum sistema"),
    "audit": ("o plano é executado", "o caso é rejeitado sem alterar nenhum sistema"),
    "verification": ("o caso é concluído", "todas as operações são compensadas e o caso termina revertido"),
}

FINAL_NEXT_STEPS = {
    CONCLUIDO: "Nada a fazer: o colaborador está no estado auditado.",
    CONCLUIDO_COM_RESSALVAS: "Tratar as ressalvas listadas na decisão final.",
    NAO_ELEGIVEL: "Corrigir o cadastro ou o evento e enviar um novo evento, se for o caso.",
    REJEITADO: "Ler o motivo da rejeição; corrigir a causa e enviar um novo evento, se for o caso.",
    REJEITADO_NA_ENTRADA: "Corrigir o evento (tipo, campos obrigatórios, matrícula ou data) e enviar de novo.",
    DUPLICADO: "Nada a fazer: o mesmo evento já foi tratado no caso original.",
    FALHOU_COMPENSADO: "Verificar o sistema que falhou e enviar o evento de novo; nada ficou aplicado.",
    ERRO: "Ler o erro no detalhe do caso e reprocessar a partir do estágio indicado.",
    CANCELADO: "Nada a fazer: o caso foi cancelado antes da execução.",
    REVERTIDO: "Corrigir a causa apontada pela auditoria interna e enviar um novo evento.",
}


def next_step(case: dict) -> dict:
    """Plain language next step of a case: what happens now, and who has to act (None means the system)."""
    status = case.get("status")
    stage = case.get("estagio") or "intake"
    names = {k: n for k, n, _ in STAGES}
    nxt = NEXT_STAGE.get(stage)
    if status in FINAL_STATUSES:
        return {"texto": FINAL_NEXT_STEPS.get(status, "Caso encerrado."), "quem": None, "encerrado": True}
    if status == PARADO:
        alvo = names.get(case.get("estagio_parado") or stage, stage)
        return {"texto": f"Parado antes de {alvo} para depuração: use Avançar no detalhe do caso.", "quem": "OPERADOR", "encerrado": False}
    if status == AGUARDANDO_AGENTE:
        return {"texto": f"{names.get(stage)} espera o agente de IA responder; o caso retoma sozinho quando o Ollama voltar.",
                "quem": None, "encerrado": False}
    if status == AGUARDANDO_APROVACAO:
        pend = case.get("aguardando") or []
        quem = sorted({p for a in pend for p in a.get("aprovadores") or []})
        sim, nao = APPROVAL_OUTCOMES.get(stage, ("o caso continua", "o caso é rejeitado"))
        partes = []
        for a in pend:
            resp = (a.get("responsavel") or {}).get("nome")
            alvo = " ou ".join(PERSONAS.get(p, {}).get("nome", p) for p in a.get("aprovadores") or [])
            partes.append(f"{a.get('tipo_rotulo')} por {alvo}{f' ({resp})' if resp else ''}")
        detalhe = "; ".join(partes) or "decisão humana"
        return {"texto": f"Decidir: {detalhe}. Aprovando, {sim}; rejeitando, {nao}.", "quem": "/".join(quem) or None, "encerrado": False}
    if status == PROCESSANDO:
        depois = f" Depois: {names.get(nxt)}." if nxt else ""
        return {"texto": f"{names.get(stage)} em andamento.{depois}", "quem": None, "encerrado": False}
    return {"texto": f"Na fila de {names.get(stage)}: {STAGE_OUTCOMES.get(stage, '')}", "quem": None, "encerrado": False}


RULE_BLOQUEANTE = "BLOQUEANTE"
RULE_EXCECIONAVEL = "EXCECIONAVEL"
RULE_ALERTA = "ALERTA"
