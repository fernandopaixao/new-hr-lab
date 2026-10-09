# Agentes de IA

O laboratório usa modelos locais no Ollama em três papéis. Nenhum deles decide sozinho o destino de um caso nem calcula números: regras determinísticas decidem, e os números vêm dos fatos (veja as ADRs [0006](adr/0006-regras-decidem-ia-audita.md), [0007](adr/0007-ollama-local-e-espera.md), [0016](adr/0016-embeddings-de-todos-os-eventos.md) e [0017](adr/0017-agente-de-linguagem-natural.md)).

| Papel | Modelo padrão | Código | Onde aparece |
| --- | --- | --- | --- |
| Agente de conferência | `qwen2.5:7b` (`OLLAMA_MODEL`) | `agent.py` | Auditoria (antes da execução) e conferência final |
| Embeddings | `nomic-embed-text` (`EMBEDDING_MODEL`) | `embeddings.py`, `indexer.py` | Índice de todos os eventos, busca semântica |
| Agente de perguntas | o mesmo do conferente, ou `ask_model` | `ask.py` | Tela Perguntar |

## Agente de conferência

### Quando é chamado

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

A resposta é restrita por um esquema JSON passado ao Ollama (`format`):

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

- Respostas são guardadas por 24 horas, com chave no hash do modelo e do prompt. Cenários repetidos não chamam o modelo de novo. Desligue em Configurações para medir latência real.
- Um semáforo limita as chamadas simultâneas (`ollama_max_concurrency`, padrão 1). Com GPU e `OLLAMA_NUM_PARALLEL` no servidor, aumente.
- `ollama_keep_alive` mantém o modelo carregado; o worker faz um aquecimento quando o Ollama fica saudável.
- `ollama_num_ctx` (8192) e `ollama_num_predict` (900) cobrem os prompts maiores (desligamento de executivo). Temperatura 0 torna a resposta estável.

### Ollama fora do ar

O caso para em **Aguardando agente de IA** e entra em `hr:waiting_agent`. O monitor de cada worker verifica a saúde a cada 10 segundos e devolve os casos para a fila quando o Ollama volta.

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

### Sem Ollama

O indexador mostra **Aguardando Ollama** e acumula as marcas. Com o modo simulado ligado, usa um embedding de hashing de 512 dimensões (palavras, prefixos de 5 letras e bigramas, sem stopwords). Esses documentos ficam em `hr:vec:simulated` e são refeitos com o modelo real quando ele volta. Vetores de modelos diferentes nunca são comparados entre si.

## Agente de perguntas

A tela **Perguntar** aceita perguntas como "quantas promoções foram barradas por interstício?", "quais regras mais barram admissões?" ou "por que o caso caso-1a2b3c foi revertido?". A resposta tem três etapas, todas visíveis na aba "Interpretação" e "Rastro":

1. **Interpretação.** O modelo converte a pergunta numa consulta estruturada (`ROUTER_SCHEMA`): intenção (CONTAGEM, AGRUPAMENTO, LISTA, BUSCA, EXPLICACAO_CASO, DESEMPENHO), filtros, agrupamento, caso citado e frase para busca semântica. O prompt traz o catálogo do laboratório (tipos de evento, status, regras que já falharam, personas, cargos, UFs e cenários). A consulta é saneada: códigos que não existem no catálogo são descartados.
2. **Evidências.** Filtros e agregações rodam sobre os fatos, em Python. Os números são exatos. A busca semântica traz os documentos mais próximos (`ask_top_k`, padrão 8), respeitando os filtros.
3. **Resposta.** O modelo escreve a resposta só com as estatísticas e os documentos (`ANSWER_SCHEMA`), cita os casos usados e declara limitações. Citações que não estão nas evidências são removidas. Emoji são retirados do texto.

Se o Ollama estiver fora do ar, a API responde 503, a menos que o modo simulado esteja ligado; nesse caso, um interpretador por palavras-chave e uma resposta por modelo de texto respondem, marcados como simulados. As 50 últimas perguntas ficam em `hr:ask:history`.

## Ajustes recomendados

| Situação | Ajuste |
| --- | --- |
| CPU sem GPU | `qwen2.5:3b` ou `llama3.2:3b` para o conferente; mantenha `ollama_max_concurrency` em 1. |
| GPU com folga | `qwen2.5:14b`; `OLLAMA_NUM_PARALLEL=4` no servidor e `ollama_max_concurrency` 4. |
| Perguntas rápidas com conferente pesado | `ask_model` com um modelo menor. |
| Respostas truncadas | Aumente `ollama_num_predict` ou `ollama_num_ctx`. |
| Timeout na primeira chamada | Aumente `ollama_timeout_s`; o modelo está carregando. |
