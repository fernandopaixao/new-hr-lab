import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Badge, Empty, Status, dur, time, useApp } from '../ui.jsx'

function Bar({ value, max, tone = 'accent', label }) {
  const pct = max ? Math.max(2, Math.round((value / max) * 100)) : 0
  return (
    <div className="hbar" title={label}>
      <div className={`hbar-fill ${tone}`} style={{ width: `${value ? pct : 0}%` }} />
    </div>
  )
}

function Timeline({ data }) {
  const pts = data?.pontos || []
  if (!pts.length) return <Empty>Sem dados.</Empty>
  const max = Math.max(1, ...pts.map((p) => Math.max(p.entradas, p.finalizados)))
  const W = 720, H = 140, bw = W / pts.length
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H + 18}`} width="100%" role="img" aria-label="Entradas e finalizações ao longo do tempo">
        {pts.map((p, i) => {
          const he = (p.entradas / max) * H, hf = (p.finalizados / max) * H, hp = (p.problemas / max) * H
          return (
            <g key={i}>
              <title>{`${time(p.inicio)}: ${p.entradas} entradas, ${p.finalizados} finalizados, ${p.problemas} com problema`}</title>
              <rect x={i * bw + 2} y={H - he} width={bw / 2 - 3} height={he} fill="var(--accent)" opacity="0.75" rx="2" />
              <rect x={i * bw + bw / 2} y={H - hf} width={bw / 2 - 3} height={hf} fill="var(--ok)" opacity="0.75" rx="2" />
              {hp ? <rect x={i * bw + bw / 2} y={H - hp} width={bw / 2 - 3} height={hp} fill="var(--bad)" rx="2" /> : null}
              {i % 4 === 0 ? <text x={i * bw + 2} y={H + 14} fontSize="10" fill="var(--muted)">{time(p.inicio)}</text> : null}
            </g>
          )
        })}
      </svg>
      <div className="row small muted">
        <span><span className="dot" style={{ background: 'var(--accent)' }} /> entradas</span>
        <span><span className="dot" style={{ background: 'var(--ok)' }} /> finalizados</span>
        <span><span className="dot" style={{ background: 'var(--bad)' }} /> finalizados com problema</span>
        <span className="right">baldes de {data.balde_min} min</span>
      </div>
    </div>
  )
}

function Kpi({ v, l, tone }) {
  return <div className="panel stat"><div className="v" style={tone ? { color: `var(--${tone})` } : null}>{v ?? '-'}</div><div className="l">{l}</div></div>
}

export default function Insights() {
  const { meta, onLive, openCase, go } = useApp()
  const [data, setData] = useState(null)
  const [periodo, setPeriodo] = useState(0)
  const [balde, setBalde] = useState(5)
  const pending = useRef(false)

  const load = useCallback(async () => {
    try { setData(await api.get(`/insights?periodo_horas=${periodo}&balde_min=${balde}&baldes=24`)) } catch { /* ignore */ }
  }, [periodo, balde])
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t) }, [load])
  useEffect(() => onLive((m) => {
    if (m.tipo !== 'case' || pending.current) return
    pending.current = true
    setTimeout(() => { pending.current = false; load() }, 2000)
  }), [onLive, load])

  if (!data) return null
  const k = data.kpis
  const maxFunnel = Math.max(1, ...data.funil.map((f) => f.alcancaram))
  const maxP95 = Math.max(1, ...data.tempos_por_estagio.map((t) => t.p95_ms || 0))
  const maxStatus = Math.max(1, ...data.por_status.map((s) => s.quantidade))
  const statuses = [...new Set(Object.values(data.matriz_evento_status).flatMap((r) => Object.keys(r)))]
  const eventName = (e) => (meta.tipos_evento || []).find((x) => x.evento === e)?.nome || e
  const agr = data.agente.concordancia
  const agrTotal = agr.concordam + agr.agente_mais_rigoroso + agr.regras_mais_rigorosas
  const idx = data.indice || {}

  return (
    <div>
      <div className="page-head">
        <div><h2>Visão da operação</h2><p>Funil, tempos, gargalos, regras que mais barram, operações, aprovações e concordância entre agente e regras. Atualiza sozinho com a linha.</p></div>
        <div className="row right">
          <select value={periodo} onChange={(e) => setPeriodo(Number(e.target.value))}>
            <option value={0}>Todo o período</option><option value={1}>Última hora</option><option value={24}>Últimas 24 horas</option>
          </select>
          <select value={balde} onChange={(e) => setBalde(Number(e.target.value))}>
            <option value={1}>Linha do tempo: 1 min</option><option value={5}>Linha do tempo: 5 min</option><option value={60}>Linha do tempo: 1 hora</option>
          </select>
          <a className="btn" href="/api/metrics" target="_blank" rel="noreferrer">Métricas Prometheus</a>
        </div>
      </div>

      <div className="stats">
        <Kpi v={k.casos} l="casos" />
        <Kpi v={k.em_andamento} l="em andamento" />
        <Kpi v={k.taxa_conclusao != null ? `${Math.round(k.taxa_conclusao * 100)}%` : '-'} l="dos finalizados concluídos" tone="ok" />
        <Kpi v={dur(k.lead_time_p50_ms)} l="tempo total p50" />
        <Kpi v={dur(k.lead_time_p95_ms)} l="tempo total p95" />
        <Kpi v={k.aprovacoes_pendentes} l="aprovações pendentes" tone={k.aprovacoes_pendentes ? 'warn' : null} />
        <Kpi v={k.compensacoes} l="sagas compensadas" tone={k.compensacoes ? 'violet' : null} />
        <Kpi v={k.replanejamentos} l="replanejamentos por concorrência" />
        <Kpi v={dur(k.agente_p95_ms)} l="agente de IA p95" />
      </div>

      {data.alertas.length ? (
        <div className="col mb">
          {data.alertas.map((a, i) => <div key={i} className={`callout ${a.nivel === 'ALTO' ? 'bad' : a.nivel === 'MEDIO' ? 'warn' : ''}`}><b>{a.nivel === 'ALTO' ? 'Atenção' : a.nivel === 'MEDIO' ? 'Observe' : 'Informação'}:</b> {a.texto}</div>)}
        </div>
      ) : <div className="callout ok mb">Nenhum alerta no momento.</div>}

      <div className="grid2 mb">
        <div className="panel panel-pad">
          <h3 className="mb">Entradas e finalizações</h3>
          <Timeline data={data.linha_do_tempo} />
        </div>
        <div className="panel panel-pad">
          <h3 className="mb">Funil da linha de produção</h3>
          <table className="tbl">
            <thead><tr><th>Estágio</th><th style={{ width: '45%' }}>Alcançaram</th><th>Concluíram</th><th>Agora</th></tr></thead>
            <tbody>{data.funil.map((f) => (
              <tr key={f.estagio}><td>{f.nome}</td><td><Bar value={f.alcancaram} max={maxFunnel} /><span className="small muted">{f.alcancaram}</span></td>
                <td>{f.concluiram}</td><td>{f.em_andamento ? <Badge tone="warn">{f.em_andamento}</Badge> : <span className="muted">0</span>}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </div>

      <div className="grid2 mb">
        <div className="panel panel-pad">
          <h3 className="mb">Tempo por estágio</h3>
          <table className="tbl">
            <thead><tr><th>Estágio</th><th>p50</th><th style={{ width: '40%' }}>p95</th><th>máx</th><th>n</th></tr></thead>
            <tbody>{data.tempos_por_estagio.map((t) => (
              <tr key={t.estagio}><td>{t.nome}</td><td>{dur(t.p50_ms)}</td>
                <td><Bar value={t.p95_ms || 0} max={maxP95} tone={t.p95_ms === maxP95 ? 'warn' : 'accent'} /><span className="small muted">{dur(t.p95_ms)}</span></td>
                <td className="small muted">{dur(t.max_ms)}</td><td className="small muted">{t.n}</td></tr>
            ))}</tbody>
          </table>
          <p className="small muted">O estágio com p95 destacado é o gargalo. A auditoria e a conferência final incluem o tempo do agente de IA; o atraso visual configurado também conta.</p>
        </div>
        <div className="panel panel-pad">
          <h3 className="mb">Situação dos casos</h3>
          {data.por_status.map((s) => (
            <div key={s.valor} className="row mb-s"><span style={{ width: 200 }}><Status value={s.valor} /></span>
              <span style={{ flex: 1 }}><Bar value={s.quantidade} max={maxStatus} tone={['CONCLUIDO', 'CONCLUIDO_COM_RESSALVAS'].includes(s.valor) ? 'ok' : 'accent'} /></span>
              <b style={{ width: 40, textAlign: 'right' }}>{s.quantidade}</b></div>
          ))}
        </div>
      </div>

      <div className="panel panel-pad mb">
        <h3 className="mb">Eventos por situação</h3>
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl heat">
            <thead><tr><th>Evento</th>{statuses.map((s) => <th key={s}><Status value={s} /></th>)}</tr></thead>
            <tbody>{Object.entries(data.matriz_evento_status).sort().map(([ev, row]) => (
              <tr key={ev}><td><b>{eventName(ev)}</b><div className="small muted mono">{ev}</div></td>
                {statuses.map((s) => <td key={s} className={row[s] ? (['CONCLUIDO', 'CONCLUIDO_COM_RESSALVAS'].includes(s) ? 'h-ok' : 'h-warn') : ''}>{row[s] || ''}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      </div>

      <div className="grid2 mb">
        <div className="panel panel-pad">
          <h3 className="mb">Regras que mais barram ou alertam</h3>
          {!data.regras_mais_falhas.length ? <Empty>Nenhuma regra falhou.</Empty> : (
            <table className="tbl">
              <thead><tr><th>Regra</th><th>Tipo</th><th>Vezes</th><th>Exemplos</th></tr></thead>
              <tbody>{data.regras_mais_falhas.map((r) => (
                <tr key={r.id}><td><b className="mono">{r.id}</b><div className="small">{r.descricao}</div><div className="small muted">{r.secao}</div></td>
                  <td><Badge tone={r.tipo === 'BLOQUEANTE' ? 'bad' : r.tipo === 'EXCECIONAVEL' ? 'warn' : 'info'}>{r.tipo}</Badge></td>
                  <td><b>{r.quantidade}</b></td>
                  <td className="small">{r.exemplos.map((c) => <div key={c}><a onClick={() => openCase(c)}>{c}</a></div>)}</td></tr>
              ))}</tbody>
            </table>
          )}
        </div>
        <div className="panel panel-pad">
          <h3 className="mb">Operações da prateleira</h3>
          {!data.operacoes.length ? <Empty>Nenhuma operação executada.</Empty> : (
            <table className="tbl">
              <thead><tr><th>Operação</th><th>Executadas</th><th>Falhas</th><th>Descartadas no plano</th></tr></thead>
              <tbody>{data.operacoes.map((o) => (
                <tr key={o.operacao}><td className="mono small">{o.operacao}</td><td>{o.executadas}</td>
                  <td>{o.falhas ? <Badge tone="bad">{o.falhas}</Badge> : 0}</td><td className="muted">{o.descartadas}</td></tr>
              ))}</tbody>
            </table>
          )}
        </div>
      </div>

      <div className="grid2 mb">
        <div className="panel panel-pad">
          <h3 className="mb">Aprovações</h3>
          <h4 className="mb-s">Pendentes por persona</h4>
          <div className="row mb">
            {Object.keys(data.aprovacoes.pendentes_por_persona).length ? Object.entries(data.aprovacoes.pendentes_por_persona).map(([p, n]) => (
              <span key={p} className="chip">{meta.personas[p]?.nome || p}: <b>{n}</b></span>)) : <span className="muted small">Nenhuma.</span>}
            {Object.keys(data.aprovacoes.pendentes_por_persona).length ? <button className="btn sm right" onClick={() => go('aprovacoes')}>Abrir aprovações</button> : null}
          </div>
          <h4 className="mb-s">Decisões registradas</h4>
          {!data.aprovacoes.decisoes_por_persona.length ? <span className="muted small">Nenhuma decisão ainda.</span> : (
            <table className="tbl">
              <thead><tr><th>Persona</th><th>Aprovadas</th><th>Rejeitadas</th><th>Tempo mediano para decidir</th></tr></thead>
              <tbody>{data.aprovacoes.decisoes_por_persona.map((p) => (
                <tr key={p.persona}><td>{p.nome || p.persona}</td><td>{p.aprovadas}</td><td>{p.rejeitadas}</td><td>{dur(p.tempo_mediano_ms)}</td></tr>
              ))}</tbody>
            </table>
          )}
        </div>
        <div className="panel panel-pad col">
          <h3>Agente de IA e regras</h3>
          <p className="small muted">Cada auditoria (antes da execução) e cada conferência final comparam a decisão das regras com a recomendação do agente.</p>
          {agrTotal ? (
            <div className="col">
              <div className="row"><span style={{ width: 230 }}>Concordam</span><span style={{ flex: 1 }}><Bar value={agr.concordam} max={agrTotal} tone="ok" /></span><b>{agr.concordam}</b></div>
              <div className="row"><span style={{ width: 230 }}>Agente mais rigoroso</span><span style={{ flex: 1 }}><Bar value={agr.agente_mais_rigoroso} max={agrTotal} tone="warn" /></span><b>{agr.agente_mais_rigoroso}</b></div>
              <div className="row"><span style={{ width: 230 }}>Regras mais rigorosas</span><span style={{ flex: 1 }}><Bar value={agr.regras_mais_rigorosas} max={agrTotal} tone="bad" /></span><b>{agr.regras_mais_rigorosas}</b></div>
              {agr.simulado ? <div className="small muted">{agr.simulado} caso(s) usaram o agente simulado.</div> : null}
            </div>
          ) : <Empty>Nenhuma auditoria ainda.</Empty>}
          <h3 className="mt">Embeddings dos eventos</h3>
          <div className="row small">
            <Badge tone={idx.estado === 'EM_DIA' ? 'ok' : idx.estado === 'AGUARDANDO_OLLAMA' || idx.estado === 'ERRO' ? 'bad' : 'info'}>{idx.estado || 'sem indexador'}</Badge>
            <span>{idx.documentos || 0} documentos indexados, {idx.pendentes || 0} na fila{idx.simulados ? `, ${idx.simulados} com embedding simulado` : ''}.</span>
            <button className="btn sm right" onClick={() => go('perguntar')}>Perguntar aos eventos</button>
          </div>
          <div className="small muted">{idx.mensagem}</div>
          <div className="small muted">Colaboradores fora do estado alvo ou do compliance: {data.conformidade_colaboradores.fora} de {data.conformidade_colaboradores.total}.</div>
        </div>
      </div>
    </div>
  )
}
