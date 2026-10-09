# API

A API fica em `http://localhost:8580/api` (pelo nginx do frontend) ou `http://localhost:8000/api` no desenvolvimento local. A documentação interativa gerada pelo FastAPI está em `/docs` na porta da API.

As rotas que alteram algo aceitam o cabeçalho `X-Persona` (padrão `OPERADOR`). Ele não autentica ninguém: só registra quem fez a ação no log ([ADR 0009](adr/0009-personas-sem-autenticacao.md)).

## Eventos e casos

| Método e rota | Corpo ou parâmetros | Resultado |
| --- | --- | --- |
| `POST /api/events` | `{evento: {...}, depuracao, breakpoints}` ou o próprio evento | Abre um caso e coloca na fila do gatilho. |
| `GET /api/cases` | `limit`, `status` | Resumos dos casos mais recentes. |
| `GET /api/cases/{id}` | - | Caso completo, com trilha. |
| `POST /api/cases/{id}/release` | `{continuar}` | Libera um caso parado para o próximo estágio; `continuar: true` desliga o passo a passo. |
| `POST /api/cases/{id}/retry` | `{estagio, evento, depuracao}` | Reprocessa a partir de um estágio, opcionalmente com o evento editado. |
| `POST /api/cases/{id}/cancel` | - | Cancela um caso que não terminou. |
| `POST /api/cases/{id}/debug` | `{depuracao, breakpoints}` | Liga o passo a passo ou define pontos de parada do caso. |

Exemplo de evento:

```json
{
  "id": "evt-promocao-0001",
  "tipo": "colaborador.promovido",
  "colaborador_id": "C0012",
  "data_efetiva": "2026-11-01",
  "dados": {"cargo_destino": "ANALISTA_PLENO", "novo_salario": 7800}
}
```

`GET /api/meta` traz os tipos de evento disponíveis, com modelos de `dados`.

## Linha e controle

| Método e rota | Corpo | Resultado |
| --- | --- | --- |
| `GET /api/control` | - | Pausa geral, estágios pausados e pontos de parada globais. |
| `POST /api/control` | `{paused, paused_stages, breakpoints}` | Altera o controle; é registrado no log. |
| `GET /api/stats` | - | Contagens por status, estágio e tipo de evento, durações e recomendações do agente (usado pela tela Linha). |
| `GET /api/stream` | - | Server-Sent Events com as atualizações de casos, controle, colaboradores e aprovações. |
| `GET /api/meta` | - | Estágios, status, personas, tipos de evento, cenários, prateleira e desvios. |
| `GET /api/health` | - | Verifica a API e o Redis. |

## Aprovações

| Método e rota | Corpo ou parâmetros | Resultado |
| --- | --- | --- |
| `GET /api/approvals` | `pendentes`, `limit` | Aprovações, com a recomendação do agente. |
| `POST /api/approvals/{id}/decide` | `{decisao: APROVAR ou REJEITAR, justificativa, persona}` | Decide. A persona precisa estar entre os aprovadores; a justificativa é obrigatória (mínimo de 5 caracteres). |

## Colaboradores

| Método e rota | Corpo | Resultado |
| --- | --- | --- |
| `GET /api/employees` | - | Lista com resumo de conformidade. |
| `GET /api/employees/{id}` | - | Cadastro, estado alvo, conformidade, casos e trilha. |
| `PUT /api/employees/{id}` | campos a alterar | Grava, incrementa a versão e registra a diferença no log. |
| `POST /api/employees/generate` | `{tamanho, semente, desvio_percentual, substituir}` | Gera o time artificial. |
| `POST /api/employees/{id}/drift` | `{tipo}` | Injeta um desvio de conformidade (os tipos estão em `meta.desvios`). |

## Contratos e prateleira

| Método e rota | Corpo ou parâmetros | Resultado |
| --- | --- | --- |
| `GET /api/contracts` | - | Contratos com a versão vigente. |
| `GET /api/contracts/{codigo}` | `versao` | Todas as versões, ou uma. |
| `POST /api/contracts/validate` | `{contrato}` ou `{yaml}` | Erros de validação, sem salvar. |
| `POST /api/contracts` | `{contrato ou yaml, nova_versao, comentario}` | Salva; por padrão como nova versão. |
| `DELETE /api/contracts/{codigo}/versions/{versao}` | - | Remove uma versão. |
| `POST /api/contracts/reset` | - | Volta aos contratos de exemplo. |
| `GET /api/shelf` | - | Catálogo de operações. |
| `POST /api/shelf/{codigo}/invoke` | `{colaborador_id, parametros, simular}` | Executa uma operação avulsa; `simular: true` (padrão) só mostra o resultado. |

## Cenários

| Método e rota | Corpo | Resultado |
| --- | --- | --- |
| `GET /api/scenarios` | - | Os 47 cenários, com o resultado esperado. |
| `POST /api/scenarios/{id}/generate` | `{enviar, depuracao, breakpoints, semente}` | Prepara os dados e dispara; `enviar: false` só mostra a prévia. |
| `POST /api/scenarios/burst` | `{quantidade, intervalo_ms, categorias, semente}` | Rajada de até 2000 eventos aleatórios. |
| `POST /api/scenarios/suite` | `{cenarios, timeout_s}` | Executa a suíte e compara esperado e obtido. |
| `GET /api/scenarios/suite`, `GET /api/scenarios/suite/{id}` | - | Execuções e resultados da suíte. |

## Agente e configurações

| Método e rota | Corpo | Resultado |
| --- | --- | --- |
| `GET /api/settings`, `PUT /api/settings` | campos a alterar | Configurações em tempo de execução (veja [operação](operacao.md#configurações)). |
| `GET /api/agent/health`, `POST /api/agent/check` | - | Saúde do Ollama e dos modelos. |
| `POST /api/agent/pull` | `{modelo}` | Baixa um modelo no Ollama (padrão: o do conferente). |
| `POST /api/agent/cache/clear` | - | Limpa o cache de respostas. |
| `POST /api/reset` | `{colaboradores, tamanho, semente, desvio_percentual}` | Limpa casos, aprovações, filas, log e índice; opcionalmente gera um novo time. |

## Log

| Método e rota | Parâmetros | Resultado |
| --- | --- | --- |
| `GET /api/logs` | `limit`, `tipo`, `case_id`, `colaborador_id`, `texto`, `antes` | Entradas, da mais recente para a mais antiga; `antes` pagina. |
| `GET /api/logs/export` | `limite` | JSONL. |

## Visibilidade, índice e perguntas

| Método e rota | Corpo ou parâmetros | Resultado |
| --- | --- | --- |
| `GET /api/insights` | `periodo_horas`, `balde_min`, `baldes` | Dados do painel Visão. |
| `GET /api/facts` | `evento_tipo`, `status`, `colaborador_id`, `regra_falha`, `periodo_horas`, `agrupar_por`, `limite` | Fatos por caso, com agrupamento opcional. |
| `GET /api/metrics` | - | Formato Prometheus. |
| `GET /api/index/status` | - | Documentos, pendentes, simulados, modelo e estado do indexador. |
| `POST /api/index/rebuild` | `{limpar}` | Marca tudo para reindexar. |
| `POST /api/search` | `{texto, k, filtros}` | Busca semântica. |
| `POST /api/ask` | `{pergunta}` | Resposta, citações, estatísticas, interpretação e rastro. 503 se o Ollama estiver fora e o modo simulado desligado. |
| `GET /api/ask/history` | `limite` | Últimas perguntas. |

Exemplo:

```bash
curl -s localhost:8580/api/ask -H 'Content-Type: application/json' \
  -d '{"pergunta": "quais regras mais barram promoções?"}' | jq .resposta
```
