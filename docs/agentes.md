# Agentes de IA

O laboratório usa modelos de linguagem em três papéis. O padrão é um modelo local no Ollama; Anthropic Claude, OpenAI (ou um serviço compatível) e Google Gemini também podem ser usados (veja [Provedores](#provedores)). Nenhum deles decide sozinho o destino de um caso nem calcula números: regras determinísticas decidem, e os números vêm dos fatos (veja as ADRs [0006](adr/0006-regras-decidem-ia-audita.md), [0007](adr/0007-ollama-local-e-espera.md), [0016](adr/0016-embeddings-de-todos-os-eventos.md), [0017](adr/0017-agente-de-linguagem-natural.md) e [0021](adr/0021-provedores-de-llm-na-nuvem.md)).

| Papel | Modelo padrão | Código | Onde aparece |
| --- | --- | --- | --- |
| Agente de conferência | motor Qwen: `qwen2.5:7b` (`OLLAMA_MODEL`) ou o modelo do provedor escolhido; motor JEV: `tev1:0.8b` (`JEV_MODEL`) | `agent.py`, `engines.py`, `llm.py` | Classificação de elegibilidade, auditoria (antes da execução) e conferência final |
| Embeddings | `nomic-embed-text` (`EMBEDDING_MODEL`), ou OpenAI, Gemini ou simulado | `embeddings.py`, `indexer.py`, `llm.py` | Índice de todos os eventos, busca semântica |
| Agente de perguntas | o mesmo do conferente, ou `ask_model` | `ask.py` | Tela Perguntar |

## Provedores

O provedor dos agentes (`llm_provider`) e o gerador de embeddings (`embedding_provider`) são escolhidos no assistente de configuração inicial, que abre na primeira visita, ou em Configurações. Toda chamada passa por `llm.py`.

| Provedor | Saída estruturada | Modelos sugeridos | Embeddings |
| --- | --- | --- | --- |
| Ollama (padrão) | `format` com o JSON Schema | `qwen2.5:7b`, `qwen2.5:3b`, `qwen2.5:14b` | `nomic-embed-text` |
| Anthropic Claude | `output_config.format` com esquema fechado | `claude-opus-5-5` (padrão), `claude-sonnet-5-5`, `claude-haiku-5-5` | não oferece |
| OpenAI ou compatível | `response_format` `json_schema` estrito | `gpt-5-mini`, `gpt-5`, `gpt-4.1-mini` | `text-embedding-3-small` |
| Google Gemini | `responseSchema` | `gemini-2.5-flash`, `gemini-2.5-pro` | `gemini-embedding-001` |

- **Claude.** O esforço de raciocínio (`anthropic_effort`, padrão `medium`) troca cuidado por tempo e custo. Nos modelos que aceitam, uma recusa de segurança é refeita no servidor por um modelo alternativo.
- **OpenAI ou compatível.** Troque a URL base (`openai_base_url`) para usar Azure OpenAI, OpenRouter, Groq, vLLM ou LM Studio. Se o modelo só aceita a temperatura padrão, ou o servidor não aceita `json_schema`, há uma segunda tentativa adaptada.
- **Chaves de API.** Vêm do `.env` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`) ou do assistente, que grava `secrets.json` no volume de dados. O `.env` tem prioridade. A chave nunca vai para o Redis nem para o log e nunca volta pela API; a interface mostra só os quatro últimos caracteres.
- **Erros.** Chave recusada, modelo inexistente, cota estourada ou falta de rede contam como IA indisponível: o caso aguarda, como com o Ollama fora do ar.
- **Custo e privacidade.** Com um provedor na nuvem, os dados dos casos (fictícios neste laboratório) vão para a API do provedor, que cobra por uso. O cache de respostas evita chamadas repetidas.

## Motores: Qwen e JEV

O agente de conferência tem dois motores, escolhidos em `agent_engine` (Configurações ou assistente, passo "Motor de decisão"). Veja a [ADR 0024](adr/0024-motor-jev-e-painel-de-desempenho.md).

| | Qwen (generativo) | JEV (modelo de decisão) |
| --- | --- | --- |
| Modelo padrão | `qwen2.5:7b` no provedor configurado | `tev1:0.8b` no Ollama 0.35+ |
| Chamada | chat com JSON Schema (`llm.chat_json`) | `POST /v1/systemone` com `state` e `questions` (`llm.decide`) |
| Entrada | o caso inteiro em JSON | poucos textos curtos por tarefa (`engines.build_state`) |
| Saída | veredito, confiança, resumo, achados e justificativa escritos pelo modelo | probabilidades: veredito (`choice`), verificações (`noul`) e risco (`score`); resumo e justificativa montados a partir delas (`engines.interpret`) |
| Achados | livres | verificações fixas; probabilidade de 50% ou mais vira achado |

- `jev_base_url` vazio usa o mesmo Ollama de `ollama_base_url`. Baixe o modelo com `ollama pull tev1:0.8b` ou com o botão "Baixar modelo JEV". Outras tags: `tev1` (4B) e `nimble` (9B).
- **Comparação** (`agent_compare_enabled`, padrão desligado): o outro motor responde a mesma tarefa logo depois, sem decidir. O caso mostra "Comparação com ... (não decide)" e o painel Desempenho mede a concordância entre os dois. Falha do motor de comparação nunca para o caso.
- **Classificação de elegibilidade** (`agent_eligibility_enabled`, padrão ligado): o agente classifica `ELEGIVEL`, `EXCECAO_NECESSARIA` ou `NAO_ELEGIVEL` depois das regras. É consultiva: a decisão é das regras, e a divergência fica no log e no caso.
- Com o JEV ativo, o indicador "IA ok" e a retomada dos casos em espera seguem o modelo de decisão. O agente de perguntas e os embeddings continuam no provedor generativo.

## Desempenho dos agentes

Cada chamada de agente, dos dois motores, grava um registro em `hr:metrics:agent` (`metrics.py`), que sobrevive à limpeza do laboratório. A tela **Desempenho** e `GET /api/metrics/agentes?periodo_horas=24&balde_min=0` mostram:

- por motor: chamadas, processamento e resposta do modelo (média, p50, p95, mín., máx.), espera por vaga, tokens, confiança, erros e concordância com as regras;
- o histórico por intervalo (automático ou escolhido), em gráfico;
- o tempo por tarefa (elegibilidade, auditoria, conferência);
- Qwen x JEV nos mesmos casos: concordância por tarefa, quem foi mais rigoroso e as divergências recentes;
- as últimas chamadas.

Tempos: **resposta** é só a chamada ao modelo; **espera** é a fila do semáforo de concorrência; **processamento** é a tarefa inteira (contexto, espera, novas tentativas e leitura). Cache, agente simulado e erros não entram nas médias. Para comparar latência real, desligue o cache e ligue a comparação. `DELETE /api/metrics/agentes` (botão "Limpar histórico") apaga o histórico.

## Agente de conferência

### Quando é chamado

- **Classificação de elegibilidade**, depois das regras de elegibilidade, quando `agent_eligibility_enabled` está ligado (tipo `ELEGIBILIDADE`, consultiva).
- **Auditoria**, antes da execução, depois que as regras do plano, as verificações do contrato de serviço, o compliance e o estado alvo foram avaliados sobre o estado projetado (tipo `AUDITORIA`).
- **Conferência final**, depois da execução, depois que os recibos e o estado final foram comparados com o que foi auditado (tipo `CONFERENCIA`).

### O que recebe

O prompt (`build_audit_prompt` e `build_verification_prompt`) contém, em JSON compacto:

- o evento e a data efetiva;
- o colaborador resumido (sem dados que não importam para a decisão);
- o contrato de processo e o estado alvo do cargo;
- o plano, com motivo e base legal de cada operação, e as operações descartadas;
- o resultado das regras determinísticas, já avaliadas;
- na conferência final, os recibos, as compensações, a diferença entre antes e depois e as divergências entre o auditado e o final.

O prompt completo e a resposta bruta ficam gravados no caso e aparecem na aba do agente, no detalhe do caso.

### O que devolve

A resposta é restrita por um esquema JSON passado ao provedor (no Ollama, `format`; nos outros, a saída estruturada de cada API):

```json
{
  "recomendacao": "APROVADO",
  "confianca": 0.86,
  "resumo": "Plano coerente com a promoção para analista pleno.",
  "achados": [
    {"severidade": "BAIXO", "referencia": "Política de movimentação", "descricao": "Aumento próximo do limite da política."}
  ],
  "justificativa": "..."
}
```

- A recomendação é **sempre** APROVADO ou REPROVADO. Qualquer outro valor é normalizado para REPROVADO.
- Confiança acima de 1 é tratada como percentual.
- Uma resposta que não é JSON válido ganha uma segunda tentativa; se falhar de novo, vale como REPROVADO com achado ALTO e o caso vai para revisão humana.

### Como a recomendação entra na decisão

| Regras | Agente | Modo `SE_REPROVADO` (padrão) | Modo `SEMPRE` |
| --- | --- | --- | --- |
| Passaram | APROVADO | Segue | Revisão humana |
| Passaram | REPROVADO | Revisão humana | Revisão humana |
| Regra excecionável falhou | qualquer | Aprovação de exceção pelas personas da regra | Exceção e revisão humana |
| Regra bloqueante falhou | qualquer | Rejeitado (o parecer do agente fica registrado) | Rejeitado |

A tabela vale para a auditoria, antes da execução: rejeitar ali não altera nenhum sistema. Na conferência final a execução já aconteceu: qualquer reprovação, das verificações ou do agente, vai para a auditoria interna, e a confirmação da reprovação reverte a execução.

Na revisão humana, a pessoa vê a recomendação do agente ao lado das regras e decide com justificativa. A recomendação nunca é omitida, mesmo quando a decisão é humana. Quando o agente discorda das regras, o painel conta como divergência e o log registra os dois lados.

### Cache, concorrência e desempenho

- Respostas são guardadas por 24 horas, com chave no hash do motor, do provedor, do modelo, da tarefa e do prompt. Cenários repetidos não chamam o modelo de novo. Desligue em Configurações para medir latência real.
- Um semáforo limita as chamadas simultâneas: `ollama_max_concurrency` (padrão 1; com GPU e `OLLAMA_NUM_PARALLEL` no servidor, aumente) e `cloud_max_concurrency` (padrão 4) para os provedores na nuvem.
- `ollama_keep_alive` mantém o modelo carregado; o worker faz um aquecimento quando o Ollama fica saudável.
- `ollama_num_ctx` (8192) e `ollama_num_predict` (900) cobrem os prompts maiores (desligamento de executivo). Temperatura 0 torna a resposta estável.

### IA fora do ar

O caso para em **Aguardando agente de IA** e entra em `hr:waiting_agent`. O monitor de cada worker verifica a saúde a cada 10 segundos (no Ollama, `/api/tags`; na nuvem, a lista de modelos da conta) e devolve os casos para a fila quando a IA volta.

Com **agente heurístico simulado** ligado (Configurações ou `HEURISTIC_FALLBACK_ENABLED=true`), um avaliador simples responde no lugar:

- reprova se alguma regra bloqueante ou excecionável falhou;
- aponta alteração contratual sem eSocial e desligamento sem cálculo de rescisão.

A decisão fica marcada como `agente: heuristico`, com o motivo, e a interface mostra "simulado". Serve para demonstrações, não substitui o modelo.

## Embeddings de todos os eventos

### O que é indexado

| Documento | Id | Texto |
| --- | --- | --- |
| Caso | `caso:{case_id}` | Narrativa do caso: evento, colaborador, cargo, UF, regras que falharam com explicação, plano, operações, falhas, compensações, aprovações com justificativa, recomendações do agente e decisão final. |
| Decisão do log | `log:{id}` | Entradas que carregam significado próprio: aprovação decidida, contrato alterado, colaborador alterado, operação falhou, compensação, evento rejeitado, replanejamento. |

Regras avaliadas, estágios e configurações não são indexados um a um: estão na narrativa do caso ou são ruído para a busca.

### Como o índice fica em dia

O serviço `indexer` lê `hr:log` com o grupo `hr-indexer`. Cada entrada marca o caso (ou a própria entrada) em `hr:vec:dirty`. Um laço processa as marcas com 1,5 segundo de espera (um caso gera muitas entradas em sequência) em lotes de 16. Se o texto não mudou, o embedding não é refeito.

`POST /api/index/rebuild` (botão "Reindexar tudo") marca tudo de novo; com `limpar=true`, apaga o índice antes. Mudar o modelo de embedding em Configurações reindexa tudo.

### Busca

1. A pergunta recebe o prefixo `search_query:` e os documentos `search_document:` (convenção do nomic-embed-text).
2. A API mantém em memória uma matriz numpy com todos os vetores, recarregada quando `hr:vec:version` muda.
3. A similaridade é o cosseno exato, somado a um pequeno reforço lexical para palavras da pergunta que aparecem no texto.
4. Filtros por tipo de evento, status e tipo de documento são aplicados antes da ordenação.

### Sem IA para embeddings

O indexador mostra **Aguardando IA** e acumula as marcas. Com o gerador `simulado`, o embedding de hashing descrito abaixo é o modelo escolhido, e não um substituto. Com o modo simulado ligado, usa um embedding de hashing de 512 dimensões (palavras, prefixos de 5 letras e bigramas, sem stopwords). Esses documentos ficam em `hr:vec:simulated` e são refeitos com o modelo real quando ele volta. Vetores de modelos diferentes nunca são comparados entre si.

## Agente de perguntas

A tela **Perguntar** aceita perguntas como "quantas promoções foram barradas por interstício?", "quais regras mais barram admissões?" ou "por que o caso caso-1a2b3c foi revertido?". A resposta tem três etapas, todas visíveis na aba "Interpretação" e "Rastro":

1. **Interpretação.** O modelo converte a pergunta numa consulta estruturada (`ROUTER_SCHEMA`): intenção (CONTAGEM, AGRUPAMENTO, LISTA, BUSCA, EXPLICACAO_CASO, DESEMPENHO), filtros, agrupamento, caso citado e frase para busca semântica. O prompt traz o catálogo do laboratório (tipos de evento, status, regras que já falharam, personas, cargos, UFs e cenários). A consulta é saneada: códigos que não existem no catálogo são descartados.
2. **Evidências.** Filtros e agregações rodam sobre os fatos, em Python. Os números são exatos. A busca semântica traz os documentos mais próximos (`ask_top_k`, padrão 8), respeitando os filtros.
3. **Resposta.** O modelo escreve a resposta só com as estatísticas e os documentos (`ANSWER_SCHEMA`), cita os casos usados e declara limitações. Citações que não estão nas evidências são removidas. Emoji são retirados do texto.

Se a IA estiver fora do ar, a API responde 503, a menos que o modo simulado esteja ligado; nesse caso, um interpretador por palavras-chave e uma resposta por modelo de texto respondem, marcados como simulados. As 50 últimas perguntas ficam em `hr:ask:history`.

## Ajustes recomendados

| Situação | Ajuste |
| --- | --- |
| CPU sem GPU | `qwen2.5:3b` ou `llama3.2:3b` para o conferente; mantenha `ollama_max_concurrency` em 1. |
| GPU com folga | `qwen2.5:14b`; `OLLAMA_NUM_PARALLEL=4` no servidor e `ollama_max_concurrency` 4. |
| Perguntas rápidas com conferente pesado | `ask_model` com um modelo menor. |
| Respostas truncadas | Aumente `ollama_num_predict` ou `ollama_num_ctx`. |
| Timeout na primeira chamada | Aumente `ollama_timeout_s`; o modelo está carregando. |
| Sem GPU e com rede | Um provedor na nuvem pelo assistente de configuração; com Claude, `anthropic_effort` em `low` deixa as chamadas mais rápidas. |
| Respostas da nuvem truncadas | Aumente `cloud_max_tokens` (o raciocínio do modelo também conta). |
