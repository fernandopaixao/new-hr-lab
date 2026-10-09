# 0009. Aprovações por persona, sem login, sempre registradas

## Contexto

O laboratório precisa de aprovações de exceção com decisões registradas. Definido com o usuário: troca de persona sem login real, e toda decisão registrada.

## Decisão

- Sete personas fixas: Operador de RH, Gestor imediato, HRBP, Jurídico, Compliance, Auditoria interna e Comitê de remuneração. A persona ativa é escolhida no topo da interface e enviada no cabeçalho `X-Persona`.
- Cada regra excecionável declara quais personas podem aprovar. A API recusa (403) decisões de outras personas.
- Toda decisão exige justificativa de pelo menos 5 caracteres e grava quem decidiu, quando, o quê e por quê no caso, na aprovação e no log.
- Há três tipos de aprovação: exceção de elegibilidade, revisão do plano e revisão da auditoria.

## Alternativas consideradas

- **Autenticação real** (OIDC). Necessária em produção, mas atrapalharia a experimentação, que depende de alternar papéis rapidamente.

## Consequências

- Não há segurança de acesso: o laboratório não deve ser exposto fora da máquina ou da rede de testes.
- **Em produção:** a persona viria do token do usuário e as alçadas de um sistema de identidade; o registro das decisões continua igual.
