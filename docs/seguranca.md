# Segurança

Este documento é para times de segurança da informação, privacidade e risco. Ele descreve o que o laboratório protege hoje, o que deliberadamente não protege por ser um ambiente de demonstração e o que precisa mudar antes de qualquer uso com dados reais.

## Postura em uma frase

O laboratório é seguro por desenho nas decisões (regras determinísticas, avaliador de expressões restrito, auditoria antes da execução, log imutável, IA sem poder de decisão), mas **não tem autenticação nem autorização reais** e roda com dados fictícios. Ele não deve ser exposto a redes não confiáveis nem receber dados pessoais reais sem os controles da seção [Caminho para produção](#caminho-para-produção).

## Escopo e ativos

| Ativo | Onde fica | Sensibilidade no laboratório | Sensibilidade em produção |
| --- | --- | --- | --- |
| Cadastro de colaboradores (nome, CPF, salário, dependentes, conduta, estabilidades, saúde ocupacional) | Redis (`hr:employee:*`) | Fictício, gerado | Dado pessoal e dado pessoal sensível (LGPD art. 5, II) |
| Casos (evento, plano, recibos, estado antes e depois) | Redis (`hr:case:*`) | Fictício | Alta |
| Log de decisões | Redis (`hr:log`) e `audit-log.jsonl` no volume de dados | Fictício | Alta; é evidência de auditoria |
| Contratos (regras e parâmetros) | Redis (`hr:contract:*`) | Baixa | Média; integridade crítica |
| Índice vetorial (narrativas dos casos) | Redis (`hr:vec:*`) | Fictício | Alta; contém o mesmo conteúdo dos casos |
| Chaves de API dos provedores de IA | `.env` ou `DATA_DIR/secrets.json` | Alta (custo e abuso) | Alta |
| Configurações | Redis (`hr:settings`) | Média | Média; controlam o destino dos dados |

## Controles existentes

### Integridade das decisões

| Controle | Como funciona | Referência |
| --- | --- | --- |
| Regras decidem, IA não | A recomendação da IA nunca aprova sozinha o que as regras barram. Divergência leva a revisão humana. | [ADR 0006](adr/0006-regras-decidem-ia-audita.md) |
| Avaliador de expressões seguro | As regras são expressões de um subconjunto do Python, interpretadas sobre a AST com lista branca de nós. Sem `import`, `lambda`, atribuição, atributos que começam com `_` ou chamadas fora da lista de funções. Não há `eval` nem `exec`. | [ADR 0004](adr/0004-avaliador-de-expressoes-seguro.md), `backend/hrlab/expr.py` |
| Validação de contratos | Todas as expressões são compiladas antes de salvar; ids únicos; uma versão nova não apaga a anterior. | `contracts.py` |
| Auditoria antes da execução | Nenhum sistema é alterado antes de o plano projetado passar pelas regras e pelo parecer do agente. | [ADR 0018](adr/0018-auditoria-antes-da-execucao.md) |
| Conferência final | Prova que o executado é igual ao auditado; divergência vai à auditoria interna e pode reverter. | [arquitetura](arquitetura.md#falhas) |
| Saga com compensação | Falha no meio da execução desfaz os passos anteriores a partir de snapshots. | [ADR 0008](adr/0008-saga-com-compensacao.md) |
| Idempotência | O mesmo evento não abre dois casos (`SET NX`). | [ADR 0010](adr/0010-concorrencia-trava-e-versao.md) |
| Trava e versão | Dois casos não alteram a mesma pessoa ao mesmo tempo; cadastro alterado depois do plano força replanejamento. | ADR 0010 |
| Segregação de funções nas aprovações | Só as personas listadas em `aprovadores` da regra podem decidir; justificativa obrigatória (mínimo de 5 caracteres); uma aprovação decidida não pode ser decidida de novo. | `pipeline.py` |

### Rastreabilidade

- Log append-only com tipo, horário, caso, colaborador, estágio, ator (sistema, worker, persona ou agente), mensagem e dados.
- Cada alteração de contrato, de colaborador e de configuração vai para o log com a persona que a fez.
- O prompt completo enviado à IA e a resposta bruta ficam gravados no caso.
- O arquivo `audit-log.jsonl` guarda todo o histórico; o stream guarda as últimas 200 mil entradas.
- Exportação JSONL filtrada na tela Log.

### Segredos

| Prática | Detalhe |
| --- | --- |
| Origem | Variável de ambiente (`.env`) primeiro; senão `secrets.json` no volume de dados, gravado pelo assistente. |
| Armazenamento | Arquivo criado com permissão `0600`, escrita atômica (arquivo temporário e `rename`). |
| Nunca no Redis | As configurações no Redis não contêm chaves. |
| Nunca no log | A conclusão do assistente registra as escolhas, não a chave. |
| Nunca na API | `GET` de configuração devolve só se a chave existe, a origem e os quatro últimos caracteres (quando a chave tem 12 ou mais). |
| Teste antes de salvar | A chave digitada é usada no teste de conexão e só é gravada ao concluir. |

### IA e dados

| Risco | Mitigação atual |
| --- | --- |
| Alucinação ou erro do modelo | A IA não decide; regras determinísticas decidem; resposta restrita por JSON Schema; valor fora de APROVADO ou REPROVADO vira REPROVADO; resposta inválida duas vezes vira REPROVADO com revisão humana. |
| Números inventados no agente de perguntas | Contagens e agregações são calculadas em Python sobre os fatos; o modelo só redige. Citações que não estão nas evidências são removidas. A consulta interpretada é saneada contra o catálogo. |
| Injeção de instruções no conteúdo do evento | O impacto é limitado: um parecer manipulado para APROVADO não passa por cima de uma regra que falhou, e um REPROVADO só leva a revisão humana. Não há ferramentas nem ações disparadas pelo modelo. |
| Minimização de dados no prompt | O auditor recebe o colaborador resumido (cargo, situação, salário, lotação, benefícios, verbas, acessos, equipamentos, estabilidades, certificações, conduta sem detalhes de advertências), sem nome e sem CPF. O evento vai inteiro e pode conter dados de admissão. |
| IA fora do ar | O fluxo para e espera por padrão. O agente heurístico simulado só responde se for ligado de propósito, e toda decisão dele é marcada. |
| Saída para a nuvem | Ollama local é o padrão. Usar Claude, OpenAI ou Gemini é uma escolha explícita no assistente, que avisa que os dados vão para o provedor. |

### Rede e contêineres

- Apenas o `frontend` (nginx, porta 8580) publica porta na máquina. A API, os workers, o indexador e o Redis ficam na rede interna do Compose.
- O nginx faz proxy de `/api/` com limite de corpo de 10 MB.
- O Redis roda com AOF (persistência) e sem porta publicada.
- O perfil opcional `ollama` publica a porta 11434 na máquina.

### Pendente de merge: teto de gastos com LLM externa (PR #8)

O [PR #8](https://github.com/fernandopaixao/new-hr-lab/pull/8), ainda não incorporado, acrescenta um controle de custo e de abuso para os provedores externos. Preço por modelo e teto são **opcionais**.

| Aspecto | Comportamento previsto |
| --- | --- |
| O que é medido | Toda chamada externa (agentes, perguntas, embeddings e teste do assistente), pelos tokens informados pelo provedor e pelo preço por modelo |
| Onde fica | Contadores no Redis por período, provedor e modelo; histórico das últimas 5000 chamadas; sobrevivem ao reinício do laboratório |
| Quando bloqueia | Antes do envio: se o gasto do período mais a estimativa do prompt passar do teto, a chamada não sai |
| Efeito no fluxo | Falha segura: os casos ficam em "Aguardando agente de IA", nenhuma decisão é tomada sem parecer |
| Visibilidade | Faixa vermelha em todas as telas, selo de gasto no topo, aviso por percentual, entrada `GASTOS_LLM` no log no primeiro bloqueio de cada episódio |
| Teste da chave | Fluxo de cinco etapas (chave, teto, conexão, modelo, chamada de teste) que mostra requisições, tempo, tokens e custo, sem expor a chave |
| Risco residual | Sem autenticação, qualquer pessoa que alcance a interface pode mudar ou zerar o teto (`PUT /api/gastos/teto`, `POST /api/gastos/zerar`); em produção, essas rotas devem ser só de administrador |

### Pendente de merge: aprovação em lote (PR #9)

O [PR #9](https://github.com/fernandopaixao/new-hr-lab/pull/9), ainda não incorporado, permite decidir várias aprovações de uma vez (`POST /api/approvals/batch`, até 200 itens). A alçada e a trilha não são relaxadas:

| Controle | Como funciona no lote |
| --- | --- |
| Alçada | Cada item passa pela mesma decisão unitária: só entra o que a persona ativa pode decidir. Um item fora da alçada falha sozinho (`FALHOU`) e não interrompe os demais. |
| Justificativa | Obrigatória, validada antes de qualquer decisão; a mesma justificativa vale para todos os itens. |
| Trilha | Cada aprovação gera o seu `APROVACAO_DECIDIDA` com a persona e o campo `lote`; um `APROVACAO_LOTE` resume o resultado de cada item (`DECIDIDA`, `IGNORADA`, `FALHOU`). |
| Parecer da IA | O diálogo de confirmação mostra quantas o agente recomenda reprovar antes de a pessoa confirmar. |
| Risco residual | Uma justificativa genérica para muitos casos dilui a explicação individual; sem login, a persona continua sendo escolhida pelo usuário. Em produção, vale limitar o lote por tipo de aprovação (por exemplo, sem lote para revisões da conferência final) e exigir SSO. |

## Lacunas conhecidas (aceitas no laboratório)

| Lacuna | Risco | Por que foi aceita | O que fazer em produção |
| --- | --- | --- | --- |
| Sem autenticação | Qualquer pessoa que alcance a porta 8580 usa tudo, inclusive reiniciar o laboratório, editar contratos e trocar o provedor de IA | Demonstração de governança por persona, decidida com o usuário ([ADR 0009](adr/0009-personas-sem-autenticacao.md)) | SSO (OIDC ou SAML) na frente da API; sessão com expiração |
| Persona vem de um cabeçalho (`X-Persona`) escolhido pelo próprio usuário | Qualquer um se passa por Comitê ou Jurídico | Mesma ADR 0009 | Persona derivada dos papéis do token; autorização por rota e por aprovação |
| CORS aberto (`allow_origins=["*"]`) | Uma página maliciosa aberta no mesmo navegador poderia chamar a API local | Facilita o desenvolvimento com Vite | Lista de origens explícita; tokens anti-CSRF ou `SameSite` estrito |
| Porta publicada em todas as interfaces | Outros na mesma rede alcançam a interface | Facilidade de demonstração em rede | Publicar em `127.0.0.1:8580` ou atrás de um proxy reverso com TLS |
| Sem TLS | Tráfego legível na rede | Uso local | TLS no proxy de entrada |
| Redis sem senha e sem TLS | Quem entra na rede interna lê e altera tudo | Rede interna do Compose | ACL do Redis, TLS, rede segregada, ou banco gerenciado |
| URLs de IA configuráveis pela interface (`ollama_base_url`, `openai_base_url`, `jev_base_url`) e teste de conexão com URL informada | A API faz requisições para o endereço que o usuário digitar (SSRF); com OpenAI, a chave segue para a URL base escolhida | Necessário para Ollama na rede e serviços compatíveis | Lista de destinos permitidos; configuração só por administrador; egress controlado |
| Dados em repouso sem criptografia | Volume do Docker legível por quem tem acesso à máquina | Dados fictícios | Criptografia de disco ou do banco; gestão de chaves |
| Segredos em arquivo no volume | Quem acessa o volume lê a chave | Simplicidade do assistente | Cofre de segredos (Vault, KMS, Secrets Manager) |
| Sem limite de taxa | Rajadas podem gerar custo alto num provedor de IA na nuvem | A tela Cenários tem rajada de propósito, para estresse | Limite por usuário. O teto de gastos opcional com LLM externa chega no PR #8 (ainda não mergeado; ver abaixo) |
| Log append-only, mas no mesmo Redis | Quem tem acesso ao Redis pode apagar o stream; o JSONL pode ser editado no volume | Laboratório | Envio para armazenamento WORM ou SIEM, com hash encadeado |
| Contratos editáveis por qualquer persona | Mudança de regra sem revisão | Laboratório | Fluxo de aprovação de contrato (quatro olhos), assinatura de versão |
| Reinício do laboratório pela interface | Apaga casos, aprovações e log | Laboratório | Inexistente em produção |

## Modelo de ameaças resumido (STRIDE)

| Categoria | Ameaça | Estado no laboratório |
| --- | --- | --- |
| Falsificação | Usuário se passa por persona aprovadora | Possível (sem login); mitigado só por registro |
| Adulteração | Alterar regra para aprovar caso específico | Possível pela interface; toda versão fica registrada com autor e data; versão anterior preservada |
| Adulteração | Manipular parecer da IA por texto no evento | Limitado: IA não decide |
| Repúdio | Negar ter aprovado uma exceção | Mitigado: aprovação com persona, horário e justificativa no log; sem identidade real, o vínculo é com a persona |
| Divulgação | Vazamento de cadastro pela API | Sem controle de acesso; dados fictícios |
| Divulgação | Envio de dados ao provedor de IA na nuvem | Escolha explícita; minimização no prompt do auditor |
| Divulgação | Exposição de chave de API | Mitigado: chave fora do Redis, do log e da API |
| Negação de serviço | Rajada de eventos ou IA lenta | Filas absorvem; casos esperam a IA; semáforo limita chamadas |
| Elevação de privilégio | Expressão de contrato que executa código | Mitigado: avaliador com lista branca, sem `eval` |

## Privacidade (LGPD)

| Tema | Situação no laboratório | Recomendação para produção |
| --- | --- | --- |
| Base legal | Dados sintéticos; não se aplica | Execução de contrato de trabalho e cumprimento de obrigação legal (art. 7, II e V); dados sensíveis (saúde ocupacional, filiação sindical) pelo art. 11, II, a |
| Minimização | Prompt do auditor sem nome e CPF | Revisar o evento enviado à IA; mascarar CPF e dados de dependentes |
| Transferência internacional | Só com provedor na nuvem, por escolha | Avaliar art. 33; preferir modelo local ou região nacional; contrato com o provedor sem retenção para treino |
| Retenção | Sem política; o log cresce até 200 mil entradas no stream e sem limite no JSONL | Tabela de temporalidade por tipo de dado; expurgo do índice vetorial junto com o caso |
| Direitos do titular | Não implementado | Consulta e exportação por colaborador (a trilha `hr:employee:{id}:log` já existe) |
| Decisões automatizadas (art. 20) | Regras decidem e cada decisão é explicada | A explicação de cada regra atende ao pedido de revisão; manter a revisão humana disponível |

## Caminho para produção

Ordem sugerida, do mais ao menos urgente:

1. Identidade: SSO na frente da API, persona derivada de papéis, autorização por rota.
2. Rede: TLS de ponta a ponta, CORS restrito, porta só atrás do proxy, Redis com ACL e TLS.
3. Segredos: cofre externo; remover `secrets.json`.
4. Destinos de IA: lista de URLs permitidas, configuração só por administrador, teto de gasto obrigatório em produção (o teto opcional do PR #8 é a base).
5. Log: envio para armazenamento imutável ou SIEM; hash encadeado por entrada.
6. Governança de contratos: aprovação de duas pessoas para nova versão; assinatura.
7. Privacidade: mascaramento no prompt e no índice, política de retenção, relatório por titular.
8. Desenvolvimento seguro: análise estática e de dependências no CI, imagens base fixadas por digest, varredura de contêineres.
9. Testes: pentest da API e testes de injeção de instruções no agente de perguntas.

## Perguntas frequentes de segurança

**A IA pode aprovar algo que a regra proíbe?** Não. Regra bloqueante rejeita mesmo com parecer APROVADO. Regra excecionável só passa com aprovação humana da persona listada.

**Um contrato pode executar código?** Não. As expressões são interpretadas por um avaliador próprio sobre a AST, com lista branca de operações e funções.

**Onde está a chave da API?** No `.env` ou em `secrets.json` (permissão 0600) no volume de dados. Nunca no Redis, no log ou nas respostas da API.

**Os dados saem da máquina?** Por padrão, não: o Ollama é local ou na rede da empresa. Só saem se alguém escolher um provedor na nuvem no assistente.

**Dá para provar quem aprovou o quê?** Dá para provar qual persona aprovou, quando e com qual justificativa. Sem login, não dá para provar qual pessoa estava atrás da persona; em produção, o SSO fecha essa lacuna.
