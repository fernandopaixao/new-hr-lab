# 0006. Regras determinísticas decidem; o agente de IA audita e sempre recomenda

## Contexto

Os agentes devem poder conferir se o plano de execução e a execução estão aderentes ao compliance e às regras de negócio, e devem usar IA. Definido com o usuário: as regras determinísticas decidem e o agente audita; mesmo quando uma pessoa decide, o agente sempre dá uma recomendação clara de APROVADO ou REPROVADO.

## Decisão

- A elegibilidade é **só determinística**. Ela é reprodutível e explicável regra a regra, e é onde estão as exigências legais.
- Na **conferência do plano** e na **auditoria**, as regras avaliam o estado projetado ou final e o agente de IA recebe o caso (evento, colaborador antes e depois, plano, recibos, regras, contrato) e responde num formato JSON fixo: recomendação, confiança, resumo, achados com severidade e referência, e justificativa.
- O caso vai para revisão humana quando as regras reprovam ou exigem aprovação, ou quando o agente recomenda REPROVADO. Com o modo "sempre", tudo passa por uma pessoa. A recomendação do agente aparece na tela de aprovação.
- O agente nunca aprova sozinho o que as regras reprovaram.

## Alternativas consideradas

- **O agente decide.** Isso não é aceitável para decisões trabalhistas: não é reprodutível, é difícil de explicar a um auditor e é sensível ao modelo.
- **Sem IA.** Perderia a segunda linha de defesa para o que as regras não cobrem, como um plano incoerente com o evento ou uma justificativa fraca.

## Consequências

- O painel mede a concordância entre agente e regras. "Agente mais rigoroso" é um sinal para revisar contratos ou o prompt.
- A suíte de cenários classifica como `DIVERGENCIA_AGENTE` os casos em que o agente reprovou o que as regras aprovaram; isso não é um erro da linha.
- O prompt e a resposta bruta de cada chamada ficam no caso, para depuração.
