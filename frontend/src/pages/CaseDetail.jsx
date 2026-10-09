import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { AgentCard, Badge, DiffTable, Empty, Json, RulesTable, Status, Tabs, dateTime, dur, money, time, useApp } from '../ui.jsx'

export function ApprovalBox({ ap, onDone }) {
  const { persona, meta, toast } = useApp()
  const [just, setJust] = useState('')
  const can = ap.status === 'PENDENTE' && ap.aprovadores.includes(persona)
  const decide = async (decisao) => {
    try {
      await api.post(`/approvals/${ap.id}/decide`, { persona, decisao, justificativa: just })
      toast(`Decisão registrada: ${decisao === 'APROVAR' ? 'aprovada' : 'rejeitada'}`)
      onDone && onDone()
    } catch (e) { toast(e.message, 'bad') }
  }
  return (
    <div className="panel panel-pad mb">
      <div className="row">
        <b>{ap.tipo_rotulo}</b>
        {ap.regra ? <Badge tone="warn">{ap.regra.id}</Badge> : null}
        <Status value={ap.status} />
        <span className="small muted right">{dateTime(ap.criado_em)}</span>
      </div>
      <p>{ap.explicacao}</p>
      {ap.regra?.base_legal ? <div className="small muted">Base: {ap.regra.base_legal}</div> : null}
      <div className="small">Quem pode decidir: {ap.aprovadores.map((a) => meta.personas[a]?.nome || a).join(', ')}</div>
      {ap.recomendacao_agente ? (
        <div className={`callout mt ${ap.recomendacao_agente.recomendacao === 'APROVADO' ? 'ok' : 'bad'}`}>
          <b>Recomendação do agente: {ap.recomendacao_agente.recomendacao}</b> ({Math.round((ap.recomendacao_agente.confianca || 0) * 100)}%). {ap.recomendacao_agente.resumo}
          {ap.recomendacao_agente.achados?.length ? <ul className="small">{ap.recomendacao_agente.achados.map((a, i) => <li key={i}>[{a.severidade}] {a.descricao}</li>)}</ul> : null}
        </div>
      ) : null}
      {ap.status !== 'PENDENTE' ? (
        <div className="callout mt small">
          {ap.status === 'CANCELADA' ? 'Cancelada' : `Decidida por ${ap.decidido_por?.pessoa} (${ap.decidido_por?.persona})`} em {dateTime(ap.decidido_em)}: {ap.justificativa}
        </div>
      ) : can ? (
        <div className="col mt">
          <textarea rows={2} placeholder="Justificativa obrigatória (fica registrada no log)" value={just} onChange={(e) => setJust(e.target.value)} style={{ fontFamily: 'inherit' }} />
          <div className="row">
            <button className="btn ok" onClick={() => decide('APROVAR')} disabled={just.trim().length < 5}>Aprovar</button>
            <button className="btn danger" onClick={() => decide('REJEITAR')} disabled={just.trim().length < 5}>Rejeitar</button>
            <span className="small muted">decidindo como {meta.personas[persona]?.pessoa}</span>
          </div>
        </div>
      ) : <div className="small muted mt">Troque a persona para {ap.aprovadores.join(' ou ')} para decidir.</div>}
    </div>
  )
}

function StageTrack({ c, meta, onPick }) {
  return (
    <div className="track">
      {meta.estagios.map((s, i) => {
        const e = c.etapas?.[s.id] || {}
        return (
          <div key={s.id} className={`step ${e.status}`} onClick={() => onPick(s.id)}>
            <div className="h">{i + 1}. {s.nome}</div>
            <div className="small">{e.status === 'PENDENTE' ? 'pendente' : (e.status || '').toLowerCase().replace('_', ' ')}</div>
            <div className="small muted">{e.duracao_ms != null ? dur(e.duracao_ms) : ''}</div>
          </div>
        )
      })}
    </div>
  )
}

const STAGE_TAB = { intake: 'evento', eligibility: 'elegibilidade', planning: 'plano', plan_review: 'conferencia', execution: 'execucao', audit: 'auditoria' }

export default function CaseDetail({ id, onClose }) {
  const { meta, onLive, toast, openCase } = useApp()
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('resumo')
  const [editEvent, setEditEvent] = useState(null)
  const [retryStage, setRetryStage] = useState('intake')

  const load = useCallback(async () => {
    try { setData(await api.get(`/cases/${id}`)) } catch (e) { toast(e.message, 'bad') }
  }, [id, toast])

  useEffect(() => { load() }, [load])
  useEffect(() => onLive((msg) => {
    if ((msg.tipo === 'case' && msg.case.id === id) || (msg.tipo === 'approval' && msg.approval.case_id === id)) load()
  }), [id, load, onLive])

  if (!data) return null
  const c = data.caso
  const act = async (fn, msg) => {
    try { await fn(); toast(msg); load() } catch (e) { toast(e.message, 'bad') }
  }
  const plano = c.plano || {}
  const pending = data.aprovacoes.filter((a) => a.status === 'PENDENTE').length

  return (
    <>
      <div className="drawer-back" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-head">
          <div className="row">
            <div>
              <div className="small muted mono">{c.id} · evento {c.evento_id}</div>
              <h2>{meta.tipos_evento.find((t) => t.evento === c.evento_tipo)?.nome || c.evento_tipo} · {c.colaborador_nome || c.colaborador_id || '-'}</h2>
            </div>
            <div className="right row">
              <Status value={c.status} />
              <button className="btn" onClick={onClose}>Fechar</button>
            </div>
          </div>
          <p className="muted" style={{ margin: '6px 0 10px' }}>{c.resumo}</p>
          <StageTrack c={c} meta={meta} onPick={(s) => setTab(STAGE_TAB[s])} />
          <div className="row mt">
            {c.status === 'PARADO' ? <>
              <button className="btn primary" onClick={() => act(() => api.post(`/cases/${id}/release`, {}), 'Avançou um estágio')}>Avançar para {meta.estagios.find((s) => s.id === c.estagio_parado)?.nome}</button>
              <button className="btn" onClick={() => act(() => api.post(`/cases/${id}/release`, { continuar: true }), 'Execução contínua')}>Continuar sem pausas</button>
            </> : null}
            {!meta.finais.includes(c.status) ? (
              <button className={`btn ${c.depuracao ? 'on' : ''}`} onClick={() => act(() => api.post(`/cases/${id}/debug`, { depuracao: !c.depuracao }), c.depuracao ? 'Passo a passo desligado' : 'Passo a passo ligado: o caso para antes de cada estágio')}>
                {c.depuracao ? 'Passo a passo ligado' : 'Ligar passo a passo'}
              </button>
            ) : null}
            <select value={retryStage} onChange={(e) => setRetryStage(e.target.value)}>
              {meta.estagios.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
            </select>
            <button className="btn" onClick={() => act(() => api.post(`/cases/${id}/retry`, { estagio: retryStage, depuracao: true }), 'Reprocessando em modo passo a passo')}>Reprocessar a partir daqui</button>
            <button className="btn" onClick={() => { setEditEvent(JSON.stringify(c.evento, null, 2)); setTab('evento') }}>Editar evento e reprocessar</button>
            {!meta.finais.includes(c.status) ? <button className="btn danger" onClick={() => act(() => api.post(`/cases/${id}/cancel`), 'Caso cancelado')}>Cancelar</button> : null}
          </div>
        </div>
        <div className="drawer-body">
          <Tabs value={tab} onChange={setTab} tabs={[
            ['resumo', 'Resumo e decisões'], ['evento', 'Evento'], ['elegibilidade', 'Elegibilidade'], ['plano', `Plano (${plano.operacoes?.length || 0})`],
            ['conferencia', 'Conferência'], ['execucao', 'Execução'], ['auditoria', 'Auditoria'], ['aprovacoes', `Aprovações${pending ? ` (${pending})` : ''}`],
            ['estado', 'Estado antes e depois'], ['log', `Trilha (${data.log.length})`],
          ]} />

          {tab === 'resumo' && (
            <div className="col">
              {c.decisao_final ? <div className={`callout ${['CONCLUIDO', 'CONCLUIDO_COM_RESSALVAS'].includes(c.status) ? 'ok' : 'bad'}`}><b>Decisão final: {c.decisao_final.rotulo}.</b> {c.decisao_final.explicacao}</div> : null}
              <div className="grid2">
                <div className="panel panel-pad">
                  <h4 className="mb">Caso</h4>
                  <dl className="kv">
                    <dt>Processo</dt><dd>{c.processo_nome || '-'} <span className="muted small">{c.processo}</span></dd>
                    <dt>Cenário</dt><dd>{c.cenario || '-'}</dd>
                    <dt>Data efetiva</dt><dd>{c.evento?.data_efetiva}</dd>
                    <dt>Cargo alvo</dt><dd>{c.cargo_alvo || '-'}</dd>
                    <dt>Criado</dt><dd>{dateTime(c.criado_em)}</dd>
                    <dt>Replanejamentos</dt><dd>{c.replanejamentos || 0}</dd>
                    {c.pai_id ? <><dt>Evento coletivo</dt><dd><a onClick={() => openCase(c.pai_id)}>{c.pai_id}</a></dd></> : null}
                    {c.filhos?.length ? <><dt>Casos gerados</dt><dd>{c.filhos.length}</dd></> : null}
                    {c.caso_original ? <><dt>Caso original</dt><dd><a onClick={() => openCase(c.caso_original)}>{c.caso_original}</a></dd></> : null}
                  </dl>
                </div>
                <div className="panel panel-pad">
                  <h4 className="mb">Explicação por estágio</h4>
                  {meta.estagios.map((s) => c.etapas?.[s.id]?.resumo ? (
                    <div key={s.id} className="mb small"><b>{s.nome}:</b> {c.etapas[s.id].resumo}</div>
                  ) : null)}
                </div>
              </div>
              {c.excecoes_aprovadas?.length ? <div className="panel panel-pad"><h4 className="mb">Exceções aprovadas</h4>
                {c.excecoes_aprovadas.map((e, i) => <div key={i} className="small">{e.regra_id} aprovada por {meta.personas[e.por]?.pessoa} ({e.por}): {e.justificativa}</div>)}</div> : null}
              <div className="grid2">
                <AgentCard review={c.agente_plano} title="Agente: conferência do plano" />
                <AgentCard review={c.agente_auditoria} title="Agente: auditoria da execução" />
              </div>
              {c.filhos?.length ? <div className="panel panel-pad"><h4 className="mb">Casos individuais gerados</h4>
                <div className="row">{c.filhos.slice(0, 200).map((f) => <a key={f} className="chip" onClick={() => openCase(f)}>{f}</a>)}</div></div> : null}
              {c.erro ? <Json value={c.erro} /> : null}
            </div>
          )}

          {tab === 'evento' && (
            <div className="col">
              <p className="muted">O evento é a única entrada do fluxo: tipo, colaborador, data efetiva e dados suficientes para elegibilidade, plano e auditoria.</p>
              {editEvent !== null ? (
                <div className="col">
                  <textarea rows={18} value={editEvent} onChange={(e) => setEditEvent(e.target.value)} />
                  <div className="row">
                    <select value={retryStage} onChange={(e) => setRetryStage(e.target.value)}>
                      {meta.estagios.filter((s) => ['intake', 'eligibility', 'planning'].includes(s.id)).map((s) => <option key={s.id} value={s.id}>a partir de {s.nome}</option>)}
                    </select>
                    <button className="btn primary" onClick={() => act(async () => {
                      const ev = JSON.parse(editEvent)
                      await api.post(`/cases/${id}/retry`, { estagio: retryStage, evento: ev, depuracao: true })
                      setEditEvent(null)
                    }, 'Evento editado; reprocessando em modo passo a passo')}>Salvar e reprocessar</button>
                    <button className="btn" onClick={() => setEditEvent(null)}>Descartar</button>
                  </div>
                </div>
              ) : <Json value={c.evento} max={600} />}
            </div>
          )}

          {tab === 'elegibilidade' && (c.elegibilidade ? (
            <div className="col">
              <div className={`callout ${c.elegibilidade.decisao === 'ELEGIVEL' ? 'ok' : c.elegibilidade.decisao === 'NAO_ELEGIVEL' ? 'bad' : 'warn'}`}>
                <Status value={c.elegibilidade.decisao} /> {c.elegibilidade.explicacao}
              </div>
              <RulesTable rules={c.elegibilidade.regras} />
            </div>
          ) : <Empty>Ainda não avaliado.</Empty>)}

          {tab === 'plano' && (plano.operacoes ? (
            <div className="col">
              <div className="callout">{plano.resumo}</div>
              {plano.problemas?.length ? <div className="callout bad">{plano.problemas.join(' ')}</div> : null}
              <table className="tbl panel">
                <thead><tr><th>#</th><th>Operação</th><th>Sistema</th><th>Parâmetros</th><th>Por que foi escolhida</th><th>Origem</th></tr></thead>
                <tbody>{plano.operacoes.map((o) => (
                  <tr key={o.seq}>
                    <td>{o.seq}</td><td><b>{o.operacao}</b><div className="small muted">{o.nome}</div></td><td><Badge>{o.sistema}</Badge></td>
                    <td className="small mono" style={{ maxWidth: 260, wordBreak: 'break-word' }}>{JSON.stringify(o.parametros)}</td>
                    <td className="small">{o.motivo}{o.base_legal ? <div className="muted">Base: {o.base_legal}</div> : null}</td>
                    <td className="small">{o.origem === 'PROCESSO' ? <Badge tone="accent">processo</Badge> : <Badge tone="violet">estado alvo</Badge>}<div className="muted">{o.fonte}</div></td>
                  </tr>
                ))}</tbody>
              </table>
              {plano.descartadas?.length ? <div className="panel panel-pad"><h4 className="mb">Operações avaliadas e descartadas</h4>
                {plano.descartadas.map((d, i) => <div key={i} className="small mb"><b>{d.operacao}</b>: {d.motivo_descarte}</div>)}</div> : null}
              <details><summary>Estado alvo calculado pelos contratos</summary><Json value={plano.estado_alvo} /></details>
            </div>
          ) : <Empty>Plano ainda não gerado.</Empty>)}

          {tab === 'conferencia' && (
            <div className="col">
              {c.conferencia_plano ? <>
                <div className="row"><h3>Conferência determinística</h3><Status value={c.conferencia_plano.decisao} /></div>
                <RulesTable rules={c.conferencia_plano.regras} onlyFailed />
              </> : <Empty>Ainda não conferido.</Empty>}
              <AgentCard review={c.agente_plano} title="Agente de conferência do plano" />
            </div>
          )}

          {tab === 'execucao' && (c.execucao ? (
            <div className="col">
              {c.execucao.falha ? <div className="callout bad">{c.execucao.falha}</div> : null}
              <table className="tbl panel">
                <thead><tr><th>#</th><th>Operação</th><th>Status</th><th>Recibo</th><th>Alterações</th></tr></thead>
                <tbody>{(c.execucao.recibos || []).map((r) => (
                  <tr key={r.id}>
                    <td>{r.seq}</td><td><b>{r.operacao}</b><div className="small muted">{r.sistema}</div></td>
                    <td><Status value={r.status} /><div className="small muted">{time(r.fim)}</div></td>
                    <td className="small">{r.descricao || r.erro}<div className="muted mono">{r.protocolo}</div></td>
                    <td className="small">{(r.alteracoes || []).map((a) => a.campo).join(', ')}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : <Empty>Ainda não executado.</Empty>)}

          {tab === 'auditoria' && (
            <div className="col">
              {c.auditoria ? <>
                <div className="row"><h3>Auditoria pelo contrato de serviço</h3><Status value={c.auditoria.decisao} /></div>
                <RulesTable rules={c.auditoria.regras} onlyFailed />
              </> : <Empty>Ainda não auditado.</Empty>}
              <AgentCard review={c.agente_auditoria} title="Agente de auditoria" />
            </div>
          )}

          {tab === 'aprovacoes' && (data.aprovacoes.length ? data.aprovacoes.map((a) => <ApprovalBox key={a.id} ap={a} onDone={load} />) : <Empty>Nenhuma aprovação neste caso.</Empty>)}

          {tab === 'estado' && (
            <div className="col">
              <h3>Alterações aplicadas</h3>
              <DiffTable diff={c.execucao?.diff} />
              <div className="grid2">
                <div><h4 className="mb">Antes</h4><Json value={c.estado_inicial} /></div>
                <div><h4 className="mb">Depois</h4><Json value={c.estado_final || plano.projetado} /></div>
              </div>
            </div>
          )}

          {tab === 'log' && (
            <div className="panel panel-pad timeline">
              {data.log.map((l, i) => (
                <div className="tl-item" key={i}>
                  <div className="when">{time(l.ts)}<div className="kind">{l.estagio}</div></div>
                  <div><div className="kind">{l.tipo} · {l.ator}</div>{l.mensagem}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
