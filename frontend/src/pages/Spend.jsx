import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, dateTime, dur, useApp } from '../ui.jsx'

export const MODEL_KEY = { ollama: 'ollama_model', anthropic: 'anthropic_model', openai: 'openai_model', gemini: 'gemini_model' }
export const EXTERNAL = ['anthropic', 'openai', 'gemini']
const NAMES = { anthropic: 'Anthropic', openai: 'OpenAI', gemini: 'Google Gemini' }
const ORIGINS = { agente: 'Agente', perguntas: 'Perguntas', embeddings: 'Embeddings', teste: 'Teste da API' }
// Typical audit: case, plan and contract in the prompt, structured answer back.
const TYPICAL = { entrada: 6000, saida: 800 }

export function usd(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  const n = Number(v)
  return 'US$ ' + n.toLocaleString('pt-BR', { minimumFractionDigits: n !== 0 && n < 1 ? 4 : 2, maximumFractionDigits: n !== 0 && n < 1 ? 4 : 2 })
}

export function callCost(price, entrada = TYPICAL.entrada, saida = TYPICAL.saida) {
  if (!price) return null
  return (entrada * Number(price.entrada) + saida * Number(price.saida)) / 1e6
}

export function priceOf(precos, prov, model) {
  const rows = precos?.[prov] || []
  const exact = rows.find((r) => r.modelo === model)
  if (exact) return exact
  const prefix = rows.filter((r) => model?.startsWith(r.modelo)).sort((a, b) => b.modelo.length - a.modelo.length)[0]
  if (prefix) return { ...prefix, modelo: model }
  if (!rows.length) return null
  const worst = rows.reduce((a, b) => (a.entrada + a.saida >= b.entrada + b.saida ? a : b))
  return { ...worst, modelo: model, origem: 'desconhecido' }
}

// ------------------------------------------------------------------ API test drawing
function endpoints(prov, vals) {
  const model = vals[MODEL_KEY[prov]]
  if (prov === 'anthropic') return ['GET https://api.anthropic.com/v1/models', 'POST https://api.anthropic.com/v1/messages']
  if (prov === 'gemini') return ['GET https://generativelanguage.googleapis.com/v1beta/models', `POST .../v1beta/models/${model}:generateContent`]
  if (prov === 'openai') {
    const base = (vals.openai_base_url || 'https://api.openai.com/v1').replace(/\/$/, '')
    return [`GET ${base}/models`, `POST ${base}/chat/completions`]
  }
  const base = (vals.ollama_base_url || '').replace(/\/$/, '')
  return [`GET ${base}/api/tags`, `POST ${base}/api/chat`]
}

const STAGES = [['chave', 'Chave de API'], ['teto', 'Teto de gastos'], ['conexao', 'Conexão'], ['modelo', 'Modelo'], ['chamada', 'Chamada de teste']]
const STATE_LABEL = { OK: 'ok', FALHOU: 'falhou', PENDENTE: 'não executado', IGNORADO: 'não se aplica', RODANDO: 'testando' }

function Mark({ state }) {
  if (state === 'OK') return <svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 7.5l2.5 2.5L11 4.5" fill="none" stroke="currentColor" strokeWidth="2" /></svg>
  if (state === 'FALHOU') return <svg width="14" height="14" viewBox="0 0 14 14"><path d="M4 4l6 6M10 4l-6 6" stroke="currentColor" strokeWidth="2" /></svg>
  if (state === 'IGNORADO') return <svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 7h8" stroke="currentColor" strokeWidth="2" /></svg>
  return <svg width="14" height="14" viewBox="0 0 14 14"><circle cx="7" cy="7" r="2.5" fill="currentColor" /></svg>
}

/** Draws the API test as a flow: key, cap, connection, model and test call, each with its state. */
export function ApiTestFlow({ r, prov, vals, running }) {
  const byId = Object.fromEntries((r?.etapas || []).map((e) => [e.id, e]))
  const [list, call] = endpoints(prov, vals)
  const nodes = STAGES.map(([id, nome]) => {
    const e = byId[id]
    const state = running ? 'RODANDO' : e?.estado || 'PENDENTE'
    return { id, nome, state, detalhe: e?.detalhe }
  })
  return (
    <div className="api-test">
      <div className="api-flow" role="list">
        <div className="api-node app" role="listitem"><b>Laboratório</b><span className="small muted">backend</span></div>
        {nodes.map((n) => (
          <React.Fragment key={n.id}>
            <span className={`api-link ${n.state.toLowerCase()}`} aria-hidden="true" />
            <div className={`api-node ${n.state.toLowerCase()}`} role="listitem" title={n.detalhe || ''}>
              <span className="api-mark"><Mark state={n.state} /></span>
              <b>{n.nome}</b>
              <span className="small">{STATE_LABEL[n.state]}</span>
            </div>
          </React.Fragment>
        ))}
        <span className={`api-link ${r?.ok ? 'ok' : 'pendente'}`} aria-hidden="true" />
        <div className={`api-node app ${r?.ok ? 'ok' : ''}`} role="listitem"><b>{prov === 'ollama' ? 'Ollama' : 'Provedor'}</b><span className="small muted mono">{vals[MODEL_KEY[prov]]}</span></div>
      </div>
      <div className="api-calls small mono">
        <div><span className="muted">1.</span> {list}</div>
        <div><span className="muted">2.</span> {call} <span className="muted">(pede {'{"resposta": "ok"}'} em JSON, até 50 tokens)</span></div>
      </div>
      {r ? (
        <ol className="api-details small">
          {nodes.filter((n) => n.detalhe && n.state !== 'FALHOU').map((n) => (
            <li key={n.id} className={n.state.toLowerCase()}><b>{n.nome}:</b> {n.detalhe}</li>
          ))}
        </ol>
      ) : <div className="small muted">O teste usa os valores desta tela, antes de salvar. A chamada de teste é pequena e entra no contador de gastos.</div>}
      {r?.ok ? <div className="callout ok small">API funcionando: {r.modelo} respondeu em {dur(r.duracao_ms)}{r.custo_usd != null ? `, custo ${usd(r.custo_usd)}` : ''}.</div> : null}
      {r && !r.ok ? <div className="callout bad small"><b>O teste parou em {STAGES.find(([k]) => k === r.etapa)?.[1] || r.etapa}.</b> {r.erro}</div> : null}
    </div>
  )
}

// ------------------------------------------------------------------ meter
export function SpendMeter({ g }) {
  if (!g) return null
  if (!(g.teto_usd > 0)) {
    return <div className="row small"><b>{usd(g.gasto_usd)}</b><span className="muted">gastos ({g.periodo_rotulo})</span><span className="right"><Badge>sem teto</Badge></span></div>
  }
  const pct = Math.min(100, (g.gasto_usd / g.teto_usd) * 100)
  const tone = g.bloqueado ? 'bad' : g.alerta ? 'warn' : 'ok'
  return (
    <div className="col" style={{ gap: 4 }}>
      <div className="row small"><b>{usd(g.gasto_usd)}</b><span className="muted">de {usd(g.teto_usd)} ({g.periodo_rotulo})</span>
        <span className="right">{g.bloqueado ? <Badge tone="bad">bloqueado</Badge> : g.alerta ? <Badge tone="warn">perto do teto</Badge> : <Badge tone="ok">dentro do teto</Badge>}</span></div>
      <div className={`meter ${tone}`}><span style={{ width: `${pct}%` }} /></div>
    </div>
  )
}

// ------------------------------------------------------------------ settings panel
export function SpendPanel() {
  const { toast, reloadStats } = useApp()
  const [g, setG] = useState(null)
  const [cap, setCap] = useState(null)
  const [price, setPrice] = useState(null)
  const [busy, setBusy] = useState(false)
  const load = async () => {
    const r = await api.get('/gastos?recentes=15')
    setG(r)
    setCap({ spend_cap_usd: r.teto_usd, spend_period: r.periodo, spend_alert_percent: r.alerta_percentual })
    setPrice(r.preco_modelo ? { entrada: r.preco_modelo.entrada, saida: r.preco_modelo.saida } : null)
  }
  useEffect(() => { load().catch((e) => toast(e.message, 'bad')) }, [])
  if (!g || !cap) return null
  const external = EXTERNAL.includes(g.provedor)
  const act = async (fn, msg) => {
    setBusy(true)
    try { const r = await fn(); setG(r); toast(msg); reloadStats() } catch (e) { toast(e.message, 'bad') } finally { setBusy(false) }
  }
  const saveCap = () => act(() => api.put('/gastos/teto', cap), 'Teto de gastos salvo e registrado no log')
  const savePrice = () => act(() => api.put('/gastos/precos', { provedor: g.provedor, modelo: g.modelo, ...price }), 'Preço salvo')
  const restorePrice = () => act(() => api.put('/gastos/precos', { provedor: g.provedor, modelo: g.modelo }), 'Preço da tabela restaurado').then(load)
  const zero = () => {
    if (!window.confirm(`Zerar o contador de gastos (${g.periodo_rotulo})? O histórico de chamadas continua no log.`)) return
    act(() => api.post('/gastos/zerar'), 'Contador zerado')
  }
  const typical = callCost(g.preco_modelo)
  return (
    <div className="panel panel-pad col mb">
      <div className="row"><h3>Teto de gastos com LLM externa</h3>
        <span className="right small muted">{external ? `Agentes em ${NAMES[g.provedor]}, ${g.modelo}` : 'Agentes no Ollama: sem custo por token'}</span></div>
      <SpendMeter g={g} />
      {g.bloqueado ? <div className="callout bad small"><b>Chamadas externas bloqueadas.</b> {g.bloqueio?.mensagem}</div> : null}
      <div className="form-grid">
        <label className="field" title="Opcional. Atingido o teto, nenhuma chamada nova é feita a Anthropic, OpenAI ou Google. Vazio ou 0: sem teto, o gasto só é contado.">Teto (US$, opcional)
          <input type="number" min="0" step="0.5" placeholder="sem teto" value={cap.spend_cap_usd || ''} onChange={(e) => setCap({ ...cap, spend_cap_usd: Number(e.target.value) || 0 })} /></label>
        <label className="field">Período
          <select value={cap.spend_period} onChange={(e) => setCap({ ...cap, spend_period: e.target.value })}>
            <option value="MENSAL">Mensal (zera todo dia 1)</option>
            <option value="TOTAL">Total (nunca zera)</option>
          </select></label>
        <label className="field" title="Registra um aviso no log quando o gasto passa deste percentual do teto.">Aviso em (% do teto)
          <input type="number" min="0" max="100" value={cap.spend_alert_percent} onChange={(e) => setCap({ ...cap, spend_alert_percent: e.target.value })} /></label>
      </div>
      <div className="row">
        <button className="btn primary" onClick={saveCap} disabled={busy}>Salvar teto</button>
        <button className="btn danger" onClick={zero} disabled={busy}>Zerar contador</button>
        <span className="small muted">Total desde o início: {usd(g.gasto_total_usd)}. {g.chamadas} chamada(s) no período.</span>
      </div>
      {external && price ? (
        <>
          <h4 className="mt">Preço de {g.modelo} (US$ por milhão de tokens, opcional)</h4>
          <div className="form-grid">
            <label className="field">Entrada<input type="number" min="0" step="0.01" value={price.entrada} onChange={(e) => setPrice({ ...price, entrada: e.target.value })} /></label>
            <label className="field">Saída<input type="number" min="0" step="0.01" value={price.saida} onChange={(e) => setPrice({ ...price, saida: e.target.value })} /></label>
          </div>
          <div className="row">
            <button className="btn" onClick={savePrice} disabled={busy}>Salvar preço</button>
            {g.preco_modelo.origem === 'editado' ? <button className="btn ghost" onClick={restorePrice} disabled={busy}>Restaurar tabela</button> : null}
            <span className="small muted">{g.preco_modelo.origem === 'desconhecido' ? 'Modelo fora da tabela: sem preço informado, a conta usa o do modelo mais caro do provedor.' : g.preco_modelo.origem === 'editado' ? 'Preço editado por você.' : 'Preço da tabela de referência.'}
              {typical != null ? ` Uma auditoria típica custa perto de ${usd(typical)}.` : ''}</span>
          </div>
        </>
      ) : null}
      {g.por_modelo?.length ? (
        <details><summary>Gasto por modelo no período</summary>
          <table className="tbl small"><tbody>{g.por_modelo.map((m) => <tr key={m.provedor + m.modelo}><td>{m.provedor}</td><td className="mono">{m.modelo}</td><td>{usd(m.custo_usd)}</td></tr>)}</tbody></table>
        </details>
      ) : null}
      {g.recentes?.length ? (
        <details><summary>Últimas chamadas cobradas</summary>
          <table className="tbl small">
            <thead><tr><th>Quando</th><th>Origem</th><th>Modelo</th><th>Tokens (entrada / saída)</th><th>Custo</th></tr></thead>
            <tbody>{g.recentes.map((c, i) => (
              <tr key={i}><td>{dateTime(c.ts)}</td><td>{ORIGINS[c.origem] || c.origem}</td><td className="mono">{c.modelo}</td>
                <td>{c.tokens_entrada.toLocaleString('pt-BR')} / {c.tokens_saida.toLocaleString('pt-BR')}{c.estimado ? ' (estimado)' : ''}</td><td>{usd(c.custo_usd)}</td></tr>
            ))}</tbody>
          </table>
        </details>
      ) : null}
      <div className="small muted">O custo de cada chamada vem dos tokens informados pelo provedor vezes o preço do modelo. Teto e preço são opcionais: sem teto o gasto só é contado. Com teto, antes de cada chamada externa o laboratório confere o gasto; atingido o teto, a chamada não é enviada, os casos aguardam a IA e a mensagem aparece aqui, no topo da tela e no log. Chamadas que já estavam em andamento terminam e entram no contador.</div>
    </div>
  )
}
