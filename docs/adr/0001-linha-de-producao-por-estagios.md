# 0001. Linha de produção com seis estágios e uma fila por estágio

## Contexto

As operações de RH pedidas seguem a mesma lógica: um evento dispara, a elegibilidade é conferida, as operações são orquestradas e a execução é auditada. O laboratório precisa permitir observar cada passo, pausar, depurar e reprocessar, como numa linha de produção.

## Decisão

Todo evento vira um **caso** que percorre seis estágios fixos: gatilho, elegibilidade, planejamento, conferência do plano, execução e auditoria. Cada estágio tem a própria fila (`hr:stream:{estagio}`). Um worker consome a fila, executa o handler do estágio e publica o caso na fila seguinte, ou o deixa esperando (aprovação, agente, depuração), ou o finaliza com uma decisão explicada.

O que muda entre uma promoção e um desligamento não é a linha, e sim o **contrato de processo** que ela lê (ADR 0003).

## Alternativas consideradas

- **Um workflow por tipo de operação** (BPMN, Temporal, Step Functions). Dá mais flexibilidade de desenho, mas cada operação vira um fluxo diferente e a visão de linha de produção se perde. Também traz uma dependência pesada para um laboratório.
- **Uma fila única com o estágio dentro da mensagem.** É mais simples, mas impede pausar uma estação, medir o acúmulo por estágio e escalar consumidores por estágio.
- **Processamento síncrono numa requisição.** Não permite observar nem pausar, e acopla o tempo do agente de IA ao tempo de resposta da interface.

## Consequências

- A interface mostra uma estação por estágio, com a fila e os casos em cada uma.
- Pausar a linha ou uma estação é só parar de consumir; as mensagens acumulam visivelmente.
- Pontos de parada ("parar antes de") e o modo passo a passo são guardas no início de cada estágio.
- Reprocessar a partir de um estágio é recolocar o caso naquela fila, com o evento editado se for preciso.
- Novas etapas (por exemplo, uma notificação pós-auditoria) exigem código; novas operações de RH não.
