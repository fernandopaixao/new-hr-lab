# Arquitetura

## Serviços

```
                         navegador
                             |
                     +---------------+
                     |   frontend    |  React + Vite, servido por nginx (porta 8580)
                     |  /api proxy   |  SSE sem buffer em /api/stream
                     +-------+-------+
                             |
                     +-------v-------+          +------------------+
                     |      api      |--------->|      Ollama      |  local, na rede ou container
                     |   FastAPI     |          |  qwen2.5:7b      |  (perguntas, embedding da busca)
                     +-------+-------+          |  nomic-embed-text|
                             |                  +--------^---------+
                             |                           |
+----------------------------v---------------------------+-----------------+
|                                Redis                                     |
|  streams por estágio, documentos JSON, log de decisões, pub/sub, índice |
+---------+-----------------------------------------------+----------------+
          |                                               |
+---------v---------+                           +---------v---------+
|   worker (N)      |-------------------------->|     indexer       |
| um loop por       |   agente de conferência   | embeddings de     |
| estágio da linha  |   (Ollama)                | todos os eventos  |
+-------------------+                           +-------------------+
```

| Serviço | Responsabilidade | Escala |
| --- | --- | --- |
| `frontend` | Interface. Recebe atualizações ao vivo por Server-Sent Events. | 1 |
| `api` | REST, SSE, geração de times e cenários, decisões de aprovação, painel, busca e perguntas. Não executa estágios. | 1 ou mais (sem estado) |
| `worker` | Consome as filas dos seis estágios e executa a lógica de cada um, inclusive chamadas ao agente de conferência. | `docker compose up --scale worker=N` |
| `indexer` | Lê o log de decisões e mantém os embeddings dos casos e das decisões. | 1 |
| `redis` | Filas, armazenamento, pub/sub e índice vetorial, com AOF ligado. | 1 |
| `ollama` | Opcional (perfil `ollama`). Em geral o Ollama roda na máquina do usuário ou num servidor da rede. | - |

## Módulos do backend

| Módulo | Papel | Depende de |
| --- | --- | --- |
| `domain.py` | Vocabulário: estágios, status, personas, tipos de aprovação e de regra. | - |
| `expr.py` | Avaliador seguro de expressões (whitelist de nós da AST do Python). | - |
| `context.py` | Monta as variáveis e funções disponíveis nas expressões (`colaborador`, `cargo_destino`, `meses_no_cargo`, `possui_beneficio(...)`...). | `expr` |
| `contracts.py` | Repositório de contratos: semente, versões, vigência, validação, YAML. | `store`, `expr` |
| `shelf.py` | Prateleira: operações, parâmetros, campos alterados, aplicação e compensação. | - |
| `engine.py` | Lógica pura da linha: regras, elegibilidade, estado alvo, plano, conferência, auditoria, conformidade. | `context`, `shelf`, `expr` |
| `agent.py` | Agente de conferência e chamadas estruturadas ao Ollama. | `store` |
| `pipeline.py` | Handlers dos estágios, aprovações, depuração, saga, concorrência e eventos coletivos. | todos acima |
| `worker.py` | Loops de consumo das filas e monitor de saúde do agente. | `pipeline` |
| `logbook.py` | Log append-only (stream, trilhas por caso e por colaborador, arquivo JSONL). | `store` |
| `facts.py` | Modelo de leitura: fatos por caso, documentos narrativos e painel de visibilidade. | `domain` |
| `embeddings.py` | Embeddings via Ollama, modo simulado, armazenamento e busca vetorial. | `store` |
| `indexer.py` | Serviço que mantém o índice em dia a partir do log. | `facts`, `embeddings` |
| `ask.py` | Agente de linguagem natural: interpretação, consulta, resposta com citações. | `facts`, `embeddings`, `agent` |
| `generators/` | Time artificial de banco e catálogo de cenários. | `contracts` (dados) |
| `api.py` | Rotas HTTP. | todos |

A regra de dependência é simples: `engine.py`, `facts.py`, `shelf.py` e `expr.py` não fazem I/O. Toda a lógica que decide algo pode ser testada sem Redis e sem rede (veja `backend/tests`).

## Fluxo de um evento

1. `POST /api/events` (ou o gerador) chama `Pipeline.submit_event`: cria o caso com status `NA_FILA`, escreve `EVENTO_RECEBIDO` no log e publica a mensagem no stream `hr:stream:intake`.
2. Um worker lê a mensagem pelo grupo de consumidores `hr-workers` (cada mensagem vai para um único worker), executa `run_stage` e confirma (`XACK`).
3. `run_stage` aplica as guardas (mensagem obsoleta, pausa, breakpoint, modo passo a passo), executa o handler do estágio e decide o próximo passo:
   - seguir: grava o caso e publica no stream do próximo estágio;
   - aguardar: `AGUARDANDO_APROVACAO`, `AGUARDANDO_AGENTE` ou `PARADO`;
   - finalizar: grava a decisão final com explicação.
4. Cada gravação de caso publica um resumo no canal `hr:updates`; a API repassa por SSE para a interface.
5. Cada decisão vai para o log (`hr:log`). O indexador lê esse stream com o próprio grupo (`hr-indexer`) e reindexa o caso.

## Armazenamento (Redis)

| Chave | Tipo | Conteúdo |
| --- | --- | --- |
| `hr:stream:{estagio}` | stream | Fila de cada estágio (grupo `hr-workers`). |
| `hr:case:{id}` | string JSON | Documento completo do caso. |
| `hr:cases` | sorted set | Índice de casos por data de criação. |
| `hr:case:{id}:log`, `hr:employee:{id}:log` | lista | Trilhas de decisão por caso e por colaborador. |
| `hr:log` | stream | Log global append-only (até 200 mil entradas; o arquivo JSONL guarda tudo). |
| `hr:event:{evento_id}` | string | Idempotência: caso já aberto para o evento. |
| `hr:employee:{id}`, `hr:employees`, `hr:seq:employee` | JSON, set, contador | Colaboradores e geração de matrícula. |
| `hr:lock:employee:{id}` | string com TTL | Trava por colaborador durante a execução. |
| `hr:contract:{codigo}`, `hr:contracts` | JSON (lista de versões), set | Contratos versionados. |
| `hr:approval:{id}`, `hr:approvals`, `hr:approvals:pending` | JSON, sorted set, set | Aprovações e pendências. |
| `hr:settings`, `hr:control` | JSON | Configurações e controle da linha (pausas, breakpoints). |
| `hr:agent:health`, `hr:agent:cache:*`, `hr:waiting_agent` | JSON, strings com TTL, hash | Saúde do Ollama, cache de respostas, casos aguardando o agente. |
| `hr:scenario_run:{id}`, `hr:scenario_runs` | JSON, lista | Execuções da suíte de cenários. |
| `hr:vec:doc:{id}`, `hr:vec:ids`, `hr:vec:version` | hash, set, contador | Índice vetorial: texto, metadados, vetor, modelo. |
| `hr:vec:dirty`, `hr:vec:simulated`, `hr:vec:status` | sorted set, set, JSON | Fila de reindexação, documentos com embedding simulado, estado do indexador. |
| `hr:ask:history` | lista | Últimas 50 perguntas e respostas. |
| `hr:updates` | pub/sub | Atualizações ao vivo para a interface. |

## Concorrência e consistência

- **Um worker por mensagem.** Grupos de consumidores dos Redis Streams garantem a entrega a um único worker. Mensagens pendentes de um worker que caiu são relidas quando ele volta com o mesmo nome de consumidor (no Docker o nome é estável: host do container e PID 1; fora dele, use `WORKER_NAME`). O estágio interrompido é retomado e o log registra a retomada. Não há redistribuição automática para outro worker (`XAUTOCLAIM`); é uma melhoria natural para produção.
- **Guarda de obsolescência.** O handler só roda se o caso estiver no estágio da mensagem e com status `NA_FILA`. Mensagens duplicadas ou atrasadas são descartadas sem efeito.
- **Idempotência de eventos.** `SET NX` em `hr:event:{id}`; um segundo envio vira um caso `DUPLICADO` apontando para o original.
- **Trava por colaborador.** A execução segura `hr:lock:employee:{id}`; dois casos do mesmo colaborador nunca escrevem ao mesmo tempo.
- **Versão do cadastro.** Cada gravação de colaborador incrementa `versao`. Se a versão mudou entre o plano e a execução, o caso volta para o planejamento (até 3 vezes) e registra `REPLANEJAMENTO`.
- **Snapshot para a auditoria.** A auditoria usa o estado final gravado pelo próprio caso; se outro caso alterou o colaborador depois, a auditoria emite o alerta `AUD-CONCORRENCIA` em vez de uma falsa divergência.

## Falhas

| Falha | Comportamento |
| --- | --- |
| Operação falha na execução | Saga compensa as operações aplicadas, na ordem inversa, restaurando os campos que cada uma declarou alterar. Operações sem compensação (como uma notificação já enviada) ficam registradas para tratamento manual. Status `FALHOU_COMPENSADO`. |
| Auditoria reprovada e confirmada por uma pessoa | A execução é revertida a partir dos snapshots. Status `REVERTIDO`. |
| Ollama fora do ar | O caso para em `AGUARDANDO_AGENTE`; o monitor verifica a saúde a cada 10 segundos e recoloca os casos na fila quando o Ollama volta. Com o modo simulado ligado, um agente heurístico responde e a decisão fica marcada. |
| Ollama responde fora do formato | Duas tentativas; depois o agente é tratado como REPROVADO e o caso vai para revisão humana. |
| Indexador sem Ollama | Os eventos continuam marcados em `hr:vec:dirty` e são indexados quando o Ollama volta; com o modo simulado, recebem embedding simulado e são refeitos depois. |
| Erro inesperado num estágio | Status `ERRO` com a mensagem; o caso pode ser reprocessado a partir de qualquer estágio, com o evento editado se necessário. |
| Worker cai no meio de um estágio | A mensagem fica pendente no grupo; quando o worker volta, ele retoma o estágio do caso que deixou em processamento. A guarda de obsolescência impede reprocessar estágios já concluídos. |

## Escala

O laboratório foi dimensionado para milhares de casos. Os pontos que mudariam em produção estão descritos nas decisões arquiteturais: armazenamento de documentos (ADR 0002), índice vetorial (ADR 0016), autenticação (ADR 0009) e observabilidade com OpenTelemetry (ADR 0015).
