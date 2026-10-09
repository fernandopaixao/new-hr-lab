# 0004. Regras como expressões avaliadas por um interpretador seguro

## Contexto

As regras dos contratos precisam ser escritas e alteradas pela interface, por pessoas que não programam, e ainda assim cobrir situações reais: "meses no cargo maior que o interstício da política", "possui CPA-20", "dependentes menores de 71 meses". Executar código vindo da interface seria um risco.

## Decisão

Regras e parâmetros são **expressões** com sintaxe de Python, avaliadas por um interpretador próprio (`expr.py`). Ele percorre a AST e aceita apenas uma lista fechada de nós: comparações, operadores aritméticos e lógicos, acesso a atributos, índices, listas, condicionais e chamadas a funções do vocabulário. Atributos com sublinhado, importações, lambdas e qualquer função fora do vocabulário são recusados.

O vocabulário (`context.py`) expõe os dados do caso (`colaborador`, `anterior`, `evento`, `cargo_atual`, `cargo_destino`, `norma`, `politica`), valores calculados (`meses_no_cargo`, `idade`, `dias_afastado`) e funções de domínio (`possui_certificacao`, `estabilidade_ativa`, `advertencias_ultimos_meses`...). Parâmetros que começam com `=` são expressões; textos de explicação aceitam `{expressao}`.

## Alternativas consideradas

- **`eval` do Python com restrições.** É fácil de contornar.
- **Uma linguagem própria com parser** (ou JSONLogic). Seria mais segura por construção, porém mais verbosa e menos legível para regras de negócio.
- **CEL ou JMESPath.** São boas opções em produção, mas exigiriam mapear todas as funções de domínio.

## Consequências

- As explicações de falha mostram valores reais, por exemplo: "Colaborador está há 5 meses no cargo; mínimo de 12."
- Os erros de expressão aparecem na validação do contrato, antes de salvar.
- Novas funções de domínio exigem código, mas um único ponto (`context.py`).
