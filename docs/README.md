# Documentação do laboratório Novo RH

Esta pasta explica o propósito, o desenho e as decisões da arquitetura. Ela foi escrita para quem vai experimentar o laboratório, estender contratos e operações ou levar as ideias para um sistema real.

## Por onde começar

| Documento | Para quem | O que responde |
| --- | --- | --- |
| [Visão geral](visao-geral.md) | Todos | Qual problema o laboratório resolve, quais são os conceitos e como um evento atravessa a linha |
| [Arquitetura](arquitetura.md) | Arquitetos e desenvolvedores | Serviços, filas, armazenamento, fluxo de dados, concorrência, falhas e escala |
| [Decisões arquiteturais](adr/README.md) | Arquitetos | Por que cada escolha foi feita, quais alternativas foram descartadas e o que muda se a premissa mudar |
| [Contratos](contratos.md) | Quem modela regras de RH | Como escrever normas, políticas, contratos de cargo e de processo; vocabulário das expressões |
| [Prateleira de operações](prateleira.md) | Quem integra sistemas | Catálogo de operações, parâmetros, campos alterados e como criar uma nova |
| [Agentes de IA](agentes.md) | Quem opera ou ajusta a IA | Agente de conferência, agente de perguntas, embeddings, prompts, modo simulado e ajuste do Ollama |
| [Visibilidade](visibilidade.md) | Operação e gestão | Estratégia de observabilidade: painel, métricas, log de decisões, rastreio por caso e alertas |
| [Cenários](cenarios.md) | Quem testa | Os 47 cenários do gerador, com o resultado esperado de cada um |
| [Operação](operacao.md) | Quem roda o laboratório | Como subir, configurar o Ollama, escalar, estressar, depurar e resolver problemas |
| [API](api.md) | Integradores | Rotas HTTP agrupadas por assunto |
| [Glossário](glossario.md) | Todos | Termos de RH, de regulação e da arquitetura usados no laboratório |

## Aviso

Os valores de piso, benefícios, gratificações e demais parâmetros da CCT dos bancários usados nos contratos de exemplo são **ilustrativos e fictícios**. Eles servem para simular situações reais e não são referência jurídica.
