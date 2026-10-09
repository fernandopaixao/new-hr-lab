<#
.SYNOPSIS
  Instalador do laboratorio Novo RH para Windows (Docker Desktop).

.DESCRIPTION
  Verifica os pre-requisitos, escolhe onde esta o Ollama, grava o .env,
  baixa os modelos, sobe o Docker Compose e confere se a API enxerga o Ollama.
  Funciona no Windows PowerShell 5.1 e no PowerShell 7.

.EXAMPLE
  .\scripts\install.ps1
  Instalacao guiada.

.EXAMPLE
  .\scripts\install.ps1 -Sim
  Sem perguntas, com os padroes.

.EXAMPLE
  .\scripts\install.ps1 -Ollama rede -OllamaUrl http://192.168.0.10:11434
  Usa um Ollama em outra maquina da rede.
#>
[CmdletBinding()]
param(
  # auto (padrao), local, rede, container ou nenhum
  [ValidateSet('auto', 'local', 'rede', 'container', 'nenhum')]
  [string]$Ollama = 'auto',
  # URL do Ollama na rede, ex.: http://192.168.0.10:11434
  [string]$OllamaUrl = '',
  # Modelo dos agentes (padrao: qwen2.5:7b)
  [string]$Modelo = '',
  # Modelo de embedding (padrao: nomic-embed-text)
  [string]$Embedding = '',
  # Porta da interface (padrao: 8080)
  [int]$Porta = 0,
  # Quantidade de workers (padrao: 1)
  [ValidateRange(1, 64)]
  [int]$Workers = 1,
  # Liga o agente heuristico simulado quando o Ollama cair
  [switch]$Simulado,
  # Nao baixa os modelos
  [switch]$SemModelos,
  # Sobe sem reconstruir as imagens
  [switch]$SemBuild,
  # Nao pergunta nada; usa os padroes
  [switch]$Sim
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root '.env'
$EnvExample = Join-Path $Root '.env.example'
$MinCompose = [version]'2.24.0'
$HealthTimeout = 300
$PullTimeout = 3600
$LocalUrl = 'http://localhost:11434'

# As chamadas ao Ollama e a API ignoram proxy HTTP: um proxy corporativo nao
# alcanca localhost nem a rede local.
$Net = @{ UseBasicParsing = $true }
if ($PSVersionTable.PSVersion.Major -ge 7) { $Net.NoProxy = $true }
else { [System.Net.WebRequest]::DefaultWebProxy = New-Object System.Net.WebProxy }

function Step($text) { Write-Host ''; Write-Host "== $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host '  [ok] ' -ForegroundColor Green -NoNewline; Write-Host $text }
function Info($text) { Write-Host "  $text" }
function Warn($text) { Write-Host '  [atencao] ' -ForegroundColor Yellow -NoNewline; Write-Host $text }
function Fail($text) { Write-Host ''; Write-Host "[erro] $text" -ForegroundColor Red; exit 1 }

if ($OllamaUrl -and $Ollama -eq 'auto') { $Ollama = 'rede' }
if ($Ollama -eq 'rede' -and -not $OllamaUrl) { Fail '-Ollama rede exige -OllamaUrl' }
if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) { $Sim = $true }

function Ask($question, $default) {
  if ($Sim) { return $default }
  $answer = Read-Host "  $question [$default]"
  if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
  return $answer.Trim()
}

# ------------------------------------------------------------------ .env
function Get-EnvValue($key) {
  if (-not (Test-Path $EnvFile)) { return '' }
  $value = ''
  foreach ($line in Get-Content -LiteralPath $EnvFile) {
    if ($line -match "^$([regex]::Escape($key))=(.*)$") { $value = $Matches[1] }
  }
  return $value
}

function Set-EnvValue($key, $value) {
  $lines = @()
  if (Test-Path $EnvFile) { $lines = @(Get-Content -LiteralPath $EnvFile) }
  $done = $false
  $out = New-Object System.Collections.Generic.List[string]
  foreach ($line in $lines) {
    if ($line -match "^$([regex]::Escape($key))=") {
      if (-not $done) { $out.Add("$key=$value"); $done = $true }
    } else { $out.Add($line) }
  }
  if (-not $done) { $out.Add("$key=$value") }
  # UTF-8 sem BOM e fim de linha LF: o Docker Compose le o .env sem problemas
  $text = ($out -join "`n") + "`n"
  [System.IO.File]::WriteAllText($EnvFile, $text, (New-Object System.Text.UTF8Encoding $false))
}

function Test-Port($port) {
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect('127.0.0.1', $port, $null, $null)
    if ($async.AsyncWaitHandle.WaitOne(500) -and $client.Connected) { return $true }
    return $false
  } catch { return $false } finally { $client.Close() }
}

function Test-Http($url, $timeout = 3) {
  try { Invoke-RestMethod -Uri $url -TimeoutSec $timeout @Net | Out-Null; return $true } catch { return $false }
}

function Get-Models($url) {
  try {
    $tags = Invoke-RestMethod -Uri "$url/api/tags" -TimeoutSec 5 @Net
    return @($tags.models | ForEach-Object { $_.name })
  } catch { return @() }
}

function Test-Model($url, $model) {
  $names = Get-Models $url
  if ($names -contains $model) { return $true }
  if ($model -notlike '*:*' -and ($names -contains "${model}:latest")) { return $true }
  return $false
}

# No Windows PowerShell 5.1, redirecionar o stderr de um programa externo com
# ErrorActionPreference = Stop vira erro fatal. Chamadas silenciosas passam por aqui.
function Invoke-Quiet([string]$exe, [string[]]$arguments) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { return (& $exe @arguments 2>$null) } catch { return $null } finally { $ErrorActionPreference = $old }
}

function Invoke-Compose {
  Push-Location $Root
  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    & docker compose @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose saiu com codigo $LASTEXITCODE" }
  } finally { $ErrorActionPreference = $old; Pop-Location }
}

function Get-ComposeOutput {
  Push-Location $Root
  try { return (Invoke-Quiet 'docker' (@('compose') + $args)) } finally { Pop-Location }
}

# --------------------------------------------------------- pre-requisitos
Step 'Verificando pre-requisitos'
Ok "PowerShell $($PSVersionTable.PSVersion)"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Fail 'Docker nao encontrado. Instale o Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/'
}
Invoke-Quiet 'docker' @('info') | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'O Docker esta instalado mas nao esta rodando. Abra o Docker Desktop, espere ele ficar pronto e rode de novo.' }
$dockerVersion = Invoke-Quiet 'docker' @('version', '--format', '{{.Server.Version}}')
Ok "Docker $dockerVersion"

Invoke-Quiet 'docker' @('compose', 'version') | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "Docker Compose v2 nao encontrado (comando 'docker compose'). Atualize o Docker Desktop." }
$composeRaw = ((Invoke-Quiet 'docker' @('compose', 'version', '--short')) -replace '^v', '') -replace '[-+].*$', ''
try { $composeVersion = [version]$composeRaw } catch { $composeVersion = [version]'0.0' }
if ($composeVersion -lt $MinCompose) { Fail "Docker Compose $composeRaw e antigo; o laboratorio precisa da versao $MinCompose ou mais nova." }
Ok "Docker Compose $composeRaw"

$memGb = 0
try { $memGb = [math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB) } catch { }
if ($memGb -gt 0) { Ok "Memoria: $memGb GB" }

# ------------------------------------------------------------------- .env
Step 'Preparando o arquivo .env'
if (Test-Path $EnvFile) {
  $backup = "$EnvFile.bak-$(Get-Date -Format 'yyyyMMddHHmmss')"
  Copy-Item -LiteralPath $EnvFile -Destination $backup
  Ok ".env existente preservado; copia em $(Split-Path -Leaf $backup)"
} else {
  if (-not (Test-Path $EnvExample)) { Fail ".env.example nao encontrado em $Root" }
  Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
  Ok '.env criado a partir do .env.example'
}

if (-not $Modelo) { $Modelo = Get-EnvValue 'OLLAMA_MODEL' }; if (-not $Modelo) { $Modelo = 'qwen2.5:7b' }
if (-not $Embedding) { $Embedding = Get-EnvValue 'EMBEDDING_MODEL' }; if (-not $Embedding) { $Embedding = 'nomic-embed-text' }
if ($Porta -le 0) { $p = Get-EnvValue 'UI_PORT'; if ($p) { $Porta = [int]$p } else { $Porta = 8080 } }

if ((Test-Port $Porta) -and -not (Test-Http "http://localhost:$Porta/api/health")) {
  Fail "A porta $Porta ja esta em uso por outro programa. Use -Porta com outra porta, por exemplo -Porta 8090."
}

# ----------------------------------------------------------------- Ollama
Step 'Localizando o Ollama'
if ($Ollama -eq 'auto') {
  if (Test-Http "$LocalUrl/api/tags") {
    $Ollama = 'local'
    Ok 'Ollama respondendo nesta maquina'
  } else {
    if (Get-Command ollama -ErrorAction SilentlyContinue) {
      Warn "O Ollama esta instalado mas nao respondeu em $LocalUrl. Para usa-lo, abra o aplicativo Ollama e rode o instalador de novo."
    } else {
      Info 'Nenhum Ollama respondeu nesta maquina.'
    }
    Info 'Escolha como o laboratorio vai usar a IA:'
    Info '  1) Ollama em container, em CPU (baixa cerca de 5 GB) (recomendado)'
    Info '  2) Ollama em outra maquina da rede'
    Info '  3) Sem Ollama, com o agente simulado'
    switch (Ask 'Opcao' '1') {
      '1' { $Ollama = 'container' }
      '2' { $Ollama = 'rede'; $OllamaUrl = Ask 'URL do Ollama (ex.: http://192.168.0.10:11434)' ''
            if (-not $OllamaUrl) { Fail 'URL do Ollama nao informada' } }
      '3' { $Ollama = 'nenhum' }
      default { Fail 'opcao invalida' }
    }
  }
}

$fallback = $null
if ($Simulado) { $fallback = 'true' }

switch ($Ollama) {
  'local' {
    $hostUrl = $LocalUrl
    $containerUrl = 'http://host.docker.internal:11434'
    if (-not (Test-Http "$hostUrl/api/tags")) { Fail "O Ollama nao respondeu em $hostUrl. Abra o aplicativo Ollama ou escolha outro modo com -Ollama." }
    Ok "Modo: Ollama desta maquina (containers usam $containerUrl)"
  }
  'rede' {
    $OllamaUrl = $OllamaUrl.TrimEnd('/')
    $hostUrl = $OllamaUrl
    $containerUrl = $OllamaUrl
    if (-not (Test-Http "$hostUrl/api/tags" 5)) { Fail "O Ollama nao respondeu em $hostUrl. Confira o endereco e se ele escuta em 0.0.0.0 (OLLAMA_HOST=0.0.0.0)." }
    Ok "Modo: Ollama na rede em $hostUrl"
  }
  'container' {
    $hostUrl = $LocalUrl
    $containerUrl = 'http://ollama:11434'
    if ((Test-Port 11434) -and -not (Get-ComposeOutput ps -q --status running ollama)) {
      Fail 'A porta 11434 ja esta em uso (provavelmente pelo Ollama desta maquina). Use -Ollama local, ou feche o outro Ollama.'
    }
    if ($memGb -gt 0 -and $memGb -lt 8) { Warn "Com $memGb GB de memoria, o $Modelo pode ficar lento ou nao carregar. Considere -Modelo qwen2.5:3b." }
    Ok 'Modo: Ollama em container, em CPU'
  }
  'nenhum' {
    $hostUrl = ''
    $containerUrl = Get-EnvValue 'OLLAMA_BASE_URL'; if (-not $containerUrl) { $containerUrl = 'http://host.docker.internal:11434' }
    $fallback = 'true'
    $SemModelos = $true
    Ok 'Modo: sem Ollama; o agente simulado fica ligado e toda decisao dele e marcada'
  }
}
# Testa o Ollama de dentro de um container, como a API vai acessa-lo. Usa a
# imagem do Redis, que o laboratorio ja precisa e que traz o wget do busybox.
if ($Ollama -eq 'local' -or $Ollama -eq 'rede') {
  Invoke-Quiet 'docker' @('run', '--rm', '--add-host=host.docker.internal:host-gateway', 'redis:7.4-alpine',
    'wget', '-q', '-T', '5', '-O', '/dev/null', "$containerUrl/api/tags") | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Ok "Os containers alcancam o Ollama em $containerUrl"
  } else {
    Warn "Os containers nao alcancam o Ollama em $containerUrl."
    Info 'Confira se o Ollama escuta em 0.0.0.0 (variavel OLLAMA_HOST=0.0.0.0) e se o firewall libera a porta 11434.'
    $answer = Ask 'Continuar mesmo assim? Os casos vao aguardar o agente (s/n)' 'n'
    if ($answer -notmatch '^(s|sim)$') { Fail 'instalacao interrompida; libere o acesso ao Ollama e rode de novo' }
  }
}

# O agente simulado so fica ligado quando pedido (-Simulado) ou sem Ollama.
if (-not $fallback) { $fallback = 'false' }

Set-EnvValue 'OLLAMA_BASE_URL' $containerUrl
Set-EnvValue 'OLLAMA_MODEL' $Modelo
Set-EnvValue 'EMBEDDING_MODEL' $Embedding
Set-EnvValue 'HEURISTIC_FALLBACK_ENABLED' $fallback
Set-EnvValue 'UI_PORT' $Porta
if ($Ollama -eq 'container') { Set-EnvValue 'COMPOSE_PROFILES' 'ollama' } else { Set-EnvValue 'COMPOSE_PROFILES' '' }
Ok '.env atualizado'

# ---------------------------------------------------------------- modelos
if (-not $SemModelos -and ($Ollama -eq 'local' -or $Ollama -eq 'rede')) {
  Step 'Conferindo os modelos'
  foreach ($m in @($Modelo, $Embedding)) {
    if (Test-Model $hostUrl $m) { Ok "$m disponivel"; continue }
    if ($Ollama -eq 'local' -and (Get-Command ollama -ErrorAction SilentlyContinue)) {
      Info "Baixando $m com o ollama pull..."
      $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
      & ollama pull $m
      $ErrorActionPreference = $old
      if ($LASTEXITCODE -ne 0) { Fail "Falha ao baixar $m" }
    } else {
      Info "Baixando $m em $hostUrl (pode levar varios minutos)..."
      try {
        $body = @{ model = $m; stream = $false } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "$hostUrl/api/pull" -Body $body -ContentType 'application/json' -TimeoutSec $PullTimeout @Net | Out-Null
      } catch { Fail "Falha ao baixar ${m}: $($_.Exception.Message)" }
    }
    Ok "$m baixado"
  }
}

# ----------------------------------------------------------------- subir
Step 'Subindo o laboratorio'
if ($Ollama -ne 'container' -and (Get-ComposeOutput --profile ollama ps -aq ollama ollama-pull)) {
  Info 'Removendo o Ollama em container de uma instalacao anterior (os modelos baixados ficam no volume).'
  Get-ComposeOutput --profile ollama rm -sf ollama ollama-pull | Out-Null
}
$upArgs = @('up', '-d', '--remove-orphans', '--scale', "worker=$Workers")
if (-not $SemBuild) { $upArgs += '--build'; Info 'Construindo as imagens; na primeira vez leva alguns minutos.' }
try { Invoke-Compose @upArgs } catch { Fail "O docker compose falhou. Veja as mensagens acima ou 'docker compose logs'." }
Ok 'Containers no ar'

Info 'Aguardando a API responder...'
$elapsed = 0
while (-not (Test-Http "http://localhost:$Porta/api/health")) {
  Start-Sleep -Seconds 3; $elapsed += 3
  if ($elapsed -ge $HealthTimeout) { Fail "A API nao respondeu em ${HealthTimeout}s. Veja 'docker compose logs api'." }
}
Ok "Interface e API respondendo em http://localhost:$Porta"

if ($Ollama -eq 'container' -and -not $SemModelos) {
  Step 'Baixando os modelos no container do Ollama'
  Info 'Acompanhe com: docker compose logs -f ollama-pull'
  $elapsed = 0
  while (-not ((Test-Model $hostUrl $Modelo) -and (Test-Model $hostUrl $Embedding))) {
    Start-Sleep -Seconds 10; $elapsed += 10
    if ($elapsed % 60 -eq 0) { Info "ainda baixando... (${elapsed}s)" }
    if ($elapsed -ge $PullTimeout) { Warn "Os modelos nao terminaram de baixar em ${PullTimeout}s; o download continua em segundo plano."; break }
  }
  if (Test-Model $hostUrl $Modelo) { Ok "$Modelo disponivel" }
  if (Test-Model $hostUrl $Embedding) { Ok "$Embedding disponivel" }
}

# Configuracoes salvas pela interface prevalecem sobre o .env. Alinha as
# configuracoes em execucao com as escolhas desta instalacao.
$api = "http://localhost:$Porta/api"
try {
  $settings = @{ ollama_base_url = $containerUrl; ollama_model = $Modelo; embedding_model = $Embedding; heuristic_fallback_enabled = ($fallback -eq 'true') } | ConvertTo-Json
  Invoke-RestMethod -Method Put -Uri "$api/settings" -Body $settings -ContentType 'application/json' -Headers @{ 'X-Persona' = 'OPERADOR' } -TimeoutSec 10 @Net | Out-Null
} catch { Warn 'Nao consegui alinhar as configuracoes; confira a tela Configuracoes.' }

# ------------------------------------------------------------- conferir
Step 'Conferindo a IA de dentro dos containers'
$check = $null
try { $check = Invoke-RestMethod -Method Post -Uri "$api/agent/check" -TimeoutSec 15 @Net } catch { }
if ($Ollama -eq 'nenhum') {
  Info 'Sem Ollama: o agente simulado responde no lugar e o indexador usa embeddings simulados.'
} elseif ($check -and $check.ok) {
  Ok "A API alcanca o Ollama em $containerUrl e o modelo $Modelo esta pronto"
  if (-not $check.modelo_embedding_disponivel) { Warn "O modelo de embedding $Embedding ainda nao esta no Ollama; a busca semantica espera por ele." }
} elseif ($check -and $check.online) {
  if ($Ollama -eq 'container') { Warn "O Ollama em container esta no ar, mas o modelo $Modelo ainda nao terminou de baixar. Acompanhe com: docker compose logs -f ollama-pull" }
  else { Warn "A API alcanca o Ollama, mas o modelo $Modelo ainda nao esta pronto. Baixe pela tela Configuracoes." }
} else {
  Warn "A API nao alcancou o Ollama em $containerUrl."
  Info 'Os casos vao aguardar o agente ate o Ollama responder. Para demonstrar sem IA, use -Simulado.'
}

# --------------------------------------------------------------- resumo
Step 'Pronto'
Info "Interface:        http://localhost:$Porta"
if ($Ollama -eq 'nenhum') { Info 'Ollama:           nenhum (agente simulado)' } else { Info "Ollama:           $Ollama ($containerUrl)" }
Info "Modelos:          $Modelo e $Embedding"
Info "Workers:          $Workers"
Info "Agente simulado:  $fallback"
Info ''
Info 'Ver logs:         docker compose logs -f api worker indexer'
Info 'Parar:            docker compose stop'
Info 'Subir de novo:    docker compose up -d'
Info 'Remover tudo:     docker compose down -v   (apaga casos, log e modelos baixados)'
Info 'Documentacao:     docs\README.md e docs\operacao.md'
