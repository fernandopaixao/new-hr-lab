# Novo RH para as áreas de negócio

Este documento apresenta a solução para quem decide e opera RH: diretoria de Pessoas, HRBPs, folha, benefícios, jurídico trabalhista, compliance, auditoria interna e gestores. Não exige conhecimento técnico. Os detalhes de implementação estão nos outros documentos da pasta.

## Em uma frase

Toda operação de RH (promoção, admissão, transferência, desligamento, reajuste da convenção, afastamento, bônus, programas com prazo) passa pela mesma linha de produção, que confere se ela é permitida, planeja o que precisa mudar em cada sistema, audita o plano antes de tocar em qualquer coisa, executa com garantia de desfazer em caso de falha e prova, no final, que o executado é igual ao aprovado. Cada decisão fica explicada.

## O problema que resolve

| Hoje, em muitas empresas | Com a solução |
| --- | --- |
| Regras espalhadas em telas, planilhas, e-mails e na cabeça de especialistas | Regras escritas em contratos legíveis, versionados e com vigência, que o próprio RH edita |
| Cada tipo de movimentação tem um fluxo próprio, com integrações ponto a ponto | Um único fluxo para todas as operações, com estágios fixos e operações reutilizáveis |
| Exceções aprovadas por e-mail, sem rastro | Exceções pedidas pela própria regra, decididas pela pessoa certa, com justificativa registrada |
| Auditoria por amostragem, meses depois | Auditoria de 100% dos casos, antes da execução, e conferência final depois |
| "Por que fulano não foi promovido?" exige investigação | Cada caso mostra que regra barrou, com o valor encontrado e o mínimo exigido |
| Falha no meio da operação deixa sistemas inconsistentes | A execução é uma saga: se um passo falha, os anteriores são desfeitos |
| Benefícios, acessos e equipamentos esquecidos depois de uma movimentação | O plano é calculado a partir do estado alvo do cargo; o que falta é acrescentado sozinho |
| Programas com prazo vencem sem ninguém perceber | A agenda de vigências avisa antes e retira o que o programa concedia na data certa |

## O que a solução entrega

### 1. Um fluxo único para todas as operações

```
evento -> gatilho -> elegibilidade -> planejamento -> auditoria -> execução -> conferência final
```

| Estágio | Pergunta de negócio que responde |
| --- | --- |
| Gatilho | O pedido está completo? Já foi feito antes? Existe regra vigente para ele nesta data? |
| Elegibilidade | A pessoa pode receber esta operação? Se não, é proibido ou cabe exceção? Quem aprova? |
| Planejamento | O que precisa mudar em cada sistema para a pessoa ficar como o cargo exige? |
| Auditoria | O plano cumpre a lei, a convenção, a política e o contrato de serviço? Alguém precisa revisar? |
| Execução | Aplicar tudo, com comprovante de cada passo, e desfazer se algo falhar |
| Conferência final | O que foi feito é exatamente o que foi auditado? |

### 2. Regras que o negócio entende e altera

As regras ficam em quatro tipos de contrato:

| Contrato | Quem é o dono natural | Exemplos |
| --- | --- | --- |
| Norma | Jurídico trabalhista e relações sindicais | Jornada de 6 horas do bancário, piso da CCT, VR e VA, estabilidade da gestante, do cipeiro, do dirigente sindical e pré-aposentadoria |
| Política | Diretoria de Pessoas | Interstício para promoção, limite de aumento, regras de conduta, programa de alto potencial |
| Cargo | Remuneração e carreira | Faixa salarial, jornada, gratificação, benefícios, acessos, equipamentos e certificações de cada cargo |
| Processo | Operações de RH | Para cada tipo de evento: o que conferir, quais operações executar e o que auditar |

Cada regra diz se é **bloqueante** (proíbe), **excecionável** (proíbe até alguém autorizado aprovar) ou **alerta** (só registra), qual é a base legal e qual frase explicar quando falhar. Por exemplo: "Colaborador está há 5 meses no cargo; mínimo de 12." Uma mudança de regra é salva como nova versão, com data de início, e vale para eventos com data efetiva a partir dali.

### 3. Exceções com dono e justificativa

Quando uma regra excecionável falha, o caso para e aparece na fila da pessoa indicada pela regra: HRBP, Jurídico, Compliance, Auditoria, Comitê de remuneração ou o gestor imediato real do colaborador. A pessoa vê a regra, o valor, a recomendação da IA e decide com justificativa obrigatória. O caso diz sempre o **próximo passo**: o que acontece agora, quem precisa agir e o que aprovar ou rejeitar provoca.

### 4. Estado alvo: a pessoa fica como o cargo exige

Cada cargo descreve como deve estar quem o ocupa. Numa promoção para coordenador, por exemplo, o plano inclui sozinho a gratificação de 55%, a jornada de 8 horas, o celular corporativo, o plano de saúde do nível e a trilha de liderança. Na reversão de cargo de confiança, retira a gratificação, volta a 6 horas e revoga os acessos. A mesma comparação aponta quem já está fora do padrão hoje (tela Colaboradores, conformidade).

### 5. Auditoria antes de qualquer alteração

O plano é aplicado em simulação sobre uma cópia do colaborador. A auditoria confere esse estado projetado contra o contrato de serviço, a norma, o cargo e o estado alvo. Um agente de IA lê o caso inteiro e dá parecer **APROVADO** ou **REPROVADO** com justificativa. Só o que passa é executado. Rejeitar nesse ponto não altera nenhum sistema.

### 6. IA como segunda linha de defesa, nunca como decisora

As regras determinísticas decidem. A IA audita, aponta riscos e sempre dá recomendação clara, inclusive quando a decisão vai para uma pessoa. Quando a IA discorda das regras, o caso vai para revisão humana e a divergência é medida. Se a IA estiver fora do ar, o fluxo espera em vez de seguir sem ela.

### 7. Rastro completo e perguntas em linguagem natural

Cada regra avaliada, operação escolhida ou descartada, aprovação e parecer fica num log que não se apaga. A tela Perguntar responde perguntas como "quantas promoções foram barradas por interstício este mês?" ou "por que o caso X foi revertido?", com números exatos e citando os casos.

### 8. Programas com vigência

O programa de alto potencial vale 12 meses a partir da data oficial. Enquanto ativo, concede bolsa de desenvolvimento, mentoria executiva e acesso à plataforma de liderança. A agenda emite o aviso 30 dias antes e o vencimento na data; os dois passam pela linha normal, que retira as concessões. Renovação e encerramento antecipado reagendam ou cancelam. Um relógio simulado permite demonstrar um ano em segundos.

### 9. Custo de IA sob controle (pendente de merge)

Por padrão a IA roda localmente (Ollama), sem custo por chamada. Quem preferir um provedor externo (Anthropic, Google Gemini ou OpenAI) escolhe no primeiro acesso, testa a chave num fluxo de cinco etapas que mostra o custo do teste e, se quiser, define um teto de gastos mensal ou total e o preço por modelo. Os dois são opcionais. Com o teto atingido, nenhuma chamada sai, os casos esperam e uma faixa vermelha avisa em todas as telas. Essa funcionalidade está no [PR #8](https://github.com/fernandopaixao/new-hr-lab/pull/8), ainda não incorporado.

## Operações cobertas

| Grupo | Eventos |
| --- | --- |
| Entrada | Admissão |
| Carreira | Promoção, mérito, reversão de cargo de confiança, mudança de jornada |
| Mobilidade | Transferência na mesma cidade, para outra base sindical com ou sem anuência, provisória de cargo de confiança |
| Saída | Desligamento sem justa causa, por justa causa, de executivo com garden leave |
| Afastamentos | Doença, acidente de trabalho, licença-maternidade, retorno |
| Família | Nascimento de filho e inclusão de dependente (auxílio-creche, licença-paternidade) |
| Remuneração variável | Bônus, com malus de compliance e limite que exige comitê |
| Coletivos | Reajuste da CCT na data-base (um caso por colaborador), varredura de conformidade |
| Programas | Inclusão, renovação, aviso, vencimento e encerramento antecipado do alto potencial |

São 54 cenários prontos, cada um com o resultado esperado, e a suíte completa compara esperado e obtido. A lista está em [cenarios.md](cenarios.md).

## Exemplos que costumam convencer

| Situação | O que a solução faz |
| --- | --- |
| Promoção de quem tem 5 meses no cargo | Pede exceção ao HRBP, mostra "5 meses; mínimo de 12" e registra quem aprovou e por quê |
| Promoção a gerente sem CPA-20 | Bloqueia: o cargo distribui investimentos e exige a certificação |
| Desligamento de gestante | Bloqueia pela estabilidade, antes de qualquer sistema ser alterado |
| Desligamento em pré-aposentadoria | Exige parecer jurídico pela cláusula da CCT |
| Jornada de 8 horas sem cargo de confiança | Bloqueia pelo art. 224 da CLT |
| Transferência de dirigente sindical | Bloqueia pelo art. 543 da CLT |
| Falha da operadora de benefícios no meio da execução | Desfaz cargo e salário já alterados e registra o motivo |
| Mérito, bônus e transferência simultâneos para a mesma pessoa | Executa um de cada vez e replaneja quando o cadastro muda |
| Esquecimento do eSocial no processo | A auditoria aponta antes da execução |

## Papéis e personas

| Persona | O que decide |
| --- | --- |
| Operador de RH | Dispara eventos, acompanha a linha, depura casos |
| Gestor imediato | Exceções que a regra atribui ao gestor; a aprovação mostra o gestor real da hierarquia |
| HRBP | Interstício, salário acima da faixa, salto de níveis |
| Jurídico trabalhista | Pré-aposentadoria, justa causa sem registro de falta |
| Compliance | Processo disciplinar aberto |
| Auditoria interna | Divergência na conferência final (confirmar reverte a execução) |
| Comitê de remuneração | Bônus e mérito acima do limite, nomeação de diretor, alto potencial com avaliação baixa |

No laboratório a troca de persona é um seletor no topo da tela, sem login. Em produção, cada persona vira um papel no provedor de identidade da empresa (veja [seguranca.md](seguranca.md)).

## Indicadores disponíveis

- Casos por situação e por tipo de evento, taxa de conclusão, tempo total p50 e p95.
- Funil por estágio: onde os casos são barrados.
- Regras que mais barram: candidatas a revisão de política ou a correção de cadastro.
- Aprovações por persona, pendências e aprovações paradas há mais de 30 minutos.
- Compensações, replanejamentos e falhas por operação (aponta a integração com problema).
- Concordância entre a IA e as regras, e entre os dois motores de IA.
- Colaboradores fora do estado alvo.

## Benefícios esperados

| Benefício | De onde vem |
| --- | --- |
| Menos passivo trabalhista | Estabilidades, irredutibilidade, jornada e base sindical conferidas em 100% dos casos, antes da execução |
| Menos retrabalho | O plano deriva tudo o que o cargo exige; nada fica esquecido |
| Auditoria contínua | Toda decisão explicada e consultável, sem amostragem |
| Agilidade para mudar regra | Nova versão de contrato, com vigência, sem projeto de TI |
| Transparência para o colaborador e o gestor | "Por que não?" respondido com a regra e o valor |
| Governança de exceções | Cada exceção tem dono, justificativa e indicador |
| Uso responsável de IA | IA explica e alerta; quem decide são as regras e as pessoas |

## O que é e o que não é

- É um **laboratório funcional** para demonstrar, experimentar e estressar a arquitetura, com time artificial de um banco, 80 colaboradores gerados e eventos sintéticos.
- Os valores da CCT dos bancários (piso, VR, VA, gratificações, PLR) são **ilustrativos e fictícios** e não servem como referência jurídica.
- Não se integra a sistemas reais de folha, ponto, benefícios ou eSocial: a prateleira de operações simula esses sistemas com recibos e protocolos. A troca por integrações reais é o principal passo para produção.
- Não tem login. As personas existem para demonstrar a governança.

## Próximos passos sugeridos para um piloto

1. Escolher um processo de alto volume e regra clara (por exemplo, mérito ou reajuste coletivo).
2. Transcrever as regras reais da política e da convenção vigente para os contratos, com o jurídico.
3. Ligar duas ou três operações da prateleira aos sistemas reais (folha e benefícios).
4. Rodar em paralelo ao processo atual, comparando decisões, por um ciclo.
5. Medir tempo de ciclo, exceções por regra e divergências encontradas.
