import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Badge, Empty, dur, time, useApp } from '../ui.jsx'

const ENGINE_COLOR = { qwen: 'var(--qwen)', jev: 'var(--jev)', heuristico: 'var(--muted)' }
const PERIODS = [[1, 'Última hora'], [24, 'Últimas 24 horas'], [168, 'Últimos 7 dias'], [720, 'Últimos 30 dias'], [0, 'Todo o histórico']]
const BUCKETS = [[0, 'automático'], [1, '1 min'], [5, '5 min'], [15, '15 min'], [60, '1 hora'], [1440, '1 dia']]
const pct = (v) => (v == null ? '-' : `${Math.round(v * 100)}%`)

function bucketLabel(ms, step) {
  const d = new Date(ms)
  if (step >= 86_400_000) return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
  if (step >= 3_600_000) return `${d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })} ${d.getHours()}h`
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

function stepLabel(ms) {
  if (ms >= 86_400_000) return `${Math.round(ms / 86_400_000)} dia(s)`
  if (ms >= 3_600_000) return `${Math.round(ms / 3_600_000)} hora(s)`
  return `${Math.round(ms / 60_000)} min`
}

function niceMax(v) {
  if (v <= 0) return 1
  const p = 10 ** Math.floor(Math.log10(v))
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v)
}

function History({ data, field, engines }) {
  const pts = data.serie
  const step = data.periodo.balde_ms
  const values = pts.flatMap((p) => engines.map((m) => p.motores[m]?.[field])).filter((v) => v != null)
  if (!values.length) return <Empty>Nenhuma chamada medida neste período.</Empty>
  const W = 760, H = 220, L = 52, B = 22, T = 8
  const max = niceMax(Math.max(...values))
  const x = (i) => L + (pts.length === 1 ? (W - L) / 2 : (i / (pts.length - 1)) * (W - L - 8))
  const y = (v) => T + (H - T - B) * (1 - v / max)
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max)
  const labelEvery = Math.max(1, Math.ceil(pts.length / 8))
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Tempo médio dos agentes ao longo do tempo, por motor">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - 4} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeWidth="1" />
            <text x={L - 6} y={y(t) + 3} fontSize="10" fill="var(--muted)" textAnchor="end">{dur(Math.round(t))}</text>
          </g>
        ))}
        {pts.map((p, i) => (i % labelEvery === 0
          ? <text key={i} x={x(i)} y={H - 6} fontSize="10" fill="var(--muted)" textAnchor="middle">{bucketLabel(p.inicio, step)}</text> : null))}
        {engines.map((m) => {
          const seg = []
          let cur = []
          pts.forEach((p, i) => {
            const v = p.motores[m]?.[field]
            if (v == null) { if (cur.length) seg.push(cur); cur = [] } else cur.push([x(i), y(v), v, p])
          })
          if (cur.length) seg.push(cur)
          return (
            <g key={m}>
              {seg.map((s, k) => (s.length > 1
                ? <polyline key={k} points={s.map(([a, b]) => `${a},${b}`).join(' ')} fill="none" stroke={ENGINE_COLOR[m]} strokeWidth="2" strokeLinejoin="round" /> : null))}
              {seg.flat().map(([a, b, v, p], k) => (
                <circle key={k} cx={a} cy={b} r="3.5" fill={ENGINE_COLOR[m]} stroke="var(--panel)" strokeWidth="1.5">
                  <title>{`${data.nomes[m] || m}, ${bucketLabel(p.inicio, step)}: ${dur(v)} em média (${p.motores[m].n} chamada(s))`}</title>
                </circle>
              ))}
            </g>
          )
        })}
      </svg>
      <div className="row small muted">
        {engines.map((m) => <span key={m}><span className="dot" style={{ background: ENGINE_COLOR[m] }} /> {data.nomes[m] || m}</span>)}
        <span className="right">cada ponto é a média de um intervalo de {stepLabel(step)}</span>
      </div>
    </div>
  )
}

function EngineCard({ row, active }) {
  const ag = row.concordancia_regras
  return (
    <div className="panel panel-pad col engine-card" style={{ borderTop: `3px solid ${ENGINE_COLOR[row.motor]}` }}>
      <div className="row">
        <h3>{row.nome}</h3>
        <span className="right">{active ? <Badge tone="ok">motor ativo</Badge> : row.chamadas ? <Badge>comparação</Badge> : <Badge>sem chamadas</Badge>}</span>
      </div>
      <div className="small muted">{row.modelos.length ? row.modelos.join(', ') : 'nenhum modelo chamado no período'}</div>
      <div className="engine-kpis">
        <div><div className="v">{dur(row.processamento_ms.media)}</div><div className="l">processamento médio</div></div>
        <div><div className="v">{dur(row.processamento_ms.p95)}</div><div className="l">processamento p95</div></div>
        <div><div className="v">{dur(row.resposta_ms.media)}</div><div className="l">resposta do modelo, média</div></div>
        <div><div className="v">{dur(row.resposta_ms.p95)}</div><div className="l">resposta do modelo, p95</div></div>
      </div>
      <dl className="kv small">
        <dt>Chamadas</dt><dd>{row.chamadas} ({row.principal} como motor ativo, {row.comparacao} em comparação)</dd>
        <dt>Medidas</dt><dd>{row.medidas} (sem cache, sem simulado, sem erro)</dd>
        <dt>Espera por vaga</dt><dd>média {dur(row.espera_ms.media)}, p95 {dur(row.espera_ms.p95)}</dd>
        <dt>Mín. e máx.</dt><dd>{dur(row.processamento_ms.min)} a {dur(row.processamento_ms.max)}</dd>
        <dt>Tokens</dt><dd>{row.tokens_entrada_media ?? '-'} de entrada, {row.tokens_saida_media ?? '-'} de saída (média)</dd>
        <dt>Confiança média</dt><dd>{pct(row.confianca_media)}</dd>
        <dt>Concorda com as regras</dt><dd>{pct(ag.taxa)} de {ag.total}{ag.total ? ` (mais rigoroso ${ag.agente_mais_rigoroso}, menos rigoroso ${ag.regras_mais_rigorosas})` : ''}</dd>
        <dt>Erros</dt><dd>{row.erros ? <Badge tone="bad">{row.erros}</Badge> : 0}{row.cache ? ` · ${row.cache} do cache` : ''}{row.simuladas ? ` · ${row.simuladas} simuladas` : ''}</dd>
      </dl>
    </div>
  )
}

function Cell({ s }) {
  if (!s || !s.n) return <td className="muted">-</td>
  return <td><b>{dur(s.media)}</b><div className="small muted">p50 {dur(s.p50)} · p95 {dur(s.p95)}</div></td>
}

export default function Performance() {
  const { onLive, openCase, go, toast } = useApp()
  const [data, setData] = useState(null)
  const [periodo, setPeriodo] = useState(24)
  const [balde, setBalde] = useState(0)
  const [field, setField] = useState('processamento_media_ms')
  const pending = useRef(false)

  const load = useCallback(async () => {
    try { setData(await api.get(`/metrics/agentes?periodo_horas=${periodo}&balde_min=${balde}`)) } catch (e) { toast(e.message, 'bad') }
  }, [periodo, balde, toast])
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t) }, [load])
  useEffect(() => onLive((m) => {
    if (m.tipo !== 'case' || pending.current) return
    pending.current = true
    setTimeout(() => { pending.current = false; load() }, 3000)
  }), [onLive, load])

  if (!data) return null
  const cfg = data.config
  const engines = data.motores.filter((m) => m === 'qwen' || m === 'jev')
  const conc = data.concordancia_motores
  const comp = data.comparativo
  const clear = async () => {
    if (!confirm('Apagar todo o histórico de desempenho dos agentes?')) return
    const r = await api.del('/metrics/agentes')
    toast(`${r.removidos} registros apagados`)
    load()
  }

  return (
    <div>
      <div className="page-head">
        <div><h2>Desempenho dos agentes</h2><p>Tempo de resposta e de processamento de cada chamada aos agentes de elegibilidade, auditoria e conferência, por motor. O histórico sobrevive à limpeza do laboratório.</p></div>
        <div className="row right">
          <select value={periodo} onChange={(e) => setPeriodo(Number(e.target.value))}>{PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <select value={balde} onChange={(e) => setBalde(Number(e.target.value))}>{BUCKETS.map(([v, l]) => <option key={v} value={v}>Intervalo: {l}</option>)}</select>
          <button className="btn danger" onClick={clear}>Limpar histórico</button>
        </div>
      </div>

      <div className={`callout mb ${cfg.comparacao ? 'ok' : ''}`}>
        Motor ativo: <b>{cfg.motor === 'jev' ? `JEV (${cfg.modelo_jev})` : `Qwen (${cfg.provedor_qwen}, ${cfg.modelo_qwen})`}</b>.
        Classificação de elegibilidade pelo agente {cfg.elegibilidade ? 'ligada' : 'desligada'}.
        {' '}{cfg.comparacao
          ? 'Comparação ligada: o outro motor responde as mesmas tarefas logo depois, sem decidir, e a concordância entre os dois aparece abaixo.'
          : 'Comparação desligada: cada motor só é medido quando está ativo. Ligue a comparação para medir os dois nos mesmos casos.'}
        {' '}<a onClick={() => go('config')}>Mudar nas configurações</a>
      </div>

      {comp ? (
        <div className="stats">
          <div className="panel stat"><div className="v" style={{ color: ENGINE_COLOR[comp.mais_rapido] }}>{comp.nome}</div><div className="l">mais rápido no período</div></div>
          <div className="panel stat"><div className="v">{String(comp.vezes).replace('.', ',')}x</div><div className="l">mais rápido no processamento médio</div></div>
          <div className="panel stat"><div className="v">{dur(comp.diferenca_media_ms)}</div><div className="l">a menos por chamada, em média</div></div>
          <div className="panel stat"><div className="v">{pct(conc.taxa)}</div><div className="l">concordância Qwen x JEV ({conc.pares} pares)</div></div>
          <div className="panel stat"><div className="v">{data.total}</div><div className="l">chamadas no período</div></div>
        </div>
      ) : null}

      <div className="grid2 mb">
        {engines.map((m) => <EngineCard key={m} row={data.por_motor[m]} active={cfg.motor === m} />)}
      </div>

      <div className="panel panel-pad mb">
        <div className="row mb">
          <h3>Histórico</h3>
          <select className="right" value={field} onChange={(e) => setField(e.target.value)}>
            <option value="processamento_media_ms">Processamento médio (tarefa inteira)</option>
            <option value="resposta_media_ms">Resposta média do modelo</option>
            <option value="processamento_p95_ms">Processamento p95</option>
          </select>
        </div>
        <History data={data} field={field} engines={engines} />
        <p className="small muted">Resposta do modelo: da requisição até a resposta. Processamento: a tarefa inteira do agente, com montagem do contexto, espera por vaga, nova tentativa e leitura da resposta. Respostas do cache, do agente simulado e chamadas com erro não entram nas médias.</p>
      </div>

      <div className="grid2 mb">
        <div className="panel panel-pad">
          <h3 className="mb">Tempo por tarefa</h3>
          <table className="tbl">
            <thead><tr><th>Tarefa</th>{engines.map((m) => <th key={m}><span className="dot" style={{ background: ENGINE_COLOR[m] }} /> {data.nomes[m]}</th>)}</tr></thead>
            <tbody>{Object.entries(data.tarefas).map(([t, label]) => (
              <tr key={t}><td>{label}<div className="small muted">{engines.map((m) => `${data.nomes[m].split(' ')[0]} n=${data.por_motor[m].por_tarefa[t].medidas}`).join(' · ')}</div></td>
                {engines.map((m) => <Cell key={m} s={data.por_motor[m].por_tarefa[t].processamento_ms} />)}</tr>
            ))}</tbody>
          </table>
        </div>
        <div className="panel panel-pad">
          <h3 className="mb">Qwen x JEV nos mesmos casos</h3>
          {!conc.pares ? <Empty>Nenhum caso avaliado pelos dois motores. Ligue a comparação nas configurações.</Empty> : (
            <>
              <table className="tbl">
                <thead><tr><th>Tarefa</th><th>Pares</th><th>Concordam</th><th>Qwen mais rigoroso</th><th>JEV mais rigoroso</th></tr></thead>
                <tbody>{Object.entries(conc.por_tarefa).map(([t, r]) => (
                  <tr key={t}><td>{data.tarefas[t]}</td><td>{r.pares}</td><td>{r.pares ? <b>{pct(r.taxa)}</b> : '-'}</td><td>{r.qwen_mais_rigoroso}</td><td>{r.jev_mais_rigoroso}</td></tr>
                ))}</tbody>
              </table>
              {conc.divergencias.length ? <>
                <h4 className="mt mb-s">Divergências recentes</h4>
                <div style={{ maxHeight: 360, overflowY: 'auto' }}><table className="tbl">
                  <thead><tr><th>Caso</th><th>Tarefa</th><th>Qwen</th><th>JEV</th><th>Regras</th></tr></thead>
                  <tbody>{conc.divergencias.map((d) => (
                    <tr key={`${d.case_id}-${d.tarefa}`}><td><a onClick={() => openCase(d.case_id)}>{d.case_id}</a><div className="small muted mono">{d.evento_tipo}</div></td>
                      <td className="small">{data.tarefas[d.tarefa]}</td><td>{d.qwen}</td><td>{d.jev}</td><td className="muted">{d.regras || '-'}</td></tr>
                  ))}</tbody>
                </table></div>
              </> : null}
            </>
          )}
        </div>
      </div>

      <div className="panel panel-pad mb">
        <h3 className="mb">Últimas chamadas</h3>
        {!data.recentes.length ? <Empty>Nenhuma chamada no período.</Empty> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="tbl">
              <thead><tr><th>Hora</th><th>Motor</th><th>Tarefa</th><th>Caso</th><th>Modelo</th><th>Resposta</th><th>Processamento</th><th>Veredito</th><th>Regras</th></tr></thead>
              <tbody>{data.recentes.map((r, i) => (
                <tr key={i}>
                  <td className="small">{time(r.ts)}</td>
                  <td><span className="dot" style={{ background: ENGINE_COLOR[r.motor] }} /> {data.nomes[r.motor] || r.motor}{r.papel === 'comparacao' ? <div className="small muted">comparação</div> : null}</td>
                  <td className="small">{data.tarefas[r.tarefa]}</td>
                  <td>{r.case_id ? <a onClick={() => openCase(r.case_id)}>{r.case_id}</a> : '-'}</td>
                  <td className="small mono">{r.modelo}</td>
                  <td>{r.cache ? <span className="muted">cache</span> : dur(r.resposta_ms)}</td>
                  <td>{dur(r.processamento_ms)}</td>
                  <td>{r.ok ? r.veredito : <Badge tone="bad" >erro</Badge>}{!r.ok && r.erro ? <div className="small muted">{r.erro}</div> : null}</td>
                  <td className="small muted">{r.veredito_regras || '-'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
