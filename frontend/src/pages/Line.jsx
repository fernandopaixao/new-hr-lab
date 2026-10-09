import React, { useMemo, useState } from 'react'
import { api } from '../api.js'
import { Badge, Status, dur, time, useApp } from '../ui.jsx'

const FINAL_OK = ['CONCLUIDO', 'CONCLUIDO_COM_RESSALVAS']

function CaseCard({ c, onOpen }) {
  const { meta } = useApp()
  const tipo = meta.tipos_evento.find((t) => t.evento === c.evento_tipo)
  return (
    <div className={`card s-${c.status}`} onClick={() => onOpen(c.id)} title={c.resumo}>
      <div className="row gap-s">
        <span className="t ellipsis" style={{ maxWidth: 150 }}>{tipo?.nome || c.evento_tipo || 'evento'}</span>
        {c.depuracao ? <Badge tone="violet">passo a passo</Badge> : null}
      </div>
      <div className="n ellipsis">{c.colaborador_nome || c.colaborador_id || 'sem colaborador'}</div>
      <div className="row gap-s" style={{ marginTop: 3 }}>
        <Status value={c.status} />
        <span className="small muted right">{time(c.atualizado_em)}</span>
      </div>
      {c.proximo_passo && !c.proximo_passo.encerrado
        ? <div className={`r next ${c.proximo_passo.quem ? 'human' : ''}`}><b>{c.proximo_passo.quem ? `Com ${c.proximo_passo.quem.split('/').map((p) => meta.personas[p]?.nome || p).join(' ou ')}: ` : 'A seguir: '}</b>{c.proximo_passo.texto}</div>
        : <div className="r">{c.resumo}</div>}
    </div>
  )
}

export default function Line() {
  const { meta, cases, stats, openCase, reloadStats, toast } = useApp()
  const [filter, setFilter] = useState('')
  const [tipo, setTipo] = useState('')
  const [hideChildren, setHideChildren] = useState(true)
  const ctl = stats?.controle || { paused_stages: [], breakpoints: [] }

  const list = useMemo(() => {
    let l = Object.values(cases)
    if (hideChildren) l = l.filter((c) => !c.pai_id || !['CONCLUIDO'].includes(c.status))
    if (tipo) l = l.filter((c) => c.evento_tipo === tipo)
    if (filter) {
      const f = filter.toLowerCase()
      l = l.filter((c) => `${c.colaborador_nome} ${c.colaborador_id} ${c.id} ${c.cenario} ${c.resumo}`.toLowerCase().includes(f))
    }
    return l.sort((a, b) => (b.atualizado_em || 0) - (a.atualizado_em || 0))
  }, [cases, filter, tipo, hideChildren])

  const byStage = useMemo(() => {
    const m = {}
    meta.estagios.forEach((s) => { m[s.id] = [] })
    m.done = []
    list.forEach((c) => {
      if (meta.finais.includes(c.status)) m.done.push(c)
      else (m[c.estagio] || m.intake).push(c)
    })
    return m
  }, [list, meta])

  const toggle = async (key, stage) => {
    const cur = new Set(ctl[key] || [])
    cur.has(stage) ? cur.delete(stage) : cur.add(stage)
    await api.post('/control', { [key]: [...cur] })
    reloadStats()
    toast(key === 'paused_stages' ? `Estágio ${cur.has(stage) ? 'pausado' : 'liberado'}` : `Ponto de parada ${cur.has(stage) ? 'ligado' : 'desligado'}`)
  }

  const s = stats?.por_status || {}
  const sum = (keys) => keys.reduce((a, k) => a + (s[k] || 0), 0)
  const moving = (stats?.filas && Object.values(stats.filas).some((q) => q.pendentes > 0)) && !ctl.paused

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Linha de produção de eventos</h2>
          <p>Cada evento percorre gatilho, elegibilidade, planejamento, auditoria, execução e conferência final. Nada é executado sem passar pela auditoria. Cada cartão diz o próximo passo; clique para depurar.</p>
        </div>
      </div>
      <div className="stats">
        <div className="panel stat"><div className="v">{stats?.total_casos ?? 0}</div><div className="l">casos no total</div></div>
        <div className="panel stat"><div className="v">{sum(['NA_FILA', 'PROCESSANDO', 'PARADO'])}</div><div className="l">em andamento</div></div>
        <div className="panel stat"><div className="v" style={{ color: 'var(--warn)' }}>{s.AGUARDANDO_APROVACAO || 0}</div><div className="l">aguardando aprovação</div></div>
        <div className="panel stat"><div className="v" style={{ color: 'var(--warn)' }}>{s.AGUARDANDO_AGENTE || 0}</div><div className="l">aguardando IA</div></div>
        <div className="panel stat"><div className="v" style={{ color: 'var(--ok)' }}>{sum(FINAL_OK)}</div><div className="l">concluídos</div></div>
        <div className="panel stat"><div className="v" style={{ color: 'var(--bad)' }}>{sum(['NAO_ELEGIVEL', 'REJEITADO', 'REJEITADO_NA_ENTRADA', 'FALHOU_COMPENSADO', 'ERRO', 'REVERTIDO'])}</div><div className="l">barrados ou com falha</div></div>
        <div className="panel stat"><div className="v">{stats?.finalizados_ultimo_minuto ?? 0}</div><div className="l">finalizados no último minuto</div></div>
        <div className="panel stat"><div className="v">{dur(stats?.agente?.duracao_media_ms)}</div><div className="l">tempo médio do agente ({stats?.agente?.chamadas || 0} chamadas)</div></div>
      </div>
      <div className="line-controls">
        <input placeholder="Buscar colaborador, caso, cenário..." value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: 280 }} />
        <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
          <option value="">Todos os tipos de evento</option>
          {meta.tipos_evento.map((t) => <option key={t.evento} value={t.evento}>{t.nome}</option>)}
        </select>
        <label className="check"><input type="checkbox" checked={hideChildren} onChange={(e) => setHideChildren(e.target.checked)} /> ocultar filhos concluídos de eventos coletivos</label>
        {ctl.paused ? <Badge tone="warn">Linha pausada</Badge> : null}
      </div>
      <div className={`conveyor mb ${moving ? 'moving' : ''}`} />
      <div className="line">
        {meta.estagios.map((st, i) => {
          const q = stats?.filas?.[st.id] || {}
          const items = byStage[st.id] || []
          const paused = (ctl.paused_stages || []).includes(st.id) || ctl.paused
          const bp = (ctl.breakpoints || []).includes(st.id)
          return (
            <div key={st.id} className={`station ${paused ? 'paused' : ''}`}>
              <div className="station-head">
                <div className="num">ESTAÇÃO {i + 1}</div>
                <div className="title">{st.nome}</div>
                <div className="desc">{st.descricao}</div>
                <div className="desc next">{st.saida}</div>
                <div className="station-stats">
                  <Badge>{items.length} casos</Badge>
                  <Badge tone={q.atraso ? 'warn' : ''}>fila {q.atraso || 0}</Badge>
                  <Badge tone={q.pendentes ? 'info' : ''}>em uso {q.pendentes || 0}</Badge>
                  {stats?.duracao_media_ms?.[st.id] != null ? <Badge>{dur(stats.duracao_media_ms[st.id])}</Badge> : null}
                </div>
                <div className="station-tools">
                  <button className={`btn sm ${paused ? 'on' : ''}`} onClick={() => toggle('paused_stages', st.id)} title="Para de consumir a fila deste estágio">{(ctl.paused_stages || []).includes(st.id) ? 'Retomar' : 'Pausar'}</button>
                  <button className={`btn sm ${bp ? 'on' : ''}`} onClick={() => toggle('breakpoints', st.id)} title="Todo caso para antes deste estágio até ser liberado">{bp ? 'Parada ligada' : 'Parar antes'}</button>
                </div>
              </div>
              <div className="station-body">
                {items.slice(0, 40).map((c) => <CaseCard key={c.id} c={c} onOpen={openCase} />)}
                {items.length > 40 ? <div className="small muted">+{items.length - 40} casos</div> : null}
                {!items.length ? <div className="small muted" style={{ padding: 8 }}>vazio</div> : null}
              </div>
            </div>
          )
        })}
        <div className="station">
          <div className="station-head">
            <div className="num">SAÍDA</div>
            <div className="title">Finalizados</div>
            <div className="desc">Concluídos, barrados, rejeitados, compensados ou revertidos.</div>
            <div className="station-stats"><Badge>{byStage.done.length} casos</Badge></div>
          </div>
          <div className="station-body">
            {byStage.done.slice(0, 60).map((c) => <CaseCard key={c.id} c={c} onOpen={openCase} />)}
          </div>
        </div>
      </div>
    </div>
  )
}
