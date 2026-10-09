# 0021. Provedores de LLM na nuvem ao lado do Ollama

## Contexto

A ADR 0007 manteve a IA no Ollama, local ou na rede, e descartou as APIs na nuvem porque os dados de RH sairiam do ambiente. Fernando pediu para permitir também outras LLMs na nuvem. Os dados do laboratório são fictícios (ADR 0012), e quem não tem GPU ganha agentes mais rápidos e mais capazes com um provedor na nuvem.

## Decisão

- Um módulo `llm.py` concentra toda chamada a modelo de linguagem: o agente de conferência, o agente de perguntas e o indexador não falam mais com o Ollama diretamente.
- Provedores dos agentes, escolhidos em `llm_provider`:
  - `ollama` (padrão): como antes, com `format` igual ao JSON Schema.
  - `anthropic`: API de Mensagens da Anthropic com `output_config.format` (saída estruturada). Esquema fechado (`additionalProperties: false`) e sem limites numéricos, que a saída estruturada não aceita. O esforço de raciocínio é configurável (`anthropic_effort`). Nos modelos que aceitam, uma recusa de segurança é refeita no servidor por um modelo alternativo (`fallbacks: "default"`).
  - `openai`: Chat Completions com `response_format` `json_schema` estrito. A URL base é configurável, então qualquer serviço compatível (Azure OpenAI, OpenRouter, Groq, vLLM, LM Studio) funciona. Modelos que só aceitam a temperatura padrão e servidores sem `json_schema` têm uma segunda tentativa adaptada.
  - `gemini`: `generateContent` com `responseSchema`.
- Embeddings, escolhidos em `embedding_provider`: `ollama`, `openai`, `gemini` ou `simulado`. A Anthropic não oferece embeddings. O nome gravado com cada vetor inclui o provedor (`openai:text-embedding-3-small`); trocar o provedor ou o modelo reindexa tudo, e vetores de nomes diferentes nunca são comparados.
- Erros de conexão, de chave (401 e 403), de modelo inexistente (404) e de cota (429) contam como IA indisponível: o caso aguarda, como já acontecia com o Ollama fora do ar. Uma resposta fora do JSON, ou uma recusa do modelo, segue o caminho de resposta inválida: nova tentativa e depois revisão humana.
- Chaves de API:
  - Vêm do ambiente (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` no `.env`) ou do arquivo `secrets.json` no volume de dados, gravado pelo assistente de configuração (ADR 0022). O ambiente tem prioridade.
  - O arquivo fica no volume compartilhado por API, workers e indexador, com permissão 600.
  - A chave nunca vai para o Redis, nunca entra no log e nunca volta pela API. A interface só sabe se existe uma chave, de onde ela vem e os quatro últimos caracteres.
- O cache de respostas passa a usar provedor, modelo e prompt na chave. O semáforo de concorrência é separado por provedor: o do Ollama continua em 1 por padrão, o da nuvem em 4.
- Chamadas HTTP diretas com `httpx`, como já era com o Ollama, em vez de um SDK por provedor: o laboratório fica com uma dependência só e o mesmo tratamento de erro para todos.

## Alternativas consideradas

- **Só Ollama.** Era a decisão da ADR 0007; não atende o pedido.
- **Um SDK por provedor.** Três dependências a mais para três chamadas simples, com tratamento de erro diferente em cada uma.
- **Guardar a chave no Redis.** O Redis é exposto a todos os serviços, entra em backups e é limpo com mais facilidade; um arquivo fora dele, legível só pelo processo, é mais simples de proteger.
- **Exigir a chave no `.env`.** Continua possível, mas obrigaria a editar arquivo e reiniciar containers; o assistente resolve pela interface.

## Consequências

- Com um provedor na nuvem, os dados dos casos são enviados à API do provedor, que cobra por uso. O assistente avisa isso ao escolher.
- O Ollama continua o padrão e o único que roda sem rede.
- A suíte de testes cobre os três provedores com um transporte HTTP simulado; nenhuma chave real é necessária.
- A ADR 0007 continua valendo para o Ollama; a alternativa "APIs de IA na nuvem" descartada nela foi revista por esta ADR.
