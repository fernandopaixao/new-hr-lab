# Decisões arquiteturais (ADR)

Cada registro segue o mesmo formato: contexto, decisão, alternativas consideradas e consequências. As decisões marcadas como "definida com o usuário" foram respondidas por Fernando no início do projeto; as demais foram tomadas durante a implementação para atender a essas respostas.

| Nº | Decisão | Origem |
| --- | --- | --- |
| [0001](0001-linha-de-producao-por-estagios.md) | Linha de produção com seis estágios e uma fila por estágio (ordem atualizada pela 0018) | desenho |
| [0002](0002-redis-como-armazenamento-unico.md) | Redis como fila, armazenamento, log, pub/sub e índice | definida com o usuário (filas) |
| [0003](0003-contratos-versionados.md) | Contratos versionados em YAML, em quatro tipos, com vigência | desenho |
| [0004](0004-avaliador-de-expressoes-seguro.md) | Regras como expressões avaliadas por um interpretador seguro | desenho |
| [0005](0005-prateleira-e-plano-derivado.md) | Prateleira desacoplada e plano derivado do estado alvo | desenho |
| [0006](0006-regras-decidem-ia-audita.md) | Regras determinísticas decidem; o agente de IA audita e sempre recomenda | definida com o usuário |
| [0007](0007-ollama-local-e-espera.md) | Ollama local ou na rede, qwen2.5:7b, saída estruturada; espera quando indisponível (nuvem revista pela 0021) | definida com o usuário |
| [0008](0008-saga-com-compensacao.md) | Execução em saga com compensação por snapshot | definida com o usuário |
| [0009](0009-personas-sem-autenticacao.md) | Aprovações por persona, sem login, sempre registradas | definida com o usuário |
| [0010](0010-concorrencia-trava-e-versao.md) | Trava por colaborador, versão do cadastro e replanejamento | desenho |
| [0011](0011-log-de-decisoes-explicado.md) | Log append-only com explicação de cada decisão | definida com o usuário |
| [0012](0012-dados-sinteticos-e-ficticios.md) | Times e eventos sintéticos; valores da CCT ilustrativos | definida com o usuário |
| [0013](0013-fastapi-react-sse.md) | FastAPI, React com Vite e atualizações por SSE | definida com o usuário |
| [0014](0014-idioma-e-sem-emoji.md) | Domínio em português, código em inglês, nenhum emoji | definida com o usuário |
| [0015](0015-estrategia-de-visibilidade.md) | Visibilidade por modelo de leitura, painel, métricas e rastro por caso | fase 2 |
| [0016](0016-embeddings-de-todos-os-eventos.md) | Embeddings de todos os eventos com indexador dedicado e busca exata | fase 2 |
| [0017](0017-agente-de-linguagem-natural.md) | Agente de linguagem natural em três etapas, com números exatos e citações | fase 2 |
| [0018](0018-auditoria-antes-da-execucao.md) | Auditoria antes da execução e conferência final depois | pedida pelo usuário |
| [0019](0019-hierarquia-e-gestor-imediato.md) | Hierarquia por gestor imediato, usada nas regras e nas aprovações | pedida pelo usuário |
| [0020](0020-proximo-passo-explicito.md) | Próximo passo explícito em cada fase | pedida pelo usuário |
| [0021](0021-provedores-de-llm-na-nuvem.md) | Provedores de LLM na nuvem (Claude, OpenAI e compatíveis, Gemini) ao lado do Ollama | pedida pelo usuário |
| [0022](0022-assistente-de-configuracao-inicial.md) | Assistente de configuração inicial na interface | pedida pelo usuário |
| [0023](0023-eventos-com-vigencia.md) | Eventos com vigência (programa de alto potencial), agenda derivada e relógio simulado | pedida pelo usuário |
| [0024](0024-motor-jev-e-painel-de-desempenho.md) | Motor JEV (modelo de decisão tev1:0.8b) ao lado do Qwen e painel de desempenho dos agentes | pedida pelo usuário |
| [0025](0025-teto-de-gastos-com-llm-externa.md) | Teto de gastos com LLM externa, bloqueio antes da chamada e assistente "Ollama ou externo" | pedida pelo usuário |
