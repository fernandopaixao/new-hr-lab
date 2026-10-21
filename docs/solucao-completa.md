# Novo RH: documento completo da solução

Documento único com tudo o que é relevante para apresentar, avaliar, operar e evoluir a solução. Serve a áreas de negócio, times técnicos, segurança e arquitetura. Os documentos específicos da pasta `docs/` aprofundam cada tema e estão indicados em cada seção.

Estado descrito: branch principal do repositório em 21/10/2026, com as entregas de 1 a 7 incorporadas (linha de produção, visibilidade e perguntas, instaladores, auditoria antes da execução, hierarquia, provedores de IA na nuvem com assistente inicial, eventos com vigência, motor JEV e painel de desempenho). O PR #8 (assistente "Ollama, externo ou sem IA", teste da API em cinco etapas e teto de gastos opcional com LLM externa) ainda não foi incorporado e está descrito à parte, na [seção 18](#pendente-de-merge-pr-8).

## Sumário

1. [Resumo executivo](#1-resumo-executivo)
2. [Problema e proposta de valor](#2-problema-e-proposta-de-valor)
3. [Conceitos](#3-conceitos)
4. [A linha de produção](#4-a-linha-de-produção)
5. [Contratos](#5-contratos)
6. [Prateleira de operações](#6-prateleira-de-operações)
7. [Aprovações, personas e hierarquia](#7-aprovações-personas-e-hierarquia)
8. [Agentes de IA](#8-agentes-de-ia)
9. [Eventos com vigência](#9-eventos-com-vigência)
10. [Visibilidade, log e perguntas](#10-visibilidade-log-e-perguntas)
11. [Cenários e dados sintéticos](#11-cenários-e-dados-sintéticos)
12. [Interface](#12-interface)
13. [Arquitetura técnica](#13-arquitetura-técnica)
14. [Segurança e privacidade](#14-segurança-e-privacidade)
15. [Operação](#15-operação)
16. [API](#16-api)
17. [Decisões arquiteturais](#17-decisões-arquiteturais)
18. [Limites, riscos e caminho para produção](#18-limites-riscos-e-caminho-para-produção)
19. [Glossário essencial](#19-glossário-essencial)
20. [Mapa: conceito, onde é aplicado e onde ver](#20-mapa-conceito-onde-é-aplicado-e-onde-ver)

---

## 1. Resumo executivo

Novo RH é um laboratório funcional de uma arquitetura de operações de RH orientada a eventos. Qualquer operação (promoção, admissão, transferência, desligamento, afastamento, bônus, reajuste da convenção coletiva, programas com prazo) é um **evento** que atravessa a mesma **linha de produção** de seis estágios:

```
evento -> gatilho -> elegibilidade -> planejamento -> auditoria -> execução (saga) -> conferência final
```

- O comportamento de cada operação está em **contratos** versionados e com vigência (norma, política, cargo e processo), não no código.
- O que muda nos sistemas é feito por **operações** reutilizáveis de uma **prateleira**, com recibo e compensação.
- O plano é **derivado do estado alvo** do cargo: o que o cargo exige e a pessoa não tem entra no plano sozinho.
- A **auditoria acontece antes da execução**, sobre um estado projetado; a **conferência final** prova que o executado é igual ao auditado.
- **Regras determinísticas decidem**; um **agente de IA** audita e sempre recomenda APROVADO ou REPROVADO com justificativa. Divergência vai para pessoas.
- **Exceções** são decididas por personas (HRBP, Jurídico, Compliance, Auditoria, Comitê, Gestor imediato real), com justificativa registrada.
- Tudo vai para um **log de decisões** append-only que alimenta painel, métricas, índice vetorial e um **agente de perguntas em linguagem natural** com números exatos e citações.

Stack: Python (FastAPI) e React (Vite), Redis Streams, Ollama local por padrão (Claude, OpenAI e Gemini opcionais), tudo em Docker Compose, com instaladores para Linux, macOS e Windows. Dados sintéticos de um banco; valores da CCT dos bancários ilustrativos e fictícios.

## 2. Problema e proposta de valor

### O problema

Boa parte das operações de RH segue o mesmo roteiro: algo acontece; alguém confere se é permitido (tempo no cargo, conduta, formação, estabilidade, CLT, CCT); vários sistemas são alterados (cargo, salário, benefícios, acessos, equipamentos, eSocial); alguém confere se tudo foi feito. Em sistemas tradicionais esse roteiro fica espalhado: regras no código e na cabeça de especialistas, exceções em e-mails, integrações ponto a ponto, auditoria por amostragem meses depois.

### A proposta

| Dor | Resposta da solução |
| --- | --- |
| Regras escondidas | Contratos legíveis, versionados, com base legal e frase de explicação |
| Fluxos diferentes por operação | Uma linha para todas as operações |
| Exceções sem rastro | A regra diz quem aprova; justificativa obrigatória; log |
| Auditoria tardia | Auditoria de 100% dos casos antes de alterar qualquer sistema |
| Itens esquecidos | Plano derivado do estado alvo do cargo |
| Falha deixa sistemas inconsistentes | Saga com compensação; reversão completa após conferência reprovada |
| "Por que não fui promovido?" | Cada regra explica o valor encontrado e o exigido |
| Programas que vencem sem controle | Agenda de vigências com aviso e vencimento pela linha |
| IA como caixa-preta | IA auditora, com prompt e resposta gravados, sem poder de decisão |

### Benefícios para o negócio

- Redução de passivo trabalhista (estabilidades, irredutibilidade, jornada e base sindical conferidas sempre).
- Menos retrabalho (benefícios, acessos e equipamentos derivados do cargo).
- Agilidade para mudar regra (nova versão com vigência, sem projeto de TI).
- Governança de exceções (dono, justificativa e indicador).
- Auditoria contínua e consultável.
- Uso responsável de IA.

Detalhes: [negocio.md](negocio.md).

## 3. Conceitos

| Conceito | Definição | Onde está |
| --- | --- | --- |
| Evento | Fato de negócio com tipo, colaborador, data efetiva e dados; basta para disparar e alimentar o fluxo | `POST /api/events`, tela Cenários, gerador |
| Caso | Registro do evento na linha: estágio, decisões, plano, recibos, aprovações, auditoria, trilha, próximo passo | `hr:case:*`, Detalhe do caso |
| Data efetiva | Data em que o evento produz efeito; escolhe as versões de contrato vigentes e é o "hoje" das regras | Evento |
| Contrato | Documento versionado com vigência: norma, política, cargo ou processo | `seeds/contracts/*.yaml`, tela Contratos |
| Regra | Expressão que deve ser verdadeira, com tipo (BLOQUEANTE, EXCECIONAVEL, ALERTA), aprovadores, base legal e explicação | Contratos |
| Estado alvo | Como deve estar quem ocupa o cargo, somado à norma e ajustado pela situação do vínculo | `engine.target_state` |
| Desvio | Diferença entre o cadastro e o estado alvo | Tela Colaboradores |
| Prateleira | Catálogo de operações desacopladas, parametrizáveis e compensáveis | `shelf.py`, tela Prateleira |
| Plano | Operações escolhidas (explícitas e derivadas) com motivo e base legal, e descartadas com explicação | Detalhe do caso |
| Estado projetado | Cópia do colaborador com o plano aplicado em simulação; é o que a auditoria avalia | Detalhe do caso |
| Saga | Execução passo a passo com compensação dos passos anteriores em caso de falha | `pipeline.py`, `shelf.py` |
| Recibo | Comprovante de operação executada: protocolo, sistema, antes e depois | Detalhe do caso |
| Persona | Papel que decide aprovações; sem login | Seletor no topo |
| Próximo passo | O que acontece agora e quem precisa agir | Cartões da Linha, Detalhe do caso |
| Agente de conferência | Modelo de IA que classifica a elegibilidade (consultiva), audita o plano e confere a execução | `agent.py`, `engines.py` |
| Programa com vigência | Participação com prazo (alto potencial, 12 meses) cujas concessões entram no estado alvo enquanto ativo | `vigencia.py`, tela Vigências |
| Relógio simulado | Data de negócio que pode ser avançada para testar prazos | `clock.py`, tela Vigências |
| Log de decisões | Registro append-only de tudo o que foi decidido e por quê | `hr:log`, `audit-log.jsonl`, tela Log |
| Fatos | Linha plana por caso, usada para contar e agregar | `facts.py` |
| Embedding | Vetor que representa o significado de um texto, para busca por semelhança | `embeddings.py`, `indexer.py` |

## 4. A linha de produção

### Estágios

| Estágio | Chave | O que faz | Saídas possíveis |
| --- | --- | --- | --- |
| Gatilho | `intake` | Idempotência, contrato de processo vigente na data efetiva, validação do esquema, existência do colaborador; eventos coletivos geram casos filhos | segue, `REJEITADO_NA_ENTRADA`, `DUPLICADO` |
| Elegibilidade | `eligibility` | Regras do processo e regras de entrada do cargo alvo; classificação consultiva pela IA | `ELEGIVEL`, `EXCECAO_NECESSARIA` (aprovação), `NAO_ELEGIVEL` |
| Planejamento | `planning` | Estado alvo, operações explícitas do processo, operações derivadas da diferença, descartes explicados | plano |
| Auditoria | `audit` | Aplica o plano em simulação; avalia regras do plano, verificações do contrato de serviço, compliance da norma e do cargo, estado alvo; parecer da IA | segue, revisão humana, `REJEITADO` |
| Execução | `execution` | Operações em ordem, com recibo; trava por colaborador; versão do cadastro; saga | segue, `FALHOU_COMPENSADO`, replanejamento |
| Conferência final | `verification` | Todas as operações com recibo; estado final igual ao projetado; IA confere | `CONCLUIDO`, `CONCLUIDO_COM_RESSALVAS`, auditoria interna, `REVERTIDO` |

### Status de um caso

Ativos: `NA_FILA`, `PROCESSANDO`, `PARADO` (breakpoint ou passo a passo), `AGUARDANDO_APROVACAO`, `AGUARDANDO_AGENTE`.
Finais: `CONCLUIDO`, `CONCLUIDO_COM_RESSALVAS`, `NAO_ELEGIVEL`, `REJEITADO`, `REJEITADO_NA_ENTRADA`, `DUPLICADO`, `FALHOU_COMPENSADO`, `ERRO`, `CANCELADO`, `REVERTIDO`.

### Exemplo: promoção de analista júnior para pleno

1. Gatilho: `colaborador.promovido` com `cargo_destino` e `novo_salario`; idempotência; contrato `PROC_PROMOCAO` vigente; esquema válido; colaborador existe.
2. Elegibilidade: situação ativa, interstício, avaliação, conduta, irredutibilidade, limite de aumento e regras de entrada do cargo destino.
3. Planejamento: estado alvo do analista pleno; alterar cargo, alterar salário (maior entre proposto, atual e mínimo da faixa), eSocial S-2206; derivadas, como trocar o plano de saúde de BASICO para PRATA.
4. Auditoria: plano aplicado em cópia; regras e verificações sobre o estado projetado; parecer da IA.
5. Execução: operações em ordem com recibos; falha compensa.
6. Conferência final: recibos completos e estado final igual ao projetado.

Resultado: "Concluído. Execução igual à auditada e com recibos; agente recomenda APROVADO."

### Decisão combinada de regras e agente (auditoria)

| Regras | Agente | Modo `SE_REPROVADO` (padrão) | Modo `SEMPRE` |
| --- | --- | --- | --- |
| Passaram | APROVADO | Segue | Revisão humana |
| Passaram | REPROVADO | Revisão humana | Revisão humana |
| Excecionável falhou | qualquer | Aprovação de exceção pelas personas da regra | Exceção e revisão humana |
| Bloqueante falhou | qualquer | Rejeitado, parecer registrado | Rejeitado |

Na conferência final, qualquer reprovação vai para a Auditoria interna; confirmar reverte a execução.

### Ferramentas de depuração

Pausar a linha ou uma estação; "parar antes" de um estágio; passo a passo; avançar ou continuar; reprocessar a partir de um estágio com o evento editado; cancelar.

Detalhes: [visao-geral.md](visao-geral.md), [ADR 0001](adr/0001-linha-de-producao-por-estagios.md), [ADR 0018](adr/0018-auditoria-antes-da-execucao.md), [ADR 0020](adr/0020-proximo-passo-explicito.md).

## 5. Contratos

### Tipos

| Tipo | Conteúdo | Exemplo de seed |
| --- | --- | --- |
| `NORMA` | Parâmetros regulatórios (piso, VR, VA, gratificações, sindicatos por UF), benefícios garantidos com condição, estado por situação do vínculo, compliance geral | `norma_clt_cct_bancarios.yaml` |
| `POLITICA` | Parâmetros internos (interstício, limites de aumento, conduta) e programas com vigência | `politica_movimentacao.yaml` |
| `CARGO` | Família, segmento, nível, cargo de confiança, estado alvo (jornada, faixa, verbas, benefícios, acessos, equipamentos, cláusulas, certificações), regras de entrada e compliance | `cargos.yaml` |
| `PROCESSO` | Evento atendido, esquema, cargo alvo, elegibilidade, orquestração, regras do plano, auditoria (SLA, compliance, verificações) e dados de eventos coletivos | `processos.yaml` |

Campos comuns: `codigo`, `tipo`, `nome`, `versao` (gerada), `vigencia` (`inicio`, `fim`), `descricao`. A versão usada é a vigente na data efetiva do evento. Salvar como nova versão preserva as anteriores.

### Cargos de exemplo

| Código | Cargo | Segmento | Nível |
| --- | --- | --- | --- |
| `CARGO_ESCRITURARIO` | Escriturário | OPERACIONAL | 1 |
| `CARGO_CAIXA` | Caixa | OPERACIONAL | 2 |
| `CARGO_ANALISTA_JR` | Analista Júnior | TECNICO | 2 |
| `CARGO_ANALISTA_PL` | Analista Pleno | TECNICO | 3 |
| `CARGO_ANALISTA_SR` | Analista Sênior | TECNICO | 4 |
| `CARGO_GERENTE_RELACIONAMENTO` | Gerente de Relacionamento | NEGOCIOS | 4 |
| `CARGO_COORDENADOR` | Coordenador | MEDIA_GESTAO | 5 |
| `CARGO_GERENTE_AGENCIA` | Gerente Geral de Agência | MEDIA_GESTAO | 6 |
| `CARGO_SUPERINTENDENTE` | Superintendente Regional | EXECUTIVO | 7 |
| `CARGO_DIRETOR` | Diretor | EXECUTIVO | 8 |

### Processos de exemplo

| Código | Evento |
| --- | --- |
| `PROC_ADMISSAO` | `colaborador.admitido` |
| `PROC_PROMOCAO` | `colaborador.promovido` |
| `PROC_MERITO` | `colaborador.merito_concedido` |
| `PROC_REVERSAO_CONFIANCA` | `colaborador.revertido_cargo_confianca` |
| `PROC_TRANSFERENCIA` | `colaborador.transferido` |
| `PROC_DESLIGAMENTO` | `colaborador.desligado` |
| `PROC_AFASTAMENTO` | `colaborador.afastado` |
| `PROC_RETORNO` | `colaborador.retornou_afastamento` |
| `PROC_REAJUSTE_CCT` | `cct.reajuste_aplicado` (coletivo) |
| `PROC_REAJUSTE_INDIVIDUAL` | `cct.reajuste_individual` |
| `PROC_INCLUSAO_DEPENDENTE` | `colaborador.dependente_incluido` |
| `PROC_BONUS` | `colaborador.bonus_concedido` |
| `PROC_MUDANCA_JORNADA` | `colaborador.jornada_alterada` |
| `PROC_CONFORMIDADE` | `auditoria.conformidade_solicitada` |
| `PROC_CONFORMIDADE_COLETIVA` | `auditoria.conformidade_coletiva` (coletivo) |
| `PROC_PROGRAMA_ALTO_POTENCIAL` | `colaborador.programa_alto_potencial_iniciado` |
| `PROC_AVISO_VENCIMENTO_PROGRAMA` | `colaborador.programa_a_vencer` |
| `PROC_VENCIMENTO_PROGRAMA` | `colaborador.programa_expirado` |
| `PROC_RENOVACAO_PROGRAMA` | `colaborador.programa_renovado` |
| `PROC_ENCERRAMENTO_PROGRAMA` | `colaborador.programa_encerrado` |

### Regras

```yaml
- id: PRM-05
  descricao: Interstício mínimo no cargo atual
  expressao: "meses_no_cargo >= politica.promocao.meses_minimos_no_cargo"
  tipo: EXCECIONAVEL          # BLOQUEANTE | EXCECIONAVEL | ALERTA
  aprovadores: [HRBP]
  base_legal: Política de movimentação interna
  explicacao_falha: "Colaborador está há {meses_no_cargo} meses no cargo; mínimo de {politica.promocao.meses_minimos_no_cargo}."
```

A expressão deve ser verdadeira para a regra ser atendida. As regras aparecem na norma (`compliance`), no cargo (`elegibilidade_entrada`, `compliance`) e no processo (`elegibilidade.regras`, `conferencia_plano.regras`, `auditoria.verificacoes`).

### Expressões

Subconjunto do Python avaliado por um interpretador seguro: comparações, `and`, `or`, `not`, `in`, aritmética, condicional, listas, acesso a atributos e funções da lista. Em parâmetros, valores e condições `quando`, texto começando com `=` é expressão.

Variáveis: `colaborador` (na auditoria, o estado projetado), `anterior`, `gestor`, `cargo_do_gestor`, `subordinados_diretos`, `niveis_acima`, `evento`, `hoje`, `programas_ativos`, `norma`, `politica`, `cargo_atual`, `cargo_destino`, `idade`, `meses_de_casa`, `anos_de_casa`, `meses_no_cargo`, `meses_na_unidade`, `meses_desde_ultimo_aumento`, `dias_afastado`.

Funções: `possui_beneficio`, `plano_beneficio`, `possui_verba`, `valor_verba`, `possui_certificacao`, `possui_acesso`, `possui_equipamento`, `possui_clausula`, `parametro_clausula`, `estabilidade_ativa`, `dependentes_menores_de`, `escolaridade_ao_menos`, `sindicato_da_uf`, `advertencias_ultimos_meses`, `operacao_executada`, `gestor_da_unidade`, `cpf_valido`, `cpf_em_uso`, `somar_meses`, `meses_entre`, `dias_entre`, `anos_entre`, `data`, `cargo`, `programa`, `programa_ativo`, `dias_para_vencer` e utilitários (`len`, `min`, `max`, `abs`, `round`, `sum`, `any`, `all`, `int`, `float`, `str`, `bool`, `vazio`).

### Mudanças para experimentar

| Mudança | Efeito |
| --- | --- |
| Interstício de 12 para 4 meses na política | "Promoção sem interstício" deixa de pedir exceção |
| Novo equipamento no estado alvo de um cargo | Promoções provisionam o item; a conformidade aponta quem já está no cargo sem ele |
| `PRM-08` de EXCECIONAVEL para BLOQUEANTE | "Promoção com processo disciplinar" passa a "Não elegível" |
| Duração do alto potencial de 12 para 6 meses | Novas inclusões vencem em seis meses |
| Remover `ENVIAR_ESOCIAL` da promoção | A auditoria aponta antes da execução |
| Remover `CALCULAR_RESCISAO` do desligamento | A auditoria rejeita o plano sem alterar sistemas |
| Nova versão da norma com VR maior e vigência futura | Eventos anteriores à vigência usam o valor antigo |

Detalhes: [contratos.md](contratos.md), [ADR 0003](adr/0003-contratos-versionados.md), [ADR 0004](adr/0004-avaliador-de-expressoes-seguro.md).

## 6. Prateleira de operações

Cada operação declara sistema de destino, parâmetros, campos que altera (usados pela compensação), ordem de execução e se é compensável. Qualquer processo pode chamá-la; o plano pode acrescentá-la por derivação do estado alvo. No laboratório os sistemas são simulados, com recibo e protocolo.

| Grupo | Operações |
| --- | --- |
| CADASTRO | `CRIAR_CADASTRO`, `ALTERAR_SITUACAO`, `ALTERAR_LOTACAO`, `ALTERAR_SINDICATO`, `ALTERAR_GESTOR`, `INCLUIR_DEPENDENTE`, `ENCERRAR_VINCULO` |
| DESENVOLVIMENTO | `INCLUIR_PROGRAMA`, `RENOVAR_PROGRAMA`, `REGISTRAR_AVISO_PROGRAMA`, `ENCERRAR_PROGRAMA` |
| FOLHA | `ALTERAR_CARGO`, `ALTERAR_SALARIO`, `APLICAR_REAJUSTE`, `ADICIONAR_VERBA`, `AJUSTAR_VERBA`, `REMOVER_VERBA`, `CALCULAR_RESCISAO` |
| PONTO | `ALTERAR_JORNADA`, `CONCEDER_LICENCA` |
| BENEFICIOS | `ADICIONAR_BENEFICIO`, `ALTERAR_BENEFICIO`, `REMOVER_BENEFICIO` |
| IAM | `CONCEDER_ACESSO`, `REVOGAR_ACESSO` |
| PATRIMONIO | `PROVISIONAR_EQUIPAMENTO`, `RECOLHER_EQUIPAMENTO` |
| JURIDICO | `INCLUIR_CLAUSULA`, `REMOVER_CLAUSULA`, `REGISTRAR_ESTABILIDADE`, `INICIAR_GARDEN_LEAVE` |
| SST | `AGENDAR_EXAME` |
| TREINAMENTO | `REGISTRAR_TREINAMENTO` |
| ESOCIAL | `ENVIAR_ESOCIAL` (S-2200, S-2205, S-2206, S-2210, S-2230, S-2299) |
| COMUNICACAO | `NOTIFICAR` (não compensável) |

A tela Prateleira executa uma operação avulsa ou em simulação. Detalhes: [prateleira.md](prateleira.md), [ADR 0005](adr/0005-prateleira-e-plano-derivado.md), [ADR 0008](adr/0008-saga-com-compensacao.md).

## 7. Aprovações, personas e hierarquia

### Personas

| Persona | Nome no laboratório | Decide |
| --- | --- | --- |
| `OPERADOR` | Operador de RH | Operação da linha, depuração |
| `GESTOR` | Gestor imediato | Exceções atribuídas ao gestor; a aprovação mostra o gestor real do colaborador |
| `HRBP` | HR Business Partner | Interstício, salário acima da faixa, salto de níveis |
| `JURIDICO` | Jurídico trabalhista | Pré-aposentadoria, justa causa sem registro |
| `COMPLIANCE` | Compliance | Processo disciplinar aberto |
| `AUDITORIA` | Auditoria interna | Divergências da conferência final |
| `COMITE` | Comitê de remuneração | Bônus e mérito acima do limite, nomeação de diretor, alto potencial com avaliação baixa |

### Tipos de aprovação

- **Exceção de elegibilidade**: libera uma regra excecionável que falhou.
- **Revisão humana da auditoria**: quando o agente reprova o que as regras aprovam, ou no modo `SEMPRE`.
- **Auditoria interna da conferência final**: confirmar a reprovação reverte a execução.

Regras de decisão: só personas listadas em `aprovadores`; decisão APROVAR ou REJEITAR; justificativa com pelo menos 5 caracteres; uma aprovação decidida não volta; a rejeição de uma cancela as demais pendentes do caso. Tudo vai para o log.

### Hierarquia

Cada colaborador tem `gestor_id`. O organograma é navegável na tela Colaboradores; as regras usam `gestor`, `cargo_do_gestor`, `subordinados_diretos`, `niveis_acima` e `gestor_da_unidade`; a operação `ALTERAR_GESTOR` mantém a árvore.

Detalhes: [ADR 0009](adr/0009-personas-sem-autenticacao.md), [ADR 0019](adr/0019-hierarquia-e-gestor-imediato.md).

## 8. Agentes de IA

### Papéis

| Papel | Modelo padrão | Onde aparece |
| --- | --- | --- |
| Agente de conferência | Motor Qwen: `qwen2.5:7b`; motor JEV: `tev1:0.8b` | Elegibilidade (consultiva), auditoria, conferência final |
| Embeddings | `nomic-embed-text` (ou OpenAI, Gemini, simulado) | Índice de todos os eventos |
| Agente de perguntas | O mesmo do conferente, ou `ask_model` | Tela Perguntar |

### Princípio

A IA nunca decide sozinha o destino de um caso nem calcula números. Ela sempre dá uma recomendação clara (APROVADO ou REPROVADO) com confiança, resumo, achados com severidade e justificativa, inclusive quando a decisão é humana.

### O que o auditor recebe e devolve

Recebe, em JSON compacto: evento e data efetiva; colaborador resumido (sem nome e CPF); contrato de processo e estado alvo; plano com motivo e base legal, e descartes; resultado das regras; na conferência final, recibos, compensações, diferença antes e depois e divergências. Devolve um JSON restrito por esquema. Valores fora de APROVADO ou REPROVADO viram REPROVADO; confiança acima de 1 vira percentual; resposta inválida ganha uma nova tentativa e, se falhar, vale REPROVADO com achado ALTO e revisão humana. Prompt e resposta bruta ficam no caso.

### Provedores

| Provedor | Saída estruturada | Modelos sugeridos | Embeddings |
| --- | --- | --- | --- |
| Ollama (padrão) | `format` com JSON Schema | `qwen2.5:7b`, `qwen2.5:3b`, `qwen2.5:14b` | `nomic-embed-text` |
| Anthropic Claude | `output_config.format` | `claude-opus-5-5` (padrão), `claude-sonnet-5-5`, `claude-haiku-5-5` | não oferece |
| OpenAI ou compatível (Azure OpenAI, OpenRouter, Groq, vLLM, LM Studio) | `response_format` `json_schema` | `gpt-5-mini`, `gpt-5`, `gpt-4.1-mini` | `text-embedding-3-small` |
| Google Gemini | `responseSchema` | `gemini-2.5-flash`, `gemini-2.5-pro` | `gemini-embedding-001` |

Chaves: `.env` primeiro, senão `secrets.json` no volume de dados (gravado pelo assistente). Nunca no Redis, no log ou na API; a interface mostra só os quatro últimos caracteres. Erros de chave, modelo, cota ou rede contam como IA indisponível.

Pendente de merge (PR #8): teto de gastos opcional com LLM externa e preço por modelo, também opcional. Com o teto atingido, a chamada externa não sai e o caso espera, como com a IA fora do ar. Veja a [seção 18](#pendente-de-merge-pr-8).

### Motores Qwen e JEV

| | Qwen (generativo) | JEV (modelo de decisão) |
| --- | --- | --- |
| Modelo | `qwen2.5:7b` no provedor configurado | `tev1:0.8b` no Ollama 0.35+ |
| Chamada | chat com JSON Schema | `POST /v1/systemone` com `state` e `questions` |
| Entrada | caso inteiro em JSON | poucos textos curtos por tarefa |
| Saída | veredito, confiança, resumo, achados e justificativa escritos | probabilidades de veredito, verificações e risco; texto montado a partir delas |

Escolha em `agent_engine`. A **comparação** (`agent_compare_enabled`) faz o outro motor responder a mesma tarefa sem decidir, para medir concordância. A **classificação de elegibilidade** (`agent_eligibility_enabled`, ligada) é consultiva. O motor JEV não foi validado contra uma instalação real do Ollama 0.35; trate os números como experimentais.

### Desempenho dos agentes

Cada chamada grava um registro em `hr:metrics:agent`, que sobrevive à limpeza do laboratório. A tela Desempenho mostra, por motor: chamadas, processamento e resposta (média, p50, p95, mínimo, máximo), espera por vaga, tokens, confiança, erros, concordância com as regras; histórico em gráfico; tempo por tarefa; Qwen contra JEV nos mesmos casos (concordância, quem foi mais rigoroso, divergências); últimas chamadas.

### Disponibilidade

IA fora do ar: o caso espera em `AGUARDANDO_AGENTE` e volta sozinho quando a IA responde (monitor a cada 10 segundos). O agente heurístico simulado só responde se ligado e marca cada decisão como simulada. Cache de respostas por 24 horas; semáforo de concorrência (`ollama_max_concurrency` 1, `cloud_max_concurrency` 4, `jev_max_concurrency` 2); aquecimento do modelo; temperatura 0.

Detalhes: [agentes.md](agentes.md), ADRs [0006](adr/0006-regras-decidem-ia-audita.md), [0007](adr/0007-ollama-local-e-espera.md), [0021](adr/0021-provedores-de-llm-na-nuvem.md), [0022](adr/0022-assistente-de-configuracao-inicial.md), [0024](adr/0024-motor-jev-e-painel-de-desempenho.md).

## 9. Eventos com vigência

- Programas definidos em `politica.programas`. O de exemplo, `ALTO_POTENCIAL`, dura 12 meses a partir da data oficial, avisa 30 dias antes, exige avaliação mínima 4 e 12 meses de casa, aceita uma renovação.
- Concessões enquanto ativo: bolsa de desenvolvimento (verba), mentoria executiva (benefício) e plataforma de liderança (acesso). Elas entram no estado alvo.
- A **agenda** é derivada dos programas ativos; cada worker confere a cada 5 segundos. Aviso e vencimento são emitidos uma única vez (`HSETNX hr:vigencia:emitidos`) como eventos comuns da linha. O vencimento retira as concessões.
- **Renovação** estende e reagenda; **encerramento antecipado** retira e cancela o vencimento; vencimento antes do prazo é bloqueado.
- **Relógio simulado** (`hr:clock`): avançar dias ou ir para uma data; afeta todas as contas de tempo; "Voltar ao calendário real" desfaz.

Detalhes: [ADR 0023](adr/0023-eventos-com-vigencia.md).

## 10. Visibilidade, log e perguntas

### Camadas

| Camada | Pergunta | Onde |
| --- | --- | --- |
| Linha ao vivo | Onde está cada caso agora? | Tela Linha (SSE) |
| Rastro do caso | Por que este caso terminou assim? | Detalhe do caso |
| Log de decisões | Quem decidiu o quê e por quê? | Tela Log, `audit-log.jsonl` |
| Painel | Como está a operação? Onde está o gargalo? | Tela Visão |
| Desempenho dos agentes | Qual motor é mais rápido e concorda mais? | Tela Desempenho |
| Métricas | Como acompanhar fora do laboratório? | `GET /api/metrics` (Prometheus) |
| Perguntas | O que as telas não respondem diretamente | Tela Perguntar |

Todas são alimentadas pelo documento do caso e pelo log; não há contadores paralelos.

### Painel Visão

KPIs (casos, em andamento, conclusão, p50 e p95, pendências, compensações, replanejamentos, latência do agente), alertas, linha do tempo, funil, tempo por estágio com gargalo destacado, matriz evento por situação, regras que mais barram, operações, aprovações por persona, concordância agente e regras, estado do índice.

Alertas: fila acumulada, esperando a IA, aprovação parada há mais de 30 minutos, taxa de falhas acima de 20% na última hora, divergência do agente, colaboradores fora do estado alvo.

### Métricas Prometheus

`hrlab_cases`, `hrlab_cases_by_event`, `hrlab_queue_messages`, `hrlab_queue_consumers`, `hrlab_stage_duration_ms`, `hrlab_approvals_pending`, `hrlab_agent_up`, `hrlab_agent_processing_ms`, `hrlab_agent_response_ms`, `hrlab_agent_calls`, `hrlab_agent_errors`, `hrlab_index_documents`, `hrlab_index_dirty`, `hrlab_index_simulated`.

### Log de decisões

Campos: `tipo`, `ts`, `case_id`, `colaborador_id`, `estagio`, `ator`, `mensagem`, `dados`. Tipos: entrada (`EVENTO_RECEBIDO`, `EVENTO_REJEITADO`, `EVENTO_DUPLICADO`), linha (`ESTAGIO`, `DECISAO_FINAL`, `REPLANEJAMENTO`, `DEPURACAO`, `CONTROLE`), regras (`REGRA_AVALIADA`, `DECISAO_ELEGIBILIDADE`, `AUDITORIA`), plano e execução (`PLANO_GERADO`, `OPERACAO_ESCOLHIDA`, `OPERACAO_DESCARTADA`, `OPERACAO_EXECUTADA`, `OPERACAO_FALHOU`, `COMPENSACAO`), agente (`AGENTE_RECOMENDACAO`, `AGENTE_INDISPONIVEL`), pessoas (`APROVACAO_SOLICITADA`, `APROVACAO_DECIDIDA`), cadastros (`COLABORADOR_ALTERADO`, `CONTRATO_ALTERADO`, `CONFIG_ALTERADA`).

Correlação: `case_id`, `evento_id`, `colaborador_id`, `pai_id` e `filhos`, aprovações `apr-...`, worker e duração de cada estágio.

### Embeddings e agente de perguntas

- Indexados: narrativa de cada caso (`caso:{id}`) e decisões do log com significado próprio (`log:{id}`).
- O indexador lê o log com grupo próprio, agrupa marcas por 1,5 segundo, lotes de 16, e não refaz embedding de texto igual.
- Busca: cosseno exato sobre matriz em memória mais reforço lexical; filtros antes da ordenação.
- Perguntas em três etapas: interpretação em consulta estruturada (CONTAGEM, AGRUPAMENTO, LISTA, BUSCA, EXPLICACAO_CASO, DESEMPENHO), saneada contra o catálogo; evidências calculadas em Python (números exatos) e busca semântica; resposta redigida só com as evidências, com citações verificadas e emoji removidos.

Detalhes: [visibilidade.md](visibilidade.md), ADRs [0011](adr/0011-log-de-decisoes-explicado.md), [0015](adr/0015-estrategia-de-visibilidade.md), [0016](adr/0016-embeddings-de-todos-os-eventos.md), [0017](adr/0017-agente-de-linguagem-natural.md).

## 11. Cenários e dados sintéticos

### Time artificial

Organização de banco com sede e agências em bases sindicais diferentes, do escriturário ao diretor, com hierarquia, tempo de casa realista, salário na faixa, benefícios e acessos coerentes. A primeira subida gera 80 colaboradores. Uma fração recebe **desvios propositais** (VR ausente, 8 horas sem cargo de confiança, gratificação abaixo do mínimo, sindicato incompatível com a UF, gestor sem celular corporativo, acesso além do previsto, plano de saúde diferente, auxílio-creche faltando). A semente torna o time reprodutível.

### 54 cenários

| Grupo | Quantidade | Exemplos |
| --- | --- | --- |
| Fluxo padrão | 20 | Promoção, promoção para média gerência, admissão, transferências, reversão de confiança, desligamentos, garden leave, afastamentos, licença-maternidade, retorno de acidente, nascimento de filho, bônus, mérito, alto potencial (inclusão, vencimento, renovação, encerramento), conformidade com divergência |
| Exige exceção | 10 | Sem interstício, processo disciplinar, salto de nível, diretor sem comitê, gerente acima da faixa, pré-aposentadoria, justa causa sem registro, bônus e mérito acima do limite, alto potencial com avaliação baixa |
| Deve bloquear | 15 | Gerente sem CPA-20, redução salarial, colaborador afastado, abaixo do piso, menor de idade, CPF inválido, transferência sem anuência, dirigente sindical, gestante, CIPA, malus de compliance, 8 horas sem confiança, alto potencial duplicado ou vencimento antecipado |
| Coletivos | 2 | Reajuste da CCT na data-base, conformidade coletiva |
| Estresse e robustez | 7 | Evento duplicado, evento inválido, colaborador inexistente, tipo desconhecido, data sem contrato vigente, falha no sistema de benefícios, eventos concorrentes |

A suíte completa roda todos e compara esperado e obtido. Também há evento manual e rajada de dezenas ou centenas de eventos aleatórios. Lista completa: [cenarios.md](cenarios.md). Dados: [ADR 0012](adr/0012-dados-sinteticos-e-ficticios.md).

## 12. Interface

| Tela | Para quê |
| --- | --- |
| Assistente de configuração | Primeira visita: provedor de IA, conexão e teste, motor de decisão, busca semântica, opções da linha, revisão |
| Linha | Linha ao vivo com uma estação por estágio; pausar; parar antes; clicar no caso |
| Detalhe do caso | Evento, regras, plano com escolhidas e descartadas, parecer do agente com prompt e resposta, recibos, compensações, auditoria, estado antes e depois, trilha, próximo passo; avançar, reprocessar, editar, cancelar |
| Desempenho | Tempos e concordância dos motores Qwen e JEV |
| Visão | Painel de visibilidade |
| Perguntar | Perguntas em linguagem natural, busca semântica e histórico |
| Cenários | 54 cenários, suíte completa, evento manual, rajada |
| Aprovações | Exceções e revisões; troca de persona no topo |
| Colaboradores | Time artificial, organograma, perfil, programas ativos, desvios, conformidade, disparo de eventos |
| Vigências | Relógio simulado e agenda de avisos e vencimentos |
| Contratos | Editor estruturado e YAML, validação, nova versão, restaurar exemplos |
| Prateleira | Catálogo e execução avulsa ou simulada |
| Log | Decisões com filtro e exportação JSONL |
| Configurações | Motor, provedor, parâmetros da IA, embeddings, revisão humana, atraso visual, falhas injetadas, reinício |

Toda a interface, os contratos e as explicações estão em português; o código está em inglês; não há emoji em nenhuma parte ([ADR 0014](adr/0014-idioma-e-sem-emoji.md)).

## 13. Arquitetura técnica

### Serviços

| Serviço | Responsabilidade | Escala |
| --- | --- | --- |
| `frontend` | React + Vite servido por nginx (porta 8580); proxy `/api`; SSE sem buffer | 1 |
| `api` | FastAPI: REST, SSE, geração de times e cenários, aprovações, painel, busca, perguntas; não executa estágios | 1 ou mais, sem estado |
| `worker` | Consome as filas dos seis estágios; chama o agente; monitor de saúde da IA; agenda de vigências | `--scale worker=N` |
| `indexer` | Mantém os embeddings a partir do log | 1 |
| `redis` | Filas, documentos, log, pub/sub, índice; AOF ligado | 1 |
| `ollama` | Opcional (perfil `ollama`) | - |

### Módulos do backend

`domain.py` (vocabulário, próximo passo), `expr.py` (avaliador seguro), `context.py` (variáveis e funções das expressões, hierarquia), `migrations.py`, `contracts.py` (repositório versionado), `shelf.py` (prateleira e compensação), `engine.py` (regras, elegibilidade, estado alvo, plano, auditoria, conferência, conformidade), `llm.py` (provedores), `apikeys.py`, `agent.py`, `engines.py` (Qwen e JEV), `metrics.py`, `clock.py`, `vigencia.py`, `pipeline.py` (handlers, aprovações, depuração, saga, coletivos), `worker.py`, `logbook.py`, `facts.py`, `embeddings.py`, `indexer.py`, `ask.py`, `generators/`, `api.py`.

`engine.py`, `facts.py`, `shelf.py` e `expr.py` não fazem I/O: tudo o que decide é testável sem Redis e sem rede. São 61 testes unitários.

### Fluxo de um evento

1. `POST /api/events` cria o caso (`NA_FILA`), grava `EVENTO_RECEBIDO` e publica em `hr:stream:intake`.
2. Um worker lê pelo grupo `hr-workers` (uma mensagem, um worker), executa `run_stage` e confirma com `XACK`.
3. `run_stage` aplica guardas (obsolescência, pausa, breakpoint, passo a passo), roda o handler e segue, aguarda ou finaliza.
4. Cada gravação publica em `hr:updates`; a API repassa por SSE.
5. Cada decisão vai para `hr:log`; o indexador lê com o grupo `hr-indexer`.

### Armazenamento (Redis)

Streams por estágio (`hr:stream:{estagio}`), casos (`hr:case:{id}`, `hr:cases`), trilhas por caso e colaborador, log global (`hr:log`, até 200 mil entradas), idempotência (`hr:event:{id}`), colaboradores (`hr:employee:*`), travas (`hr:lock:employee:{id}`), contratos (`hr:contract:*`), aprovações (`hr:approval:*`), configurações e controle (`hr:settings`, `hr:control`, `hr:setup`), saúde e cache da IA, relógio (`hr:clock`), agenda emitida (`hr:vigencia:emitidos`), execuções da suíte, índice vetorial (`hr:vec:*`), histórico de perguntas (`hr:ask:history`), métricas dos agentes (`hr:metrics:agent`), pub/sub (`hr:updates`).

### Concorrência e consistência

Um worker por mensagem; retomada de pendentes pelo mesmo consumidor após queda; guarda de obsolescência; idempotência com `SET NX`; trava por colaborador; versão do cadastro com replanejamento (até 3 vezes); snapshot para a conferência final, com alerta `FIN-CONCORRENCIA` em vez de falsa divergência.

### Falhas

| Falha | Comportamento |
| --- | --- |
| Operação falha | Saga compensa em ordem inversa; não compensáveis ficam registradas; `FALHOU_COMPENSADO` |
| Auditoria reprovada | Nada alterado; `REJEITADO` |
| Conferência reprovada e confirmada | Execução revertida; `REVERTIDO` |
| IA fora do ar | `AGUARDANDO_AGENTE`; retomada automática |
| IA fora do formato | Duas tentativas; depois REPROVADO e revisão humana |
| Indexador sem IA | Marcas acumulam; indexa quando volta |
| Erro inesperado | `ERRO`; reprocessável de qualquer estágio |
| Worker cai | Estágio retomado quando ele volta |

### Princípios, atributos de qualidade e trade-offs

Uma linha, muitos processos; comportamento em dados; plano derivado do estado alvo; operações desacopladas; decisão determinística e IA auditora; auditar antes de alterar; falhar de forma reversível; tudo explicado; lógica pura testável; provedor de IA trocável.

Trade-offs aceitos: Redis para tudo (simplicidade contra volume e consultas); fila por estágio (controle contra mensagens); YAML com expressões (legível contra exigir cuidado); IA síncrona no estágio (parecer antes da decisão contra gargalo); personas sem login (demonstração contra segurança); fatos por requisição (consistência contra custo com volume).

Detalhes: [arquitetura.md](arquitetura.md).

## 14. Segurança e privacidade

### Controles existentes

- Regras decidem; a IA não aprova o que a regra barra.
- Avaliador de expressões com lista branca sobre a AST; sem `eval`, `exec`, `import`, `lambda`, atributos com `_` ou funções fora da lista.
- Validação de contratos antes de salvar; versões anteriores preservadas.
- Auditoria antes da execução, conferência final, saga, idempotência, trava e versão.
- Aprovação só pelas personas da regra, justificativa obrigatória, sem nova decisão.
- Log append-only com ator; prompt e resposta da IA gravados.
- Chaves de API fora do Redis, do log e da API; arquivo `0600` com escrita atômica.
- Saída estruturada da IA, normalização para REPROVADO, números calculados fora do modelo, citações verificadas.
- Minimização no prompt do auditor (sem nome e CPF).
- Ollama local por padrão; nuvem só por escolha explícita.
- Só o frontend publica porta; API, workers e Redis na rede interna; corpo limitado a 10 MB.

### Lacunas aceitas no laboratório

Sem autenticação; persona por cabeçalho `X-Persona`; CORS aberto; porta publicada em todas as interfaces; sem TLS; Redis sem senha; URLs de IA configuráveis pela interface (risco de SSRF e de enviar a chave a outro destino); dados em repouso sem criptografia; segredo em arquivo; sem limite de taxa (o teto de gastos opcional com LLM externa chega no PR #8, ainda não mergeado); log no mesmo Redis; contratos editáveis por qualquer persona; reinício pela interface.

### Privacidade (LGPD)

Dados sintéticos. Em produção: base legal de contrato de trabalho e obrigação legal, dados sensíveis (saúde ocupacional, filiação sindical) pelo art. 11; minimização e mascaramento no prompt e no índice; avaliação de transferência internacional com provedor na nuvem; política de retenção; relatório por titular; explicação de decisões automatizadas (art. 20) já atendida pela explicação de cada regra.

Detalhes, modelo de ameaças STRIDE e plano de endurecimento: [seguranca.md](seguranca.md).

## 15. Operação

### Instalação

```bash
./scripts/install.sh            # Linux e macOS
scripts\install.cmd             # Windows (ou .\scripts\install.ps1)
```

O instalador confere Docker e Compose 2.24+, cria ou atualiza o `.env` (com cópia de segurança), escolhe a porta (8580 ou a próxima livre), encontra o Ollama (máquina, rede, container, nuvem ou nenhum) e o testa de dentro de um container, baixa modelos, sobe o compose, alinha as configurações e confere a IA. Opções: `--ollama`, `--ollama-url`, `--modelo`, `--embedding`, `--sem-modelos`, `--porta`, `--porta-ollama`, `--workers`, `--simulado`, `--sem-build`, `--sim`.

Sem instalador: `cp .env.example .env && docker compose up -d --build`. Interface em http://localhost:8580.

### Assistente de configuração inicial

Abre na primeira visita e em Configurações: Início, IA dos agentes, Conexão (com teste que lista modelos e faz chamada mínima), Busca semântica, Linha, Revisão. "Pular e manter como está" não muda nada. As escolhas vão para o log; a chave não.

### Configurações principais

| Configuração | Padrão |
| --- | --- |
| Provedor (`LLM_PROVIDER`) | `ollama` |
| Motor (`AGENT_ENGINE`) | `qwen` |
| Modelo do conferente (`OLLAMA_MODEL`) | `qwen2.5:7b` |
| Modelo JEV (`JEV_MODEL`) | `tev1:0.8b` |
| Classificação de elegibilidade | ligada |
| Comparação entre motores | desligada |
| Agente simulado (`HEURISTIC_FALLBACK_ENABLED`) | desligado |
| Revisão humana (`HUMAN_REVIEW_MODE`) | `SE_REPROVADO` |
| Cache do agente | ligado, 24 horas |
| Atraso visual (`STAGE_DELAY_MS`) | 700 ms |
| Falhas injetadas (`FAILURE_RATE_PERCENT`) | 0 |
| Gerador de embeddings | `ollama`, `nomic-embed-text` |
| Documentos por pergunta (`ASK_TOP_K`) | 8 |

Lista completa: [operacao.md](operacao.md#configurações).

### Estresse, reinício e testes

- `docker compose up -d --scale worker=4`; atraso 0; rajada de 200 a 500 eventos; acompanhar em Linha, Visão e `/api/metrics`.
- Reiniciar laboratório (limpa casos, aprovações, filas, log e índice); restaurar contratos; `docker compose down -v` para apagar tudo.
- `cd backend && python -m pytest -q tests`: 61 testes, sem Redis, sem Ollama e sem chave.

### Rotina de demonstração

Promoção padrão; promoção sem interstício com aprovação do HRBP; organograma; mudar o interstício numa nova versão; suíte completa; Visão e Perguntar; inclusão no alto potencial e avanço do relógio. Roteiros por público: [apresentacao.md](apresentacao.md).

## 16. API

Rotas agrupadas (detalhes em [api.md](api.md)):

| Grupo | Rotas |
| --- | --- |
| Eventos e casos | `POST /api/events`, `GET /api/cases`, `GET /api/cases/{id}`, `POST /api/cases/{id}/release`, `/retry`, `/cancel`, `/debug` |
| Linha e controle | `GET/POST /api/control`, `GET /api/stats`, `GET /api/stream` (SSE), `GET /api/meta`, `GET /api/health` |
| Vigências e relógio | `GET /api/clock`, `POST /api/clock/advance`, `PUT /api/clock`, `GET /api/vigencias`, `POST /api/vigencias/tick` |
| Aprovações | `GET /api/approvals`, `POST /api/approvals/{id}/decide` |
| Colaboradores | `GET /api/employees`, `GET/PUT /api/employees/{id}`, `POST /api/employees/generate`, `POST /api/employees/{id}/drift` |
| Contratos e prateleira | `GET /api/contracts`, `GET /api/contracts/{codigo}`, `POST /api/contracts/validate`, `POST /api/contracts`, `DELETE /api/contracts/{codigo}/versions/{versao}`, `POST /api/contracts/reset`, `GET /api/shelf`, `POST /api/shelf/{codigo}/invoke` |
| Cenários | `GET /api/scenarios`, `POST /api/scenarios/{id}/generate`, `POST /api/scenarios/burst`, `POST/GET /api/scenarios/suite`, `GET /api/scenarios/suite/{id}` |
| Agente e configurações | `GET/PUT /api/settings`, `GET /api/agent/health`, `POST /api/agent/check`, `POST /api/agent/pull`, `GET/DELETE /api/metrics/agentes`, `POST /api/agent/cache/clear`, `GET /api/setup`, `POST /api/setup/test`, `POST /api/setup/test-jev`, `PUT /api/setup/key`, `POST /api/setup/complete`, `POST /api/reset` |
| Log | `GET /api/logs`, `GET /api/logs/export` |
| Visibilidade, índice e perguntas | `GET /api/insights`, `GET /api/facts`, `GET /api/metrics`, `GET /api/index/status`, `POST /api/index/rebuild`, `POST /api/search`, `POST /api/ask`, `GET /api/ask/history` |

A persona é informada no cabeçalho `X-Persona`.

## 17. Decisões arquiteturais

| Nº | Decisão |
| --- | --- |
| 0001 | Linha de produção com seis estágios e uma fila por estágio |
| 0002 | Redis como fila, armazenamento, log, pub/sub e índice |
| 0003 | Contratos versionados em YAML, em quatro tipos, com vigência |
| 0004 | Regras como expressões avaliadas por um interpretador seguro |
| 0005 | Prateleira desacoplada e plano derivado do estado alvo |
| 0006 | Regras determinísticas decidem; o agente de IA audita e sempre recomenda |
| 0007 | Ollama local ou na rede, saída estruturada; espera quando indisponível |
| 0008 | Execução em saga com compensação por snapshot |
| 0009 | Aprovações por persona, sem login, sempre registradas |
| 0010 | Trava por colaborador, versão do cadastro e replanejamento |
| 0011 | Log append-only com explicação de cada decisão |
| 0012 | Times e eventos sintéticos; valores da CCT ilustrativos |
| 0013 | FastAPI, React com Vite e atualizações por SSE |
| 0014 | Domínio em português, código em inglês, nenhum emoji |
| 0015 | Visibilidade por modelo de leitura, painel, métricas e rastro por caso |
| 0016 | Embeddings de todos os eventos com indexador dedicado e busca exata |
| 0017 | Agente de linguagem natural em três etapas, com números exatos e citações |
| 0018 | Auditoria antes da execução e conferência final depois |
| 0019 | Hierarquia por gestor imediato, usada nas regras e nas aprovações |
| 0020 | Próximo passo explícito em cada fase |
| 0021 | Provedores de LLM na nuvem ao lado do Ollama |
| 0022 | Assistente de configuração inicial na interface |
| 0023 | Eventos com vigência, agenda derivada e relógio simulado |
| 0024 | Motor JEV ao lado do Qwen e painel de desempenho dos agentes |
| 0025 | Teto de gastos com LLM externa (no PR #8, pendente de merge) |

Cada ADR traz contexto, decisão, alternativas e consequências: [adr/README.md](adr/README.md).

## 18. Limites, riscos e caminho para produção

### Limites atuais

- Laboratório com dados sintéticos e valores da CCT fictícios.
- Integrações simuladas pela prateleira.
- Sem autenticação; personas por seletor.
- Redis como único armazenamento; índice vetorial em memória na API.
- Sem redistribuição automática de mensagens de um worker que não volta (`XAUTOCLAIM`).
- Motor JEV experimental, não validado contra uma instalação real do Ollama 0.35.

### Pendente de merge: PR #8

Ainda não incorporado à branch principal: o [PR #8](https://github.com/fernandopaixao/new-hr-lab/pull/8), em revisão, acrescenta três funcionalidades aos provedores externos. O comportamento pode mudar até o merge.

- **Assistente de primeiro acesso "Ollama, externo ou sem IA".** No passo 2, a pessoa escolhe Ollama, um provedor externo (Anthropic, Google Gemini ou OpenAI) ou nenhuma IA.
- **Teste da API em cinco etapas.** Chave, teto, conexão, modelo e chamada de teste, mostrando as requisições feitas, o tempo, os tokens, o custo do teste e em qual etapa o teste parou.
- **Teto de gastos com LLM externa (opcional).** O preço por modelo e o teto são configurações opcionais, não etapas obrigatórias do assistente. Quando configurados, cada chamada externa (agentes, perguntas, embeddings e o teste do assistente) é precificada pelos tokens informados pelo provedor e por uma tabela de preço por modelo (US$ por milhão de tokens, editável). Os contadores ficam no Redis, por período (`MENSAL` ou `TOTAL`), provedor e modelo, e sobrevivem ao reinício do laboratório. Antes de cada chamada, `llm.py` confere o teto: se o gasto mais a estimativa do prompt passar do limite, a chamada não é enviada, os casos ficam em "Aguardando agente de IA", uma faixa vermelha "Chamadas externas bloqueadas" aparece em todas as telas e o primeiro bloqueio de cada episódio grava `GASTOS_LLM` no log. Há aviso por percentual do teto, painel em Configurações (medidor, gasto por modelo, últimas chamadas, zerar contador), selo de gasto no topo e as rotas `GET /api/gastos`, `PUT /api/gastos/teto`, `PUT /api/gastos/precos` e `POST /api/gastos/zerar`. Registrado na ADR 0025 do mesmo PR.

### Caminho para produção

| Tema | Produção sugerida |
| --- | --- |
| Identidade | SSO (OIDC), papéis, autorização por rota e por aprovação |
| Rede | TLS, CORS restrito, proxy reverso, Redis com ACL e TLS |
| Segredos | Cofre externo |
| IA | Destinos permitidos, configuração por administrador, teto de gasto, avaliação contínua de concordância |
| Armazenamento | Banco transacional para casos, cadastro e contratos; log em armazenamento imutável |
| Mensageria | Streams com reivindicação de pendentes, ou Kafka particionado por colaborador |
| Integrações | Adaptadores reais com idempotência, timeout, retentativa e compensação |
| Índice vetorial | pgvector, Redis Stack ou OpenSearch |
| Observabilidade | OpenTelemetry com `case_id` como trace id; Alertmanager; SLO por `auditoria.sla_horas` |
| Governança de contratos | Quatro olhos, homologação, suíte de cenários como portão de publicação |
| Implantação | Kubernetes ou serviço gerenciado; CI com testes, análise estática e varredura de imagens |

### Piloto sugerido

1. Um processo de alto volume e regra clara (mérito ou reajuste coletivo).
2. Regras reais transcritas com o jurídico.
3. Duas ou três operações ligadas a sistemas reais.
4. Execução em paralelo ao processo atual por um ciclo.
5. Medição de tempo de ciclo, exceções por regra e divergências.

## 19. Glossário essencial

| Termo | Significado |
| --- | --- |
| CLT | Consolidação das Leis do Trabalho |
| CCT | Convenção coletiva de trabalho (aqui, dos bancários, com valores fictícios) |
| Jornada de 6 horas | Regra geral do bancário (CLT art. 224) |
| Cargo de confiança | 8 horas e gratificação de ao menos um terço (art. 224, par. 2) |
| Cargo de gestão | Sem controle de jornada (art. 62, II) |
| Interstício | Tempo mínimo no cargo antes de nova promoção |
| Irredutibilidade | Proibição de reduzir salário (CF art. 7, VI) |
| Estabilidade | Período em que a dispensa sem justa causa é vedada (gestante, acidentária, CIPA, dirigente sindical, pré-aposentadoria) |
| Garden leave | Afastamento remunerado de executivos entre o aviso e o fim do vínculo |
| CPA-20 | Certificação da ANBIMA para quem atende clientes em investimentos |
| eSocial | Sistema do governo que recebe os eventos trabalhistas |
| Saga | Execução em passos com compensação |
| Estado alvo | Como o colaborador deve estar pelo cargo e pela norma |
| Estado projetado | Colaborador com o plano aplicado em simulação |
| SSE | Server-Sent Events |
| Grupo de consumidores | Recurso dos Redis Streams que entrega cada mensagem a um único worker |

Glossário completo: [glossario.md](glossario.md).

## 20. Mapa: conceito, onde é aplicado e onde ver

| Conceito | Onde é aplicado | Código | Tela | Cenário que demonstra |
| --- | --- | --- | --- | --- |
| Evento suficiente | Gatilho | `pipeline.submit_event` | Cenários, evento manual | `promocao_padrao` |
| Idempotência | Gatilho | `store` (`SET NX`) | Detalhe do caso | `evento_duplicado` |
| Contrato vigente na data | Gatilho, todas as regras | `contracts.py` | Contratos | `data_sem_contrato_vigente` |
| Regra bloqueante | Elegibilidade, auditoria | `engine.py`, `expr.py` | Detalhe do caso | `desligamento_gestante` |
| Regra excecionável | Elegibilidade | `engine.py`, `pipeline.decide` | Aprovações | `promocao_sem_intersticio` |
| Estado alvo e plano derivado | Planejamento | `engine.target_state`, `shelf.py` | Detalhe do caso, Colaboradores | `promocao_media_gestao` |
| Operação descartada explicada | Planejamento | `engine.py` | Detalhe do caso (plano) | qualquer caso com plano |
| Auditoria antes da execução | Auditoria | `engine.py`, `agent.py` | Detalhe do caso | `desligamento_sem_justa_causa` |
| IA auditora | Elegibilidade, auditoria, conferência | `agent.py`, `engines.py`, `llm.py` | Detalhe do caso (aba do agente), Desempenho | qualquer |
| Revisão humana | Auditoria | `pipeline.py` | Aprovações | modo `SEMPRE` |
| Saga e compensação | Execução | `pipeline.py`, `shelf.py` | Detalhe do caso | `falha_no_sistema_de_beneficios` |
| Trava e replanejamento | Execução | `pipeline.py` | Log (`REPLANEJAMENTO`) | `eventos_concorrentes` |
| Conferência final | Conferência | `engine.py` | Detalhe do caso | qualquer concluído |
| Evento coletivo | Gatilho | `pipeline.py` | Linha (casos filhos) | `reajuste_cct_coletivo` |
| Hierarquia | Regras e aprovações | `context.py` | Colaboradores (organograma), Aprovações do Gestor | perfil de qualquer colaborador |
| Próximo passo | Todos os estágios | `domain.py` | Linha, Detalhe do caso | qualquer |
| Programa com vigência | Agenda, planejamento | `vigencia.py`, `clock.py` | Vigências, Colaboradores | `alto_potencial_inclusao`, `alto_potencial_vencimento` |
| Conformidade | Auditoria, varredura | `engine.py` | Colaboradores | `conformidade_coletiva` |
| Log explicado | Todos | `logbook.py` | Log | qualquer |
| Painel e métricas | Leitura | `facts.py`, `api.py` | Visão, `/api/metrics` | rajada |
| Embeddings e perguntas | Leitura | `embeddings.py`, `indexer.py`, `ask.py` | Perguntar | após a suíte |
| Provedor de IA trocável | Agentes | `llm.py`, `apikeys.py` | Assistente, Configurações | qualquer |
| Teto de gastos com LLM externa (PR #8, pendente) | Antes de cada chamada externa | `budget.py`, `llm.py` | Configurações, faixa vermelha no topo | teto baixo com provedor externo |
| Motores Qwen e JEV | Agentes | `engines.py`, `metrics.py` | Desempenho | comparação ligada |

Uma versão navegável deste mapa, com a linha de produção animada e explicações por público, está em [demo/index.html](demo/index.html).
