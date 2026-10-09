# Operação

## Subir

```bash
cp .env.example .env
docker compose up -d --build
```

A interface fica em http://localhost:8080 (porta em `UI_PORT`). Na primeira subida, a API carrega os contratos de exemplo e gera um time de 80 colaboradores.

| Serviço | Para que serve | Como ver o log |
| --- | --- | --- |
| `redis` | Filas e dados (volume `redisdata`, AOF ligado) | `docker compose logs redis` |
| `api` | REST e SSE | `docker compose logs -f api` |
| `worker` | Estágios da linha | `docker compose logs -f worker` |
| `indexer` | Embeddings dos eventos | `docker compose logs -f indexer` |
| `frontend` | Interface (nginx) | `docker compose logs frontend` |

O log de decisões também é gravado em `audit-log.jsonl`, no volume de dados da API e dos workers.

## Ollama

| Onde está | `OLLAMA_BASE_URL` |
| --- | --- |
| Na própria máquina | `http://host.docker.internal:11434` (padrão) |
| Em outra máquina da rede | `http://IP:11434` |
| Em container (`docker compose --profile ollama up -d`) | `http://ollama:11434` |

- No Linux, o Ollama da máquina precisa escutar fora do loopback: `OLLAMA_HOST=0.0.0.0 ollama serve`.
- Os modelos necessários são `qwen2.5:7b` e `nomic-embed-text`. Baixe com `ollama pull` ou pelos botões em Configurações. O perfil `ollama` baixa os dois sozinho.
- O selo no topo da interface mostra "IA ok" quando o Ollama responde e os modelos existem.

## Configurações

Todas podem ser alteradas na tela Configurações sem reiniciar; as variáveis de ambiente definem os valores iniciais. Cada alteração vai para o log.

| Configuração | Variável | Padrão | Efeito |
| --- | --- | --- | --- |
| URL do Ollama | `OLLAMA_BASE_URL` | `http://localhost:11434` (o compose usa `host.docker.internal`) | Onde estão os modelos. |
| Modelo do conferente | `OLLAMA_MODEL` | `qwen2.5:7b` | Conferência do plano e auditoria. |
| Timeout | `OLLAMA_TIMEOUT_S` | 180 | Segundos por chamada. |
| Contexto e resposta | `OLLAMA_NUM_CTX`, `OLLAMA_NUM_PREDICT` | 8192, 900 | Tokens de contexto e de saída. |
| Manter carregado | `OLLAMA_KEEP_ALIVE` | `30m` | Tempo que o modelo fica na memória. |
| Chamadas simultâneas | `OLLAMA_MAX_CONCURRENCY` | 1 | Por processo de worker. |
| Temperatura | `OLLAMA_TEMPERATURE` | 0 | Estabilidade das respostas. |
| Cache do agente | `AGENT_CACHE_ENABLED` | ligado | Reaproveita respostas por 24 horas. |
| Agente simulado | `HEURISTIC_FALLBACK_ENABLED` | desligado | Sem Ollama: desligado espera, ligado responde com heurística marcada. |
| Revisão humana | `HUMAN_REVIEW_MODE` | `SE_REPROVADO` | `SEMPRE` exige decisão humana em todo plano e auditoria. |
| Atraso visual | `STAGE_DELAY_MS` | 700 | Pausa em cada estágio para acompanhar a linha. Use 0 em estresse. |
| Falhas injetadas | `FAILURE_RATE_PERCENT` | 0 | Probabilidade de falha por operação, para exercitar a saga. |
| Modelo de embedding | `EMBEDDING_MODEL` | `nomic-embed-text` | Mudar reindexa tudo. |
| Indexação | `INDEXING_ENABLED` | ligada | Desligada, o indexador para. |
| Modelo das perguntas | `ASK_MODEL` | vazio (o do conferente) | Permite um modelo menor para perguntas. |
| Documentos por pergunta | `ASK_TOP_K` | 8 | Quantos documentos a busca semântica entrega ao agente. |

Variáveis só de ambiente: `REDIS_URL`, `DATA_DIR`, `STAGE_CONCURRENCY` (casos simultâneos por estágio em cada worker, padrão 4) e `WORKER_NAME` (nome fixo de consumidor, fora do Docker).

## Rotina de demonstração

1. **Cenários**, escolha "Promoção padrão" e dispare. Acompanhe na **Linha**.
2. Clique no caso: veja regras, plano, parecer do agente e recibos.
3. Dispare "Promoção sem interstício". O caso para em **Aguardando aprovação**. Troque a persona para HRBP, abra **Aprovações** e decida com justificativa.
4. Em **Contratos**, mude o interstício da política, salve como nova versão e dispare o cenário de novo.
5. Rode a **suíte completa** e compare esperado e obtido.
6. Abra **Visão** para o painel e **Perguntar** para perguntas como "quais regras mais barram promoções?".

## Depuração

| Ferramenta | Onde | O que faz |
| --- | --- | --- |
| Pausar a linha | Linha, botão no topo | Nenhum worker consome; as mensagens acumulam nas filas. |
| Pausar uma estação | Linha, botão da estação | Só aquele estágio para. |
| Parar antes | Linha, marcador da estação | Todo caso para antes do estágio, com status `PARADO`. |
| Passo a passo | Ao disparar um cenário ou no detalhe do caso | O caso para antes de cada estágio. |
| Avançar ou continuar | Detalhe do caso | Libera um estágio, ou libera e desliga o passo a passo. |
| Reprocessar | Detalhe do caso | Volta a um estágio, opcionalmente com o evento editado. |
| Cancelar | Detalhe do caso | Encerra um caso que não terminou. |

## Estresse

```bash
docker compose up -d --scale worker=4
```

1. Em Configurações, ponha o atraso visual em 0 e, se quiser, falhas em 5%.
2. Em Cenários, aba "Rajada de eventos", dispare 200 a 500 eventos.
3. Acompanhe filas e tempos na Linha e na Visão; `GET /api/metrics` mostra o mesmo.

O gargalo costuma ser o Ollama. Com o cache ligado, eventos parecidos reaproveitam a resposta; para medir a latência real, desligue o cache. Com `--scale worker=N`, cada worker faz até `OLLAMA_MAX_CONCURRENCY` chamadas simultâneas.

## Reiniciar

- **Configurações, Reiniciar laboratório**: limpa casos, aprovações, filas, log e índice; opcionalmente gera um time novo. Contratos e configurações ficam.
- **Contratos, Restaurar exemplos**: volta aos contratos de exemplo.
- **Do zero**: `docker compose down -v` apaga também os volumes.

## Problemas comuns

| Sintoma | Causa provável | Solução |
| --- | --- | --- |
| Casos parados em "Aguardando agente de IA" | Ollama inacessível ou sem o modelo | Verifique o selo de IA e `OLLAMA_BASE_URL`; baixe o modelo em Configurações. No Linux, `OLLAMA_HOST=0.0.0.0`. |
| Selo "IA ok" mas casos lentos | Modelo em CPU | Use um modelo menor ou GPU; veja [agentes](agentes.md#ajustes-recomendados). |
| Índice "Aguardando Ollama" | Falta `nomic-embed-text` | Botão "Baixar modelo de embedding" em Configurações. |
| Perguntar responde 503 | Ollama fora e modo simulado desligado | Suba o Ollama ou ligue o agente simulado. |
| Filas crescendo sem andar | Linha ou estação pausada | Verifique os botões de pausa na Linha. |
| Cenário responde "nenhum colaborador adequado" | Time pequeno ou sem o perfil | Gere um time maior em Colaboradores. |
| Muitos "Falhou e compensado" | Falhas injetadas ligadas | Zere em Configurações. |
| Interface sem atualizações ao vivo | Proxy com buffer no SSE | Use o nginx do compose ou desligue o buffer em `/api/stream`. |

## Testes

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q tests
```

Os testes cobrem o avaliador de expressões, a validação de contratos, o motor (elegibilidade, estado alvo, plano, auditoria) e os fatos, o embedding simulado e o agente de perguntas. Não precisam de Redis nem de Ollama. A suíte de cenários, na tela Cenários, é o teste de ponta a ponta.
