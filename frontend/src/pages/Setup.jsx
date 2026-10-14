import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, dur } from '../ui.jsx'

const STEPS = [
  ['inicio', 'Início'],
  ['ia', 'IA dos agentes'],
  ['conexao', 'Conexão'],
  ['motor', 'Motor de decisão'],
  ['embeddings', 'Busca semântica'],
  ['linha', 'Linha'],
  ['revisao', 'Revisão'],
]

const MODEL_KEY = { ollama: 'ollama_model', anthropic: 'anthropic_model', openai: 'openai_model', gemini: 'gemini_model' }
const EMB_MODEL_KEY = { ollama: 'embedding_model', openai: 'openai_embedding_model', gemini: 'gemini_embedding_model', simulado: null }
const EFFORTS = [['low', 'Baixo (mais rápido e barato)'], ['medium', 'Médio (padrão)'], ['high', 'Alto'], ['xhigh', 'Muito alto'], ['max', 'Máximo']]

// Embedding provider that matches the chat provider; Claude has none of its own.
function defaultEmbedding(provider) {
  if (provider === 'openai' || provider === 'gemini' || provider === 'ollama') return provider
  return 'simulado'
}

function KeyStatus({ st }) {
  if (!st?.configurada) return <Badge tone="warn">nenhuma chave salva</Badge>
  return <Badge tone="ok">chave salva{st.final ? `, termina em ${st.final}` : ''} ({st.origem})</Badge>
}

function TestResult({ r }) {
  if (!r) return null
  if (r.ok) {
    return <div className="callout ok small">Conexão funcionando: o modelo {r.modelo} respondeu em {dur(r.duracao_ms)}.</div>
  }
  const where = { conexao: 'Não foi possível conectar', modelo: 'Conectou, mas o modelo não está disponível', chamada: 'Conectou, mas a chamada de teste falhou' }[r.etapa] || 'Falhou'
  return <div className="callout bad small"><b>{where}.</b> {r.erro}</div>
}

export default function Setup({ onDone, onCancel }) {
  const [info, setInfo] = useState(null)
  const [vals, setVals] = useState(null)
  const [simulated, setSimulated] = useState(false)
  const [step, setStep] = useState(0)
  const [key, setKey] = useState('')
  const [test, setTest] = useState(null)
  const [models, setModels] = useState([])
  const [busy, setBusy] = useState('')
  const [jevTest, setJevTest] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/setup').then((r) => {
      setInfo(r)
      setVals({ ...r.valores })
    }).catch((e) => setError(e.message))
  }, [])

  if (error && !info) return <div className="setup"><div className="panel panel-pad callout bad">Falha ao carregar o assistente: {error}</div></div>
  if (!info || !vals) return <div className="setup"><div className="empty">Carregando o assistente...</div></div>

  const prov = vals.llm_provider
  const p = info.provedores[prov]
  const set = (patch) => setVals((v) => ({ ...v, ...patch }))
  const chooseProvider = (k) => {
    setSimulated(k === 'simulado')
    if (k === 'simulado') {
      set({ llm_provider: 'ollama', embedding_provider: 'simulado', heuristic_fallback_enabled: true })
    } else {
      set({ llm_provider: k, embedding_provider: defaultEmbedding(k), heuristic_fallback_enabled: info.valores.heuristic_fallback_enabled && k === info.valores.llm_provider })
    }
    setTest(null); setModels([]); setKey('')
  }

  const runTest = async () => {
    setBusy('teste'); setTest(null)
    try {
      const r = await api.post('/setup/test', { provedor: prov, modelo: vals[MODEL_KEY[prov]], chave: key || undefined, valores: vals })
      setTest(r)
      if (r.modelos?.length) setModels(r.modelos)
    } catch (e) { setTest({ ok: false, etapa: 'conexao', erro: e.message }) } finally { setBusy('') }
  }

  const pull = async (modelo) => {
    setBusy(`pull:${modelo}`)
    try {
      await api.put('/settings', { ollama_base_url: vals.ollama_base_url })
      await api.post('/agent/pull', { modelo })
      await runTest()
    } catch (e) { setTest({ ok: false, etapa: 'modelo', erro: `falha ao baixar ${modelo}: ${e.message}` }) } finally { setBusy('') }
  }

  const runJevTest = async () => {
    setBusy('jev'); setJevTest(null)
    try { setJevTest(await api.post('/setup/test-jev', { modelo: vals.jev_model, valores: vals })) } catch (e) { setJevTest({ ok: false, etapa: 'conexao', erro: e.message }) } finally { setBusy('') }
  }

  const pullJev = async () => {
    setBusy('pull-jev')
    try {
      await api.put('/settings', { ollama_base_url: vals.ollama_base_url, jev_base_url: vals.jev_base_url, jev_model: vals.jev_model })
      await api.post('/agent/pull', { motor: 'jev', modelo: vals.jev_model })
      await runJevTest()
    } catch (e) { setJevTest({ ok: false, etapa: 'modelo', erro: `falha ao baixar ${vals.jev_model}: ${e.message}` }) } finally { setBusy('') }
  }

  const finish = async (skip = false) => {
    setBusy('concluir'); setError('')
    try {
      if (!skip && key && p.chave) await api.put('/setup/key', { provedor: prov, chave: key })
      await api.post('/setup/complete', skip ? { pulado: true } : { valores: vals })
      onDone()
    } catch (e) { setError(e.message); setBusy('') }
  }

  const keyStatus = info.chaves[prov]
  const needsKey = !simulated && p.chave && !key && !keyStatus?.configurada
  const embProv = vals.embedding_provider
  const embNeedsKey = info.provedores[embProv]?.chave && embProv !== prov && !info.chaves[embProv]?.configurada
  const canNext = [
    true,
    true,
    simulated || !needsKey,
    true,
    !embNeedsKey,
    true,
    true,
  ][step]
  const datalist = [...new Set([...(p.modelos || []), ...models])]

  return (
    <div className="setup">
      <div className="setup-card panel">
        <div className="setup-head">
          <div>
            <h2>Configuração inicial</h2>
            <p className="muted small">Escolha a IA que audita os casos e responde às perguntas. Tudo pode ser mudado depois em Configurações.</p>
          </div>
          {onCancel ? <button className="btn ghost right" onClick={onCancel}>Fechar</button> : null}
        </div>
        <ol className="setup-steps">
          {STEPS.map(([k, label], i) => (
            <li key={k} className={i === step ? 'active' : i < step ? 'done' : ''}>
              <button className="linklike" disabled={i > step} onClick={() => setStep(i)}><span className="n">{i + 1}</span>{label}</button>
            </li>
          ))}
        </ol>

        <div className="setup-body">
          {step === 0 && (
            <div className="col">
              <p>Este assistente aparece na primeira vez que o laboratório abre. Ele define qual modelo de linguagem os agentes usam: um Ollama local ou na rede, ou um provedor na nuvem (Anthropic Claude, OpenAI ou compatível, Google Gemini).</p>
              <h4>Ambiente encontrado</h4>
              <dl className="kv">
                <dt>Interface</dt><dd className="mono">{location.origin}</dd>
                <dt>Redis</dt><dd><span className="mono">{info.ambiente.redis}</span> <Badge tone="ok">conectado, versão {info.ambiente.redis_versao}</Badge></dd>
                <dt>Dados</dt><dd>{info.ambiente.colaboradores} colaboradores, {info.ambiente.casos} casos</dd>
                <dt>IA atual</dt><dd>{info.provedores[info.valores.llm_provider]?.nome}, {info.valores[MODEL_KEY[info.valores.llm_provider]]}</dd>
              </dl>
              <div className="callout small">A porta da interface e o endereço do Redis vêm da instalação. Para mudá-los, rode o instalador de novo (por exemplo, <code>./scripts/install.sh --porta 8590</code>) ou edite o arquivo <code>.env</code> e suba os containers outra vez.</div>
            </div>
          )}

          {step === 1 && (
            <div className="col">
              <p>Qual IA os agentes de auditoria, de conferência final e de perguntas devem usar?</p>
              <div className="provider-grid">
                {Object.entries(info.provedores).map(([k, pv]) => (
                  <button key={k} className={`provider ${!simulated && prov === k ? 'on' : ''}`} onClick={() => chooseProvider(k)}>
                    <b>{pv.nome}</b>
                    <span className="small muted">{pv.descricao}</span>
                    <span className="small">{pv.chave ? (info.chaves[k]?.configurada ? <Badge tone="ok">chave salva</Badge> : <Badge>precisa de chave de API</Badge>) : <Badge tone="ok">sem chave</Badge>}</span>
                  </button>
                ))}
                <button className={`provider ${simulated ? 'on' : ''}`} onClick={() => chooseProvider('simulado')}>
                  <b>Sem IA (agente simulado)</b>
                  <span className="small muted">Um agente heurístico responde no lugar da IA e cada decisão dele fica marcada. Bom para demonstrações sem rede.</span>
                  <span className="small"><Badge tone="warn">sem IA de verdade</Badge></span>
                </button>
              </div>
              {p.chave && !simulated ? <div className="callout warn small">Com um provedor na nuvem, os dados dos casos (fictícios neste laboratório) são enviados à API do provedor, que cobra por uso.</div> : null}
            </div>
          )}

          {step === 2 && (
            <div className="col">
              {simulated ? (
                <div className="callout">Sem IA não há conexão a configurar. O agente simulado responde na hora e a busca semântica usa embeddings simulados.</div>
              ) : (
                <>
                  <h4>{p.nome}</h4>
                  {prov === 'ollama' ? (
                    <label className="field">URL do Ollama
                      <input value={vals.ollama_base_url} onChange={(e) => set({ ollama_base_url: e.target.value })} />
                      <span className="small muted">Nesta máquina: http://host.docker.internal:11434. Na rede: http://192.168.0.10:11434. Em container: http://ollama:11434.</span>
                    </label>
                  ) : (
                    <label className="field">Chave de API
                      <input type="password" autoComplete="off" value={key} placeholder={keyStatus?.configurada ? 'deixe em branco para manter a chave salva' : 'cole a chave aqui'}
                        onChange={(e) => setKey(e.target.value.trim())} />
                      <span className="small"><KeyStatus st={keyStatus} />{p.chave_url ? <> Gere uma em <a href={p.chave_url} target="_blank" rel="noreferrer">{p.chave_url}</a>.</> : null}</span>
                      <span className="small muted">A chave fica num arquivo do volume de dados, nunca é mostrada de volta nem registrada no log. Uma chave definida no .env tem prioridade.</span>
                    </label>
                  )}
                  {prov === 'openai' ? (
                    <label className="field">URL base
                      <input value={vals.openai_base_url} onChange={(e) => set({ openai_base_url: e.target.value })} />
                      <span className="small muted">OpenAI: https://api.openai.com/v1. Para OpenRouter, Groq, Azure OpenAI ou um servidor vLLM, use a URL compatível do serviço.</span>
                    </label>
                  ) : null}
                  <label className="field">Modelo
                    <input list="setup-models" value={vals[MODEL_KEY[prov]]} onChange={(e) => set({ [MODEL_KEY[prov]]: e.target.value })} />
                    <datalist id="setup-models">{datalist.map((m) => <option key={m} value={m} />)}</datalist>
                    <span className="small muted">Sugestões: {p.modelos.join(', ')}. Depois de testar, a lista mostra os modelos da sua conta ou servidor.</span>
                  </label>
                  {prov === 'anthropic' ? (
                    <label className="field">Esforço de raciocínio
                      <select value={vals.anthropic_effort} onChange={(e) => set({ anthropic_effort: e.target.value })}>
                        {EFFORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                      </select>
                      <span className="small muted">Esforço maior deixa a auditoria mais cuidadosa, porém mais lenta e cara.</span>
                    </label>
                  ) : null}
                  <div className="row">
                    <button className="btn" onClick={runTest} disabled={!!busy || needsKey}>{busy === 'teste' ? 'Testando...' : 'Testar conexão'}</button>
                    {prov === 'ollama' && test?.etapa === 'modelo' ? (
                      <button className="btn" onClick={() => pull(vals.ollama_model)} disabled={!!busy}>{busy.startsWith('pull') ? 'Baixando...' : `Baixar ${vals.ollama_model}`}</button>
                    ) : null}
                    {needsKey ? <span className="small muted">Informe a chave para testar e seguir.</span> : null}
                  </div>
                  <TestResult r={test} />
                </>
              )}
            </div>
          )}

          {step === 3 && (
            <div className="col">
              <p>Qual motor classifica a elegibilidade e audita os planos e as execuções? As regras determinísticas continuam decidindo; o motor recomenda e explica.</p>
              <div className="provider-grid">
                {Object.entries(info.motores).map(([k, m]) => (
                  <button key={k} className={`provider ${vals.agent_engine === k ? 'on' : ''}`} onClick={() => set({ agent_engine: k })}>
                    <b>{m.nome}</b>
                    <span className="small muted">{m.descricao}</span>
                    <span className="small mono">{k === 'jev' ? vals.jev_model : (simulated ? 'agente simulado' : `${p.nome}, ${vals[MODEL_KEY[prov]]}`)}</span>
                  </button>
                ))}
              </div>
              {vals.agent_engine === 'jev' || vals.agent_compare_enabled ? (
                <>
                  <label className="field">Modelo JEV
                    <input value={vals.jev_model} onChange={(e) => set({ jev_model: e.target.value })} />
                    <span className="small muted">Tags do Ollama: tev1:0.8b (padrão, o menor e mais rápido), tev1 (4B) ou nimble (9B). Exige Ollama 0.35 ou mais novo.</span>
                  </label>
                  <label className="field">URL do Ollama do JEV
                    <input value={vals.jev_base_url} placeholder={vals.ollama_base_url} onChange={(e) => set({ jev_base_url: e.target.value })} />
                    <span className="small muted">Vazio usa o mesmo Ollama do passo 3.</span>
                  </label>
                  <div className="row">
                    <button className="btn" onClick={runJevTest} disabled={!!busy}>{busy === 'jev' ? 'Testando...' : 'Testar JEV'}</button>
                    {jevTest?.etapa === 'modelo' ? <button className="btn" onClick={pullJev} disabled={!!busy}>{busy === 'pull-jev' ? 'Baixando...' : `Baixar ${vals.jev_model}`}</button> : null}
                  </div>
                  <TestResult r={jevTest} />
                </>
              ) : null}
              <label className="check"><input type="checkbox" checked={vals.agent_eligibility_enabled} onChange={(e) => set({ agent_eligibility_enabled: e.target.checked })} />
                O agente também classifica a elegibilidade</label>
              <label className="check"><input type="checkbox" checked={vals.agent_compare_enabled} onChange={(e) => set({ agent_compare_enabled: e.target.checked })} />
                Comparar Qwen e JEV nos mesmos casos (o outro motor responde depois, sem decidir)</label>
              <div className="small muted">O painel Desempenho mostra o tempo de resposta e de processamento de cada motor ao longo do tempo.</div>
            </div>
          )}

          {step === 4 && (
            <div className="col">
              <p>A busca semântica e o agente de perguntas usam embeddings de cada evento. Escolha quem gera esses vetores.</p>
              <div className="provider-grid">
                {Object.entries(info.provedores_embedding).map(([k, ep]) => (
                  <button key={k} className={`provider ${embProv === k ? 'on' : ''}`} onClick={() => set({ embedding_provider: k })}>
                    <b>{ep.nome}</b>
                    {EMB_MODEL_KEY[k] ? <span className="small muted mono">{vals[EMB_MODEL_KEY[k]]}</span> : <span className="small muted">Vetores por palavras, sem IA.</span>}
                  </button>
                ))}
              </div>
              {EMB_MODEL_KEY[embProv] ? (
                <label className="field">Modelo de embedding
                  <input value={vals[EMB_MODEL_KEY[embProv]]} onChange={(e) => set({ [EMB_MODEL_KEY[embProv]]: e.target.value })} />
                </label>
              ) : null}
              {prov === 'anthropic' && !simulated ? <div className="callout small">A Anthropic não oferece embeddings. Use o Ollama, a OpenAI, o Gemini ou o simulado.</div> : null}
              {embNeedsKey ? <div className="callout warn small">{info.provedores[embProv].nome} precisa de uma chave salva. Escolha outro, ou configure a chave de {info.provedores[embProv].nome} escolhendo-o como IA dos agentes no passo 2.</div> : null}
              <div className="small muted">Trocar o gerador de embeddings reindexa todos os eventos em segundo plano.</div>
            </div>
          )}

          {step === 5 && (
            <div className="col">
              <label className="field">Revisão humana
                <select value={vals.human_review_mode} onChange={(e) => set({ human_review_mode: e.target.value })}>
                  <option value="SE_REPROVADO">Somente quando o agente ou as regras reprovarem</option>
                  <option value="SEMPRE">Sempre (toda auditoria e toda conferência final passam por uma pessoa)</option>
                </select>
              </label>
              {!simulated ? (
                <label className="check"><input type="checkbox" checked={vals.heuristic_fallback_enabled} onChange={(e) => set({ heuristic_fallback_enabled: e.target.checked })} />
                  Usar o agente simulado quando a IA estiver indisponível (desligado: os casos aguardam a IA voltar)</label>
              ) : null}
              <label className="field">Atraso visual por estágio (ms)
                <input type="number" value={vals.stage_delay_ms} onChange={(e) => set({ stage_delay_ms: Number(e.target.value) })} />
                <span className="small muted">Deixa o movimento na linha observável. Use 0 em testes de estresse.</span>
              </label>
            </div>
          )}

          {step === 6 && (
            <div className="col">
              <dl className="kv">
                <dt>IA dos agentes</dt><dd>{simulated ? 'Sem IA (agente simulado)' : `${p.nome}, ${vals[MODEL_KEY[prov]]}`}</dd>
                {!simulated && p.chave ? <><dt>Chave de API</dt><dd>{key ? 'nova chave, será salva ao concluir' : <KeyStatus st={keyStatus} />}</dd></> : null}
                {!simulated && prov === 'ollama' ? <><dt>Ollama</dt><dd className="mono">{vals.ollama_base_url}</dd></> : null}
                {prov === 'openai' && !simulated ? <><dt>URL base</dt><dd className="mono">{vals.openai_base_url}</dd></> : null}
                <dt>Motor de decisão</dt><dd>{info.motores[vals.agent_engine]?.nome}{vals.agent_engine === 'jev' ? `, ${vals.jev_model}` : ''}{vals.agent_compare_enabled ? ' (com comparação)' : ''}</dd>
                <dt>Busca semântica</dt><dd>{info.provedores_embedding[embProv].nome}{EMB_MODEL_KEY[embProv] ? `, ${vals[EMB_MODEL_KEY[embProv]]}` : ''}</dd>
                <dt>Revisão humana</dt><dd>{vals.human_review_mode === 'SEMPRE' ? 'Sempre' : 'Quando o agente ou as regras reprovarem'}</dd>
                <dt>Sem IA disponível</dt><dd>{vals.heuristic_fallback_enabled ? 'o agente simulado responde' : 'os casos aguardam a IA voltar'}</dd>
              </dl>
              {!simulated && !test?.ok ? <div className="callout warn small">A conexão ainda não foi testada com sucesso. Você pode concluir assim mesmo; os casos aguardam até a IA responder.</div> : null}
              <div className="small muted">Ao concluir, as escolhas ficam no log como alteração de configuração.</div>
            </div>
          )}
        </div>

        {error ? <div className="callout bad small">{error}</div> : null}
        <div className="setup-foot row">
          {!onCancel ? <button className="btn ghost" onClick={() => finish(true)} disabled={!!busy}>Pular e manter como está</button> : null}
          <span className="right" />
          {step > 0 ? <button className="btn" onClick={() => setStep(step - 1)} disabled={!!busy}>Voltar</button> : null}
          {step < STEPS.length - 1
            ? <button className="btn primary" onClick={() => setStep(step + 1)} disabled={!canNext}>Continuar</button>
            : <button className="btn primary" onClick={() => finish(false)} disabled={!!busy}>{busy === 'concluir' ? 'Salvando...' : 'Concluir'}</button>}
        </div>
      </div>
    </div>
  )
}
