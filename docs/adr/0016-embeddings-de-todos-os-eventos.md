# 0016. Embeddings de todos os eventos com indexador dedicado e busca exata

## Contexto

Fase 2: embedding de todos os eventos, para servir a um agente de linguagem natural. Os mesmos padrões da base continuam valendo: Ollama, Docker e espera quando a IA está indisponível.

## Decisão

- **O que é embutido:**
  - um **documento narrativo por caso** (evento, colaborador, situação, elegibilidade, regras que falharam, plano, descartes, pareceres do agente, falhas, aprovações com justificativa, auditoria e decisão final), regenerado quando o caso muda;
  - um documento por **decisão do log** que tem valor próprio: aprovação decidida, alteração de contrato, alteração de colaborador, falha de operação, compensação, evento rejeitado e replanejamento.

  Controles do laboratório (pausa, configurações, reindexação) ficam de fora para não poluir as respostas.
- **Quem embute:** um serviço `indexer` separado, que lê o stream do log com o próprio grupo de consumidores, marca o que mudou num sorted set e embute em lotes depois de um *debounce* de 1,5 segundo. Assim, um caso que passa por seis estágios em um segundo é embutido uma vez. Textos que não mudaram não são reembutidos (hash do texto).
- **Modelo:** `nomic-embed-text` via `/api/embed` do Ollama, com os prefixos de tarefa do modelo (`search_document:` e `search_query:`). Trocar o modelo nas configurações marca tudo para reindexação, porque vetores de modelos diferentes não são comparáveis.
- **Armazenamento e busca:** vetores float32 no Redis, ao lado do texto e dos metadados. Cada processo da API mantém uma matriz numpy normalizada e a recarrega quando a versão do índice muda. A busca é exata (similaridade de cosseno), com filtros por metadados (tipo de evento, status, colaborador, cargo, UF, fonte) e um pequeno bônus lexical.
- **Sem Ollama:** os eventos ficam marcados e esperam. Com o modo simulado ligado, um embedding determinístico por hashing (palavras, radicais de 5 letras e bigramas, 512 dimensões) é usado e marcado. Esses documentos são reembutidos sozinhos quando o Ollama volta. Na busca simulada, todos os textos são comparados com o modelo simulado, para que nada fique de fora.

## Alternativas consideradas

- **Redis Stack (RediSearch) ou Qdrant com índice HNSW.** É a escolha certa acima de centenas de milhares de documentos. Aqui, trocaria a imagem do Redis ou acrescentaria um serviço para ganhar milissegundos que a busca exata já entrega.
- **Embutir dentro do worker.** Acoplaria a latência do embedding à linha de produção, e uma falha do modelo de embedding pararia os casos.
- **Embutir cada entrada do log.** O volume seria dezenas de vezes maior, com textos curtos e repetitivos; o documento por caso concentra o significado.

## Consequências

- O índice é eventualmente consistente: há um atraso de segundos entre o evento e a busca.
- O painel mostra o estado do indexador (em dia, indexando, aguardando o Ollama), os documentos e a fila.
- `POST /api/index/rebuild` reconstrói tudo; reiniciar o laboratório também limpa o índice.
