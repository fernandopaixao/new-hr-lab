import React, { createContext, useContext, useState, useCallback, useEffect } from 'react'

export const AppCtx = createContext(null)
export const useApp = () => useContext(AppCtx)

const STATUS_TONE = {
  NA_FILA: '', PROCESSANDO: 'info', PARADO: 'violet', AGUARDANDO_APROVACAO: 'warn', AGUARDANDO_AGENTE: 'warn',
  CONCLUIDO: 'ok', CONCLUIDO_COM_RESSALVAS: 'ok', NAO_ELEGIVEL: 'bad', REJEITADO: 'bad', REJEITADO_NA_ENTRADA: 'bad',
  DUPLICADO: '', FALHOU_COMPENSADO: 'bad', ERRO: 'bad', CANCELADO: '', REVERTIDO: 'bad',
  PENDENTE: 'warn', APROVADA: 'ok', REJEITADA: 'bad', CANCELADA: '',
  OK: 'ok', DIVERGENTE: 'bad', DIVERGENCIA_AGENTE: 'warn', EXECUTANDO: 'info', SEM_CANDIDATO: '', TEMPO_ESGOTADO: 'bad', CONCLUIDA: 'ok',
  APROVADO: 'ok', REPROVADO: 'bad', APROVADO_COM_RESSALVAS: 'warn', REQUER_APROVACAO: 'warn',
  ELEGIVEL: 'ok', EXCECAO_NECESSARIA: 'warn', EXECUTADA: 'ok', FALHOU: 'bad', COMPENSADA: 'violet', NAO_COMPENSAVEL: 'warn',
  BLOQUEANTE: 'bad', EXCECIONAVEL: 'warn', ALERTA: 'info',
}

const EXTRA_LABELS = {
  PENDENTE: 'Pendente', APROVADA: 'Aprovada', REJEITADA: 'Rejeitada', CANCELADA: 'Cancelada', OK: 'Conforme esperado',
  DIVERGENTE: 'Divergente', DIVERGENCIA_AGENTE: 'Agente mais rigoroso', EXECUTANDO: 'Executando', SEM_CANDIDATO: 'Sem candidato',
  TEMPO_ESGOTADO: 'Tempo esgotado', CONCLUIDA: 'Concluída', APROVADO: 'Aprovado', REPROVADO: 'Reprovado',
  APROVADO_COM_RESSALVAS: 'Aprovado com ressalvas', REQUER_APROVACAO: 'Requer aprovação', ELEGIVEL: 'Elegível',
  EXCECAO_NECESSARIA: 'Exceção necessária', EXECUTADA: 'Executada', FALHOU: 'Falhou', COMPENSADA: 'Compensada',
  NAO_COMPENSAVEL: 'Não compensável', BLOQUEANTE: 'Bloqueante', EXCECIONAVEL: 'Excecionável', ALERTA: 'Alerta',
}

export function Status({ value, label }) {
  const { meta } = useApp()
  if (!value) return null
  const text = label || meta?.status?.[value] || EXTRA_LABELS[value] || value
  const tone = STATUS_TONE[value] ?? ''
  return (
    <span className={`badge ${tone}`}>
      {value === 'PROCESSANDO' || value === 'EXECUTANDO' ? <span className="dot pulse" /> : null}
      {text}
    </span>
  )
}

export function Badge({ tone = '', children }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

export function money(v) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

export function time(ms) {
  if (!ms) return '-'
  const d = new Date(Number(ms))
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function dateTime(ms) {
  if (!ms) return '-'
  return new Date(Number(ms)).toLocaleString('pt-BR')
}

export function dur(ms) {
  if (ms === null || ms === undefined) return '-'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

export function Json({ value, max = 420 }) {
  return (
    <pre className="panel panel-pad" style={{ maxHeight: max, overflow: 'auto', background: 'var(--panel-2)' }}>
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs">
      {tabs.map(([k, label]) => (
        <button key={k} className={value === k ? 'active' : ''} onClick={() => onChange(k)}>{label}</button>
      ))}
    </div>
  )
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>
}

export function Modal({ title, onClose, children, footer }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') { e.stopImmediatePropagation(); onClose() } }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose])
  return (
    <div className="modal" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="panel">
        <div className="panel-pad row" style={{ borderBottom: '1px solid var(--border)' }}>
          <h3>{title}</h3>
          <button className="btn ghost right" onClick={onClose}>Fechar</button>
        </div>
        <div className="panel-pad">{children}</div>
        {footer ? <div className="panel-pad row" style={{ borderTop: '1px solid var(--border)', justifyContent: 'flex-end' }}>{footer}</div> : null}
      </div>
    </div>
  )
}

export function RulesTable({ rules, onlyFailed = false }) {
  const [showAll, setShowAll] = useState(!onlyFailed)
  if (!rules || !rules.length) return <Empty>Nenhuma regra avaliada.</Empty>
  const shown = showAll ? rules : rules.filter((r) => !r.passou)
  return (
    <div>
      <div className="row small muted mb">
        <span>{rules.filter((r) => r.passou).length} de {rules.length} regras atendidas</span>
        <label className="check right"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> mostrar todas</label>
      </div>
      <table className="tbl">
        <thead><tr><th>Resultado</th><th>Regra</th><th>Tipo</th><th>Explicação</th><th>Base legal</th><th>Origem</th></tr></thead>
        <tbody>
          {shown.map((r, i) => (
            <tr key={i} className={!r.passou ? (r.tipo === 'BLOQUEANTE' ? 'fail' : 'warnrow') : ''}>
              <td>{r.passou ? <Badge tone="ok">Atende</Badge> : <Badge tone={r.tipo === 'BLOQUEANTE' ? 'bad' : 'warn'}>Não atende</Badge>}</td>
              <td><b>{r.id}</b><div className="small muted">{r.descricao}</div>
                {r.expressao ? <details className="small"><summary>expressão</summary><code>{r.expressao}</code></details> : null}</td>
              <td><Status value={r.tipo} />{r.aprovadores?.length ? <div className="small muted">aprova: {r.aprovadores.join(', ')}</div> : null}</td>
              <td>{r.explicacao}{r.erro ? <div className="small" style={{ color: 'var(--bad)' }}>{r.erro}</div> : null}</td>
              <td className="small">{r.base_legal || '-'}</td>
              <td className="small muted">{r.origem}</td>
            </tr>
          ))}
          {!shown.length ? <tr><td colSpan={6}><Empty>Todas as regras foram atendidas.</Empty></td></tr> : null}
        </tbody>
      </table>
    </div>
  )
}

const ENGINE_NAMES = { qwen: 'Qwen', jev: 'JEV', heuristico: 'simulado' }
const VERDICT_TONE = { APROVADO: 'APROVADO', ELEGIVEL: 'APROVADO', REPROVADO: 'REPROVADO', NAO_ELEGIVEL: 'REPROVADO', EXCECAO_NECESSARIA: 'EXCECAO' }

export function AgentCard({ review, title }) {
  if (!review) return <Empty>O agente ainda não avaliou.</Empty>
  const verdict = review.veredito || review.recomendacao || review.classificacao
  const tone = VERDICT_TONE[verdict] || ''
  const comp = review.comparacao
  return (
    <div className={`agent-card ${tone}`}>
      <div className="row">
        <div>
          <h4>{title}</h4>
          <div className={`rec ${tone}`}>{review.classificacao ? 'Classificação' : 'Recomendação'}: {verdict}</div>
        </div>
        <div className="right small muted" style={{ textAlign: 'right' }}>
          <div>{review.agente === 'heuristico' ? <Badge tone="warn">agente simulado (heurístico)</Badge>
            : <>{review.motor ? <Badge tone="violet">motor {ENGINE_NAMES[review.motor] || review.motor}</Badge> : null} <Badge tone="info">{review.modelo}</Badge></>}</div>
          <div>confiança {Math.round((review.confianca || 0) * 100)}% · {dur(review.processamento_ms ?? review.duracao_ms)}{review.resposta_ms != null && !review.cache ? ` (modelo ${dur(review.resposta_ms)})` : ''}{review.cache ? ' · cache' : ''}{review.tokens_por_segundo ? ` · ${review.tokens_por_segundo} tok/s` : ''}</div>
        </div>
      </div>
      {comp ? (
        <div className={`callout small ${comp.erro ? 'warn' : comp.concorda ? 'ok' : 'warn'}`}>
          <b>Comparação com {ENGINE_NAMES[comp.motor] || comp.motor}</b> (não decide): {comp.erro ? `falhou: ${comp.erro}`
            : <>{comp.veredito}, confiança {Math.round((comp.confianca || 0) * 100)}%, {dur(comp.processamento_ms)}{comp.cache ? ' (cache)' : ''}. {comp.concorda ? 'Os dois motores concordam.' : 'Os motores divergem.'}</>}
        </div>
      ) : null}
      <p>{review.resumo}</p>
      {review.achados?.length ? (
        <table className="tbl">
          <thead><tr><th>Severidade</th><th>Referência</th><th>Achado</th></tr></thead>
          <tbody>{review.achados.map((a, i) => (
            <tr key={i}><td><Badge tone={['CRITICO', 'ALTO'].includes(a.severidade) ? 'bad' : a.severidade === 'MEDIO' ? 'warn' : 'info'}>{a.severidade}</Badge></td>
              <td className="small">{a.referencia || '-'}</td><td>{a.descricao}</td></tr>
          ))}</tbody>
        </table>
      ) : <div className="small muted">Sem achados.</div>}
      <p className="small"><b>Justificativa:</b> {review.justificativa}</p>
      {review.motivo_fallback ? <div className="callout warn small">Fallback heurístico usado porque: {review.motivo_fallback}</div> : null}
      <details className="small mt"><summary>Depurar chamada ao agente (prompt e resposta bruta)</summary>
        <h4 className="mt">Prompt</h4><pre className="panel panel-pad" style={{ maxHeight: 300, overflow: 'auto' }}>{review.prompt}</pre>
        {review.resposta_bruta ? <><h4 className="mt">Resposta bruta</h4><pre className="panel panel-pad">{review.resposta_bruta}</pre></> : null}
        <div className="muted mt">tokens prompt {review.prompt_eval_count ?? '-'} · tokens resposta {review.eval_count ?? '-'} · tentativas {review.tentativas ?? 1}</div>
      </details>
    </div>
  )
}

export function useToasts() {
  const [toasts, setToasts] = useState([])
  const push = useCallback((text, tone = '') => {
    const id = Math.random()
    setToasts((t) => [...t.slice(-2), { id, text, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500)
  }, [])
  const view = (
    <div className="toast-wrap">{toasts.map((t) => <div key={t.id} className={`toast ${t.tone}`}>{t.text}</div>)}</div>
  )
  return [push, view]
}

export function DiffTable({ diff }) {
  if (!diff || !diff.length) return <Empty>Sem alterações.</Empty>
  const fmt = (v) => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v ?? '-'))
  const cell = { maxWidth: 420, wordBreak: 'break-word' }
  const listDiff = (a, b) => {
    const ka = new Set(a.map((x) => JSON.stringify(x)))
    const kb = new Set(b.map((x) => JSON.stringify(x)))
    return [a.filter((x) => !kb.has(JSON.stringify(x))), b.filter((x) => !ka.has(JSON.stringify(x)))]
  }
  return (
    <table className="tbl">
      <thead><tr><th>Campo</th><th>Antes</th><th>Depois</th></tr></thead>
      <tbody>{diff.map((d, i) => {
        if (Array.isArray(d.antes) && Array.isArray(d.depois)) {
          const [removed, added] = listDiff(d.antes, d.depois)
          return (
            <tr key={i}><td><b>{d.campo}</b><div className="small muted">{d.antes.length} para {d.depois.length} itens</div></td>
              <td className="small mono diff-old" style={cell}>{removed.length ? removed.map((x, j) => <div key={j}>{fmt(x)}</div>) : <span className="muted">nada removido</span>}</td>
              <td className="small mono diff-new" style={cell}>{added.length ? added.map((x, j) => <div key={j}>{fmt(x)}</div>) : <span className="muted">nada incluído</span>}</td></tr>
          )
        }
        return (
          <tr key={i}><td><b>{d.campo}</b></td>
            <td className="small mono diff-old" style={cell}>{fmt(d.antes)}</td>
            <td className="small mono diff-new" style={cell}>{fmt(d.depois)}</td></tr>
        )
      })}</tbody>
    </table>
  )
}
