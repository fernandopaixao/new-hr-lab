# Glossário

## RH e regulação

| Termo | Significado no laboratório |
| --- | --- |
| CLT | Consolidação das Leis do Trabalho. Base das regras da norma (jornada, rescisão, estabilidades, irredutibilidade). |
| CCT | Convenção coletiva de trabalho. Aqui, a dos bancários, com valores **ilustrativos e fictícios** (piso, VR, VA, auxílio-creche, gratificação de função, PLR). |
| FENABAN | Federação Nacional dos Bancos, parte patronal da CCT dos bancários. |
| Sindicato da base territorial | Sindicato que representa o colaborador conforme a UF de trabalho. A norma lista os sindicatos e as UFs. |
| Jornada de 6 horas | Regra geral do bancário (CLT art. 224). |
| Cargo de confiança | Função com jornada de 8 horas e gratificação de pelo menos um terço do salário (CLT art. 224, par. 2). |
| Cargo de gestão (art. 62, II) | Gerentes sem controle de jornada; no laboratório, `regime_jornada: GESTAO_62_II`. |
| Gratificação de função | Verba paga a cargos de confiança e de gestão, em percentual do salário. |
| Irredutibilidade salarial | Proibição de reduzir salário (CF art. 7, VI). Regra presente em promoções e transferências. |
| Interstício | Tempo mínimo no cargo antes de uma nova promoção, definido na política. |
| Estabilidade | Período em que o desligamento sem justa causa é vedado: gestante, acidentária, membro da CIPA, dirigente sindical, pré-aposentadoria (cláusula da CCT). |
| Garden leave | Afastamento remunerado de executivos entre o aviso de saída e o fim do vínculo, previsto em cláusula. Situação `GARDEN_LEAVE`. |
| Não concorrência | Cláusula que restringe trabalhar para concorrentes por um período, com compensação. |
| Certificação CPA-20 | Certificação da ANBIMA exigida, nos contratos de exemplo, para cargos que atendem clientes em investimentos. |
| eSocial | Sistema do governo que recebe os eventos trabalhistas. A prateleira tem `ENVIAR_ESOCIAL`. |
| Rescisão | Cálculo de verbas no desligamento (CLT art. 477). |
| Mérito | Aumento salarial sem mudança de cargo, por desempenho. |
| Reajuste coletivo | Aumento definido pela CCT, aplicado a todos os elegíveis. No laboratório é um evento coletivo. |

## Arquitetura

| Termo | Significado |
| --- | --- |
| Evento | Fato de negócio com tipo, colaborador, data efetiva e dados. Dispara um caso. |
| Data efetiva | Data em que o evento produz efeito. Escolhe as versões vigentes dos contratos e é o "hoje" das expressões. |
| Caso | Registro de um evento atravessando a linha, com tudo o que aconteceu nele. |
| Evento coletivo | Evento sem colaborador, que gera um caso filho por pessoa selecionada. |
| Linha de produção | Sequência fixa de seis estágios: gatilho, elegibilidade, planejamento, conferência do plano, execução e auditoria. |
| Estágio ou estação | Uma etapa da linha, com fila própria no Redis. |
| Contrato | Documento versionado que descreve regras e estado alvo: norma, política, cargo ou processo. |
| Vigência | Período em que uma versão de contrato vale. |
| Regra | Expressão que deve ser verdadeira, com tipo (bloqueante, excecionável, alerta), base legal e explicação de falha. |
| Exceção | Aprovação humana que libera uma regra excecionável que falhou. |
| Estado alvo (to-be) | Como o colaborador deve estar, pelo cargo e pela norma: jornada, faixa, verbas, benefícios, acessos, equipamentos, cláusulas. |
| Conformidade (compliance) | Regras que valem sempre para o cargo ou para todos, conferidas no plano, na auditoria e na tela Colaboradores. |
| Desvio | Diferença entre o cadastro e o estado alvo. Pode ser injetado para testes. |
| Prateleira | Catálogo de operações reutilizáveis que alteram sistemas. |
| Operação | Item da prateleira: parâmetros, campos alterados, aplicação e compensação. |
| Operação derivada | Operação acrescentada ao plano pela diferença entre o estado atual e o estado alvo. |
| Plano | Lista ordenada de operações escolhidas, com motivo e base legal, e das operações descartadas. |
| Estado projetado | Cópia do colaborador com o plano aplicado em simulação, usada na conferência. |
| Recibo | Comprovante de uma operação executada: protocolo, sistema, antes e depois. |
| Saga | Execução em passos com compensação dos passos já feitos em caso de falha. |
| Compensação | Desfazer de uma operação, restaurando os campos que ela declarou alterar. |
| Reversão | Compensação da execução inteira depois de uma auditoria reprovada e confirmada. |
| Replanejamento | Volta ao planejamento quando o cadastro mudou entre o plano e a execução. |
| Agente de conferência | Modelo de linguagem que audita plano e execução e recomenda APROVADO ou REPROVADO. |
| Agente simulado (heurístico) | Substituto opcional do agente quando o Ollama está fora; toda decisão dele é marcada. |
| Persona | Papel que decide aprovações (Operador, Gestor, HRBP, Jurídico, Compliance, Auditoria, Comitê). Não há login. |
| Log de decisões | Registro append-only de tudo o que foi decidido e por quê. |
| Fatos | Linha plana por caso, usada pelo painel e pelo agente de perguntas para contar e agregar. |
| Embedding | Vetor numérico que representa o significado de um texto; permite busca por semelhança. |
| Índice vetorial | Conjunto de embeddings dos casos e das decisões, mantido pelo indexador. |
| Agente de perguntas | Agente que responde perguntas em linguagem natural com números dos fatos e documentos do índice. |
| Grupo de consumidores | Recurso dos Redis Streams que entrega cada mensagem a um único worker. |
| SSE | Server-Sent Events: canal da API para a interface receber atualizações ao vivo. |
