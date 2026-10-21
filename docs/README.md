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
| [Agentes de IA](agentes.md) | Quem opera ou ajusta a IA | Agente de conferência, agente de perguntas, embeddings, provedores de IA (Ollama, Claude, OpenAI, Gemini), prompts, modo simulado e ajustes |
| [Visibilidade](visibilidade.md) | Operação e gestão | Estratégia de observabilidade: painel, métricas, log de decisões, rastreio por caso e alertas |
| [Cenários](cenarios.md) | Quem testa | Os 54 cenários do gerador, com o resultado esperado de cada um |
| [Operação](operacao.md) | Quem roda o laboratório | Como instalar com os scripts, usar o assistente de configuração, configurar o Ollama ou um provedor na nuvem, escalar, estressar, depurar e resolver problemas |
| [API](api.md) | Integradores | Rotas HTTP agrupadas por assunto |
| [Glossário](glossario.md) | Todos | Termos de RH, de regulação e da arquitetura usados no laboratório |

## Para apresentar a solução

| Documento | Para quem | O que responde |
| --- | --- | --- |
| [Documento completo](solucao-completa.md) | Todos | Tudo o que é relevante num único arquivo: valor, conceitos, linha, contratos, prateleira, IA, vigências, visibilidade, arquitetura, segurança, operação, API, ADRs e caminho para produção |
| [Demonstração interativa](demo/index.html) | Todos | Página HTML que funciona sem o laboratório: linha ao vivo com cenários, conceitos e onde são aplicados, regras, estado alvo, IA, vigências, arquitetura e segurança |
| [Negócio](negocio.md) | Pessoas, HRBP, folha, benefícios, jurídico, compliance | Problema, capacidades, exemplos, papéis, indicadores, benefícios e piloto |
| [Segurança](seguranca.md) | Segurança da informação e privacidade | Ativos, controles, lacunas aceitas, ameaças, LGPD e endurecimento para produção |
| [Roteiro de apresentação](apresentacao.md) | Quem apresenta | Roteiros cronometrados por público e perguntas frequentes |

A [Arquitetura](arquitetura.md) também traz princípios, visão de contexto, atributos de qualidade, trade-offs e caminho para produção.

## Aviso

Os valores de piso, benefícios, gratificações e demais parâmetros da CCT dos bancários usados nos contratos de exemplo são **ilustrativos e fictícios**. Eles servem para simular situações reais e não são referência jurídica.
