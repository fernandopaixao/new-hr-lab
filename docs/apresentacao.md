# Roteiro de apresentação

Guia para apresentar a solução a públicos diferentes. Cada roteiro diz a mensagem principal, o que mostrar no laboratório, quanto tempo leva e as perguntas que costumam aparecer. A demonstração interativa em [demo/index.html](demo/index.html) funciona sem o laboratório rodando e pode abrir qualquer apresentação.

## Preparação (10 minutos antes)

1. Suba o laboratório (`./scripts/install.sh` ou `docker compose up -d`) e abra http://localhost:8580.
2. Confira o selo "IA ok" no topo. Sem IA disponível, ligue o agente heurístico simulado em Configurações e avise que as decisões aparecem como simuladas.
3. Em Configurações, deixe o atraso visual em 700 ms (a linha fica fácil de acompanhar) e a injeção de falhas em 0.
4. Se a sala já viu o laboratório, use Configurações, Reiniciar laboratório, para começar limpo.
5. Deixe abertas as abas: Linha, Cenários, Aprovações, Visão e Perguntar.

## Mapa de documentos por público

| Público | Abrir primeiro | Depois |
| --- | --- | --- |
| Negócio (Pessoas, HRBP, folha, benefícios, jurídico, compliance) | [negocio.md](negocio.md) | [cenarios.md](cenarios.md), [glossario.md](glossario.md) |
| Times técnicos (desenvolvimento, integração, operação) | [arquitetura.md](arquitetura.md) | [contratos.md](contratos.md), [prateleira.md](prateleira.md), [api.md](api.md), [operacao.md](operacao.md), [agentes.md](agentes.md) |
| Segurança e privacidade | [seguranca.md](seguranca.md) | [ADR 0004](adr/0004-avaliador-de-expressoes-seguro.md), [ADR 0006](adr/0006-regras-decidem-ia-audita.md), [ADR 0009](adr/0009-personas-sem-autenticacao.md), [ADR 0021](adr/0021-provedores-de-llm-na-nuvem.md) |
| Arquitetura | [arquitetura.md](arquitetura.md#princípios-de-arquitetura) | [adr/README.md](adr/README.md), [visibilidade.md](visibilidade.md) |
| Todos, num único arquivo | [solucao-completa.md](solucao-completa.md) | |

## Negócio (30 minutos)

**Mensagem:** toda operação de RH passa pela mesma linha, que confere, planeja, audita antes de alterar, executa com garantia de desfazer e explica cada decisão. As regras são do RH, não do código.

| Minuto | O que mostrar | O que dizer |
| --- | --- | --- |
| 0 a 5 | Demo HTML, aba "Linha de produção" | O problema: regras espalhadas, exceções por e-mail, auditoria por amostragem |
| 5 a 10 | Cenários, "Promoção padrão"; acompanhar na Linha; abrir o caso | Estado alvo: o plano incluiu sozinho o plano de saúde do nível; auditoria antes da execução; parecer da IA; recibos |
| 10 a 15 | Cenários, "Promoção sem interstício"; trocar persona para HRBP; Aprovações | A regra diz quem aprova; justificativa obrigatória; próximo passo explícito |
| 15 a 18 | Cenários, "Desligamento de gestante" | Bloqueio pela estabilidade antes de qualquer sistema ser tocado |
| 18 a 22 | Contratos, política, mudar o interstício de 12 para 4 meses, salvar nova versão; repetir o cenário | Mudança de regra sem projeto de TI, com versão e vigência |
| 22 a 26 | Cenários, "Inclusão no programa de alto potencial"; Vigências, avançar "+1 ano" | Programas com prazo vencem sozinhos e retiram o que concediam |
| 26 a 30 | Visão e Perguntar: "quais regras mais barram promoções?" | Indicadores e respostas com números exatos e citações |

Perguntas comuns:

- *Quem mantém as regras?* O dono de cada contrato: jurídico para a norma, Pessoas para a política, remuneração para os cargos, operações para os processos.
- *A IA decide?* Não. Ela audita e recomenda; as regras e as pessoas decidem.
- *E se a regra estiver errada?* Muda-se o contrato numa nova versão; a anterior continua registrada e vale para eventos com data efetiva anterior.
- *Os valores da CCT são reais?* Não. São ilustrativos e fictícios.

## Times técnicos (45 minutos)

**Mensagem:** uma linha de seis estágios com fila por estágio, contratos como dados, uma prateleira de operações compensáveis e lógica de decisão pura e testável.

| Minuto | O que mostrar | O que dizer |
| --- | --- | --- |
| 0 a 8 | [arquitetura.md](arquitetura.md): serviços, módulos, fluxo de um evento | API sem estado, workers horizontais, indexador, Redis Streams com grupo de consumidores |
| 8 a 15 | Contratos, YAML do `PROC_PROMOCAO` | Regras com tipo e base legal; `orquestracao.operacoes` com `quando` e parâmetros por expressão; `derivar_estado_alvo` |
| 15 a 22 | Prateleira; execução avulsa de uma operação | Parâmetros, campos alterados, ordem e compensação; recibo com protocolo |
| 22 a 30 | Linha: "parar antes" da Execução; detalhe do caso, passo a passo, reprocessar com evento editado | Ferramentas de depuração |
| 30 a 37 | Cenários, "Falha no sistema de benefícios" (a falha vem no próprio cenário); depois, falhas injetadas em 5% em Configurações | Saga: compensação em ordem inversa, `FALHOU_COMPENSADO` |
| 37 a 42 | `docker compose up -d --scale worker=3`; rajada de 200 eventos; Visão | Escala horizontal, gargalo no agente, trava e replanejamento |
| 42 a 45 | `pytest -q tests` | 61 testes sem Redis e sem rede |

Perguntas comuns:

- *Como acrescentar um novo tipo de evento?* Novo contrato de processo com `evento`, `evento_schema`, `elegibilidade`, `orquestracao` e `auditoria`. Nenhuma mudança na linha.
- *Como integrar um sistema real?* Implementar a função da operação na prateleira contra o sistema, mantendo campos alterados e compensação. O plano e a auditoria não mudam.
- *E se um worker cair?* A mensagem fica pendente no grupo e o estágio é retomado quando ele volta; a guarda de obsolescência evita repetir estágios concluídos.
- *Por que Redis?* Um único componente para fila, documentos, log, pub/sub e índice ([ADR 0002](adr/0002-redis-como-armazenamento-unico.md)). Em produção, a troca está descrita em [arquitetura.md](arquitetura.md#caminho-para-produção).

## Segurança (30 minutos)

**Mensagem:** as decisões são protegidas por desenho; o acesso não, porque é um laboratório. A lista de lacunas e o caminho para produção estão escritos.

| Minuto | O que mostrar | O que dizer |
| --- | --- | --- |
| 0 a 5 | [seguranca.md](seguranca.md), postura e ativos | Laboratório com dados fictícios, sem login por decisão |
| 5 a 12 | Contratos: tentar salvar uma expressão com `__import__` ou `lambda` | O avaliador recusa; não há `eval` |
| 12 a 18 | Detalhe de um caso, aba do agente: prompt e resposta bruta | Minimização de dados; IA não decide; parecer gravado |
| 18 a 22 | Configurações, provedor de IA: chave aparece só com os quatro últimos caracteres; com o PR #8 mergeado, o teto de gastos opcional e a faixa de bloqueio | Chave fora do Redis, do log e da API; custo da IA externa sob controle |
| 22 a 27 | Log: filtro por `APROVACAO_DECIDIDA` e `CONTRATO_ALTERADO`; exportar JSONL | Rastreabilidade de quem decidiu e alterou o quê |
| 27 a 30 | Tabela de lacunas e caminho para produção | SSO, TLS, CORS, cofre, egress da IA, log imutável |

## Arquitetura (45 minutos)

**Mensagem:** a linha separa decidir, planejar, auditar e executar; os contratos separam o comportamento do código; a IA entra como auditora medida, com provedor e motor trocáveis.

| Minuto | O que mostrar | O que dizer |
| --- | --- | --- |
| 0 a 10 | Princípios e visão de contexto em [arquitetura.md](arquitetura.md#princípios-de-arquitetura) | Uma linha, muitos processos; plano derivado do estado alvo |
| 10 a 20 | [ADRs 0001, 0003, 0005, 0006, 0018](adr/README.md) | Por que auditar antes de executar; por que regras decidem |
| 20 a 28 | Atributos de qualidade e trade-offs | Onde Redis e fatos por requisição deixam de servir |
| 28 a 36 | Tela Desempenho com comparação Qwen e JEV ligada | Medir concordância e latência antes de trocar de motor |
| 36 a 45 | Caminho para produção | Identidade, armazenamento, mensageria, integrações, observabilidade |

## Encerramento sugerido

1. Recapitular o fluxo: evento, gatilho, elegibilidade, planejamento, auditoria, execução, conferência final.
2. Mostrar a lista de 54 cenários e o resultado da suíte completa.
3. Propor o piloto descrito em [negocio.md](negocio.md#próximos-passos-sugeridos-para-um-piloto).
