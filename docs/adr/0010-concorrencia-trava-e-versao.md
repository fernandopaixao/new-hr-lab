# 0010. Trava por colaborador, versão do cadastro e replanejamento

## Contexto

Com vários workers e rajadas de eventos, dois casos podem tratar o mesmo colaborador ao mesmo tempo. Um exemplo é uma transferência e um reajuste coletivo. Sem cuidado, um sobrescreve o outro ou executa um plano calculado sobre dados velhos.

## Decisão

- **Trava por colaborador** (`SET NX` com TTL) durante a execução.
- **Versão do cadastro:** cada gravação incrementa `versao`. O plano registra a versão em que foi calculado; se ela mudou até a execução, o caso volta ao planejamento (até 3 vezes) e registra `REPLANEJAMENTO`.
- **Guarda de obsolescência:** um estágio só roda se o caso estiver naquele estágio e na fila. Mensagens repetidas ou atrasadas não têm efeito.
- **Idempotência de eventos** pelo id do evento.
- **Retomada após queda:** um worker que volta com o mesmo nome relê suas mensagens pendentes e retoma o estágio que deixou em processamento.
- A conferência final compara o estado final gravado pelo próprio caso; se outro caso alterou o colaborador depois, emite o alerta `FIN-CONCORRENCIA` em vez de acusar uma divergência falsa.

## Alternativas consideradas

- **Uma fila por colaborador** (ordenação por chave, como partições do Kafka). Garante a ordem, mas complica o modelo de filas por estágio.
- **Bloquear o colaborador desde o gatilho.** É mais simples, mas trava casos longos (aguardando aprovação) e cria filas de espera invisíveis.

## Consequências

- O cenário de estresse "eventos concorrentes" exercita esse caminho, e o painel conta os replanejamentos.
