# 0020. Próximo passo explícito em cada fase

## Contexto

A linha mostrava onde cada caso estava, mas não o que vinha depois nem quem precisava agir. Fernando pediu para deixar claro o próximo passo em cada fase.

## Decisão

- Cada estágio declara a sua saída (`STAGE_OUTCOMES` em `domain.py`): para onde vai cada resultado possível. A tela Linha mostra a saída no cabeçalho de cada estação, e o detalhe do caso mostra a saída ao passar o mouse em cada estágio.
- Cada caso carrega `proximo_passo`, calculado no backend a cada gravação por `next_step(caso)`:
  - `texto`: o que acontece agora ou o que precisa ser decidido, com o efeito de aprovar e de rejeitar;
  - `quem`: as personas que precisam agir, ou vazio quando é o sistema;
  - `encerrado`: se o caso terminou (o texto diz então o que fazer com o resultado).
- Aprovações pendentes ficam também em `aguardando` no caso, com o gestor real quando for o caso, para o próximo passo nomear quem decide.

## Alternativas consideradas

- **Calcular só na interface.** Duplicaria regras de negócio no frontend e deixaria a API, o log e o agente de perguntas sem a informação.

## Consequências

- O cartão de cada caso na Linha mostra o próximo passo no lugar do resumo enquanto o caso está aberto.
- Mudanças no fluxo exigem atualizar `STAGE_OUTCOMES`, `APPROVAL_OUTCOMES` e `FINAL_NEXT_STEPS`, que ficam junto da definição dos estágios.
