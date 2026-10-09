# 0008. Execução em saga com compensação por snapshot

## Contexto

A execução altera vários "sistemas" (folha, benefícios, IAM, patrimônio, eSocial). Definido com o usuário: falhas são tratadas como saga com compensação.

## Decisão

- As operações do plano são executadas em ordem. Antes de cada uma, o executor guarda um **snapshot dos campos que ela declara alterar** (ADR 0005). Cada operação gera um recibo com protocolo.
- Se uma operação falha, as já aplicadas são compensadas na ordem inversa, restaurando os snapshots. Operações não compensáveis (por exemplo, uma notificação enviada) ficam marcadas para tratamento manual.
- Se a auditoria reprova e a revisão humana confirma, a mesma compensação reverte a execução (status `REVERTIDO`).
- Falhas podem ser injetadas por evento (`simular_falha_em`) ou por percentual global nas configurações.

## Alternativas consideradas

- **Transação única.** Não existe entre sistemas diferentes no mundo real.
- **Compensação escrita por operação** (uma função inversa para cada uma). Seria mais fiel a integrações reais, mas dobraria o código da prateleira. O snapshot por campos declarados cobre o laboratório e deixa explícito o que cada operação toca.

## Consequências

- O cadastro é gravado após cada operação, para que uma queda no meio deixe um estado coerente com os recibos.
- Em integrações reais, cada operação precisaria de idempotência no sistema de destino e de uma ação de compensação própria; o contrato da prateleira já tem o lugar para isso (`compensavel`).
