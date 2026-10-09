# 0012. Times e eventos sintéticos; valores da CCT ilustrativos

## Contexto

O laboratório precisa de um gerador artificial de eventos e de composição de time, com o máximo de cenários possível. Definido com o usuário: valores ilustrativos da CCT FENABAN, marcados como fictícios.

## Decisão

- **Gerador de time:** organização de banco com sede e agências em bases sindicais diferentes, cargos do escriturário ao diretor, distribuição realista de tempo de casa, salário dentro da faixa, benefícios e acessos coerentes com o estado alvo. Uma fração configurável recebe **desvios propositais** (vale-refeição ausente, jornada de 8h sem cargo de confiança, gratificação abaixo do mínimo, sindicato incompatível com a UF, gestor sem celular corporativo, acesso além do previsto, plano de saúde diferente do contrato, auxílio-creche faltando) para os agentes encontrarem. A semente torna o time reprodutível.
- **Gerador de eventos:** 47 cenários em cinco categorias. Cada cenário escolhe um colaborador adequado (ou o prepara), monta o evento e declara o status esperado. A suíte compara o esperado com o obtido; a rajada envia cenários aleatórios.
- **Valores da norma:** pisos, VR, VA, auxílio-creche e gratificações são fictícios, com aviso no contrato e na documentação.

## Consequências

- Os cenários documentam o comportamento esperado e servem de teste de regressão quando os contratos mudam.
- Nenhum dado pessoal real é usado. Os CPFs gerados são válidos apenas no dígito verificador.
