# 0011. Log append-only com explicação de cada decisão

## Contexto

As alterações precisam ser escritas em log, e as decisões do algoritmo explicadas: por que tais operações foram escolhidas, por que alguém não é elegível. As aprovações de exceção precisam ficar registradas.

## Decisão

- Cada passo relevante escreve uma entrada com tipo, ator, caso, colaborador, estágio, mensagem em português e dados estruturados. Os tipos incluem evento recebido ou rejeitado, regra avaliada, decisão de elegibilidade, operação escolhida ou descartada, operação executada ou falha, compensação, recomendação do agente, aprovação solicitada ou decidida, auditoria, decisão final e alterações de colaborador, contrato e configuração.
- As mensagens são escritas para pessoas, por exemplo: "3. ALTERAR_BENEFICIO escolhida (derivada do contrato): Benefício SAUDE deve ser plano OURO pelo contrato CARGO_COORDENADOR v1; atual PRATA."
- O log é append-only, gravado em três lugares: o stream global, as trilhas por caso e por colaborador, e um arquivo JSONL no volume de dados, que pode ser exportado pela interface.

## Consequências

- O mesmo log alimenta a interface, o indexador de embeddings (ADR 0016) e a auditoria externa.
- O volume cresce com a quantidade de regras; o stream é limitado a cerca de 200 mil entradas, e o arquivo guarda tudo.
