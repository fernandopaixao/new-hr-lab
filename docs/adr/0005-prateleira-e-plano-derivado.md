# 0005. Prateleira desacoplada e plano derivado do estado alvo

## Contexto

Operações como adicionar ou remover benefício, alterar salário ou incluir verba de bônus devem ficar numa prateleira, para serem chamadas e parametrizadas de forma desacoplada do processo.

## Decisão

1. Cada operação da prateleira (`shelf.py`) declara código, nome, sistema de destino, parâmetros tipados, **campos do cadastro que altera**, ordem de execução e se é compensável. A implementação recebe o colaborador e os parâmetros e devolve uma descrição legível.
2. O plano de um caso combina duas fontes:
   - **operações explícitas** do contrato de processo, com parâmetros em expressão, condição `quando`, motivo e base legal;
   - **operações derivadas** da diferença entre o estado atual do colaborador e o **estado alvo** calculado pelo contrato do cargo e pela norma (benefícios, verbas, acessos, equipamentos, cláusulas, jornada, sindicato, piso).
3. O planejamento roda as explícitas em simulação antes de calcular a diferença, para não duplicar o que o processo já faz. Operações descartadas (condição falsa ou já atendida) ficam no plano com o motivo.

## Alternativas consideradas

- **Só operações explícitas no processo.** Cada processo precisaria listar todas as consequências de uma mudança de cargo, e um novo benefício no cargo exigiria alterar todos os processos.
- **Só estado alvo** (reconciliação pura, como um operador do Kubernetes). Perde ações que não são estado, como eSocial, exame e notificação, e perde o motivo de negócio de cada passo.

## Consequências

- Incluir o celular corporativo no cargo de coordenador faz todas as promoções para coordenador provisionarem o aparelho, e a conferência de conformidade passa a apontar quem ainda não o tem.
- A mesma operação pode ser executada de forma avulsa pela tela Prateleira, simulada ou aplicada, com registro no log.
- Os campos declarados por operação tornam a compensação genérica (ADR 0008).
