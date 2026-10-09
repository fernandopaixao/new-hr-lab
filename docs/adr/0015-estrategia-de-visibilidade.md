# 0015. Visibilidade por modelo de leitura, painel, métricas e rastro por caso

## Contexto

Fase 2, pedida pelo usuário depois da base: criar uma estratégia de visibilidade. Quem opera uma linha de eventos de RH precisa responder rapidamente onde as coisas param, por quê, quanto tempo levam e se a IA está ajudando ou atrapalhando.

## Decisão

A visibilidade tem quatro camadas, do detalhe ao agregado:

1. **Rastro por caso.** Na tela da linha, cada caso tem a trilha completa: estágios com tempo e worker, regras com explicação, plano, prompt e resposta do agente, recibos, compensações e aprovações. O `case_id` e o `evento_id` correlacionam tudo, inclusive o log.
2. **Log de decisões** (ADR 0011), filtrável e exportável.
3. **Modelo de leitura (`facts.py`).** Cada caso vira uma linha plana com tipo, status, colaborador, cargo, UF, tempos por estágio, regras que falharam, operações executadas, falhas, aprovações e recomendações. O painel e o agente de perguntas usam esses fatos, nunca o modelo de linguagem, para contar e agregar.
4. **Painel Visão e métricas.** O painel mostra:
   - KPIs: casos, em andamento, taxa de conclusão, tempo total p50 e p95, pendências, compensações, replanejamentos e latência do agente;
   - entradas e finalizações ao longo do tempo;
   - funil por estágio e tempo por estágio, com o gargalo destacado;
   - matriz de evento por situação;
   - regras que mais barram;
   - operações executadas, com falha e descartadas;
   - aprovações por persona;
   - concordância entre agente e regras;
   - estado do índice de embeddings.

   `GET /api/metrics` expõe o mesmo conteúdo em formato Prometheus, para Grafana ou qualquer coletor.
5. **Alertas calculados:** fila acumulada, casos esperando o Ollama, aprovação pendente há mais de 30 minutos, mais de 20% de falhas na última hora, agente reprovando o que as regras aprovam e colaboradores fora do estado alvo.

## Alternativas consideradas

- **Stack completa de observabilidade** (OpenTelemetry, Prometheus, Grafana, Loki) no compose. É o caminho de produção, mas quadruplica os serviços do laboratório. O endpoint Prometheus deixa a porta aberta sem impor a stack.
- **Painel calculado pelo LLM.** É lento e não confiável para números.

## Consequências

- O painel calcula a partir de todos os casos a cada requisição; é rápido para milhares de casos. Em produção, os fatos seriam materializados num banco analítico, atualizados pelo mesmo stream de log.
- **Em produção:** traces OpenTelemetry por estágio (o `case_id` como trace id), logs estruturados enviados ao coletor e SLOs por tipo de evento (o contrato de processo já tem `sla_horas` na auditoria).
