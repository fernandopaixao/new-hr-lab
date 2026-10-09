# 0007. Ollama local ou na rede, qwen2.5:7b, saída estruturada; espera quando indisponível

## Contexto

O agente de conferência deve usar IA e ser otimizado para trabalhar com Ollama, na máquina local ou na rede. Definido com o usuário: modelo qwen2.5:7b. Quando o Ollama estiver indisponível, o fluxo para e espera; um modo heurístico simulado pode ser ligado nas configurações.

## Decisão

- Chamada a `/api/chat` com `format` igual ao JSON Schema da resposta (saída estruturada), `temperature` 0 e `seed` fixo para reprodutibilidade, `num_ctx` e `num_predict` configuráveis e `keep_alive` para manter o modelo carregado.
- O prompt é compacto: o colaborador é resumido aos campos relevantes e as regras vêm agrupadas. Isso reduz tokens e tempo em CPU.
- Um semáforo limita as chamadas simultâneas por worker (padrão 1, adequado a uma GPU local).
- Respostas idênticas ficam em cache por 24 horas (hash do modelo mais o prompt).
- Um monitor verifica `/api/tags` a cada 10 segundos e aquece o modelo quando ele fica disponível.
- Indisponível: o caso vai para `AGUARDANDO_AGENTE` e volta à fila sozinho quando o Ollama responde. Com o modo simulado ligado, um agente heurístico responde e a decisão fica marcada como simulada.
- Resposta fora do formato: uma nova tentativa; depois disso, recomendação REPROVADO com o erro, o que leva à revisão humana.
- URL, modelo, tempo limite, contexto e concorrência são editáveis na interface. A tela de configurações também baixa os modelos.

## Alternativas consideradas

- **APIs de IA na nuvem.** Os dados de RH sairiam do ambiente, o que vai contra o pedido.
- **Fallback automático para heurística.** Esconde que a IA não participou da decisão. Por isso o fallback só existe quando é ligado explicitamente.

## Consequências

- O laboratório roda sem GPU, mas o qwen2.5:7b em CPU leva dezenas de segundos por chamada; modelos menores (qwen2.5:3b) são uma opção nas configurações.
- Em Linux, o Ollama da máquina precisa escutar em `0.0.0.0` para ser alcançado pelos containers.
