# 0019. Hierarquia por gestor imediato, usada nas regras e nas aprovações

## Contexto

Fernando pediu uma hierarquia. O cadastro já tinha `gestor_id`, preenchido pelo gerador do time, mas nada usava esse campo: a persona Gestor era uma pessoa fixa ("Marcos Teixeira") para qualquer colaborador.

## Decisão

- **Fonte única:** `gestor_id` no cadastro. A organização gerada tem diretoria, superintendências, coordenações na sede e gerentes de agência; todo colaborador, menos a diretoria, tem um gestor imediato de nível igual ou superior.
- **Contexto das regras:** `gestor` (cadastro do gestor imediato), `cargo_do_gestor`, `subordinados_diretos`, `niveis_acima` e `gestor_da_unidade(unidade)`, que devolve o responsável pela unidade com nível acima do colaborador.
- **Regras e operações nos contratos de exemplo:**
  - admissão e transferência definem o gestor imediato (informado no evento ou o responsável pela unidade de destino) com `ALTERAR_GESTOR`;
  - promoção emite alerta se o cargo de destino ficar acima do cargo do gestor (`PRM-HIER`);
  - desligamento de quem tem equipe emite alerta para definir o novo gestor (`DSL-HIER`).
- **Aprovações:** quando uma regra pede `GESTOR`, a aprovação guarda o gestor imediato real do caso (`responsavel`), e a interface e o log mostram o nome. A persona Gestor continua sendo quem decide, porque não há login (ADR 0009).
- **Interface:** organograma navegável na tela Colaboradores e cadeia de gestão e equipe direta no perfil.

## Alternativas consideradas

- **Estrutura organizacional separada (unidades com responsável).** Mais fiel a um sistema real, mas exigiria um novo cadastro e um novo tipo de contrato. O gestor imediato no colaborador cobre o que o laboratório precisa.
- **Uma persona por gestor real.** Exigiria login ou centenas de personas; contraria a ADR 0009.

## Consequências

- As regras novas estão nos contratos de exemplo. Uma instalação existente recebe essas regras com "Restaurar contratos de exemplo" na tela Contratos, que descarta versões editadas.
- O responsável por uma unidade é calculado a partir do cadastro, então uma transferência para uma unidade inexistente não muda o gestor.
