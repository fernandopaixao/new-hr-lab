#!/usr/bin/env bash
# Instalador do laboratorio Novo RH para Linux e macOS.
#
# Verifica os pre-requisitos, escolhe onde esta o Ollama (ou se a IA fica na
# nuvem), grava o .env, baixa os modelos, sobe o Docker Compose e confere se a
# API enxerga a IA. Na primeira vez, a interface abre o assistente de
# configuracao inicial, onde se escolhe o provedor de IA e a chave de API.
#
#   ./scripts/install.sh            instalacao guiada
#   ./scripts/install.sh --sim      sem perguntas, com os padroes
#   ./scripts/install.sh --ajuda    todas as opcoes
#
# Compativel com o bash 3.2 do macOS. As chamadas ao Ollama e a API ignoram proxy
# HTTP (--noproxy): um proxy corporativo nao alcanca localhost nem a rede local.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.example"
MIN_COMPOSE="2.24.0"

OLLAMA_MODE="auto"
OLLAMA_URL=""
MODEL=""
EMBED_MODEL=""
PORT=""
PORT_EXPLICIT=0
OLLAMA_PORT=""
OLLAMA_PORT_EXPLICIT=0
DEFAULT_PORT=8580
OLD_DEFAULT_PORT=8080
WORKERS=1
FALLBACK=""
PULL_MODELS=1
BUILD=1
ASSUME_YES=0
HEALTH_TIMEOUT=300
PULL_TIMEOUT=3600

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_BOLD=$'\033[1m'; C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
  C_BOLD=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_DIM=""; C_OFF=""
fi

step() { printf '\n%s== %s%s\n' "$C_BOLD" "$1" "$C_OFF"; }
ok() { printf '  %s[ok]%s %s\n' "$C_GREEN" "$C_OFF" "$1"; }
info() { printf '  %s\n' "$1"; }
warn() { printf '  %s[atencao]%s %s\n' "$C_YELLOW" "$C_OFF" "$1"; }
fail() { printf '\n%s[erro]%s %s\n' "$C_RED" "$C_OFF" "$1" >&2; exit 1; }

usage() {
  cat <<'EOF'
Uso: ./scripts/install.sh [opcoes]

Onde esta o Ollama:
  --ollama MODO       auto (padrao), local, rede, container, nuvem ou nenhum
                        auto       usa o Ollama desta maquina se ele responder;
                                   senao pergunta (com --sim, usa container)
                        local      Ollama instalado nesta maquina
                        rede       Ollama em outra maquina (exige --ollama-url)
                        container  sobe o Ollama em container, em CPU
                        nuvem      sem Ollama; a IA e um provedor na nuvem
                                   (Claude, OpenAI ou Gemini), escolhido no
                                   assistente da interface
                        nenhum     sem Ollama; liga o agente simulado
  --ollama-url URL    URL do Ollama na rede, ex.: http://192.168.0.10:11434

Modelos e servicos:
  --modelo NOME       modelo dos agentes (padrao: qwen2.5:7b)
  --embedding NOME    modelo de embedding (padrao: nomic-embed-text)
  --sem-modelos       nao baixa os modelos
  --porta N           porta da interface (padrao: 8580); se a porta padrao
                      estiver ocupada, o instalador oferece a proxima livre
  --porta-ollama N    porta do Ollama em container na maquina (padrao: 11434)
  --workers N         quantidade de workers (padrao: 1)
  --simulado          liga o agente heuristico simulado quando o Ollama cair
                      (sem esta opcao ele fica desligado, exceto em --ollama nenhum)
  --sem-build         sobe sem reconstruir as imagens

Execucao:
  -y, --sim           nao pergunta nada; usa os padroes
  -h, --ajuda         mostra esta ajuda
EOF
}

need_value() { [ $# -ge 2 ] && [ -n "$2" ] || fail "a opcao $1 precisa de um valor"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --ollama) need_value "$@"; OLLAMA_MODE="$2"; shift 2 ;;
    --ollama-url) need_value "$@"; OLLAMA_URL="$2"; [ "$OLLAMA_MODE" = "auto" ] && OLLAMA_MODE="rede"; shift 2 ;;
    --modelo) need_value "$@"; MODEL="$2"; shift 2 ;;
    --embedding) need_value "$@"; EMBED_MODEL="$2"; shift 2 ;;
    --porta) need_value "$@"; PORT="$2"; PORT_EXPLICIT=1; shift 2 ;;
    --porta-ollama) need_value "$@"; OLLAMA_PORT="$2"; OLLAMA_PORT_EXPLICIT=1; shift 2 ;;
    --workers) need_value "$@"; WORKERS="$2"; shift 2 ;;
    --simulado) FALLBACK="true"; shift ;;
    --sem-modelos) PULL_MODELS=0; shift ;;
    --sem-build) BUILD=0; shift ;;
    -y|--sim) ASSUME_YES=1; shift ;;
    -h|--ajuda|--help) usage; exit 0 ;;
    *) usage >&2; fail "opcao desconhecida: $1" ;;
  esac
done

case "$OLLAMA_MODE" in auto|local|rede|container|nuvem|nenhum) ;; *) fail "--ollama deve ser auto, local, rede, container, nuvem ou nenhum" ;; esac
case "$WORKERS" in ''|*[!0-9]*) fail "--workers deve ser um numero" ;; esac
[ "$WORKERS" -ge 1 ] || fail "--workers deve ser pelo menos 1"
for p in "$PORT" "$OLLAMA_PORT"; do
  case "$p" in *[!0-9]*) fail "--porta e --porta-ollama devem ser numeros" ;; esac
done
[ "$OLLAMA_MODE" = "rede" ] && [ -z "$OLLAMA_URL" ] && fail "--ollama rede exige --ollama-url"
[ -t 0 ] || ASSUME_YES=1

ask() {
  # ask "pergunta" "padrao" -> resposta em REPLY
  if [ "$ASSUME_YES" = 1 ]; then REPLY="$2"; return; fi
  printf '  %s [%s]: ' "$1" "$2"
  read -r REPLY || REPLY=""
  [ -n "$REPLY" ] || REPLY="$2"
}

# ------------------------------------------------------------------ .env
env_get() {
  [ -f "$ENV_FILE" ] || return 0
  awk -F= -v k="$1" '$1 == k { sub(/^[^=]*=/, ""); v = $0 } END { if (v != "") print v }' "$ENV_FILE"
}

env_set() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp)"
  awk -v k="$key" -v v="$value" '
    BEGIN { done = 0 }
    $0 ~ "^" k "=" { if (!done) { print k "=" v; done = 1 }; next }
    { print }
    END { if (!done) print k "=" v }' "$ENV_FILE" > "$tmp"
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
}

version_ge() {
  # version_ge 2.29.1 2.24.0
  local a b i
  IFS=. read -r -a a <<< "${1%%[-+]*}"
  IFS=. read -r -a b <<< "$2"
  for i in 0 1 2; do
    local x="${a[$i]:-0}" y="${b[$i]:-0}"
    x="${x//[!0-9]/}"; y="${y//[!0-9]/}"
    [ "${x:-0}" -gt "${y:-0}" ] && return 0
    [ "${x:-0}" -lt "${y:-0}" ] && return 1
  done
  return 0
}

free_port() {
  # free_port INICIO -> primeira porta livre a partir de INICIO
  local p="$1" tries=0
  while port_in_use "$p"; do
    p=$((p + 1)); tries=$((tries + 1))
    [ "$tries" -lt 100 ] || return 1
  done
  echo "$p"
}

port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && return 0
  return 1
}

http_ok() { curl -fsS --noproxy "*" --max-time "${2:-3}" "$1" >/dev/null 2>&1; }

has_model() {
  # has_model URL MODELO
  local tags
  tags="$(curl -fsS --noproxy "*" --max-time 5 "$1/api/tags" 2>/dev/null)" || return 1
  # grep sobre here-string: com pipefail, um pipe para grep -q pode falhar por SIGPIPE
  grep -qF "\"name\":\"$2\"" <<< "$tags" && return 0
  case "$2" in *:*) return 1 ;; esac
  grep -qF "\"name\":\"$2:latest\"" <<< "$tags"
}

compose() { (cd "$ROOT" && docker compose "$@"); }

# --------------------------------------------------------- pre-requisitos
step "Verificando pre-requisitos"
OS="$(uname -s)"
case "$OS" in
  Linux) ok "Sistema: Linux" ;;
  Darwin) ok "Sistema: macOS" ;;
  *) warn "Sistema $OS nao testado; no Windows use scripts\\install.ps1" ;;
esac

command -v curl >/dev/null 2>&1 || fail "curl nao encontrado. Instale o curl e rode de novo."
command -v docker >/dev/null 2>&1 || fail "Docker nao encontrado. Instale o Docker Desktop (macOS) ou o Docker Engine (Linux): https://docs.docker.com/get-docker/"
if ! docker info >/dev/null 2>&1; then
  if docker info 2>&1 | grep -qi "permission denied"; then
    fail "Sem permissao para usar o Docker. Adicione seu usuario ao grupo docker (sudo usermod -aG docker \$USER), saia e entre de novo na sessao."
  fi
  fail "O Docker esta instalado mas nao esta rodando. Abra o Docker Desktop ou rode 'sudo systemctl start docker'."
fi
ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '')"

docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 nao encontrado (comando 'docker compose'). Atualize o Docker."
COMPOSE_VERSION="$(docker compose version --short 2>/dev/null | sed 's/^v//')"
version_ge "$COMPOSE_VERSION" "$MIN_COMPOSE" || fail "Docker Compose $COMPOSE_VERSION e antigo; o laboratorio precisa da versao $MIN_COMPOSE ou mais nova."
ok "Docker Compose $COMPOSE_VERSION"

MEM_GB=""
if [ "$OS" = "Linux" ] && [ -r /proc/meminfo ]; then
  MEM_GB=$(( $(awk '/MemTotal/ { print $2 }' /proc/meminfo) / 1024 / 1024 ))
elif [ "$OS" = "Darwin" ]; then
  MEM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1024 / 1024 / 1024 ))
fi
[ -n "$MEM_GB" ] && ok "Memoria: ${MEM_GB} GB"

# ------------------------------------------------------------------- .env
step "Preparando o arquivo .env"
if [ -f "$ENV_FILE" ]; then
  BACKUP="$ENV_FILE.bak-$(date +%Y%m%d%H%M%S)"
  cp "$ENV_FILE" "$BACKUP"
  ok ".env existente preservado; copia em $(basename "$BACKUP")"
else
  [ -f "$ENV_EXAMPLE" ] || fail ".env.example nao encontrado em $ROOT"
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  ok ".env criado a partir do .env.example"
fi

[ -n "$MODEL" ] || MODEL="$(env_get OLLAMA_MODEL)"; [ -n "$MODEL" ] || MODEL="qwen2.5:7b"
[ -n "$EMBED_MODEL" ] || EMBED_MODEL="$(env_get EMBEDDING_MODEL)"; [ -n "$EMBED_MODEL" ] || EMBED_MODEL="nomic-embed-text"
if [ -z "$PORT" ]; then
  PORT="$(env_get UI_PORT)"
  if [ "$PORT" = "$OLD_DEFAULT_PORT" ]; then
    info "A porta padrao da interface mudou de $OLD_DEFAULT_PORT para $DEFAULT_PORT; o .env sera atualizado."
    PORT="$DEFAULT_PORT"
  fi
  [ -n "$PORT" ] || PORT="$DEFAULT_PORT"
fi

# Porta ocupada por outro programa (e nao por uma instalacao anterior).
OWN_UI="$(compose port frontend 80 2>/dev/null || true)"
if port_in_use "$PORT" && [ "${OWN_UI##*:}" != "$PORT" ] && ! http_ok "http://localhost:$PORT/api/health"; then
  [ "$PORT_EXPLICIT" = 0 ] || fail "A porta $PORT ja esta em uso por outro programa. Escolha outra com --porta."
  SUGGESTED="$(free_port $((PORT + 1)))" || fail "Nao encontrei porta livre perto de $PORT. Escolha uma com --porta."
  warn "A porta $PORT ja esta em uso por outro programa."
  ask "Porta da interface" "$SUGGESTED"
  case "$REPLY" in ''|*[!0-9]*) fail "porta invalida: $REPLY" ;; esac
  if [ "$REPLY" != "$SUGGESTED" ] && port_in_use "$REPLY"; then fail "A porta $REPLY tambem esta em uso."; fi
  PORT="$REPLY"
fi
ok "Porta da interface: $PORT"

# ----------------------------------------------------------------- Ollama
step "Localizando o Ollama"
LOCAL_URL="http://localhost:11434"
if [ "$OLLAMA_MODE" = "auto" ]; then
  if http_ok "$LOCAL_URL/api/tags"; then
    OLLAMA_MODE="local"
    ok "Ollama respondendo nesta maquina"
  else
    if command -v ollama >/dev/null 2>&1; then
      warn "O Ollama esta instalado mas nao respondeu em $LOCAL_URL. Para usa-lo, inicie com 'ollama serve' e rode o instalador de novo."
    else
      info "Nenhum Ollama respondeu nesta maquina."
    fi
    info "Escolha como o laboratorio vai usar a IA:"
    info "  1) Ollama em container, em CPU (baixa cerca de 5 GB) (recomendado)"
    info "  2) Ollama em outra maquina da rede"
    info "  3) IA na nuvem (Claude, OpenAI ou Gemini), escolhida no assistente da interface"
    info "  4) Sem IA, com o agente simulado"
    ask "Opcao" "1"
    case "$REPLY" in
      1) OLLAMA_MODE="container" ;;
      2) OLLAMA_MODE="rede"; ask "URL do Ollama (ex.: http://192.168.0.10:11434)" ""; OLLAMA_URL="$REPLY"
         [ -n "$OLLAMA_URL" ] || fail "URL do Ollama nao informada" ;;
      3) OLLAMA_MODE="nuvem" ;;
      4) OLLAMA_MODE="nenhum" ;;
      *) fail "opcao invalida: $REPLY" ;;
    esac
  fi
fi

case "$OLLAMA_MODE" in
  local)
    HOST_URL="$LOCAL_URL"
    CONTAINER_URL="http://host.docker.internal:11434"
    http_ok "$HOST_URL/api/tags" || fail "O Ollama nao respondeu em $HOST_URL. Inicie com 'ollama serve' ou escolha outro modo com --ollama."
    ok "Modo: Ollama desta maquina (containers usam $CONTAINER_URL)"
    ;;
  rede)
    OLLAMA_URL="${OLLAMA_URL%/}"
    HOST_URL="$OLLAMA_URL"
    CONTAINER_URL="$OLLAMA_URL"
    http_ok "$HOST_URL/api/tags" 5 || fail "O Ollama nao respondeu em $HOST_URL. Confira o endereco e se ele escuta em 0.0.0.0 (OLLAMA_HOST=0.0.0.0)."
    ok "Modo: Ollama na rede em $HOST_URL"
    ;;
  container)
    CONTAINER_URL="http://ollama:11434"
    [ -n "$OLLAMA_PORT" ] || OLLAMA_PORT="$(env_get OLLAMA_PORT)"; [ -n "$OLLAMA_PORT" ] || OLLAMA_PORT=11434
    # Ocupada pelo proprio Ollama em container de uma instalacao anterior nao conta.
    OWN_OLLAMA="$(compose port ollama 11434 2>/dev/null || true)"
    if port_in_use "$OLLAMA_PORT" && [ "${OWN_OLLAMA##*:}" != "$OLLAMA_PORT" ]; then
      [ "$OLLAMA_PORT_EXPLICIT" = 0 ] || fail "A porta $OLLAMA_PORT ja esta em uso. Escolha outra com --porta-ollama."
      NEW_OLLAMA_PORT="$(free_port $((OLLAMA_PORT + 1)))" || fail "Nao encontrei porta livre para o Ollama. Escolha uma com --porta-ollama."
      warn "A porta $OLLAMA_PORT ja esta em uso (provavelmente por outro Ollama); o Ollama em container vai usar a $NEW_OLLAMA_PORT."
      OLLAMA_PORT="$NEW_OLLAMA_PORT"
    fi
    HOST_URL="http://localhost:$OLLAMA_PORT"
    if [ -n "$MEM_GB" ] && [ "$MEM_GB" -lt 8 ]; then
      warn "Com ${MEM_GB} GB de memoria, o $MODEL pode ficar lento ou nao carregar. Considere --modelo qwen2.5:3b."
    fi
    ok "Modo: Ollama em container, em CPU (porta $OLLAMA_PORT na maquina)"
    ;;
  nuvem)
    HOST_URL=""
    CONTAINER_URL="$(env_get OLLAMA_BASE_URL)"; [ -n "$CONTAINER_URL" ] || CONTAINER_URL="http://host.docker.internal:11434"
    PULL_MODELS=0
    ok "Modo: IA na nuvem; escolha o provedor e informe a chave no assistente da interface"
    ;;
  nenhum)
    HOST_URL=""
    CONTAINER_URL="$(env_get OLLAMA_BASE_URL)"; [ -n "$CONTAINER_URL" ] || CONTAINER_URL="http://host.docker.internal:11434"
    FALLBACK="true"
    PULL_MODELS=0
    ok "Modo: sem Ollama; o agente simulado fica ligado e toda decisao dele e marcada"
    ;;
esac
# Testa o Ollama de dentro de um container, como a API vai acessa-lo. Usa a
# imagem do Redis, que o laboratorio ja precisa e que traz o wget do busybox.
if [ "$OLLAMA_MODE" = "local" ] || [ "$OLLAMA_MODE" = "rede" ]; then
  if docker run --rm --add-host=host.docker.internal:host-gateway redis:7.4-alpine \
       wget -q -T 5 -O /dev/null "$CONTAINER_URL/api/tags" >/dev/null 2>&1; then
    ok "Os containers alcancam o Ollama em $CONTAINER_URL"
  else
    warn "Os containers nao alcancam o Ollama em $CONTAINER_URL."
    if [ "$OLLAMA_MODE" = "local" ] && [ "$OS" = "Linux" ]; then
      info "No Linux, o Ollama costuma escutar so em 127.0.0.1. Libere o acesso e rode o instalador de novo:"
      info "  sudo systemctl edit ollama    (acrescente as duas linhas abaixo)"
      info "    [Service]"
      info "    Environment=\"OLLAMA_HOST=0.0.0.0\""
      info "  sudo systemctl restart ollama"
      info "Sem systemd: OLLAMA_HOST=0.0.0.0 ollama serve"
    else
      info "Confira se o Ollama escuta em 0.0.0.0 (OLLAMA_HOST=0.0.0.0) e se o firewall libera a porta 11434."
    fi
    ask "Continuar mesmo assim? Os casos vao aguardar o agente (s/n)" "n"
    case "$REPLY" in s|S|sim) ;; *) fail "instalacao interrompida; libere o acesso ao Ollama e rode de novo" ;; esac
  fi
fi

# O agente simulado so fica ligado quando pedido (--simulado) ou sem Ollama.
[ -n "$FALLBACK" ] || FALLBACK="false"

env_set OLLAMA_BASE_URL "$CONTAINER_URL"
env_set OLLAMA_MODEL "$MODEL"
env_set EMBEDDING_MODEL "$EMBED_MODEL"
env_set HEURISTIC_FALLBACK_ENABLED "$FALLBACK"
env_set UI_PORT "$PORT"
[ -z "$OLLAMA_PORT" ] || env_set OLLAMA_PORT "$OLLAMA_PORT"
if [ "$OLLAMA_MODE" = "container" ]; then
  env_set COMPOSE_PROFILES "ollama"
else
  env_set COMPOSE_PROFILES ""
fi
ok ".env atualizado"

# ---------------------------------------------------------------- modelos
pull_via_api() {
  # pull_via_api URL MODELO
  local body
  info "Baixando $2 em $1 (pode levar varios minutos)..."
  body="$(curl -fsS --noproxy "*" --max-time "$PULL_TIMEOUT" -X POST "$1/api/pull" \
    -H 'Content-Type: application/json' -d "{\"model\":\"$2\",\"stream\":false}" 2>&1)" \
    || fail "Falha ao baixar $2: $body"
}

if [ "$PULL_MODELS" = 1 ] && { [ "$OLLAMA_MODE" = "local" ] || [ "$OLLAMA_MODE" = "rede" ]; }; then
  step "Conferindo os modelos"
  for m in "$MODEL" "$EMBED_MODEL"; do
    if has_model "$HOST_URL" "$m"; then
      ok "$m disponivel"
    elif [ "$OLLAMA_MODE" = "local" ] && command -v ollama >/dev/null 2>&1; then
      info "Baixando $m com o ollama pull..."
      OLLAMA_HOST="$HOST_URL" ollama pull "$m" || fail "Falha ao baixar $m"
      ok "$m baixado"
    else
      pull_via_api "$HOST_URL" "$m"
      ok "$m baixado"
    fi
  done
fi

# ----------------------------------------------------------------- subir
step "Subindo o laboratorio"
UP_ARGS="up -d --remove-orphans --scale worker=$WORKERS"
[ "$BUILD" = 1 ] && UP_ARGS="$UP_ARGS --build"
[ "$BUILD" = 1 ] && info "Construindo as imagens; na primeira vez leva alguns minutos."
if [ "$OLLAMA_MODE" != "container" ] && [ -n "$(compose --profile ollama ps -aq ollama ollama-pull 2>/dev/null)" ]; then
  info "Removendo o Ollama em container de uma instalacao anterior (os modelos baixados ficam no volume)."
  compose --profile ollama rm -sf ollama ollama-pull >/dev/null 2>&1 || true
fi
# shellcheck disable=SC2086
compose $UP_ARGS || fail "O docker compose falhou. Veja as mensagens acima ou 'docker compose logs'."
ok "Containers no ar"

info "Aguardando a API responder..."
elapsed=0
until http_ok "http://localhost:$PORT/api/health"; do
  sleep 3; elapsed=$((elapsed + 3))
  [ "$elapsed" -lt "$HEALTH_TIMEOUT" ] || fail "A API nao respondeu em ${HEALTH_TIMEOUT}s. Veja 'docker compose logs api'."
done
ok "Interface e API respondendo em http://localhost:$PORT"

if [ "$OLLAMA_MODE" = "container" ] && [ "$PULL_MODELS" = 1 ]; then
  step "Baixando os modelos no container do Ollama"
  info "Acompanhe com: docker compose logs -f ollama-pull"
  elapsed=0
  until has_model "$HOST_URL" "$MODEL" && has_model "$HOST_URL" "$EMBED_MODEL"; do
    sleep 10; elapsed=$((elapsed + 10))
    if [ $((elapsed % 60)) -eq 0 ]; then info "ainda baixando... (${elapsed}s)"; fi
    if [ "$elapsed" -ge "$PULL_TIMEOUT" ]; then
      warn "Os modelos nao terminaram de baixar em ${PULL_TIMEOUT}s; o download continua em segundo plano."
      break
    fi
  done
  has_model "$HOST_URL" "$MODEL" && ok "$MODEL disponivel"
  has_model "$HOST_URL" "$EMBED_MODEL" && ok "$EMBED_MODEL disponivel"
fi

# Configuracoes salvas pela interface prevalecem sobre o .env. Alinha as
# configuracoes em execucao com as escolhas desta instalacao.
API="http://localhost:$PORT/api"
SETTINGS_BODY="{\"ollama_base_url\":\"$CONTAINER_URL\",\"ollama_model\":\"$MODEL\",\"embedding_model\":\"$EMBED_MODEL\",\"heuristic_fallback_enabled\":$FALLBACK}"
curl -fsS --noproxy "*" --max-time 10 -X PUT "$API/settings" -H 'Content-Type: application/json' -H 'X-Persona: OPERADOR' \
  -d "$SETTINGS_BODY" >/dev/null 2>&1 || warn "Nao consegui alinhar as configuracoes; confira a tela Configuracoes."

# ------------------------------------------------------------- conferir
step "Conferindo a IA de dentro dos containers"
CHECK="$(curl -fsS --noproxy "*" --max-time 15 -X POST "$API/agent/check" 2>/dev/null || true)"
if [ "$OLLAMA_MODE" = "nenhum" ]; then
  info "Sem Ollama: o agente simulado responde no lugar e o indexador usa embeddings simulados."
elif [ "$OLLAMA_MODE" = "nuvem" ]; then
  if grep -q '"ok": *true' <<< "$CHECK"; then
    ok "A API alcanca o provedor de IA configurado"
  else
    info "Abra a interface: o assistente de configuracao pede o provedor (Claude, OpenAI ou Gemini), o modelo e a chave de API."
    info "Ate la, os casos aguardam a IA."
  fi
elif grep -q '"ok": *true' <<< "$CHECK"; then
  ok "A API alcanca o Ollama em $CONTAINER_URL e o modelo $MODEL esta pronto"
  grep -q '"modelo_embedding_disponivel": *true' <<< "$CHECK" \
    || warn "O modelo de embedding $EMBED_MODEL ainda nao esta no Ollama; a busca semantica espera por ele."
elif grep -q '"online": *true' <<< "$CHECK"; then
  if [ "$OLLAMA_MODE" = "container" ]; then
    warn "O Ollama em container esta no ar, mas o modelo $MODEL ainda nao terminou de baixar. Acompanhe com: docker compose logs -f ollama-pull"
  else
    warn "A API alcanca o Ollama, mas o modelo $MODEL ainda nao esta pronto. Baixe pela tela Configuracoes."
  fi
else
  warn "A API nao alcancou o Ollama em $CONTAINER_URL."
  if [ "$OLLAMA_MODE" = "local" ] && [ "$OS" = "Linux" ]; then
    info "No Linux, o Ollama precisa escutar em 0.0.0.0 (OLLAMA_HOST=0.0.0.0) para os containers o alcancarem."
  fi
  info "Os casos vao aguardar o agente ate o Ollama responder. Para demonstrar sem IA, use --simulado."
fi

# --------------------------------------------------------------- resumo
if [ "$OLLAMA_MODE" = "nenhum" ]; then OLLAMA_SUMMARY="nenhum (agente simulado)"
elif [ "$OLLAMA_MODE" = "nuvem" ]; then OLLAMA_SUMMARY="nenhum (IA na nuvem, definida no assistente)"; else OLLAMA_SUMMARY="$OLLAMA_MODE ($CONTAINER_URL)"; fi
if curl -fsS --noproxy "*" --max-time 10 "$API/setup" 2>/dev/null | grep -q '"concluido": *true'; then
  SETUP_SUMMARY="ja feita; para refazer, Configuracoes, Abrir assistente de configuracao"
else
  SETUP_SUMMARY="abra a interface: o assistente de configuracao inicial aparece na primeira visita"
fi
step "Pronto"
cat <<EOF
  Interface:        http://localhost:$PORT
  Configuracao:     $SETUP_SUMMARY
  Ollama:           $OLLAMA_SUMMARY
  Modelos:          $MODEL e $EMBED_MODEL
  Workers:          $WORKERS
  Agente simulado:  $FALLBACK

  ${C_DIM}Ver logs:         docker compose logs -f api worker indexer
  Parar:            docker compose stop
  Subir de novo:    docker compose up -d
  Remover tudo:     docker compose down -v   (apaga casos, log e modelos baixados)
  Documentacao:     docs/README.md e docs/operacao.md${C_OFF}
EOF
