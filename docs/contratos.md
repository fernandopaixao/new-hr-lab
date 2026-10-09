# Contratos

Os contratos descrevem o comportamento das operações de RH sem código. Há quatro tipos (veja a [ADR 0003](adr/0003-contratos-versionados.md)). Os exemplos ficam em `backend/hrlab/seeds/contracts/` e podem ser editados pela tela Contratos, no editor estruturado ou em YAML.

## Campos comuns

| Campo | Obrigatório | Descrição |
| --- | --- | --- |
| `codigo` | sim | Identificador estável, por exemplo `PROC_PROMOCAO` ou `CARGO_COORDENADOR`. |
| `tipo` | sim | `NORMA`, `POLITICA`, `CARGO` ou `PROCESSO`. |
| `nome` | sim | Nome para pessoas. |
| `versao` | gerado | Número da versão. Salvar como nova versão incrementa. |
| `vigencia` | sim | `{inicio: AAAA-MM-DD, fim: AAAA-MM-DD ou null}`. A versão usada é a vigente na data efetiva do evento. |
| `descricao` | não | Texto livre. |

## Regras

Regras aparecem na norma (`compliance`), no cargo (`elegibilidade_entrada`, `compliance`) e no processo (`elegibilidade.regras`, `conferencia_plano.regras`, `auditoria.verificacoes`). As duas últimas seções são avaliadas juntas no estágio de auditoria, antes da execução. Todas têm o mesmo formato:

```yaml
- id: PRM-05
  descricao: Interstício mínimo no cargo atual
  expressao: "meses_no_cargo >= politica.promocao.meses_minimos_no_cargo"
  tipo: EXCECIONAVEL          # BLOQUEANTE | EXCECIONAVEL | ALERTA
  aprovadores: [HRBP]         # obrigatório quando EXCECIONAVEL
  base_legal: Política de movimentação interna
  explicacao_falha: "Colaborador está há {meses_no_cargo} meses no cargo; mínimo de {politica.promocao.meses_minimos_no_cargo}."
```

- A `expressao` deve ser **verdadeira para a regra ser atendida**.
- `BLOQUEANTE` barra o caso. `EXCECIONAVEL` barra até que uma das personas em `aprovadores` aprove. `ALERTA` só registra.
- `explicacao_falha` aceita `{expressao}`, que é substituída pelo valor no momento da avaliação.
- Os ids precisam ser únicos dentro do contrato. A validação compila todas as expressões antes de salvar.

## Expressões

As expressões usam a sintaxe do Python, avaliada por um interpretador seguro ([ADR 0004](adr/0004-avaliador-de-expressoes-seguro.md)). São aceitos comparações, `and`, `or`, `not`, `in`, aritmética, `x if c else y`, listas, acesso a atributos (`colaborador.conduta.advertencias`) e as funções abaixo. Atributos ausentes valem `None`.

Em parâmetros de operação, valores de verbas e benefícios e condições `quando`, um texto que começa com `=` é uma expressão: `novo_salario: "=round(colaborador.salario_base * 1.05, 2)"`.

### Variáveis

| Nome | Conteúdo |
| --- | --- |
| `colaborador` | Cadastro atual. Na auditoria, é o estado projetado pelo plano. |
| `anterior` | Cadastro antes da execução (auditoria). |
| `gestor`, `cargo_do_gestor` | Cadastro e contrato de cargo do gestor imediato (vazios no topo da organização). |
| `subordinados_diretos`, `niveis_acima` | Tamanho da equipe direta e quantos gestores há acima na cadeia. |
| `evento` | O evento, com `tipo`, `data_efetiva`, `dados` e `colaborador_id`. |
| `hoje` | Data efetiva do evento (AAAA-MM-DD). |
| `norma`, `politica` | Parâmetros (`parametros`) da norma e da política vigentes. |
| `cargo_atual`, `cargo_destino` | Contratos de cargo atual e alvo, com `nivel`, `segmento`, `familia`, `cargo_confianca` e `estado_alvo`. |
| `idade`, `meses_de_casa`, `anos_de_casa` | Calculados na data efetiva. |
| `meses_no_cargo`, `meses_na_unidade`, `meses_desde_ultimo_aumento`, `dias_afastado` | Calculados na data efetiva. |

### Funções

| Função | Retorna |
| --- | --- |
| `possui_beneficio(codigo)`, `plano_beneficio(codigo)` | Se tem o benefício e qual plano. |
| `possui_verba(codigo)`, `valor_verba(codigo)` | Se tem a verba e a soma dos valores. |
| `possui_certificacao(codigo)`, `possui_acesso(codigo)`, `possui_equipamento(codigo)` | Verdadeiro ou falso. |
| `possui_clausula(codigo)`, `parametro_clausula(codigo, parametro)` | Cláusulas contratuais (garden leave, não concorrência...). |
| `estabilidade_ativa(tipo=None)` | Se há estabilidade vigente na data (GESTANTE, ACIDENTARIA, CIPA, DIRIGENTE_SINDICAL, PRE_APOSENTADORIA...). |
| `dependentes_menores_de(meses)` | Quantidade de dependentes até a idade em meses. |
| `escolaridade_ao_menos(nivel)` | Compara com a escala de escolaridade. |
| `sindicato_da_uf(uf)` | Código do sindicato da base territorial, pela norma. |
| `advertencias_ultimos_meses(meses)` | Advertências na janela. |
| `operacao_executada(codigo)` | Na auditoria, antes da execução: se a operação está no plano. A conferência final depois prova que cada operação planejada tem recibo. |
| `gestor_da_unidade(unidade)` | Matrícula do responsável pela unidade com nível acima do colaborador, ou vazio. |
| `cpf_valido(cpf)`, `cpf_em_uso(cpf)` | Dígito verificador e duplicidade entre colaboradores ativos. |
| `somar_meses(data, n)`, `meses_entre(a, b)`, `dias_entre(a, b)`, `anos_entre(a, b)`, `data(texto)` | Datas. |
| `cargo(codigo)` | Contrato de um cargo qualquer. |
| `len`, `min`, `max`, `abs`, `round`, `sum`, `any`, `all`, `int`, `float`, `str`, `bool`, `vazio(x)` | Utilitários. |

## Norma (`NORMA`)

```yaml
parametros:            # valores usados nas expressões como norma.<nome>
  piso_escritorio: 3600.0
  vr_valor_dia: 52.0
  sindicatos:
    - {codigo: SEEB-SP, nome: Sindicato dos Bancários de São Paulo, ufs: [SP]}
beneficios:            # benefícios garantidos a todos, com condição
  - codigo: VR
    nome: Vale-refeição
    plano: CCT
    valor: "=norma.vr_valor_dia * norma.vr_dias_mes"
    quando: "=colaborador.situacao in ['ATIVO', 'GARDEN_LEAVE']"
estado_por_situacao:   # o que muda no estado alvo conforme a situação do vínculo
  DESLIGADO: {beneficios: [], verbas: [], acessos: [], equipamentos: []}
  AFASTADO: {acessos: [EMAIL]}
compliance:            # regras que valem para qualquer colaborador, a qualquer momento
  - id: NRM-01
    ...
```

## Política (`POLITICA`)

Contém só `parametros`, usados como `politica.<grupo>.<nome>`. Por exemplo, `politica.promocao.meses_minimos_no_cargo` e `politica.conduta.max_advertencias`.

## Cargo (`CARGO`)

```yaml
cargo: GERENTE_AGENCIA
familia: GESTAO
segmento: MEDIA_GESTAO       # OPERACIONAL | TECNICO | MEDIA_GESTAO | EXECUTIVO
nivel: 6
cargo_confianca: true
estado_alvo:                 # como deve estar quem ocupa o cargo
  regime_jornada: GESTAO_62_II
  jornada_horas: 8
  faixa_salarial: {min: 15000, max: 24000}
  verbas:
    - {codigo: GRAT_GESTAO, nome: Gratificação de gestão, valor: "=round(colaborador.salario_base * norma.gratificacao_gestao_min_percentual / 100, 2)"}
  beneficios:
    - {codigo: SAUDE, nome: Plano de saúde, plano: PLATINA}
  acessos: [EMAIL, CRM_VAREJO, CREDITO_ALCADA_3]
  equipamentos: [NOTEBOOK, CELULAR_CORPORATIVO]
  clausulas: []              # executivos: GARDEN_LEAVE, NAO_CONCORRENCIA com parâmetros
  certificacoes_exigidas: [CPA-20]
elegibilidade_entrada:       # avaliadas quando alguém entra no cargo (promoção, admissão, reversão)
  - id: GAG-ENT-01
    ...
compliance:                  # avaliadas sempre: conferência, auditoria e varreduras de conformidade
  - id: GAG-CMP-01
    descricao: Média gerência possui celular corporativo
    expressao: "colaborador.situacao != 'ATIVO' or possui_equipamento('CELULAR_CORPORATIVO')"
    tipo: BLOQUEANTE
```

O **estado alvo** de um colaborador é o estado alvo do cargo somado aos benefícios da norma que se aplicam e ao sindicato da UF, ajustado pela situação do vínculo. É o que o planejamento persegue e o que a auditoria e a conferência de conformidade cobram. As regras de compliance do cargo não se aplicam a desligados.

## Processo (`PROCESSO`)

```yaml
evento: colaborador.promovido
evento_schema:
  obrigatorios: [dados.cargo_destino]
  colaborador: DEVE_EXISTIR          # DEVE_EXISTIR | NAO_DEVE_EXISTIR (admissão) | NAO_SE_APLICA (coletivo)
cargo_alvo: "=evento.dados.cargo_destino"   # vazio: o cargo atual
elegibilidade:
  incluir_entrada_cargo_alvo: true   # soma as regras de entrada do cargo alvo
  regras: [...]
orquestracao:
  derivar_estado_alvo: true          # acrescenta operações pela diferença com o estado alvo
  operacoes:
    - operacao: ALTERAR_SALARIO
      quando: "=max(evento.dados.novo_salario or 0, cargo_destino.estado_alvo.faixa_salarial.min) > colaborador.salario_base"
      parametros:
        novo_salario: "=max(evento.dados.novo_salario or 0, colaborador.salario_base, cargo_destino.estado_alvo.faixa_salarial.min)"
      motivo: Novo salário é o maior entre o proposto, o atual e o mínimo da faixa.
      base_legal: CF art. 7 VI
conferencia_plano:
  regras: [...]                      # avaliadas na auditoria, sobre o estado projetado; `anterior` é o estado atual
auditoria:
  sla_horas: 48
  incluir_compliance: true           # soma o compliance da norma e do cargo
  verificacoes: [...]                # também avaliadas antes da execução, sobre o estado projetado
coletivo:                            # só para eventos coletivos
  gera_evento: cct.reajuste_individual
  selecao: "colaborador.situacao != 'DESLIGADO'"
  dados: {percentual: "=evento.dados.percentual"}
```

Um evento coletivo não altera ninguém diretamente: o gatilho seleciona os colaboradores pela expressão `selecao` e abre um caso filho por pessoa, com o evento `gera_evento` e os `dados` resolvidos.

## Exemplos de mudanças para experimentar

| Mudança | Onde | Efeito esperado |
| --- | --- | --- |
| Reduzir `politica.promocao.meses_minimos_no_cargo` de 12 para 4 | Política | Cenário "Promoção sem interstício" (5 meses no cargo) deixa de pedir exceção |
| Incluir um item em `estado_alvo.equipamentos` de um cargo | Cargo | Promoções para o cargo provisionam o item (operação derivada); a conformidade aponta quem já está no cargo sem ele |
| Trocar `PRM-08` (processo disciplinar) de `EXCECIONAVEL` para `BLOQUEANTE` | Processo de promoção | O cenário "Promoção com processo disciplinar" passa a terminar em "Não elegível" |
| Remover `ENVIAR_ESOCIAL` da orquestração da promoção | Processo de promoção | A auditoria (regras ou agente) aponta o eSocial faltando antes de executar |
| Remover `CALCULAR_RESCISAO` da orquestração do desligamento | Processo de desligamento | A auditoria rejeita o plano antes da execução, sem alterar nenhum sistema |
| Nova versão da norma com `vr_valor_dia` maior e vigência futura | Norma | Eventos com data efetiva antes da vigência usam o valor antigo |
