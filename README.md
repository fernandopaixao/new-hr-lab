# Novo RH: laboratório de eventos

Laboratório para criar, demonstrar, experimentar e estressar uma arquitetura de operações de RH orientada a eventos.

Toda operação de RH segue a mesma linha de produção:

```
evento -> gatilho -> elegibilidade -> planejamento -> conferência do plano -> execução (saga) -> auditoria
```

- **Eventos** (promoção, admissão, transferência, desligamento, reajuste da CCT, etc.) bastam para disparar e alimentar o fluxo inteiro.
- **Contratos** versionados e com vigência descrevem as regras:
  - **norma**: CLT e CCT dos bancários, com valores ilustrativos e fictícios;
  - **política** interna;
  - **cargo**: estado alvo e compliance de cada posição, como garden leave para executivos e celular corporativo para a média gerência;
  - **processo**: elegibilidade, orquestração, conferência e auditoria.
- **Prateleira de serviços**: operações desacopladas e parametrizáveis que qualquer processo pode chamar, como adicionar benefício, alterar salário, incluir verba de bônus ou revogar acesso.
- **Agente de conferência com IA (Ollama)**: audita o plano e a execução e sempre dá uma recomendação clara, APROVADO ou REPROVADO, com justificativa. Regras determinísticas decidem; o agente é a segunda linha de defesa.
- **Aprovações de exceção** por persona, com justificativa registrada.
- **Log de decisões** explica por que uma operação foi escolhida ou descartada, por que alguém não é elegível e quem aprovou o quê.
- **Visibilidade**: painel com funil, gargalos, regras que mais barram, aprovações e concordância entre agente e regras, além de métricas Prometheus.
- **Embeddings de todos os eventos** (`nomic-embed-text`) e um **agente de perguntas em linguagem natural**, que responde com números exatos e cita os casos.

A documentação completa, com as decisões arquiteturais, está em [docs/](docs/README.md).

## Como rodar

Pré-requisitos: Docker com Compose 2.24 ou mais novo. O Ollama é opcional: o instalador usa o da máquina, um da rede ou sobe um em container.

```bash
./scripts/install.sh            # Linux e macOS
```

```powershell
scripts\install.cmd             # Windows (ou .\scripts\install.ps1)
```

O instalador confere os pré-requisitos, encontra o Ollama, testa se os containers o alcançam, grava o `.env`, baixa os modelos, sobe o laboratório e confere a IA de dentro da API. Ao final, abra http://localhost:8580. Com `--sim` (ou `-Sim` no Windows) ele não faz perguntas; `--ajuda` lista as opções. Os detalhes estão em [docs/operacao.md](docs/operacao.md#instalador).

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

Se o Ollama estiver fora do ar, os casos param em "Aguardando agente de IA" e são retomados sozinhos quando ele volta. Para demonstrações sem IA, ligue o agente heurístico simulado em Configurações ou use `HEURISTIC_FALLBACK_ENABLED=true`. Toda decisão desse agente fica marcada como simulada.

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
| Visão | Painel de visibilidade: KPIs, alertas, linha do tempo, funil, tempo por estágio, evento por situação, regras que mais barram, operações, aprovações, agente e índice. |
| Perguntar | Perguntas em linguagem natural sobre todos os eventos, busca semântica e histórico. Cada resposta mostra a interpretação, os números exatos e as fontes. |
| Cenários | 47 cenários reais, de exceção, de bloqueio, coletivos e de estresse, cada um com o resultado esperado. Também traz a suíte completa com comparação entre esperado e obtido, evento manual e rajada. |
| Aprovações | Exceções de elegibilidade e revisões humanas do plano e da auditoria. Troque a persona no topo para decidir como HRBP, Jurídico, Compliance, Comitê e outras. |
| Colaboradores | Time artificial: edite cargo, datas, salário, conduta, estabilidades e dependentes; injete desvios; confira a conformidade; dispare eventos. |
| Contratos | Editor estruturado e YAML para incluir ou remover regras e operações, mudar vigências e salvar como nova versão. |
| Prateleira | Catálogo de operações, com execução avulsa ou simulada. |
| Log | Todas as decisões e alterações, com filtro e exportação em JSONL. |
| Configurações | Parâmetros do Ollama, modelos de embedding e de perguntas, modo de revisão humana, atraso visual, injeção de falhas e reinício do laboratório. |

## Desenvolvimento local

```bash
# backend (requer Redis em localhost:6379)
cd backend && pip install -r requirements.txt -r requirements-dev.txt
python -m hrlab.worker &
python -m hrlab.indexer &
uvicorn hrlab.api:app --reload --port 8000
python -m pytest -q tests      # 27 testes, sem Redis e sem Ollama

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
  agent.py          agente de conferência com Ollama (e heurístico opcional)
  facts.py          modelo de leitura: fatos por caso, narrativas e painel
  embeddings.py     embeddings via Ollama, modo simulado e busca vetorial
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
