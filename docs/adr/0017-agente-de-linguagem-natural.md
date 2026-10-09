# 0017. Agente de linguagem natural em três etapas, com números exatos e citações

## Contexto

Fase 2: um agente de linguagem natural baseado nos eventos da solução. Perguntas típicas misturam contagem ("quantas promoções foram barradas?"), agrupamento ("quais regras mais barram?"), explicação ("o que aconteceu com os desligamentos de executivos?") e desempenho ("qual estágio está mais lento?"). Modelos locais de 7B erram contas e inventam detalhes quando recebem dados demais.

## Decisão

Separar o que o modelo faz bem do que o código faz bem, em três etapas registradas no rastro da resposta:

1. **Interpretação.** O modelo transforma a pergunta numa consulta estruturada (JSON Schema): intenção (contagem, agrupamento, lista, busca, explicação de caso ou desempenho), filtros, campo de agrupamento, id de caso e uma frase para a busca semântica. O prompt traz o catálogo do laboratório (tipos de evento, status, personas, cargos, UFs, regras que já falharam). A consulta é **sanitizada**: valores fora do catálogo são descartados.
2. **Recuperação determinística.** Filtros e agregações rodam sobre os fatos (ADR 0015) e produzem números exatos. Em seguida, a busca semântica (ADR 0016) traz os eventos mais parecidos, respeitando os filtros.
3. **Resposta.** O modelo escreve a resposta **apenas a partir das evidências** (estatísticas e documentos), cita os casos usados e declara limitações. As citações são validadas: ids que não estavam nas evidências são descartados e mostrados como tal. Emoji são removidos.

Sem Ollama, a pergunta é recusada com uma mensagem clara, a menos que o modo simulado esteja ligado. Nesse caso, um interpretador por palavras-chave e uma resposta por modelo de texto respondem, marcados como simulados. As últimas 50 perguntas ficam no histórico.

## Alternativas consideradas

- **RAG puro** (só busca semântica e resposta). Responde mal a perguntas de contagem e agregação, que são a maioria das perguntas operacionais.
- **Text-to-SQL ou geração de código.** É poderoso, mas exigiria um banco relacional e executar código gerado, um risco desproporcional para o laboratório.
- **Agente com várias chamadas de ferramentas.** Modelos 7B locais seguem mal cadeias longas de ferramentas; duas chamadas estruturadas são mais previsíveis e baratas.

## Consequências

- Os números da resposta sempre batem com o painel, porque vêm do mesmo modelo de leitura.
- A tela Perguntar mostra as fontes, os números exatos, como a pergunta foi entendida e o rastro completo (prompts, respostas brutas, tempos), o que permite depurar o agente.
- A qualidade das explicações depende do modelo. `ask_model` permite usar um modelo maior só para perguntas, mantendo o modelo de conferência.
