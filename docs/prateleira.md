# Prateleira de operações

Catálogo gerado a partir de `backend/hrlab/shelf.py`. Cada operação declara o sistema de destino, os parâmetros, os campos do cadastro que altera (usados pela compensação da saga) e a ordem de execução dentro de um plano.


## CADASTRO

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `CRIAR_CADASTRO` | Criar cadastro | `colaborador_id`* (texto), `dados`* (objeto) | * | 10 | sim |
| `ALTERAR_SITUACAO` | Alterar situação do vínculo | `situacao`* (texto), `motivo` (texto), `inicio` (data), `previsao_retorno` (data) | situacao, afastamento, historico_afastamentos, historico | 15 | sim |
| `ALTERAR_LOTACAO` | Alterar lotação | `unidade`* (texto), `cidade`* (texto), `uf`* (texto), `centro_custo` (texto) | unidade, cidade, uf, centro_custo, data_inicio_unidade, historico | 20 | sim |
| `ALTERAR_SINDICATO` | Alterar enquadramento sindical | `sindicato`* (texto) | sindicato, historico | 22 | sim |
| `ALTERAR_GESTOR` | Alterar gestor imediato | `gestor_id`* (texto) | gestor_id | 24 | sim |
| `INCLUIR_DEPENDENTE` | Incluir dependente | `nome`* (texto), `parentesco`* (texto), `data_nascimento`* (data) | dependentes | 26 | sim |
| `ENCERRAR_VINCULO` | Encerrar vínculo | `tipo`* (texto) | desligamento | 90 | sim |

- `CRIAR_CADASTRO`: Cria o registro do colaborador a partir dos dados de admissão.
- `ALTERAR_SITUACAO`: Altera a situação (ATIVO, AFASTADO, GARDEN_LEAVE, DESLIGADO) e registra o afastamento.
- `ALTERAR_LOTACAO`: Altera unidade, município, UF e centro de custo.
- `ALTERAR_SINDICATO`: Altera o sindicato conforme a base territorial da lotação.
- `ALTERAR_GESTOR`: Altera o gestor imediato.
- `INCLUIR_DEPENDENTE`: Inclui dependente no cadastro.
- `ENCERRAR_VINCULO`: Registra o encerramento do contrato de trabalho.

## DESENVOLVIMENTO

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `INCLUIR_PROGRAMA` | Incluir em programa com vigência | `programa`* (texto), `nome` (texto), `inicio`* (data), `fim`* (data), `aviso_dias` (numero), `concessoes` (objeto), `evento_aviso` (texto), `evento_vencimento` (texto) | programas, historico | 25 | sim |
| `RENOVAR_PROGRAMA` | Renovar programa | `programa`* (texto), `novo_fim`* (data), `motivo` (texto) | programas, historico | 26 | sim |
| `REGISTRAR_AVISO_PROGRAMA` | Registrar aviso de vencimento | `programa`* (texto) | programas | 27 | sim |
| `ENCERRAR_PROGRAMA` | Encerrar programa | `programa`* (texto), `status`* (texto), `motivo` (texto) | programas, historico | 28 | sim |

- `INCLUIR_PROGRAMA`: Registra o colaborador em um programa com início oficial, fim e eventos de aviso e vencimento agendados.
- `RENOVAR_PROGRAMA`: Estende a vigência de um programa ativo; aviso e vencimento são reagendados para o novo fim.
- `REGISTRAR_AVISO_PROGRAMA`: Marca que o aviso de vencimento do programa foi enviado.
- `ENCERRAR_PROGRAMA`: Encerra um programa ativo por vencimento (EXPIRADO) ou antecipadamente (ENCERRADO). Com programa '*', encerra todos.

## FOLHA

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `ALTERAR_CARGO` | Alterar cargo | `cargo`* (texto) | cargo, data_inicio_cargo, historico_cargos, historico | 30 | sim |
| `ALTERAR_SALARIO` | Alterar salário | `novo_salario`* (numero), `motivo` (texto) | salario_base, historico_salarial | 32 | sim |
| `APLICAR_REAJUSTE` | Aplicar reajuste percentual | `percentual`* (numero) | salario_base, historico_salarial | 33 | sim |
| `ADICIONAR_VERBA` | Adicionar verba | `codigo`* (texto), `nome` (texto), `valor`* (numero), `recorrente` (booleano), `origem` (texto), `competencia` (data) | verbas | 40 | sim |
| `AJUSTAR_VERBA` | Ajustar valor de verba | `codigo`* (texto), `valor`* (numero) | verbas | 41 | sim |
| `REMOVER_VERBA` | Remover verba | `codigo`* (texto) | verbas | 42 | sim |
| `CALCULAR_RESCISAO` | Calcular rescisão | `tipo`* (texto), `aviso` (texto) | rescisao | 60 | sim |

- `ALTERAR_CARGO`: Altera o cargo e reinicia a contagem de tempo no cargo.
- `ALTERAR_SALARIO`: Altera o salário base e registra no histórico salarial.
- `APLICAR_REAJUSTE`: Aplica reajuste percentual ao salário base (ex.: CCT).
- `ADICIONAR_VERBA`: Inclui uma verba de folha (gratificação, adicional, bônus).
- `AJUSTAR_VERBA`: Ajusta o valor de uma verba recorrente existente.
- `REMOVER_VERBA`: Remove uma verba da folha.
- `CALCULAR_RESCISAO`: Calcula verbas rescisórias (valores ilustrativos): saldo, aviso prévio proporcional, 13º, férias e multa do FGTS.

## PONTO

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `ALTERAR_JORNADA` | Alterar jornada | `horas`* (numero), `regime` (texto) | jornada_horas, regime_jornada | 35 | sim |
| `CONCEDER_LICENCA` | Conceder licença | `tipo`* (texto), `dias`* (numero) | licencas | 37 | sim |

- `ALTERAR_JORNADA`: Altera a jornada diária e o regime de controle.
- `CONCEDER_LICENCA`: Registra licença remunerada (maternidade, paternidade).

## BENEFICIOS

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `ADICIONAR_BENEFICIO` | Adicionar benefício | `codigo`* (texto), `nome` (texto), `plano` (texto), `valor` (numero) | beneficios | 50 | sim |
| `ALTERAR_BENEFICIO` | Alterar plano de benefício | `codigo`* (texto), `plano` (texto), `valor` (numero) | beneficios | 51 | sim |
| `REMOVER_BENEFICIO` | Remover benefício | `codigo`* (texto) | beneficios | 52 | sim |

- `ADICIONAR_BENEFICIO`: Provisiona benefício junto à operadora.
- `ALTERAR_BENEFICIO`: Altera plano ou valor de um benefício existente.
- `REMOVER_BENEFICIO`: Cancela benefício junto à operadora.

## IAM

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `CONCEDER_ACESSO` | Conceder acesso | `acesso`* (texto) | acessos | 70 | sim |
| `REVOGAR_ACESSO` | Revogar acesso | `acesso`* (texto) | acessos | 71 | sim |

- `CONCEDER_ACESSO`: Concede perfil de acesso em sistema.
- `REVOGAR_ACESSO`: Revoga perfil de acesso em sistema.

## PATRIMONIO

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `PROVISIONAR_EQUIPAMENTO` | Provisionar equipamento | `equipamento`* (texto) | equipamentos | 75 | sim |
| `RECOLHER_EQUIPAMENTO` | Recolher equipamento | `equipamento`* (texto) | equipamentos | 76 | sim |

- `PROVISIONAR_EQUIPAMENTO`: Entrega equipamento ao colaborador.
- `RECOLHER_EQUIPAMENTO`: Recolhe equipamento do colaborador.

## JURIDICO

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `INCLUIR_CLAUSULA` | Incluir cláusula contratual | `codigo`* (texto), `nome` (texto), `parametros` (objeto) | clausulas | 80 | sim |
| `REMOVER_CLAUSULA` | Remover cláusula contratual | `codigo`* (texto) | clausulas | 81 | sim |
| `REGISTRAR_ESTABILIDADE` | Registrar estabilidade | `tipo`* (texto), `inicio`* (data), `fim` (data), `base_legal` (texto) | estabilidades | 82 | sim |
| `INICIAR_GARDEN_LEAVE` | Iniciar garden leave | `dias`* (numero) | garden_leave | 84 | sim |

- `INCLUIR_CLAUSULA`: Inclui cláusula (garden leave, não concorrência).
- `REMOVER_CLAUSULA`: Remove cláusula contratual por aditivo.
- `REGISTRAR_ESTABILIDADE`: Registra período de estabilidade provisória.
- `INICIAR_GARDEN_LEAVE`: Inicia período de garden leave remunerado.

## SST

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `AGENDAR_EXAME` | Agendar exame ocupacional | `tipo`* (texto) | exames | 85 | sim |

- `AGENDAR_EXAME`: Agenda exame ocupacional (ASO) conforme o PCMSO.

## TREINAMENTO

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `REGISTRAR_TREINAMENTO` | Registrar treinamento obrigatório | `curso`* (texto) | treinamentos | 86 | sim |

- `REGISTRAR_TREINAMENTO`: Matricula em trilha obrigatória.

## ESOCIAL

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `ENVIAR_ESOCIAL` | Enviar evento eSocial | `evento`* (texto), `descricao` (texto) | esocial | 95 | sim |

- `ENVIAR_ESOCIAL`: Transmite evento ao eSocial (simulado).

## COMUNICACAO

| Código | Nome | Parâmetros (* obrigatório) | Altera | Ordem | Compensável |
| --- | --- | --- | --- | --- | --- |
| `NOTIFICAR` | Notificar | `destinatarios`* (lista), `assunto`* (texto), `mensagem` (texto) | - | 99 | não |

- `NOTIFICAR`: Envia comunicação a colaborador, gestor e áreas.
