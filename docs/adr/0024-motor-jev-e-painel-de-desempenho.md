# 0024. Motor JEV ao lado do Qwen e painel de desempenho dos agentes

## Contexto

Fernando pediu uma versão paralela à atual, otimizada para funcionar com JEV na classificação de elegibilidade e na auditoria dos eventos, com a escolha entre Qwen e JEV nas configurações e um painel com o tempo médio de processamento dos agentes, histórico, que mostre a performance de um e de outro.

JEV é o estilo de modelo de decisão que o Ollama passou a servir na versão 0.35 (post "Ollama now supports JEV-style decision models"). O modelo pedido é o `tev1:0.8b` (Tev1 com 0,8 bilhão de parâmetros, experimental). Um modelo de decisão não escreve texto: recebe textos nomeados (`state`) e perguntas nomeadas (`questions`) no endpoint `POST /v1/systemone` e responde todas as perguntas numa só chamada, com uma probabilidade para cada opção. Os tipos de pergunta são `choice` (opções com descrição), `noul` (sim ou não, respondida com uma probabilidade) e `score` (rótulos ordenados).

## Decisão

- **Motor plugável, mesma linha de produção.** A "versão paralela" é um segundo motor dos agentes dentro do mesmo laboratório, escolhido em `agent_engine` (`qwen` ou `jev`), e não um fork nem outro serviço. A linha, os contratos, as regras e as aprovações são os mesmos; só muda quem recomenda.
  - `qwen`: o agente generativo de antes, no provedor configurado (ADR 0021), `qwen2.5:7b` no Ollama por padrão.
  - `jev`: o modelo de decisão `jev_model` (`tev1:0.8b` por padrão) no Ollama de `jev_base_url` (vazio usa `ollama_base_url`), módulo `engines.py`.
- **As regras continuam decidindo (ADR 0006).** Os dois motores recomendam. Nada no fluxo de aprovações mudou.
- **Classificação de elegibilidade pelo agente.** Nova tarefa `ELEGIBILIDADE`, ligada por `agent_eligibility_enabled` (padrão ligado), com as classes do motor de regras (`ELEGIVEL`, `EXCECAO_NECESSARIA`, `NAO_ELEGIVEL`). É consultiva: a decisão é das regras; quando o agente diverge, o log registra e o caso mostra o aviso. Com a IA fora do ar o caso aguarda, como na auditoria.
- **Como o JEV foi otimizado.** Em vez de um prompt JSON grande, cada tarefa manda poucos textos curtos (evento, colaborador, plano, regras em uma linha cada) e um conjunto fixo de perguntas:
  - o veredito é uma pergunta `choice` com as mesmas opções que a linha usa;
  - cada verificação que o agente generativo escreveria como achado (violação legal, operação obrigatória ausente, redução salarial, acesso indevido, recibo ausente, estado divergente, restrição de conduta) é uma pergunta `noul`; probabilidade de 50% ou mais vira achado com severidade e referência fixas;
  - o risco é uma pergunta `score` com quatro rótulos (baixo, médio, alto, crítico).
  O resumo e a justificativa são escritos pelo laboratório a partir das probabilidades, então toda decisão continua explicada no log. Uma resposta sem todas as perguntas, ou com opção fora da lista, conta como resposta inválida (nova tentativa e depois revisão humana).
- **Comparação opcional.** Com `agent_compare_enabled` (padrão desligado) o outro motor responde a mesma tarefa logo depois do motor ativo, sem decidir. Falha do motor de comparação nunca para o caso. O resultado aparece no caso como "Comparação com JEV (não decide)". Fica desligado por padrão porque soma o tempo do segundo motor a cada estágio com agente, o que pesa quando o Qwen roda numa GPU local.
- **Uma medição por chamada.** Cada chamada de agente, dos dois motores, grava um registro no stream Redis `hr:metrics:agent` (até 200 mil registros, os mais antigos saem primeiro): motor, papel (ativo ou comparação), tarefa, caso, modelo, tempos, tokens, tentativas, cache, erro, veredito do agente e veredito das regras. O stream não é apagado ao reiniciar o laboratório; tem botão próprio de limpeza.
  - `resposta_ms`: só a chamada ao modelo (da requisição até a resposta);
  - `espera_ms`: espera por vaga no semáforo de concorrência do provedor;
  - `processamento_ms`: a tarefa inteira do agente (contexto, espera, novas tentativas, leitura e normalização).
  Respostas do cache, do agente simulado e chamadas com erro não entram nas médias; aparecem como contagens.
- **Painel Desempenho.** Nova tela com período e intervalo escolhíveis: cartões lado a lado por motor (média, p50, p95, mín., máx., espera, tokens, confiança, erros, concordância com as regras), gráfico do histórico por motor, tempo por tarefa, concordância Qwen x JEV nos mesmos casos (por tarefa, quem foi mais rigoroso, divergências recentes com link para o caso) e as últimas chamadas. A rota `/api/metrics/agentes` entrega os mesmos números, e `/api/metrics` (Prometheus) ganhou `hrlab_agent_processing_ms` e `hrlab_agent_response_ms` por motor.
- **Saúde.** Quando o JEV é o motor ativo, o indicador "IA ok" e a retomada dos casos que aguardam o agente seguem o modelo de decisão; a saúde do provedor generativo continua visível nas configurações, porque o agente de perguntas e os embeddings seguem nele.

## Alternativas consideradas

- **Uma segunda aplicação ou um fork só com JEV.** Duplicaria contratos, linha e interface, e a comparação exigiria juntar dados de dois sistemas.
- **Usar o JEV pelo endpoint de chat com JSON Schema.** O modelo de decisão é feito para perguntas tipadas com probabilidades; tratá-lo como gerador de texto perderia justamente a velocidade e as probabilidades.
- **Deixar o JEV decidir a elegibilidade.** Contraria a ADR 0006 e o modelo é experimental; a divergência fica medida para Fernando avaliar.
- **Calcular as métricas a partir dos casos.** Os casos são apagados ao reiniciar o laboratório e só guardam a última chamada de cada estágio; o histórico pedido precisa de um registro por chamada que sobreviva.
- **Prometheus e Grafana como painel.** Continuam possíveis pela rota de métricas, mas exigiriam mais containers para responder a uma pergunta que o laboratório já sabe responder.

## Consequências

- O JEV exige Ollama 0.35 ou mais novo e o modelo baixado (`ollama pull tev1:0.8b`, ou o botão "Baixar modelo JEV"). Sem o endpoint, a mensagem diz para atualizar o Ollama.
- A resposta do JEV não tem texto livre; a justificativa mostra as probabilidades e os achados vêm de verificações fixas. Achados fora dessas verificações só o Qwen encontra.
- Com a classificação de elegibilidade ligada, cada caso faz uma chamada de agente a mais. Pode ser desligada nas configurações.
- O cache de respostas passou a separar motor e tarefa na chave; as auditorias do Qwen já guardadas continuam valendo.
