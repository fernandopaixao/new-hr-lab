# Visão geral

## O problema

Boa parte das operações de RH segue o mesmo roteiro, ainda que cada uma pareça única:

1. Algo acontece: uma promoção é aprovada, alguém é admitido, a convenção coletiva reajusta salários.
2. Alguém confere se a operação é permitida: tempo mínimo no cargo, processo disciplinar, formação, estabilidade, regras da CLT e da CCT.
3. Se for permitida, ou se uma exceção for aprovada, vários sistemas são alterados: cargo, salário, benefícios, acessos, equipamentos, eSocial.
4. Alguém confere, com base em um contrato de serviço, se tudo foi aplicado corretamente.

Em sistemas tradicionais esse roteiro fica espalhado em telas, planilhas, workflows e integrações ponto a ponto. As regras ficam escondidas no código, as exceções em e-mails e a auditoria acontece meses depois, por amostragem.

## A proposta

O laboratório trata cada operação de RH como um **evento** que percorre uma **linha de produção** com estágios fixos. O comportamento de cada operação não fica no código: ele é descrito em **contratos** versionados. As alterações nos sistemas são feitas por **operações** reutilizáveis de uma **prateleira**. Cada estágio deixa registrada a decisão e a explicação.

```
            +---------+   +---------------+   +--------------+   +-------------+   +----------+   +-----------+
 evento --> | Gatilho |-->| Elegibilidade |-->| Planejamento |-->| Conferência |-->| Execução |-->| Auditoria |--> decisão final
            +---------+   +---------------+   +--------------+   |  do plano   |   |  (saga)  |   +-----------+
                 |               |                               +-------------+        |               |
                 v               v                                      |               v               v
             rejeitado     não elegível ou                       revisão humana    compensação    revisão humana
             duplicado     exceção (aprovação)                    se reprovado      e reversão      e reversão
```

### Conceitos

| Conceito | O que é | Onde está |
| --- | --- | --- |
| Evento | Fato de negócio com tipo, colaborador, data efetiva e dados. É suficiente para disparar e alimentar todo o fluxo. | Interface, gerador de cenários, `POST /api/events` |
| Caso | Registro de um evento na linha: estágio atual, decisões, plano, recibos, aprovações, auditoria e trilha. | Redis (`hr:case:*`) |
| Contrato de norma | Regras e parâmetros regulatórios que valem para todos (CLT e CCT dos bancários). | `seeds/contracts/norma_clt_cct_bancarios.yaml` |
| Contrato de política | Parâmetros internos da empresa (interstício, limites de aumento, conduta). | `seeds/contracts/politica_movimentacao.yaml` |
| Contrato de cargo | Estado alvo de quem ocupa o cargo (jornada, faixa, verbas, benefícios, acessos, equipamentos, cláusulas), regras de entrada e compliance permanente. | `seeds/contracts/cargos.yaml` |
| Contrato de processo | Para um tipo de evento: esquema, elegibilidade, orquestração e auditoria (regras do plano e verificações do contrato de serviço). | `seeds/contracts/processos.yaml` |
| Prateleira | Catálogo de operações desacopladas, parametrizáveis e compensáveis. | `backend/hrlab/shelf.py` |
| Agente de conferência | Modelo de linguagem (Ollama local por padrão, ou Claude, OpenAI ou Gemini na nuvem) que audita o plano e a execução e recomenda APROVADO ou REPROVADO. | `backend/hrlab/agent.py` |
| Aprovação | Decisão humana de uma persona sobre uma exceção ou uma revisão, sempre com justificativa. | Tela Aprovações |
| Log de decisões | Registro append-only de cada regra, escolha, execução, compensação, recomendação e aprovação, com explicação. | Tela Log, `audit-log.jsonl` |

## Como um evento atravessa a linha

O exemplo é a promoção de um analista júnior para analista pleno.

1. **Gatilho.** O evento `colaborador.promovido` chega com `cargo_destino` e `novo_salario`. O gatilho garante idempotência (o mesmo evento não abre dois casos), encontra o contrato de processo vigente na data efetiva, valida o esquema e confirma que o colaborador existe.
2. **Elegibilidade.** As regras do processo de promoção (situação ativa, interstício, avaliação, conduta, irredutibilidade, limite de aumento) e as regras de entrada do cargo destino são avaliadas. Cada regra tem tipo: `BLOQUEANTE` barra; `EXCECIONAVEL` barra até que uma persona aprove a exceção; `ALERTA` só registra. O resultado é `ELEGIVEL`, `EXCECAO_NECESSARIA` ou `NAO_ELEGIVEL`, com a explicação de cada regra.
3. **Planejamento.** O motor calcula o **estado alvo** do colaborador pelo contrato do cargo destino e pela norma. O plano junta as operações explícitas do processo (alterar cargo, alterar salário, eSocial) com as operações **derivadas** da diferença entre o estado atual e o estado alvo (por exemplo, trocar o plano de saúde ou conceder um acesso). Cada operação traz o motivo e a base legal. As operações descartadas também são explicadas.
4. **Auditoria.** Antes de qualquer sistema ser alterado, o plano é aplicado em simulação sobre uma cópia do colaborador e a auditoria avalia, sobre esse estado projetado, as regras do plano, as verificações do contrato de serviço, o compliance da norma e do cargo e o estado alvo. O agente de IA recebe o caso e recomenda APROVADO ou REPROVADO, com achados. Regra bloqueante rejeita sem alterar nada; exceção ou parecer contrário do agente vai para uma pessoa. Só o que passa aqui é executado ([ADR 0018](adr/0018-auditoria-antes-da-execucao.md)).
5. **Execução.** As operações são aplicadas em ordem, cada uma com recibo e protocolo. Se uma falha, a saga compensa as já aplicadas, restaurando os campos que elas alteraram. Uma trava por colaborador impede que dois casos alterem a mesma pessoa ao mesmo tempo, e um controle de versão força o replanejamento se o cadastro mudou depois do plano.
6. **Conferência final.** Prova que o executado é igual ao auditado: todas as operações têm recibo e o estado final é igual ao projetado. O agente confere a execução. Uma divergência vai para a auditoria interna; se ela confirmar, a execução é revertida.

Ao final o caso recebe uma decisão com explicação, por exemplo: "Concluído. Execução igual à auditada e com recibos; agente recomenda APROVADO."

Em todas as fases o caso diz o **próximo passo**: o que acontece agora, quem precisa agir e o que aprovar ou rejeitar provoca ([ADR 0020](adr/0020-proximo-passo-explicito.md)). Quando uma regra pede o Gestor, a aprovação mostra o gestor imediato real do colaborador ([ADR 0019](adr/0019-hierarquia-e-gestor-imediato.md)).

## O que o laboratório permite experimentar

- Ajustar colaboradores (cargo, datas, salário, conduta, estabilidades, dependentes) e ver como a elegibilidade muda.
- Alterar contratos (incluir ou remover regras e operações, mudar vigências) e salvar como nova versão, sem tocar no código.
- Disparar 54 cenários reais, de exceção, de bloqueio, coletivos e de estresse, ou eventos manuais e rajadas.
- Pausar a linha ou uma estação, parar antes de um estágio, avançar passo a passo, editar o evento e reprocessar.
- Decidir exceções com personas diferentes e ver cada decisão registrada.
- Incluir alguém no programa de alto potencial, avançar o relógio simulado e ver o aviso e o vencimento passarem pela linha e retirarem o que o programa concedia.
- Injetar falhas para exercitar a compensação, e escalar workers para observar concorrência.
- Acompanhar a operação no painel Visão e fazer perguntas em linguagem natural sobre todos os eventos.
