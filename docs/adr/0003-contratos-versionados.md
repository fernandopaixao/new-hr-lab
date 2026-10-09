# 0003. Contratos versionados em YAML, em quatro tipos, com vigência

## Contexto

Os contratos devem descrever o estado desejado e o estado de compliance de cada situação de cargo (executivos têm garden leave, média gerência tem celular corporativo) e contemplar CLT, sindicato e CCT dos bancários. A interface deve permitir incluir e remover operações e regras e mudar vigências.

## Decisão

Separar quatro tipos de contrato, cada um com uma responsabilidade:

| Tipo | Responde | Exemplo |
| --- | --- | --- |
| `NORMA` | O que a lei e a convenção exigem de todos | jornada de 6h, pisos, VR e VA, auxílio-creche, estabilidades, irredutibilidade |
| `POLITICA` | Parâmetros internos da empresa | interstício mínimo, limite de aumento, janela de advertências |
| `CARGO` | Como deve estar quem ocupa o cargo | faixa salarial, gratificação, benefícios, acessos, equipamentos, cláusulas; regras de entrada; compliance permanente |
| `PROCESSO` | Como tratar um tipo de evento | esquema do evento, cargo alvo, elegibilidade, orquestração, conferência do plano, auditoria, fan-out coletivo |

Todo contrato tem `codigo`, `versao` e `vigencia` (início e fim). O motor resolve a versão vigente na **data efetiva do evento**, não na data de processamento. Salvar pela interface cria uma nova versão ou sobrescreve a atual, sempre com validação (expressões compiladas, operações existentes, parâmetros obrigatórios) e registro no log. Os exemplos ficam em YAML em `seeds/contracts` e podem ser restaurados.

## Alternativas consideradas

- **Regras em código** (uma classe por processo). Mais rápido de escrever, mas tira o controle das mãos de quem conhece as regras e impede mudar a vigência sem deploy.
- **Um motor de regras de mercado** (Drools, DMN). É poderoso, mas tem uma curva de aprendizado alta, e a explicação das decisões fica menos natural para o RH.
- **Um contrato único por processo** contendo tudo. Repetiria as regras da CLT e do cargo em cada processo, e uma mudança na CCT exigiria alterar dezenas de contratos.

## Consequências

- Uma mudança na CCT (por exemplo, o valor do VR) é uma nova versão da norma, com vigência a partir da data-base; eventos com data efetiva anterior continuam usando a versão antiga.
- O estado alvo do cargo é a fonte da verdade para benefícios, verbas, acessos e equipamentos. Ele alimenta o plano (ADR 0005), a auditoria e a conferência de conformidade dos colaboradores.
- O caso guarda a versão do processo usada, e o reprocessamento usa a mesma versão.
