# Novo RH: laboratório de eventos

Laboratório para criar, demonstrar, experimentar e estressar uma arquitetura de operações de RH orientada a eventos.

Toda operação de RH segue a mesma linha de produção:

```
evento -> gatilho -> elegibilidade -> planejamento -> auditoria -> execução (saga) -> conferência final
```

- **Eventos** (promoção, admissão, transferência, desligamento, reajuste da CCT, etc.) bastam para disparar e alimentar o fluxo inteiro.
- **Contratos** versionados e com vigência descrevem as regras:
  - **norma**: CLT e CCT dos bancários, com valores ilustrativos e fictícios;
  - **política** interna;
  - **cargo**: estado alvo e compliance de cada posição, como garden leave para executivos e celular corporativo para a média gerência;
  - **processo**: elegibilidade, orquestração e auditoria, avaliada antes de qualquer sistema ser alterado.
- **Prateleira de serviços**: operações desacopladas e parametrizáveis que qualquer processo pode chamar, como adicionar benefício, alterar salário, incluir verba de bônus ou revogar acesso.
- **Agente de conferência com IA**: Ollama local ou na rede por padrão, ou Anthropic Claude, OpenAI (e serviços compatíveis) ou Google Gemini na nuvem. Ele audita o plano antes da execução, confere a execução depois e sempre dá uma recomendação clara, APROVADO ou REPROVADO, com justificativa. Regras determinísticas decidem; o agente é a segunda linha de defesa.
- **Eventos com vigência**: programas com prazo, como o de alto potencial (12 meses a partir da data oficial). A agenda emite o aviso antes do fim e o vencimento na data, os dois pela linha normal, que retira o que o programa concedia; renovação e encerramento antecipado reagendam ou cancelam. Um relógio simulado permite avançar o tempo para testar.
- **Hierarquia**: cada colaborador tem gestor imediato; o organograma é navegável, as regras usam a hierarquia e as aprovações do gestor mostram o gestor real.
- **Próximo passo** explícito em cada fase e em cada caso: o que acontece agora e quem precisa agir.
- **Aprovações de exceção** por persona, com justificativa registrada.
- **Log de decisões** explica por que uma operação foi escolhida ou descartada, por que alguém não é elegível e quem aprovou o quê.
- **Visibilidade**: painel com funil, gargalos, regras que mais barram, aprovações e concordância entre agente e regras, além de métricas Prometheus.
- **Embeddings de todos os eventos** (`nomic-embed-text`) e um **agente de perguntas em linguagem natural**, que responde com números exatos e cita os casos.

A documentação completa, com as decisões arquiteturais, está em [docs/](docs/README.md).

## Como rodar

Pré-requisitos: Docker com Compose 2.24 ou mais novo. O Ollama é opcional: o instalador usa o da máquina, um da rede ou sobe um em container, e a IA também pode ser um provedor na nuvem.

```bash
./scripts/install.sh            # Linux e macOS
```

```powershell
scripts\install.cmd             # Windows (ou .\scripts\install.ps1)
```

O instalador confere os pré-requisitos, encontra o Ollama, testa se os containers o alcançam, grava o `.env`, baixa os modelos, sobe o laboratório e confere a IA de dentro da API. Ao final, abra http://localhost:8580. Na primeira visita, o **assistente de configuração inicial** pede o provedor de IA, o modelo e, para a nuvem, a chave de API, e testa a conexão antes de salvar ([detalhes](docs/operacao.md#assistente-de-configuração-inicial)). Com `--sim` (ou `-Sim` no Windows) ele não faz perguntas; `--ajuda` lista as opções. Os detalhes estão em [docs/operacao.md](docs/operacao.md#instalador).

Sem o instalador:

```bash
cp .env.example .env        # ajuste OLLAMA_BASE_URL se necessário
docker compose up -d --build
```

### Onde está o Ollama

| Situação | OLLAMA_BASE_URL |
| --- | --- |
| Ollama instalado na própria máquina | `http://host.docker.internal:11434` (padrão) |
| Ollama em outra máquina da rede | `http://IP-DA-MAQUINA:11434` |
| Ollama em container (perfil `ollama`) | `http://ollama:11434` |

- No Linux, o Ollama da máquina precisa escutar fora do loopback. Rode `OLLAMA_HOST=0.0.0.0 ollama serve` ou ajuste o serviço do systemd.
- Para subir o Ollama junto, em CPU, com download automático do modelo, use `docker compose --profile ollama up -d --build`.
- Os modelos padrão são `qwen2.5:7b` (agentes) e `nomic-embed-text` (embeddings). Baixe com `ollama pull` ou pelos botões da tela de Configurações.

### IA na nuvem

Escolha no assistente (ou em Configurações) entre Anthropic Claude, OpenAI ou compatível (Azure OpenAI, OpenRouter, Groq, vLLM, trocando a URL base) e Google Gemini. A chave digitada no assistente fica num arquivo do volume de dados, nunca no Redis nem no log; uma chave em `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` ou `GEMINI_API_KEY` no `.env` tem prioridade. Com um provedor na nuvem, os dados dos casos (fictícios) vão para a API do provedor, que cobra por uso. Veja [docs/agentes.md](docs/agentes.md#provedores).

Com provedor externo, o assistente também cadastra um **teto de gastos** em dólares (mensal ou total, US$ 10 por padrão). Cada chamada é precificada pelos tokens informados pelo provedor; atingido o teto, nenhuma chamada nova é enviada, os casos aguardam a IA e uma faixa vermelha aparece no topo da tela, além da entrada no log. O painel em Configurações mostra o gasto, os preços por modelo e as últimas chamadas ([ADR 0025](docs/adr/0025-teto-de-gastos-com-llm-externa.md)).

### Motor JEV

Além do agente generativo (Qwen), a elegibilidade e as auditorias podem usar um modelo de decisão no estilo JEV, servido pelo Ollama 0.35 ou mais novo: `ollama pull tev1:0.8b` e escolha "JEV" em Configurações ou no assistente. Ligue "Comparar os dois motores" para medir Qwen e JEV nos mesmos casos na tela Desempenho. Veja [docs/agentes.md](docs/agentes.md#motores-qwen-e-jev).

Se a IA estiver fora do ar, os casos param em "Aguardando agente de IA" e são retomados sozinhos quando ela volta. Para demonstrações sem IA, ligue o agente heurístico simulado em Configurações ou use `HEURISTIC_FALLBACK_ENABLED=true`. Toda decisão desse agente fica marcada como simulada.

### Estresse

```bash
docker compose up -d --scale worker=3
```

Na tela Cenários, a aba "Rajada de eventos" dispara dezenas de eventos aleatórios. Em Configurações você pode injetar falhas nas operações para exercitar a compensação da saga.

## O que dá para fazer na interface

| Tela | Para quê |
| --- | --- |
| Linha | Linha de produção ao vivo, com uma estação por estágio. Permite pausar a linha ou uma estação, "parar antes" de um estágio e clicar em um caso para depurar. |
| Detalhe do caso | Evento, regras avaliadas, plano com operações escolhidas e descartadas, parecer do agente com prompt e resposta bruta, recibos da execução, compensações, auditoria, estado antes e depois e trilha completa. Permite avançar passo a passo, reprocessar a partir de um estágio, editar o evento e cancelar. |
| Desempenho | Tempo de resposta e de processamento dos agentes por motor (Qwen e JEV), histórico, tempo por tarefa e concordância entre os motores nos mesmos casos. |
| Visão | Painel de visibilidade: KPIs, alertas, linha do tempo, funil, tempo por estágio, evento por situação, regras que mais barram, operações, aprovações, agente e índice. |
| Perguntar | Perguntas em linguagem natural sobre todos os eventos, busca semântica e histórico. Cada resposta mostra a interpretação, os números exatos e as fontes. |
| Cenários | 54 cenários reais, de exceção, de bloqueio, coletivos e de estresse, cada um com o resultado esperado. Também traz a suíte completa com comparação entre esperado e obtido, evento manual e rajada. |
| Aprovações | Exceções de elegibilidade e revisões humanas do plano e da auditoria. Troque a persona no topo para decidir como HRBP, Jurídico, Compliance, Comitê e outras. |
| Colaboradores | Time artificial: edite cargo, datas, salário, conduta, estabilidades e dependentes; veja os programas ativos e o tempo que falta; injete desvios; confira a conformidade; dispare eventos. |
| Vigências | Relógio simulado (avançar dias ou ir para uma data) e agenda de avisos e vencimentos dos programas ativos, com o caso que cada evento abriu. |
| Contratos | Editor estruturado e YAML para incluir ou remover regras e operações, mudar vigências e salvar como nova versão. |
| Prateleira | Catálogo de operações, com execução avulsa ou simulada. |
| Log | Todas as decisões e alterações, com filtro e exportação em JSONL. |
| Configurações | Teto de gastos com LLM externa (gasto, preço por modelo, últimas chamadas), motor dos agentes (Qwen ou JEV) e comparação entre eles, provedor de IA e assistente de configuração, parâmetros do Ollama e da nuvem, gerador de embeddings e modelo de perguntas, modo de revisão humana, atraso visual, injeção de falhas e reinício do laboratório. |

## Desenvolvimento local

```bash
# backend (requer Redis em localhost:6379)
cd backend && pip install -r requirements.txt -r requirements-dev.txt
python -m hrlab.worker &
python -m hrlab.indexer &
uvicorn hrlab.api:app --reload --port 8000
python -m pytest -q tests      # 42 testes, sem Redis e sem rede

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## Estrutura

```
backend/hrlab/
  api.py            API REST e SSE (FastAPI)
  worker.py         consumidores das filas por estágio (Redis Streams)
  pipeline.py       handlers de cada estágio, aprovações, depuração e saga
  engine.py         regras, elegibilidade, plano, conferência e auditoria (lógica pura)
  shelf.py          prateleira de operações e compensação
  agent.py          agente de conferência (e heurístico opcional)
  llm.py            provedores de IA: Ollama, Claude, OpenAI e compatíveis, Gemini
  apikeys.py        chaves de API dos provedores na nuvem
  budget.py         teto de gastos: preço por modelo, contador e bloqueio das chamadas externas
  facts.py          modelo de leitura: fatos por caso, narrativas e painel
  embeddings.py     embeddings pelo provedor escolhido, modo simulado e busca vetorial
  indexer.py        serviço que indexa os eventos a partir do log
  ask.py            agente de perguntas em linguagem natural
  contracts.py      repositório versionado de contratos
  context.py        variáveis e funções disponíveis nas expressões dos contratos
  expr.py           avaliador seguro de expressões
  generators/       gerador de time e gerador de eventos e cenários
  seeds/contracts/  contratos de exemplo (YAML)
frontend/src/       interface React
docs/               documentação e decisões arquiteturais (ADRs)
```

Os valores de piso, VR, VA, PLR e demais parâmetros da CCT são **ilustrativos e fictícios**.
