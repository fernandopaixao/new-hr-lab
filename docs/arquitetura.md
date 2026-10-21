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
                     |      api      |--------->|  IA: Ollama ou   |  Ollama local, na rede ou container;
                     |   FastAPI     |          |  Claude, OpenAI, |  ou um provedor na nuvem
                     +-------+-------+          |  Gemini          |  (perguntas, embedding da busca)
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
| estágio da linha  |   (provedor de IA)        | todos os eventos  |
+-------------------+                           +-------------------+
```

| Serviço | Responsabilidade | Escala |
| --- | --- | --- |
| `frontend` | Interface. Recebe atualizações ao vivo por Server-Sent Events. | 1 |
| `api` | REST, SSE, geração de times e cenários, decisões de aprovação, painel, busca e perguntas. Não executa estágios. | 1 ou mais (sem estado) |
| `worker` | Consome as filas dos seis estágios e executa a lógica de cada um, inclusive chamadas ao agente de conferência. | `docker compose up --scale worker=N` |
| `indexer` | Lê o log de decisões e mantém os embeddings dos casos e das decisões. | 1 |
| `redis` | Filas, armazenamento, pub/sub e índice vetorial, com AOF ligado. | 1 |
| `ollama` | Opcional (perfil `ollama`). Em geral o Ollama roda na máquina do usuário ou num servidor da rede; com um provedor na nuvem, não é necessário. | - |

## Módulos do backend

| Módulo | Papel | Depende de |
| --- | --- | --- |
| `domain.py` | Vocabulário: estágios e suas saídas, status, personas, tipos de aprovação e de regra, cálculo do próximo passo. | - |
| `expr.py` | Avaliador seguro de expressões (whitelist de nós da AST do Python). | - |
| `context.py` | Monta as variáveis e funções disponíveis nas expressões (`colaborador`, `cargo_destino`, `gestor`, `meses_no_cargo`, `possui_beneficio(...)`...) e navega a hierarquia. | `expr` |
| `migrations.py` | Migrações únicas de dados gravados, rodadas na partida da API (por exemplo, a troca de ordem da ADR 0018). | `store`, `domain` |
| `contracts.py` | Repositório de contratos: semente, versões, vigência, validação, YAML. | `store`, `expr` |
| `shelf.py` | Prateleira: operações, parâmetros, campos alterados, aplicação e compensação. | - |
| `engine.py` | Lógica pura da linha: regras, elegibilidade, estado alvo, plano, auditoria antes da execução, conferência final, conformidade. | `context`, `shelf`, `expr` |
| `llm.py` | Provedores de IA (Ollama, Claude, OpenAI e compatíveis, Gemini): chamada estruturada, lista de modelos, embeddings, saúde e teste de conexão. | `apikeys` |
| `apikeys.py` | Chaves de API: ambiente primeiro, depois `secrets.json` no volume de dados. Nunca no Redis. | `config` |
| `agent.py` | Agente de conferência sobre `llm.py`. | `store`, `llm` |
| `clock.py` | Relógio simulado: data de negócio compartilhada pela API e pelos workers. | `store` |
| `vigencia.py` | Agenda de vigências derivada dos programas ativos; emite aviso e vencimento pela linha, uma vez cada. | `clock`, `store` |
| `pipeline.py` | Handlers dos estágios, aprovações, depuração, saga, concorrência e eventos coletivos. | todos acima |
| `worker.py` | Loops de consumo das filas, monitor de saúde do agente e conferência periódica da agenda de vigências. | `pipeline`, `vigencia` |
| `logbook.py` | Log append-only (stream, trilhas por caso e por colaborador, arquivo JSONL). | `store` |
| `facts.py` | Modelo de leitura: fatos por caso, documentos narrativos e painel de visibilidade. | `domain` |
| `embeddings.py` | Embeddings pelo provedor escolhido, modo simulado, armazenamento e busca vetorial. | `store`, `llm` |
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
| `hr:settings`, `hr:control`, `hr:setup` | JSON | Configurações, controle da linha (pausas, breakpoints) e estado do assistente de configuração. As chaves de API não ficam no Redis. |
| `hr:agent:health`, `hr:agent:cache:*`, `hr:waiting_agent` | JSON, strings com TTL, hash | Saúde do provedor de IA, cache de respostas, casos aguardando o agente. |
| `hr:clock` | JSON | Data do relógio simulado; vazio, vale o calendário real. |
| `hr:vigencia:emitidos` | hash | Itens da agenda já emitidos (id fixo do evento para o caso que o recebeu). Garante uma emissão por item. |
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
- **Snapshot para a conferência final.** A conferência final usa o estado final gravado pelo próprio caso; se outro caso alterou o colaborador depois, emite o alerta `FIN-CONCORRENCIA` em vez de uma falsa divergência.

## Falhas

| Falha | Comportamento |
| --- | --- |
| Operação falha na execução | Saga compensa as operações aplicadas, na ordem inversa, restaurando os campos que cada uma declarou alterar. Operações sem compensação (como uma notificação já enviada) ficam registradas para tratamento manual. Status `FALHOU_COMPENSADO`. |
| Auditoria reprovada antes da execução | Nada foi alterado. Status `REJEITADO`. |
| Conferência final reprovada e confirmada pela auditoria interna | A execução é revertida a partir dos snapshots. Status `REVERTIDO`. |
| IA fora do ar (Ollama parado, ou na nuvem: sem rede, chave recusada, modelo inexistente, cota estourada) | O caso para em `AGUARDANDO_AGENTE`; o monitor verifica a saúde a cada 10 segundos e recoloca os casos na fila quando a IA volta. Com o modo simulado ligado, um agente heurístico responde e a decisão fica marcada. |
| IA responde fora do formato ou recusa | Duas tentativas; depois o agente é tratado como REPROVADO e o caso vai para revisão humana. |
| Indexador sem IA | Os eventos continuam marcados em `hr:vec:dirty` e são indexados quando o gerador de embeddings volta; com o modo simulado, recebem embedding simulado e são refeitos depois. |
| Erro inesperado num estágio | Status `ERRO` com a mensagem; o caso pode ser reprocessado a partir de qualquer estágio, com o evento editado se necessário. |
| Worker cai no meio de um estágio | A mensagem fica pendente no grupo; quando o worker volta, ele retoma o estágio do caso que deixou em processamento. A guarda de obsolescência impede reprocessar estágios já concluídos. |

## Escala

O laboratório foi dimensionado para milhares de casos. Os pontos que mudariam em produção estão descritos nas decisões arquiteturais: armazenamento de documentos (ADR 0002), índice vetorial (ADR 0016), autenticação (ADR 0009) e observabilidade com OpenTelemetry (ADR 0015).

## Princípios de arquitetura

| Princípio | Como aparece no código | Decisão |
| --- | --- | --- |
| Uma linha, muitos processos | Os seis estágios são os mesmos para qualquer evento; o que muda é o contrato de processo | [ADR 0001](adr/0001-linha-de-producao-por-estagios.md) |
| Comportamento em dados, não em código | Normas, políticas, cargos e processos são contratos YAML versionados com vigência | [ADR 0003](adr/0003-contratos-versionados.md) |
| Plano derivado do estado alvo | O planejamento compara o estado atual com o que o cargo e a norma exigem e acrescenta o que falta | [ADR 0005](adr/0005-prateleira-e-plano-derivado.md) |
| Operações desacopladas | A prateleira declara parâmetros, campos alterados e compensação; qualquer processo reutiliza | ADR 0005 |
| Decisão determinística, IA auditora | Regras decidem; o agente recomenda e a divergência vai para pessoas | [ADR 0006](adr/0006-regras-decidem-ia-audita.md) |
| Auditar antes de alterar | O plano é aplicado em simulação e auditado antes da execução | [ADR 0018](adr/0018-auditoria-antes-da-execucao.md) |
| Falhar de forma reversível | Saga com compensação por snapshot; reversão completa após conferência reprovada | [ADR 0008](adr/0008-saga-com-compensacao.md) |
| Tudo explicado | Cada decisão vai para o log com a explicação; o mesmo log alimenta painel, índice e perguntas | [ADR 0011](adr/0011-log-de-decisoes-explicado.md), [ADR 0015](adr/0015-estrategia-de-visibilidade.md) |
| Lote sem atalho (PR #9, pendente) | `decide_batch` chama a decisão unitária para cada item, então alçada, validação e log são os mesmos de uma decisão avulsa; um resumo `APROVACAO_LOTE` liga os itens | ADR 0026 (PR #9) |
| Lógica pura testável | `engine.py`, `facts.py`, `shelf.py` e `expr.py` sem I/O | seção [Módulos do backend](#módulos-do-backend) |
| Provedor de IA trocável | Toda chamada passa por `llm.py`; motores Qwen e JEV por `engines.py`. Pendente de merge (PR #8): `budget.py` confere o teto de gastos opcional antes de cada chamada externa, e o bloqueio é tratado como IA indisponível | [ADR 0021](adr/0021-provedores-de-llm-na-nuvem.md), [ADR 0024](adr/0024-motor-jev-e-painel-de-desempenho.md), ADR 0025 (PR #8) |

## Visão de contexto

```
   Operador, HRBP, Jurídico,           +-----------------------------+          Provedores de IA
   Compliance, Auditoria, Comitê ----->|                             |-------> Ollama (padrão, local ou rede)
   (personas na interface)             |     Laboratório Novo RH     |-------> Claude, OpenAI, Gemini (opcional)
                                       |                             |
   Prometheus (opcional) <-------------|  linha de produção de RH    |
                                       |  contratos, prateleira,     |  Sistemas de destino (simulados pela prateleira):
   Gerador de cenários e de time ----->|  agentes, log, painel       |-------> cadastro, folha, ponto, benefícios, IAM,
                                       +-----------------------------+          patrimônio, jurídico, SST, treinamento,
                                                                                eSocial, comunicação
```

Em produção, cada grupo da prateleira (`CADASTRO`, `FOLHA`, `PONTO`, `BENEFICIOS`, `IAM`, `PATRIMONIO`, `JURIDICO`, `SST`, `TREINAMENTO`, `ESOCIAL`, `COMUNICACAO`) vira um adaptador para o sistema real, mantendo o contrato da operação (parâmetros, campos alterados, compensação, recibo).

## Atributos de qualidade

| Atributo | Como é atendido | Como medir no laboratório |
| --- | --- | --- |
| Correção | Regras determinísticas, estado projetado auditado, conferência final, 54 cenários com resultado esperado, 61 testes unitários | Suíte completa na tela Cenários; `pytest` |
| Explicabilidade | Explicação por regra, por operação escolhida ou descartada, por aprovação e por parecer; próximo passo em cada fase | Detalhe do caso, tela Log |
| Auditabilidade | Log append-only, prompt e resposta da IA gravados, recibos com protocolo | Exportação JSONL |
| Resiliência | Filas por estágio, retomada após queda de worker, espera pela IA, saga, idempotência | Injeção de falhas, `docker compose restart worker` |
| Consistência | Trava por colaborador, versão do cadastro, replanejamento, snapshot na conferência | Cenário `eventos_concorrentes` |
| Escalabilidade | Workers horizontais por grupo de consumidores; API sem estado | `--scale worker=N` e rajada de eventos |
| Modificabilidade | Contrato novo ou operação nova sem mudar a linha; provedor de IA trocável | Editor de contratos; [prateleira](prateleira.md) |
| Observabilidade | Painel, métricas Prometheus, desempenho por motor de IA, rastro por caso | Telas Visão e Desempenho, `GET /api/metrics` |
| Portabilidade | Docker Compose; instaladores para Linux, macOS e Windows | `scripts/install.*` |
| Custo e privacidade da IA | Ollama local por padrão, cache de 24 horas, semáforo de concorrência | Tela Desempenho |

## Trade-offs aceitos

| Escolha | Ganho | Custo | Quando rever |
| --- | --- | --- | --- |
| Redis para tudo | Um único componente de infraestrutura, simples de subir | Sem consultas relacionais; memória limita o volume; índice vetorial em memória na API | Acima de dezenas de milhares de casos ou com requisitos de retenção longa |
| Uma fila por estágio | Pausa, breakpoint e escala por estação | Mais mensagens por caso | Se a latência por caso for crítica |
| Contratos em YAML com expressões | O negócio lê e altera as regras | Expressões ainda pedem cuidado; não há editor visual de regra | Ao abrir a edição para áreas de negócio em produção |
| IA síncrona no estágio | Parecer disponível antes da decisão | Estágio de auditoria é o gargalo | Com volume alto: modelo menor, GPU, JEV ou cache |
| Personas sem login | Demonstração da governança sem infraestrutura de identidade | Sem segurança de acesso | Antes de qualquer uso real ([seguranca.md](seguranca.md)) |
| Fatos calculados por requisição | Painel sempre igual ao log | Custo cresce com o volume | Com milhares de casos por dia: banco analítico alimentado pelo log |

## Caminho para produção

| Tema | Laboratório | Produção sugerida |
| --- | --- | --- |
| Identidade | Persona escolhida na interface | SSO (OIDC), papéis no provedor de identidade, autorização por rota |
| Armazenamento | Redis com AOF | Banco transacional para casos, cadastro e contratos; Redis ou Kafka para filas; armazenamento imutável para o log |
| Mensageria | Redis Streams, sem `XAUTOCLAIM` | Streams com reivindicação de pendentes, ou Kafka com partição por colaborador |
| Integrações | Prateleira simulada | Adaptadores por sistema com idempotência, timeout, retentativa e compensação real |
| Índice vetorial | Matriz numpy em memória | Banco vetorial (pgvector, Redis Stack, OpenSearch) |
| Observabilidade | Painel próprio e Prometheus | OpenTelemetry com `case_id` como trace id; Alertmanager com as condições do painel |
| IA | Ollama local, nuvem opcional | Modelo local em GPU dedicada ou provedor com contrato de não retenção; teto de gasto; avaliação contínua de concordância |
| Governança de contratos | Qualquer persona salva nova versão | Aprovação de duas pessoas, ambiente de homologação, suíte de cenários como portão de publicação |
| Implantação | Docker Compose | Kubernetes ou serviço gerenciado; CI com testes, análise estática e varredura de imagens |
