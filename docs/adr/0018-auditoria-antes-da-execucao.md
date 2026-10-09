# 0018. Auditoria antes da execução e conferência final depois

## Contexto

Até aqui a linha era gatilho, elegibilidade, planejamento, conferência do plano, execução e auditoria. As verificações do contrato de serviço (por exemplo, "o desligamento calculou a rescisão" ou "a admissão agendou o exame") só rodavam depois da execução. Quando falhavam, os sistemas já tinham sido alterados e a saída era reverter, com operações que nem sempre podem ser desfeitas (uma comunicação enviada, um evento do eSocial). Fernando pediu para mover a auditoria para antes da execução.

## Decisão

A linha passa a ser **gatilho, elegibilidade, planejamento, auditoria, execução e conferência final**.

**Auditoria (antes da execução)** é a porta obrigatória: nada é executado sem passar por ela. Junta o que antes estava dividido entre a conferência do plano e a auditoria, sempre sobre o **estado projetado** pelo plano:

- regras de `conferencia_plano` do processo;
- verificações de `auditoria.verificacoes` do contrato de serviço (`operacao_executada(X)` lê "X está no plano");
- compliance da norma e do cargo;
- problemas da simulação do plano (`PLANO-SIMULACAO`);
- aderência ao estado alvo (`AUD-ESTADO-ALVO`);
- parecer do agente de IA sobre o plano.

| Resultado | O que acontece |
| --- | --- |
| Tudo atendido e agente APROVADO | Segue para a execução |
| Alerta | Segue; o alerta vira ressalva na decisão final |
| Regra excecionável falhou | Aprovação de exceção pelas personas da regra |
| Agente REPROVADO, ou modo `SEMPRE` | Revisão humana da auditoria (Auditoria interna ou Compliance) |
| Regra bloqueante falhou | Rejeitado, sem nenhum sistema alterado |

**Conferência final (depois da execução)** fica, mas com papel menor e preciso: provar que o executado é igual ao auditado.

- `FIN-RECIBOS`: toda operação planejada tem recibo de execução.
- `FIN-PROJECAO`: o estado final é igual ao estado projetado que a auditoria aprovou.
- `FIN-CONCORRENCIA` (alerta): outro caso alterou o colaborador depois desta execução.
- Parecer do agente de IA sobre a execução.

Se a conferência ou o agente reprovar, a auditoria interna decide; rejeitar compensa todas as operações (ADR 0008).

## Por que manter a conferência final

A pergunta de Fernando permitia eliminar a etapa depois da execução. Ela foi mantida porque a auditoria antes da execução só enxerga a simulação. Falhas de integração, uma operação que aplicou algo diferente do simulado ou uma alteração concorrente só aparecem depois. A conferência final custa pouco (não reavalia as regras de negócio, só compara com o que foi auditado) e é o único ponto que garante que o colaborador está, de fato, no estado aprovado.

## Alternativas consideradas

- **Manter as duas etapas como estavam.** Continuaria descobrindo falhas de contrato só depois de alterar os sistemas.
- **Auditar só antes e confiar na saga.** A saga cobre falhas que lançam erro; não cobre uma operação que "deu certo" com o resultado errado.
- **Repetir todas as verificações depois da execução.** Duplica regras e explicações sem acrescentar garantia: se o final é igual ao projetado e o projetado foi auditado, o final está auditado.

## Consequências

- Campos do caso: `auditoria`, `agente_auditoria` e `recomendacao_auditoria` agora são da auditoria antes da execução; `conferencia_final`, `agente_conferencia` e `recomendacao_conferencia` são da etapa final. `conferencia_plano`, `agente_plano` e `recomendacao_plano` deixam de existir no caso.
- Aprovações: `REVISAO_AUDITORIA` (antes da execução, rejeição sem efeito nos sistemas) e `REVISAO_CONFERENCIA_FINAL` (depois, rejeição reverte). `REVISAO_PLANO` deixa de existir.
- Os nomes das seções no YAML dos contratos (`conferencia_plano`, `auditoria`) não mudam; só muda o momento em que são avaliadas.
- Na partida da API, uma migração única (`migrations.py`) renomeia estágios, campos e aprovações dos casos gravados antes da mudança e recoloca na fila os casos que estavam a caminho dessas etapas.
- O replanejamento por concorrência (ADR 0010) volta para o planejamento e passa de novo pela auditoria.
