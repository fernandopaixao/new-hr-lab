# 0014. Domínio em português, código em inglês, nenhum emoji

## Contexto

Definido com o usuário: interface, contratos e explicações em português; código em inglês; nunca usar emoji em nada da solução.

## Decisão

- Termos de domínio ficam em português em todo lugar onde uma pessoa lê: contratos, campos dos documentos (`colaborador`, `salario_base`, `elegibilidade`), status, mensagens de log, prompts e respostas dos agentes, interface e documentação.
- Nomes de módulos, classes, funções e comentários de código ficam em inglês.
- Nenhum emoji em código, interface, contratos, documentação, commits ou respostas. O agente de perguntas remove emoji que o modelo eventualmente produza.

## Consequências

- Os campos dos documentos JSON estão em português mesmo dentro do código em inglês. Isso é intencional: eles são o vocabulário compartilhado com quem escreve contratos.
