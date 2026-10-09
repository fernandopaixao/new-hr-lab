import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, Empty, Status, useApp } from '../ui.jsx'

const fmtDate = (iso) => (iso ? String(iso).slice(0, 10).split('-').reverse().join('/') : '-')
const SITUACAO = { AGENDADO: ['', 'Agendado'], VENCIDO: ['warn', 'Na data, aguardando a agenda'], EMITIDO: ['ok', 'Emitido para a linha'] }
const STEPS = [[1, '+1 dia'], [7, '+7 dias'], [30, '+30 dias'], [90, '+90 dias'], [365, '+1 ano']]

function when(dias) {
  if (dias === 0) return 'hoje'
  if (dias < 0) return `há ${-dias} dia${dias === -1 ? '' : 's'}`
  return `em ${dias} dia${dias === 1 ? '' : 's'}`
}

export default function Validity() {
  const { meta, toast, openCase, onLive, cases, relogio, reloadStats } = useApp()
  const eventName = (tipo) => meta.tipos_evento.find((t) => t.evento === tipo)?.nome || tipo
  const [agenda, setAgenda] = useState(null)
  const [data, setData] = useState('')
  const [busy, setBusy] = useState(false)
  const [last, setLast] = useState(null)

  const load = useCallback(async () => setAgenda(await api.get('/vigencias')), [])
  useEffect(() => { load() }, [load])
  useEffect(() => onLive((m) => { if (m.tipo === 'clock' || (m.tipo === 'log' && m.entry.tipo === 'DECISAO_FINAL')) load() }), [onLive, load])

  const after = async (r, msg) => {
    setLast(r.emitidos || [])
    toast(`${msg}${r.emitidos?.length ? `; ${r.emitidos.length} evento(s) emitidos pela agenda` : '; nenhum evento vencido'}`)
    await Promise.all([load(), reloadStats()])
  }
  const run = async (fn) => {
    setBusy(true)
    try { await fn() } catch (e) { toast(e.message, 'bad') } finally { setBusy(false) }
  }
  const advance = (dias) => run(async () => after(await api.post('/clock/advance', { dias }), `Relógio avançado ${dias} dia(s)`))
  const setDate = (value) => run(async () => after(await api.put('/clock', { data: value }), value ? `Relógio em ${fmtDate(value)}` : 'Relógio de volta ao calendário real'))
  const tick = () => run(async () => after(await api.post('/vigencias/tick', {}), 'Agenda verificada'))

  const itens = agenda?.itens || []
  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Vigências</h2>
          <p>Eventos com prazo: um programa vale por um período a partir da data oficial. A agenda emite o aviso alguns dias antes do fim e o vencimento na data final; os dois entram na linha normal (elegibilidade, planejamento, auditoria, execução e conferência final), que desfaz o que o programa concedia. O relógio simulado permite avançar o tempo para testar e demonstrar.</p>
        </div>
      </div>
      <div className="grid2 mb">
        <section className="panel panel-pad col">
          <h4 className="section-title">Relógio simulado</h4>
          <div className="row">
            <div className="big">{fmtDate(relogio?.hoje)}</div>
            {relogio?.simulado ? <Badge tone="violet">data simulada</Badge> : <Badge tone="ok">calendário real</Badge>}
          </div>
          <div className="small muted">
            {relogio?.simulado ? `O calendário real está em ${fmtDate(relogio.data_real)}. ` : ''}
            Eventos sem data efetiva, cenários e a conformidade passam a usar esta data.
          </div>
          <div className="row gap-s wrap">
            {STEPS.map(([d, label]) => <button key={d} className="btn sm" disabled={busy} onClick={() => advance(d)}>{label}</button>)}
          </div>
          <div className="row gap-s">
            <input type="date" value={data} onChange={(e) => setData(e.target.value)} style={{ width: 170 }} />
            <button className="btn sm" disabled={busy || !data} onClick={() => setDate(data)}>Ir para a data</button>
            {relogio?.simulado ? <button className="btn sm ghost right" disabled={busy} onClick={() => setDate(null)}>Voltar ao calendário real</button> : null}
          </div>
        </section>
        <section className="panel panel-pad col">
          <h4 className="section-title">Como a agenda funciona</h4>
          <div className="small">A agenda é derivada dos programas ativos de cada colaborador: renovar muda a data final e reagenda o aviso e o vencimento; encerrar antes do fim cancela os dois. Os trabalhadores conferem a agenda a cada poucos segundos, e mudar o relógio confere na hora.</div>
          <div className="small muted">Cada evento tem identificador fixo (colaborador, programa, data final e tipo) e é reservado antes do envio, então nunca é emitido duas vezes.</div>
          <div className="row"><button className="btn sm right" disabled={busy} onClick={tick}>Conferir a agenda agora</button></div>
        </section>
      </div>
      {last && last.length ? (
        <div className="callout mb">
          <b>Emitidos agora:</b> {last.map((c) => <a key={c.id} className="mr" onClick={() => openCase(c.id)}>{c.colaborador_nome || c.colaborador_id} ({eventName(c.evento_tipo).toLowerCase()})</a>)}
        </div>
      ) : null}
      <section className="panel">
        <div className="panel-pad row" style={{ borderBottom: '1px solid var(--border)' }}>
          <h4>Agenda de vigências</h4>
          <span className="small muted right">{itens.length} evento(s) agendados ou emitidos de programas ativos</span>
        </div>
        {!agenda ? <Empty>Carregando...</Empty> : !itens.length ? <Empty>Nenhum programa ativo. Inclua alguém no programa de alto potencial pelo cenário da suíte ou por um evento manual.</Empty> : (
          <table className="tbl">
            <thead><tr><th>Data</th><th>Quando</th><th>Colaborador</th><th>Programa</th><th>Evento</th><th>Situação</th><th>Caso</th></tr></thead>
            <tbody>
              {itens.map((i) => {
                const [tone, label] = SITUACAO[i.situacao] || ['', i.situacao]
                const caso = i.emitido && cases[i.emitido]
                return (
                  <tr key={i.evento_id}>
                    <td>{fmtDate(i.data)}</td>
                    <td className="small muted">{when(i.vence_em_dias)}</td>
                    <td>{i.colaborador_nome} <span className="small muted mono">{i.colaborador_id}</span></td>
                    <td>{i.programa_nome || i.programa} <span className="small muted">até {fmtDate(i.fim)}</span></td>
                    <td>{i.tipo === 'aviso' ? 'Aviso de vencimento' : 'Vencimento'}</td>
                    <td><Badge tone={tone}>{label}</Badge></td>
                    <td>{caso ? <a onClick={() => openCase(caso.id)}><Status value={caso.status} /></a>
                      : (i.emitido && !String(i.emitido).startsWith('caso') ? <span className="small muted">{String(i.emitido).replace('cenario:', 'cenário ')}</span> : null)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
