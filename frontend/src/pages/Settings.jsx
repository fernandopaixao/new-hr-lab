import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, Json, dateTime, useApp } from '../ui.jsx'
import { SpendPanel } from './Spend.jsx'

const FIELDS = [
  ['ollama_base_url', 'URL do Ollama', 'text', 'Local (http://host.docker.internal:11434), na rede (http://192.168.0.10:11434) ou o container (http://ollama:11434).'],
  ['ollama_model', 'Modelo', 'text', 'Recomendado: qwen2.5:7b. Modelos menores (qwen2.5:3b) respondem mais rápido.'],
  ['ollama_timeout_s', 'Tempo limite (s)', 'number', ''],
  ['ollama_num_ctx', 'Contexto (tokens)', 'number', 'Janela de contexto; 8192 cobre plano e contrato.'],
  ['ollama_num_predict', 'Máximo de tokens na resposta', 'number', ''],
  ['ollama_keep_alive', 'Manter modelo carregado', 'text', 'Evita recarregar o modelo entre casos (ex.: 30m).'],
  ['ollama_max_concurrency', 'Chamadas simultâneas por worker', 'number', 'Use 1 para GPU local; aumente para servidores na rede.'],
  ['ollama_temperature', 'Temperatura', 'number', '0 deixa as auditorias reprodutíveis.'],
  ['stage_delay_ms', 'Atraso visual por estágio (ms)', 'number', 'Deixa o movimento na linha observável. Use 0 em testes de estresse.'],
  ['failure_rate_percent', 'Falhas injetadas por operação (%)', 'number', 'Simula sistemas instáveis para exercitar a saga.'],
]

const CLOUD_FIELDS = {
  anthropic: [['anthropic_model', 'Modelo', 'text'], ['anthropic_effort', 'Esforço de raciocínio', 'text']],
  openai: [['openai_model', 'Modelo', 'text'], ['openai_base_url', 'URL base (OpenAI ou compatível)', 'text']],
  gemini: [['gemini_model', 'Modelo', 'text']],
}
const EMB_MODEL_KEY = { ollama: 'embedding_model', openai: 'openai_embedding_model', gemini: 'gemini_embedding_model' }

export default function Settings() {
  const { toast, stats, reloadStats, openSetup, go } = useApp()
  const [vals, setVals] = useState(null)
  const [health, setHealth] = useState(null)
  const [setup, setSetup] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    api.get('/settings').then((r) => setVals(r.valores))
    api.get('/agent/health').then(setHealth)
    api.get('/setup').then(setSetup)
  }, [stats?.agente?.saude?.provedor])
  if (!vals || !setup) return null
  const prov = vals.llm_provider
  const provs = setup.provedores
  const key = setup.chaves[prov]
  const set = (k, v) => setVals({ ...vals, [k]: v })
  const save = async () => {
    try { setVals((await api.put('/settings', vals)).valores); toast('Configurações salvas e registradas no log') } catch (e) { toast(e.message, 'bad') }
  }
  const check = async () => { setHealth(await api.post('/agent/check')); reloadStats() }
  const pull = async (modelo, motor) => {
    setBusy(true)
    try {
      if (motor === 'jev') await api.put('/settings', { jev_model: vals.jev_model, jev_base_url: vals.jev_base_url })
      await api.post('/agent/pull', { ...(modelo ? { modelo } : {}), ...(motor ? { motor } : {}) })
      toast(`Modelo ${modelo || vals.ollama_model} baixado`); check()
    } catch (e) { toast(e.message, 'bad') } finally { setBusy(false) }
  }
  return (
    <div>
      <div className="page-head"><div><h2>Configurações</h2><p>Parâmetros do agente de IA e do comportamento da linha. Alterações valem na hora e ficam no log.</p></div>
        <button className="btn right" onClick={openSetup}>Abrir assistente de configuração</button></div>
      <SpendPanel key={prov} />
      <div className="panel panel-pad col mb">
        <div className="row"><h3>Motor dos agentes de elegibilidade e auditoria</h3>
          <button className="btn sm right" onClick={() => go('desempenho')}>Ver desempenho</button></div>
        <div className="provider-grid">
          {Object.entries(setup.motores).map(([k, m]) => (
            <button key={k} className={`provider ${vals.agent_engine === k ? 'on' : ''}`} onClick={() => set('agent_engine', k)}>
              <b>{m.nome}</b>
              <span className="small muted">{m.descricao}</span>
              <span className="small mono">{k === 'jev' ? vals.jev_model : `${provs[prov]?.nome}, ${vals[{ ollama: 'ollama_model', anthropic: 'anthropic_model', openai: 'openai_model', gemini: 'gemini_model' }[prov]]}`}</span>
            </button>
          ))}
        </div>
        <div className="form-grid">
          <label className="field" title="Tag do modelo de decisão no Ollama, como em 'ollama pull tev1:0.8b'.">Modelo JEV
            <input value={vals.jev_model} list="jev-models" onChange={(e) => set('jev_model', e.target.value)} />
            <datalist id="jev-models">{['tev1:0.8b', 'tev1', 'nimble'].map((m) => <option key={m} value={m} />)}</datalist></label>
          <label className="field" title="Vazio usa a mesma URL do Ollama abaixo. O endpoint /v1/systemone exige Ollama 0.35 ou mais novo.">URL do Ollama do JEV
            <input value={vals.jev_base_url} placeholder={vals.ollama_base_url} onChange={(e) => set('jev_base_url', e.target.value)} /></label>
          <label className="field">Tempo limite do JEV (s)<input type="number" value={vals.jev_timeout_s} onChange={(e) => set('jev_timeout_s', Number(e.target.value))} /></label>
          <label className="field" title="Decisões simultâneas por worker no modelo JEV.">Chamadas simultâneas do JEV<input type="number" value={vals.jev_max_concurrency} onChange={(e) => set('jev_max_concurrency', Number(e.target.value))} /></label>
        </div>
        <label className="check"><input type="checkbox" checked={vals.agent_eligibility_enabled} onChange={(e) => set('agent_eligibility_enabled', e.target.checked)} />
          O agente também classifica a elegibilidade (as regras continuam decidindo; divergências ficam no log)</label>
        <label className="check"><input type="checkbox" checked={vals.agent_compare_enabled} onChange={(e) => set('agent_compare_enabled', e.target.checked)} />
          Comparar os dois motores: o outro motor responde as mesmas tarefas logo depois, sem decidir</label>
        <div className="small muted">A comparação mede Qwen e JEV nos mesmos casos e mostra a concordância entre eles no painel de desempenho. Ela soma o tempo do segundo motor a cada estágio com agente.</div>
        <div className="row">
          <button className="btn primary" onClick={save}>Salvar</button>
          <button className="btn" onClick={() => pull(vals.jev_model, 'jev')} disabled={busy}>{busy ? 'Baixando...' : 'Baixar modelo JEV'}</button>
          {health?.jev ? <span className="small">{health.jev.ok ? <Badge tone="ok">JEV disponível</Badge> : <Badge tone="bad">JEV indisponível</Badge>} {health.jev.erro || ''}</span> : null}
        </div>
      </div>
      <div className="grid2">
        <div className="panel panel-pad col">
          <h3>Provedor de IA</h3>
          <div className="form-grid">
            <label className="field">Provedor dos agentes
              <select value={prov} onChange={(e) => set('llm_provider', e.target.value)}>
                {Object.entries(provs).map(([k, p]) => <option key={k} value={k}>{p.nome}</option>)}
              </select>
            </label>
            {(CLOUD_FIELDS[prov] || []).map(([k, label, type]) => (
              <label key={k} className="field">{label}{k === 'anthropic_effort'
                ? <select value={vals[k]} onChange={(e) => set(k, e.target.value)}>{['low', 'medium', 'high', 'xhigh', 'max'].map((x) => <option key={x} value={x}>{x}</option>)}</select>
                : <input type={type} value={vals[k]} list={k.endsWith('_model') ? 'cfg-models' : undefined} onChange={(e) => set(k, e.target.value)} />}</label>
            ))}
            {prov !== 'ollama' ? <>
              <label className="field" title="Tempo limite de cada chamada ao provedor na nuvem.">Tempo limite (s)<input type="number" value={vals.cloud_timeout_s} onChange={(e) => set('cloud_timeout_s', Number(e.target.value))} /></label>
              <label className="field" title="Chamadas simultâneas por worker ao provedor na nuvem.">Chamadas simultâneas<input type="number" value={vals.cloud_max_concurrency} onChange={(e) => set('cloud_max_concurrency', Number(e.target.value))} /></label>
              <label className="field" title="Máximo de tokens por resposta, incluindo o raciocínio do modelo.">Máximo de tokens<input type="number" value={vals.cloud_max_tokens} onChange={(e) => set('cloud_max_tokens', Number(e.target.value))} /></label>
            </> : null}
            <datalist id="cfg-models">{(provs[prov]?.modelos || []).map((m) => <option key={m} value={m} />)}</datalist>
          </div>
          {provs[prov]?.chave ? (
            <div className="small">{key?.configurada
              ? <Badge tone="ok">chave de API salva{key.final ? `, termina em ${key.final}` : ''} ({key.origem})</Badge>
              : <Badge tone="bad">sem chave de API</Badge>} Para trocar a chave, use o assistente de configuração.</div>
          ) : null}
          <h3 className="mt">Ollama</h3>
          <div className="form-grid">
            {FIELDS.slice(0, 8).map(([k, label, type, help]) => (
              <label key={k} className="field" title={help}>{label}<input type={type} value={vals[k]} onChange={(e) => set(k, type === 'number' ? Number(e.target.value) : e.target.value)} /></label>
            ))}
          </div>
          <label className="check"><input type="checkbox" checked={vals.heuristic_fallback_enabled} onChange={(e) => set('heuristic_fallback_enabled', e.target.checked)} />
            Usar agente simulado (heurístico) quando a IA estiver indisponível</label>
          <div className="small muted">Desligado (padrão): os casos param em "Aguardando agente de IA" e são retomados sozinhos quando a IA volta. Ligado: um agente heurístico responde, marcado como simulado em cada decisão.</div>
          <label className="check"><input type="checkbox" checked={vals.agent_cache_enabled} onChange={(e) => set('agent_cache_enabled', e.target.checked)} /> Reaproveitar respostas idênticas (cache)</label>
          <label className="field">Revisão humana
            <select value={vals.human_review_mode} onChange={(e) => set('human_review_mode', e.target.value)}>
              <option value="SE_REPROVADO">Somente quando o agente ou as regras reprovarem</option>
              <option value="SEMPRE">Sempre (toda auditoria e toda conferência final passam por uma pessoa)</option>
            </select>
          </label>
          <h3 className="mt">Embeddings e perguntas</h3>
          <div className="form-grid">
            <label className="field" title="Quem gera os embeddings dos eventos. Trocar reindexa tudo.">Gerador de embeddings
              <select value={vals.embedding_provider} onChange={(e) => set('embedding_provider', e.target.value)}>
                {Object.entries(setup.provedores_embedding).map(([k, p]) => <option key={k} value={k}>{p.nome}</option>)}
              </select></label>
            {EMB_MODEL_KEY[vals.embedding_provider] ? (
              <label className="field" title="Trocar o modelo reindexa tudo.">Modelo de embedding
                <input value={vals[EMB_MODEL_KEY[vals.embedding_provider]]} onChange={(e) => set(EMB_MODEL_KEY[vals.embedding_provider], e.target.value)} /></label>
            ) : null}
            <label className="field" title="Vazio usa o mesmo modelo do agente de conferência, no mesmo provedor.">Modelo do agente de perguntas
              <input value={vals.ask_model} placeholder={vals[{ ollama: 'ollama_model', anthropic: 'anthropic_model', openai: 'openai_model', gemini: 'gemini_model' }[prov]]} onChange={(e) => set('ask_model', e.target.value)} /></label>
            <label className="field" title="Quantos eventos parecidos entram como evidência em cada resposta.">Documentos por resposta
              <input type="number" value={vals.ask_top_k} onChange={(e) => set('ask_top_k', Number(e.target.value))} /></label>
          </div>
          <label className="check"><input type="checkbox" checked={vals.indexing_enabled} onChange={(e) => set('indexing_enabled', e.target.checked)} /> Indexar eventos continuamente</label>
          <div className="row"><button className="btn primary" onClick={save}>Salvar</button></div>
        </div>
        <div className="col">
          <div className="panel panel-pad col">
            <div className="row"><h3>Saúde da IA generativa</h3><span className="right">{(health?.ok_qwen ?? health?.ok) ? <Badge tone="ok">disponível</Badge> : <Badge tone="bad">indisponível</Badge>}</span></div>
            <dl className="kv">
              <dt>Provedor</dt><dd>{health?.provedor_nome || provs[prov]?.nome}</dd>
              {health?.url ? <><dt>URL</dt><dd className="mono">{health.url}</dd></> : null}
              <dt>Modelo</dt><dd>{health?.modelo} {health?.modelo_disponivel ? <Badge tone="ok">disponível</Badge> : <Badge tone="warn">indisponível</Badge>}</dd>
              <dt>Embedding</dt><dd>{health?.modelo_embedding} {health?.provedor_embedding === 'simulado' ? <Badge tone="warn">simulado</Badge> : health?.modelo_embedding_disponivel ? <Badge tone="ok">disponível</Badge> : <Badge tone="warn">indisponível</Badge>}</dd>
              {health?.erro_embedding ? <><dt>Erro embedding</dt><dd className="small" style={{ color: 'var(--bad)' }}>{health.erro_embedding}</dd></> : null}
              <dt>Modelos disponíveis</dt><dd className="small" style={{ maxHeight: 90, overflow: 'auto' }}>{(health?.modelos || []).join(', ') || '-'}</dd>
              <dt>Verificado</dt><dd>{dateTime(health?.verificado_em)}</dd>
              {(health?.erro_qwen ?? health?.erro) ? <><dt>Erro</dt><dd className="small" style={{ color: 'var(--bad)' }}>{health.erro_qwen ?? health.erro}</dd></> : null}
            </dl>
            <div className="row">
              <button className="btn" onClick={check}>Verificar agora</button>
              {prov === 'ollama' ? <button className="btn" onClick={() => pull()} disabled={busy}>{busy ? 'Baixando...' : 'Baixar modelo do agente'}</button> : null}
              {vals.embedding_provider === 'ollama' ? <button className="btn" onClick={() => pull(vals.embedding_model)} disabled={busy}>Baixar modelo de embedding</button> : null}
              <button className="btn" onClick={async () => { const r = await api.post('/agent/cache/clear'); toast(`${r.removidos} respostas removidas do cache`) }}>Limpar cache</button>
            </div>
            <div className="small muted">Estatísticas: {stats?.agente?.chamadas || 0} chamadas, média {stats?.agente?.duracao_media_ms ?? '-'} ms, recomendações {JSON.stringify(stats?.agente?.recomendacoes || {})}.</div>
          </div>
          <div className="panel panel-pad col">
            <h3>Linha de produção</h3>
            <div className="form-grid">
              {FIELDS.slice(8).map(([k, label, type, help]) => (
                <label key={k} className="field" title={help}>{label}<input type={type} value={vals[k]} onChange={(e) => set(k, Number(e.target.value))} /></label>
              ))}
            </div>
            <div className="row"><button className="btn primary" onClick={save}>Salvar</button></div>
          </div>
          <div className="panel panel-pad col">
            <h3>Reiniciar laboratório</h3>
            <p className="small muted">Limpa casos, aprovações, filas, log e embeddings. Opcionalmente gera um novo time.</p>
            <div className="row">
              <button className="btn danger" onClick={async () => { await api.post('/reset', {}); toast('Laboratório reiniciado'); reloadStats() }}>Limpar execução</button>
              <button className="btn danger" onClick={async () => { await api.post('/reset', { colaboradores: true }); toast('Laboratório reiniciado com novo time'); reloadStats() }}>Limpar e gerar novo time</button>
            </div>
          </div>
          <details><summary>Filas (Redis Streams)</summary><Json value={stats?.filas} /></details>
        </div>
      </div>
    </div>
  )
}
