# 0013. FastAPI, React com Vite e atualizações por SSE

## Contexto

Definido com o usuário: FastAPI no backend e React com Vite na interface. A interface deve ser elegante e simples, e deve mostrar a linha de produção ao vivo.

## Decisão

- **API em FastAPI** (assíncrona, com o cliente assíncrono do Redis). Ela não executa estágios, então pode ser reiniciada ou escalada sem afetar a linha.
- **Interface em React 18 sem biblioteca de componentes:** CSS próprio com variáveis e modo escuro, gráficos em SVG simples. O build é servido por nginx, que faz proxy de `/api`.
- **Atualizações ao vivo por Server-Sent Events** (`/api/stream`), alimentados pelo pub/sub do Redis. A interface mantém os casos em memória e recarrega os detalhes sob demanda.

## Alternativas consideradas

- **WebSocket.** Bidirecional, mas desnecessário: os comandos vão por REST.
- **Polling.** É mais simples, mas a linha de produção perderia a sensação de movimento.
- **Biblioteca de componentes** (MUI, Ant). Acelera, mas pesa e uniformiza demais o visual.

## Consequências

- O nginx desliga o buffer para `/api/stream`. Atrás de outro proxy, a mesma configuração é necessária.
