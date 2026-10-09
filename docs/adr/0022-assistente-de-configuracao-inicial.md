# 0022. Assistente de configuração inicial na interface

## Contexto

Fernando pediu um wizard de configuração inicial. Com provedores na nuvem (ADR 0021), a primeira subida exige escolhas que o instalador não consegue fazer bem: qual provedor, qual modelo, qual chave e se ela funciona. Os instaladores rodam no terminal e não deveriam receber uma chave de API.

## Decisão

- Na primeira visita, a interface abre o assistente em vez das telas. Ele tem seis passos:
  1. Início: o ambiente encontrado (endereço da interface, Redis e versão, colaboradores e casos, IA atual).
  2. IA dos agentes: Ollama, Claude, OpenAI ou compatível, Gemini, ou sem IA (agente simulado).
  3. Conexão: URL do Ollama ou chave de API, URL base (OpenAI), modelo e esforço (Claude). O botão "Testar conexão" lista os modelos da conta e faz uma chamada estruturada mínima; o erro diz em que etapa falhou (conexão, modelo ou chamada). Com o Ollama, um modelo ausente pode ser baixado dali.
  4. Busca semântica: quem gera os embeddings.
  5. Linha: modo de revisão humana, agente simulado quando a IA cair e atraso visual.
  6. Revisão e conclusão.
- A porta da interface e o endereço do Redis aparecem no passo 1, mas não são editáveis: eles valem para os containers e só mudam com o instalador ou o `.env`. O assistente diz como.
- O teste usa a chave digitada sem gravá-la. A chave só é salva ao concluir, pelo `PUT /api/setup/key`, e o log registra que uma chave foi configurada, nunca o valor.
- Concluir grava as configurações como uma alteração comum (com log) e marca `hr:setup` como concluído. "Pular e manter como está" também marca, sem mudar nada.
- O assistente pode ser reaberto a qualquer momento em Configurações. Reiniciar o laboratório não o faz reaparecer.
- Os instaladores ganharam o modo `nuvem` (sem Ollama, IA escolhida no assistente) e, ao final, dizem se o assistente ainda precisa ser feito.

## Alternativas consideradas

- **Perguntar provedor e chave no instalador.** A chave ficaria no histórico do terminal e no `.env` em texto claro, e o teste de conexão teria de ser reescrito em Bash e em PowerShell.
- **Só a tela de Configurações.** Funciona para quem já conhece o laboratório, mas não guia a primeira subida nem testa a chave antes de salvar.

## Consequências

- Uma instalação existente também vê o assistente uma vez depois da atualização, já preenchido com a configuração atual; "Pular e manter como está" encerra sem mudar nada.
- O estado do assistente fica em `hr:setup` e a chave em `secrets.json` no volume `hrdata`; `docker compose down -v` apaga os dois.
