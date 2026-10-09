# Operação

## Subir

### Instalador

| Sistema | Comando |
| --- | --- |
| Linux e macOS | `./scripts/install.sh` |
| Windows | `scripts\install.cmd` ou `.\scripts\install.ps1` (Windows PowerShell 5.1 ou PowerShell 7) |

O instalador faz, nesta ordem:

1. Confere o Docker, se ele está rodando, e o Docker Compose 2.24 ou mais novo (o `docker-compose.yml` usa `env_file` opcional, que exige essa versão).
2. Cria o `.env` a partir do `.env.example` ou, se já existir, guarda uma cópia (`.env.bak-AAAAMMDDHHMMSS`) e altera só as chaves que escolhe.
3. Escolhe a porta da interface (padrão 8580). Se ela estiver ocupada por outro programa, oferece a próxima livre (com `--sim`, usa essa direto). Uma instalação anterior do laboratório na mesma porta não conta. Um `.env` antigo com a porta 8080, o padrão anterior, passa para 8580. Uma porta passada em `--porta` é respeitada: se estiver ocupada, o instalador para.
4. Encontra o Ollama. No modo `auto`, usa o da máquina se ele responder em `localhost:11434`; se não, oferece Ollama em container, Ollama na rede, IA na nuvem ou nenhum.
5. Testa o Ollama **de dentro de um container**, do mesmo jeito que a API vai acessá-lo. É o que pega o caso mais comum no Linux: o Ollama escutando só em 127.0.0.1. Nesse caso mostra como liberar e para.
6. Baixa os modelos que faltam (`ollama pull` ou a API do Ollama). No modo container, o serviço `ollama-pull` baixa e o instalador espera.
7. Sobe o compose (`up -d --build`, com a quantidade de workers pedida) e espera a API responder.
8. Alinha as configurações em execução com as escolhas da instalação. Configurações salvas pela tela Configurações valem mais que o `.env`; sem esse passo, uma URL antiga do Ollama continuaria valendo.
9. Pede à API para conferir a IA e mostra o resultado e um resumo, incluindo se o [assistente de configuração](#assistente-de-configuração-inicial) ainda precisa ser feito.

Pode ser rodado de novo a qualquer momento para trocar o modo do Ollama, os modelos, a porta ou a quantidade de workers. Os dados (casos, log, colaboradores) ficam.

| Opção (Linux e macOS) | Opção (Windows) | Efeito |
| --- | --- | --- |
| `--ollama MODO` | `-Ollama MODO` | `auto` (padrão), `local`, `rede`, `container`, `nuvem` ou `nenhum`. |
| `--ollama-url URL` | `-OllamaUrl URL` | Ollama em outra máquina; implica o modo `rede`. |
| `--modelo NOME` | `-Modelo NOME` | Modelo dos agentes (padrão `qwen2.5:7b`). |
| `--embedding NOME` | `-Embedding NOME` | Modelo de embedding (padrão `nomic-embed-text`). |
| `--sem-modelos` | `-SemModelos` | Não baixa modelos. |
| `--porta N` | `-Porta N` | Porta da interface (padrão 8580). |
| `--porta-ollama N` | `-PortaOllama N` | Porta do Ollama em container na máquina (padrão 11434). Se a padrão estiver ocupada, usa a próxima livre. |
| `--workers N` | `-Workers N` | Quantidade de workers (padrão 1). |
| `--simulado` | `-Simulado` | Liga o agente simulado quando o Ollama cair. Fica desligado sem esta opção, exceto no modo `nenhum`. |
| `--sem-build` | `-SemBuild` | Sobe sem reconstruir as imagens. |
| `--sim` | `-Sim` | Não pergunta nada. Sem Ollama na máquina, escolhe o modo container. |

| Modo | `OLLAMA_BASE_URL` gravado | Observação |
| --- | --- | --- |
| `local` | `http://host.docker.internal:11434` | No Linux, o Ollama precisa escutar em 0.0.0.0. |
| `rede` | a URL informada | O Ollama remoto precisa escutar em 0.0.0.0 e a porta 11434 precisa estar liberada. |
| `container` | `http://ollama:11434` | Grava `COMPOSE_PROFILES=ollama`, então um `docker compose up -d` depois também sobe o Ollama. A porta na máquina fica em `OLLAMA_PORT`; dentro da rede do compose é sempre 11434. Os modelos ficam no volume `ollama`. |
| `nuvem` | o que já estava | Sem Ollama. O provedor (Claude, OpenAI ou Gemini), o modelo e a chave são escolhidos no assistente da interface. Até lá, os casos aguardam a IA. |
| `nenhum` | o que já estava | Liga o agente simulado e os embeddings simulados. |

### Manualmente

```bash
cp .env.example .env
docker compose up -d --build
```

A interface fica em http://localhost:8580 (porta em `UI_PORT`). Na primeira subida, a API carrega os contratos de exemplo e gera um time de 80 colaboradores.

| Serviço | Para que serve | Como ver o log |
| --- | --- | --- |
| `redis` | Filas e dados (volume `redisdata`, AOF ligado) | `docker compose logs redis` |
| `api` | REST e SSE | `docker compose logs -f api` |
| `worker` | Estágios da linha | `docker compose logs -f worker` |
| `indexer` | Embeddings dos eventos | `docker compose logs -f indexer` |
| `frontend` | Interface (nginx) | `docker compose logs frontend` |

O log de decisões também é gravado em `audit-log.jsonl`, no volume de dados da API e dos workers.

## Assistente de configuração inicial

Na primeira visita, a interface abre o assistente ([ADR 0022](adr/0022-assistente-de-configuracao-inicial.md)). Ele pode ser reaberto em **Configurações, Abrir assistente de configuração**.

1. **Início**: mostra o endereço da interface, o Redis e a versão, quantos colaboradores e casos existem e a IA atual. A porta e o Redis vêm da instalação; para mudá-los, rode o instalador de novo ou edite o `.env`.
2. **IA dos agentes**: Ollama, Anthropic Claude, OpenAI ou compatível, Google Gemini ou sem IA (agente simulado).
3. **Conexão**: URL do Ollama ou chave de API, URL base (OpenAI), modelo e esforço (Claude). **Testar conexão** lista os modelos da conta e faz uma chamada mínima; o erro diz se falhou a conexão, o modelo ou a chamada. A chave digitada é usada no teste e só é salva ao concluir.
4. **Busca semântica**: quem gera os embeddings (Ollama, OpenAI, Gemini ou simulado). A Anthropic não oferece embeddings.
5. **Linha**: revisão humana, agente simulado quando a IA cair e atraso visual.
6. **Revisão**: resumo e **Concluir**. As escolhas vão para o log; a chave não.

**Pular e manter como está** fecha o assistente sem mudar nada. Detalhes dos provedores em [agentes](agentes.md#provedores).

## Ollama

| Onde está | `OLLAMA_BASE_URL` |
| --- | --- |
| Na própria máquina | `http://host.docker.internal:11434` (padrão) |
| Em outra máquina da rede | `http://IP:11434` |
| Em container (`docker compose --profile ollama up -d`) | `http://ollama:11434` |

- No Linux, o Ollama da máquina precisa escutar fora do loopback: `OLLAMA_HOST=0.0.0.0 ollama serve`.
- Os modelos necessários são `qwen2.5:7b` e `nomic-embed-text`. Baixe com `ollama pull` ou pelos botões em Configurações. O perfil `ollama` baixa os dois sozinho.
- O selo no topo da interface mostra "IA ok" quando o provedor escolhido responde e o modelo existe.

## Configurações

Todas podem ser alteradas na tela Configurações sem reiniciar; as variáveis de ambiente definem os valores iniciais. Cada alteração vai para o log.

| Configuração | Variável | Padrão | Efeito |
| --- | --- | --- | --- |
| Provedor dos agentes | `LLM_PROVIDER` | `ollama` | `ollama`, `anthropic`, `openai` ou `gemini`. |
| Modelo Claude e esforço | `ANTHROPIC_MODEL`, `ANTHROPIC_EFFORT` | `claude-opus-5-5`, `medium` | Usados com `anthropic`. |
| Modelo e URL base OpenAI | `OPENAI_MODEL`, `OPENAI_BASE_URL` | `gpt-5-mini`, `https://api.openai.com/v1` | Usados com `openai`; a URL aceita serviços compatíveis. |
| Modelo Gemini | `GEMINI_MODEL` | `gemini-2.5-flash` | Usado com `gemini`. |
| Nuvem: timeout, tokens, simultâneas | `CLOUD_TIMEOUT_S`, `CLOUD_MAX_TOKENS`, `CLOUD_MAX_CONCURRENCY` | 120, 16000, 4 | Por chamada e por processo de worker. |
| URL do Ollama | `OLLAMA_BASE_URL` | `http://localhost:11434` (o compose usa `host.docker.internal`) | Onde estão os modelos. |
| Modelo do conferente | `OLLAMA_MODEL` | `qwen2.5:7b` | Auditoria antes da execução e conferência final. |
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
| Gerador de embeddings | `EMBEDDING_PROVIDER` | `ollama` | `ollama`, `openai`, `gemini` ou `simulado`. Mudar reindexa tudo. |
| Modelo de embedding | `EMBEDDING_MODEL`, `OPENAI_EMBEDDING_MODEL`, `GEMINI_EMBEDDING_MODEL` | `nomic-embed-text`, `text-embedding-3-small`, `gemini-embedding-001` | Mudar reindexa tudo. |
| Indexação | `INDEXING_ENABLED` | ligada | Desligada, o indexador para. |
| Modelo das perguntas | `ASK_MODEL` | vazio (o do conferente) | Permite um modelo menor para perguntas. |
| Documentos por pergunta | `ASK_TOP_K` | 8 | Quantos documentos a busca semântica entrega ao agente. |

Variáveis só de ambiente: as chaves de API (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` ou `GOOGLE_API_KEY`), que têm prioridade sobre a chave salva pelo assistente, `REDIS_URL`, `DATA_DIR`, `STAGE_CONCURRENCY` (casos simultâneos por estágio em cada worker, padrão 4) `WORKER_NAME` (nome fixo de consumidor, fora do Docker) e `AGENDA_INTERVAL_S` (segundos entre conferências da agenda de vigências em cada worker, padrão 5).

## Rotina de demonstração

1. **Cenários**, escolha "Promoção padrão" e dispare. Acompanhe na **Linha**.
2. Clique no caso: veja regras, plano, a auditoria feita antes da execução, o parecer do agente, os recibos e a conferência final. O quadro **Próximo passo** diz o que acontece agora e quem age.
3. Dispare "Promoção sem interstício". O caso para em **Aguardando aprovação**, e o cartão na Linha diz quem precisa decidir. Troque a persona para HRBP, abra **Aprovações** e decida com justificativa.
4. Em **Colaboradores**, navegue pelo organograma, abra um perfil e clique no gestor ou na equipe para subir e descer na hierarquia.
5. Em **Contratos**, mude o interstício da política, salve como nova versão e dispare o cenário de novo.
6. Rode a **suíte completa** e compare esperado e obtido.
7. Abra **Visão** para o painel e **Perguntar** para perguntas como "quais regras mais barram promoções?".
8. Dispare "Inclusão no programa de alto potencial" em **Cenários** e abra o perfil da pessoa: o programa aparece com o tempo que falta, o aviso e o vencimento agendados. Em **Vigências**, avance o relógio (por exemplo, "+1 ano"): a agenda emite o aviso e o vencimento, que passam pela linha e retiram bolsa, mentoria e acesso. "Voltar ao calendário real" desfaz a simulação de data.

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

### Atualizar uma instalação existente

- Casos gravados antes da auditoria passar para antes da execução ([ADR 0018](adr/0018-auditoria-antes-da-execucao.md)) são migrados sozinhos na primeira partida da API: estágios, campos e aprovações pendentes ganham os nomes novos, e casos que estavam a caminho dessas etapas voltam para a fila. Nada precisa ser feito.
- Depois de atualizar para a versão com provedores na nuvem, o assistente de configuração aparece uma vez, já preenchido com a configuração atual. **Pular e manter como está** encerra sem mudar nada.
- As regras de hierarquia ([ADR 0019](adr/0019-hierarquia-e-gestor-imediato.md)) estão nos contratos de exemplo. Contratos já carregados não são trocados sozinhos; use **Contratos, Restaurar exemplos** para recebê-las (versões editadas à mão são descartadas).

## Problemas comuns

| Sintoma | Causa provável | Solução |
| --- | --- | --- |
| Casos parados em "Aguardando agente de IA" | Ollama inacessível ou sem o modelo; na nuvem, chave ausente ou recusada, modelo errado ou cota estourada | Passe o mouse no selo de IA para ver o erro. Ollama: confira `OLLAMA_BASE_URL` e baixe o modelo em Configurações (no Linux, `OLLAMA_HOST=0.0.0.0`). Nuvem: refaça o teste no assistente de configuração. |
| Selo "IA ok" mas casos lentos | Modelo em CPU | Use um modelo menor ou GPU; veja [agentes](agentes.md#ajustes-recomendados). |
| Índice "Aguardando IA" | Falta `nomic-embed-text`, ou o gerador de embeddings na nuvem está sem chave | Ollama: "Baixar modelo de embedding" em Configurações. Nuvem: salve a chave pelo assistente ou escolha outro gerador. |
| Perguntar responde 503 | IA fora e modo simulado desligado | Resolva a IA (selo no topo) ou ligue o agente simulado. |
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

Os testes cobrem o avaliador de expressões, a validação de contratos, o motor (elegibilidade, estado alvo, plano, auditoria) e os fatos, o embedding simulado, o agente de perguntas e os provedores de IA na nuvem (com um transporte HTTP simulado). Não precisam de Redis, de Ollama nem de chave de API. A suíte de cenários, na tela Cenários, é o teste de ponta a ponta.
