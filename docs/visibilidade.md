# Visibilidade

A estratégia está registrada na [ADR 0015](adr/0015-estrategia-de-visibilidade.md). Este documento mostra como usá-la no dia a dia: que pergunta cada camada responde e onde olhar.

## Camadas

| Camada | Pergunta que responde | Onde |
| --- | --- | --- |
| Linha ao vivo | O que está acontecendo agora? Onde está cada caso? | Tela Linha |
| Rastro do caso | Por que este caso terminou assim? | Detalhe do caso |
| Log de decisões | Quem decidiu o quê, quando e com qual explicação? | Tela Log, `GET /api/logs`, `audit-log.jsonl` |
| Painel | Como a operação está indo? Onde está o gargalo? | Tela Visão, `GET /api/insights` |
| Métricas | Como acompanhar fora do laboratório? | `GET /api/metrics` (Prometheus) |
| Perguntas | Qualquer pergunta que as telas não respondem diretamente | Tela Perguntar, `POST /api/ask` |

Todas as camadas são alimentadas pelos mesmos dados: o documento do caso e o log append-only. Não há contadores mantidos à parte que possam divergir.

## Correlação

- `case_id` identifica o caso em todas as telas, no log, no índice vetorial e nas citações do agente de perguntas.
- `evento_id` liga o caso ao evento de origem e garante a idempotência.
- `colaborador_id` liga todos os casos e alterações de uma pessoa (trilha em `hr:employee:{id}:log`).
- `pai_id` e `filhos` ligam os casos individuais ao caso do evento coletivo que os gerou (por exemplo, o reajuste da CCT).
- Cada aprovação (`apr-...`) guarda o `case_id`, o estágio e a regra que a originou.
- Cada estágio registra o `worker` que o executou, o início e a duração.

## Painel Visão

| Bloco | Como ler |
| --- | --- |
| KPIs | Casos, em andamento, taxa de conclusão, tempo total p50 e p95, pendências de aprovação, compensações, replanejamentos e latência do agente. |
| Alertas | Aparecem só quando há algo a fazer (lista abaixo). |
| Linha do tempo | Entradas, finalizações e problemas por intervalo. Entradas acima das finalizações por vários intervalos indicam fila crescendo. |
| Funil | Quantos casos alcançaram e concluíram cada estágio. A maior queda mostra onde os casos são barrados. |
| Tempo por estágio | p50, p95 e máximo. O gargalo fica destacado; em geral é a conferência ou a auditoria, por causa do modelo. |
| Evento por situação | Matriz com tipo de evento nas linhas e status nas colunas. Mostra, por exemplo, se desligamentos estão sendo revertidos mais que outros eventos. |
| Regras que mais barram | Candidatas a revisão de política ou a ajuste de dados. |
| Operações | Executadas, com falha e descartadas. Falhas concentradas numa operação apontam para a integração. |
| Aprovações por persona | Volume e decisões de cada persona. |
| Agente e regras | Quantas vezes concordaram e discordaram. Discordância alta pede revisão do prompt, do modelo ou das regras. |
| Índice | Documentos, pendentes, simulados e modelo de embedding. |

### Alertas

| Alerta | Condição | O que fazer |
| --- | --- | --- |
| Fila acumulada | Mensagens pendentes num estágio | Verifique pausas; escale workers. |
| Esperando o Ollama | Casos em "Aguardando agente de IA" | Verifique `OLLAMA_BASE_URL` e o modelo em Configurações. |
| Aprovação parada | Pendente há mais de 30 minutos | Troque para a persona indicada e decida. |
| Taxa de falhas | Mais de 20% de falhas na última hora | Veja a injeção de falhas em Configurações e o bloco Operações. |
| Divergência do agente | Agente reprova o que as regras aprovam | Abra os casos e compare o parecer com as regras. |
| Fora do estado alvo | Colaboradores com desvio de conformidade | Tela Colaboradores, filtro de conformidade. |

## Métricas Prometheus

`GET /api/metrics` expõe:

| Métrica | Rótulos |
| --- | --- |
| `hrlab_cases` | `status` |
| `hrlab_cases_by_event` | `evento` |
| `hrlab_queue_messages` | `estagio`, `tipo` (pendentes, atraso) |
| `hrlab_queue_consumers` | `estagio` |
| `hrlab_stage_duration_ms` | `estagio`, `quantile` (0.5, 0.95), com `_count` |
| `hrlab_approvals_pending` | - |
| `hrlab_agent_up` | - |
| `hrlab_index_documents`, `hrlab_index_dirty`, `hrlab_index_simulated` | - |

Para coletar, aponte um Prometheus para `http://localhost:8080/api/metrics`.

## Log de decisões

Cada entrada tem `tipo`, `ts`, `case_id`, `colaborador_id`, `estagio`, `ator` (sistema, worker, persona ou agente), `mensagem` e `dados`. Os tipos são:

| Grupo | Tipos |
| --- | --- |
| Entrada | `EVENTO_RECEBIDO`, `EVENTO_REJEITADO`, `EVENTO_DUPLICADO` |
| Linha | `ESTAGIO`, `DECISAO_FINAL`, `REPLANEJAMENTO`, `DEPURACAO`, `CONTROLE` |
| Regras | `REGRA_AVALIADA`, `DECISAO_ELEGIBILIDADE`, `AUDITORIA` |
| Plano e execução | `PLANO_GERADO`, `OPERACAO_ESCOLHIDA`, `OPERACAO_DESCARTADA`, `OPERACAO_EXECUTADA`, `OPERACAO_FALHOU`, `COMPENSACAO` |
| Agente | `AGENTE_RECOMENDACAO`, `AGENTE_INDISPONIVEL` |
| Pessoas | `APROVACAO_SOLICITADA`, `APROVACAO_DECIDIDA` |
| Cadastros | `COLABORADOR_ALTERADO`, `CONTRATO_ALTERADO`, `CONFIG_ALTERADA` |

O stream `hr:log` guarda até 200 mil entradas; o arquivo `audit-log.jsonl`, no volume de dados, guarda tudo. A exportação na tela Log gera JSONL com os filtros aplicados.

## Caminho para produção

- Traces OpenTelemetry por estágio, com o `case_id` como trace id, e spans para cada operação e chamada ao modelo.
- Fatos materializados num banco analítico, alimentados pelo stream de log, em vez de calculados a cada requisição.
- SLO por tipo de evento a partir de `auditoria.sla_horas` do contrato de processo.
- Alertas no Alertmanager com as mesmas condições do painel.
