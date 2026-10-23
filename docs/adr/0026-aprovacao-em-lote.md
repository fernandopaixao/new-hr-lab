# 0026. Aprovação em lote, decidida e registrada uma a uma

## Contexto

Fernando pediu para aprovar em lote na tela Aprovações. Com a suíte de cenários, a injeção de desvios ou um reajuste coletivo, uma persona como o Comitê de remuneração ou o HRBP acumula dezenas de exceções parecidas, e decidir uma por uma, com a mesma justificativa digitada várias vezes, é lento e não acrescenta controle.

O lote não pode enfraquecer o que a ADR 0009 garante: cada decisão tem persona autorizada, justificativa e registro próprio no caso, na aprovação e no log.

## Decisão

- **O lote é um laço sobre a decisão unitária.** `Pipeline.decide_batch` recebe os ids, a decisão (`APROVAR` ou `REJEITAR`), a justificativa e a persona, e chama `decide` para cada aprovação, em ordem. Não há caminho paralelo: a mesma validação de persona e status, o mesmo `APROVACAO_DECIDIDA` no log, a mesma exceção aprovada no caso e o mesmo efeito na linha (seguir, rejeitar, compensar na conferência final).
- **Cada aprovação guarda o número do lote.** O lote recebe um id `lote-...`. A aprovação ganha o campo `lote` e a mensagem do log diz "no lote ...". O histórico mostra o lote abaixo de quem decidiu.
- **Um resumo a mais no log.** Ao final, um `APROVACAO_LOTE` registra quem decidiu, a decisão, a justificativa e o resultado de cada item. Ele não substitui as entradas individuais; serve para achar o lote inteiro de uma vez.
- **Uma falha não para o lote.** Cada item termina como `DECIDIDA`, `IGNORADA` (já não estava pendente, por exemplo cancelada porque outra aprovação do mesmo caso foi rejeitada no próprio lote) ou `FALHOU` (persona sem alçada, aprovação inexistente). A resposta e a tela mostram os itens que não foram decididos e o motivo.
- **Validação antes de começar.** Lista vazia, decisão inválida, justificativa curta ou mais de 200 itens recusam o lote inteiro, sem decidir nada.
- **Aprovar e rejeitar.** Os dois entram no lote, porque o efeito de cada um já está definido por estágio (`resultado_aprovacao`).
- **Na tela.** Filtros por tipo de aprovação, tipo de evento e recomendação do agente; caixa de seleção em cada aprovação que a persona pode decidir; botão para selecionar todas as filtradas; justificativa única. Antes de confirmar, um diálogo mostra quantas selecionadas o agente recomenda reprovar, o que aprovar ou rejeitar provoca em cada estágio envolvido e, na rejeição, se há mais de uma aprovação do mesmo caso.

## Alternativas consideradas

- **Endpoint em lote com transação única (tudo ou nada).** O Redis não dá transação entre casos com os efeitos de linha (filas, compensação), e desfazer uma aprovação já aplicada exigiria uma compensação nova só para isso. Decidir item a item, com o resultado de cada um, é mais simples e honesto.
- **Laço no navegador chamando a decisão unitária.** Funciona, mas não deixa um registro do lote no servidor nem o número do lote nas aprovações, e uma aba fechada no meio deixa o lote pela metade sem rastro.
- **Justificativa por item.** Contradiz o objetivo do lote. Quem precisa justificar um caso de forma diferente continua tendo a decisão unitária no mesmo cartão.

## Consequências

- Uma decisão em lote é auditável do mesmo jeito que uma unitária, e o lote inteiro é encontrado pelo seu id no log.
- O lote é sequencial: 200 itens fazem 200 decisões em sequência, o que é rápido no laboratório. A rejeição na conferência final compensa operações e é a parte mais lenta.
- A recomendação do agente fica visível no filtro e no diálogo, mas não impede aprovar em lote o que ele recomenda reprovar; a decisão continua sendo humana.
- **Em produção:** limitar o lote por alçada e valor, exigir uma segunda pessoa acima de certo tamanho e processar lotes grandes em fila, com progresso.
