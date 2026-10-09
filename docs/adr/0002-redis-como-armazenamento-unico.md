# 0002. Redis como fila, armazenamento, log, pub/sub e índice

## Contexto

Definido com o usuário: filas com Redis Streams. O laboratório também precisa guardar casos, colaboradores, contratos, aprovações e o log, publicar atualizações ao vivo e, na fase 2, guardar embeddings. Ele deve subir com um único `docker compose up`.

## Decisão

Usar o Redis para tudo:

- Redis Streams com grupos de consumidores para as filas dos estágios e para o log;
- documentos JSON em chaves simples para casos, colaboradores, contratos e aprovações;
- sorted sets e sets como índices;
- pub/sub (`hr:updates`) para a interface;
- hashes para o índice vetorial (ADR 0016).

O Redis roda com AOF (`appendonly yes`) e volume persistente. O log também é gravado num arquivo JSONL no volume de dados, para sobreviver fora do Redis.

## Alternativas consideradas

- **PostgreSQL para documentos e Redis para filas.** É o desenho mais provável em produção (consultas, integridade, relatórios), mas acrescenta um serviço, migrações e um ORM sem ganho para o laboratório.
- **Kafka ou RabbitMQ.** São mais robustos para alto volume, mas pesados para rodar localmente e redundantes com os Streams.
- **Banco vetorial dedicado** (Qdrant, pgvector, Redis Stack). Avaliado na ADR 0016.

## Consequências

- Uma única dependência de infraestrutura, fácil de reiniciar e inspecionar (`redis-cli`).
- As consultas analíticas (painel, agente de perguntas) leem os casos e calculam em memória. Isso é adequado para milhares de casos; para milhões, o modelo de leitura deve ir para um banco analítico.
- Não há transações entre documentos. A consistência vem da trava por colaborador, da versão do cadastro e da guarda de obsolescência (ADR 0010).
- **Em produção:** documentos e log iriam para um banco relacional ou de documentos com retenção e backup, e o Redis ficaria com filas e cache.
