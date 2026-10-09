"""Shared vocabulary: pipeline stages, case statuses, personas, event types."""
from __future__ import annotations

# Production line stages, in order.
STAGES = [
    ("intake", "Gatilho", "Recebe e valida o evento, garante idempotência e abre o caso."),
    ("eligibility", "Elegibilidade", "Avalia regras de política, conduta, CLT e CCT do contrato do processo e do cargo."),
    ("planning", "Planejamento", "Calcula o estado alvo pelo contrato e escolhe operações da prateleira."),
    ("plan_review", "Conferência do plano", "Agente de IA e regras conferem o plano contra compliance."),
    ("execution", "Execução", "Executa as operações em saga, com compensação em caso de falha."),
    ("audit", "Auditoria", "Confere o estado resultante contra o contrato de serviço e o compliance."),
]
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

ACTIVE_STATUSES = {NA_FILA, PROCESSANDO, PARADO, AGUARDANDO_APROVACAO, AGUARDANDO_AGENTE}
FINAL_STATUSES = {
    CONCLUIDO, CONCLUIDO_COM_RESSALVAS, NAO_ELEGIVEL, REJEITADO, REJEITADO_NA_ENTRADA,
    DUPLICADO, FALHOU_COMPENSADO, ERRO, CANCELADO,
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
APPROVAL_PLANO = "REVISAO_PLANO"
APPROVAL_AUDITORIA = "REVISAO_AUDITORIA"
APPROVAL_TYPE_LABELS = {
    APPROVAL_EXCECAO: "Exceção de elegibilidade",
    APPROVAL_PLANO: "Revisão humana do plano",
    APPROVAL_AUDITORIA: "Revisão humana da auditoria",
}

RULE_BLOQUEANTE = "BLOQUEANTE"
RULE_EXCECIONAVEL = "EXCECIONAVEL"
RULE_ALERTA = "ALERTA"
