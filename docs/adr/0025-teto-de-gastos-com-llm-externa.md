# 0025. Teto de gastos com LLM externa e assistente "Ollama ou externo"

## Contexto

Fernando pediu, em 2026-10-21, que o laboratório use também LLMs externas (Anthropic, Google e OpenAI), que o primeiro acesso pergunte se a IA será Ollama ou externa e, se externa, configure modelo e chave de API, desenhe o teste da API e cadastre um teto de gastos. Ao exceder o teto, nenhuma chamada nova deve ser feita e uma mensagem de erro deve aparecer.

Os provedores externos já existiam (ADR 0021) e o assistente também (ADR 0022). Faltavam o controle de gastos, a pergunta explícita "Ollama ou externo" e um teste da API que mostre onde parou.

## Decisão

- **Custo por chamada.** Cada chamada externa (agentes, perguntas, embeddings e o teste do assistente) é precificada pelos tokens que o provedor informa vezes uma tabela de preço por modelo, em US$ por milhão de tokens (`budget.py`). A tabela vem com os preços de lista de 2026-10 e é editável na interface; um modelo fora da tabela usa o preço do modelo mais caro do mesmo provedor até alguém informar o preço. Quando o provedor não informa os tokens (Gemini em embeddings, servidores compatíveis sem `usage`), o custo é estimado pelo tamanho do texto e marcado como estimado.
- **Teto e preço opcionais** (pedido do Fernando em 2026-10-21). Configurações `spend_cap_usd` (padrão 0, sem teto), `spend_period` (`MENSAL`, padrão, zera todo dia 1 em UTC; ou `TOTAL`) e `spend_alert_percent` (padrão 80). Sem teto, o gasto só é contado e mostrado; nada é bloqueado. O preço da tabela já vem preenchido e só precisa ser informado para modelos fora dela ou com preço diferente.
- **Bloqueio antes de enviar (com teto).** `llm.py` consulta o razão antes de cada chamada externa, inclusive a listagem de modelos da verificação de saúde. Se o gasto do período mais a estimativa do prompt passar do teto, a chamada não é enviada: `BudgetExceeded`, que é um `AgentUnavailable`. Os casos ficam em "Aguardando agente de IA" como quando o provedor cai (ou o agente simulado responde, se ligado), o indexador espera e o agente de perguntas responde 503 com a mensagem.
- **Mensagem de erro.** O primeiro bloqueio de cada episódio grava uma entrada `GASTOS_LLM` no log e um aviso no log do processo; a interface mostra uma faixa vermelha no topo de todas as telas, o selo de gasto fica vermelho e o painel "Teto de gastos com LLM externa" em Configurações repete a mensagem. Passar do percentual de aviso também grava uma entrada no log.
- **Persistência.** Os contadores ficam em Redis (`hr:gastos:acum`, por período, provedor e modelo), com o histórico das últimas 5000 chamadas em `hr:gastos:log`. O Redis do compose usa AOF, então os gastos sobrevivem a reinícios; o "Reiniciar laboratório" não os apaga. Zerar o contador é uma ação explícita, registrada no log.
- **Assistente.** O passo 2 pergunta "Ollama, externo ou sem IA"; escolhido externo, aparecem Anthropic, Google Gemini e OpenAI. O passo 3 pede modelo e chave e desenha o teste da API como um fluxo de cinco etapas (chave, teto, conexão, modelo, chamada de teste), com o endereço de cada requisição, o tempo, os tokens e o custo do teste. O passo 4 permite, opcionalmente, cadastrar o teto, o período, o aviso e o preço do modelo escolhido, e mostra quantas auditorias típicas o teto cobre.
- O teste do assistente confere o teto com os valores digitados, mas não marca o laboratório como bloqueado, porque esses valores ainda não foram salvos.

## Alternativas consideradas

- **Consultar o faturamento do provedor.** Anthropic, OpenAI e Google têm APIs de custo, mas exigem chaves administrativas e respondem com atraso de minutos a horas; o bloqueio chegaria tarde.
- **Reservar o custo máximo de saída antes de cada chamada.** Evitaria passar do teto, mas com `max_tokens` de 16000 cada chamada reservaria até US$ 0,32 no Claude Opus 5.5 e bloquearia cedo demais com tetos pequenos.
- **Limite em tokens em vez de dinheiro.** Mais simples, mas o pedido foi um teto de gastos e o preço por token varia até cem vezes entre modelos.

## Consequências

- O gasto pode passar do teto pelas chamadas que já estavam em andamento quando ele foi atingido (no máximo `cloud_max_concurrency` por processo de worker). A primeira chamada seguinte já é recusada.
- O custo é uma estimativa do laboratório, não a fatura: cache de prompt, descontos e mudanças de preço do provedor não entram. Para um servidor compatível próprio (vLLM, LM Studio), cadastre preço zero para o modelo.
- O Ollama e o modelo JEV rodam localmente e nunca são precificados nem bloqueados.
