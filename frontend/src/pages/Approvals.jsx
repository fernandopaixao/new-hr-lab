import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, Empty, Modal, Status, dateTime, useApp } from '../ui.jsx'
import { ApprovalBox } from './CaseDetail.jsx'

const RESULT_LABEL = { DECIDIDA: 'decidida', IGNORADA: 'ignorada', FALHOU: 'falhou' }

export default function Approvals() {
  const { persona, meta, onLive, openCase, toast } = useApp()
  const [items, setItems] = useState([])
  const [onlyMine, setOnlyMine] = useState(true)
  const [tipo, setTipo] = useState('')
  const [evento, setEvento] = useState('')
  const [rec, setRec] = useState('')
  const [selected, setSelected] = useState(() => new Set())
  const [just, setJust] = useState('')
  const [confirming, setConfirming] = useState(null)
  const [busy, setBusy] = useState(false)
  const [lastBatch, setLastBatch] = useState(null)

  const load = useCallback(async () => setItems(await api.get('/approvals?limit=400')), [])
  useEffect(() => { load() }, [load])
  useEffect(() => onLive((m) => { if (m.tipo === 'approval') load() }), [onLive, load])
  useEffect(() => { setSelected(new Set()) }, [persona])

  const allPending = items.filter((a) => a.status === 'PENDENTE')
  const pending = allPending.filter((a) => (!onlyMine || a.aprovadores.includes(persona))
    && (!tipo || a.tipo === tipo) && (!evento || a.evento_tipo === evento)
    && (!rec || (a.recomendacao_agente?.recomendacao || 'SEM') === rec))
  const history = items.filter((a) => a.status !== 'PENDENTE')
  const decidable = pending.filter((a) => a.aprovadores.includes(persona))
  // only what is visible counts: changing a filter never decides something the person cannot see
  const chosenItems = decidable.filter((a) => selected.has(a.id))
  const chosen = chosenItems.map((a) => a.id)
  const tipos = [...new Set(allPending.map((a) => a.tipo))].map((t) => [t, allPending.find((a) => a.tipo === t)?.tipo_rotulo || t])
  const eventos = [...new Set(allPending.map((a) => a.evento_tipo))]
  const eventName = (e) => meta.tipos_evento.find((t) => t.evento === e)?.nome || e

  const toggle = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const selectAll = () => setSelected(new Set(decidable.map((a) => a.id)))
  const clear = () => setSelected(new Set())

  const recCount = (r) => chosenItems.filter((a) => (a.recomendacao_agente?.recomendacao || 'SEM') === r).length
  const sameCaseCount = chosenItems.length - new Set(chosenItems.map((a) => a.case_id)).size

  const run = async () => {
    const decisao = confirming
    setBusy(true)
    try {
      const out = await api.post('/approvals/batch', { ids: chosen, persona, decisao, justificativa: just })
      setLastBatch(out)
      toast(`${out.lote}: ${out.decididas} decidida(s)${out.ignoradas ? `, ${out.ignoradas} ignorada(s)` : ''}${out.falhas ? `, ${out.falhas} com falha` : ''}`, out.falhas ? 'bad' : undefined)
      setConfirming(null)
      setJust('')
      clear()
      load()
    } catch (e) { toast(e.message, 'bad') } finally { setBusy(false) }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Aprovações de exceção e revisões humanas</h2>
          <p>Toda decisão exige justificativa e fica registrada com quem decidiu, quando e por quê. Você está como <b>{meta.personas[persona]?.nome}</b> ({meta.personas[persona]?.pessoa}).</p>
        </div>
        <label className="check right"><input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} /> só o que minha persona pode decidir</label>
      </div>
      <div className="grid2">
        <div>
          <h3 className="mb">Pendentes ({pending.length})</h3>
          <div className="row mb gap-s">
            <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Todos os tipos</option>
              {tipos.map(([t, l]) => <option key={t} value={t}>{l}</option>)}
            </select>
            <select value={evento} onChange={(e) => setEvento(e.target.value)}>
              <option value="">Todos os eventos</option>
              {eventos.map((e) => <option key={e} value={e}>{eventName(e)}</option>)}
            </select>
            <select value={rec} onChange={(e) => setRec(e.target.value)}>
              <option value="">Qualquer recomendação</option>
              <option value="APROVADO">Agente recomenda aprovar</option>
              <option value="REPROVADO">Agente recomenda reprovar</option>
              <option value="SEM">Sem recomendação</option>
            </select>
          </div>
          {decidable.length ? (
            <div className="panel panel-pad mb">
              <div className="row">
                <b>Decisão em lote</b>
                <span className="small muted">{chosen.length} selecionada(s)</span>
                <button className="btn sm right" onClick={selectAll}>Selecionar as {decidable.length} filtradas que posso decidir</button>
                <button className="btn sm ghost" onClick={clear} disabled={!chosen.length}>Limpar</button>
              </div>
              {chosen.length ? (
                <div className="col mt">
                  <textarea rows={2} placeholder="Justificativa obrigatória, aplicada a cada aprovação do lote e registrada no log" value={just} onChange={(e) => setJust(e.target.value)} style={{ fontFamily: 'inherit' }} />
                  <div className="row">
                    <button className="btn ok" onClick={() => setConfirming('APROVAR')} disabled={just.trim().length < 5}>Aprovar selecionadas ({chosen.length})</button>
                    <button className="btn danger" onClick={() => setConfirming('REJEITAR')} disabled={just.trim().length < 5}>Rejeitar selecionadas ({chosen.length})</button>
                    <span className="small muted">decidindo como {meta.personas[persona]?.pessoa}</span>
                  </div>
                </div>
              ) : <div className="small muted mt">Marque as aprovações abaixo ou selecione todas as filtradas para decidir de uma vez.</div>}
            </div>
          ) : null}
          {lastBatch ? (
            <div className={`callout mb small ${lastBatch.falhas ? 'warn' : 'ok'}`}>
              <div className="row">
                <b>{lastBatch.lote}</b>
                <span>{lastBatch.decisao === 'APROVAR' ? 'aprovação' : 'rejeição'}: {lastBatch.decididas} decidida(s), {lastBatch.ignoradas} ignorada(s), {lastBatch.falhas} com falha</span>
                <button className="btn sm ghost right" onClick={() => setLastBatch(null)}>Fechar</button>
              </div>
              {lastBatch.resultados.some((r) => r.resultado !== 'DECIDIDA') ? (
                <ul>{lastBatch.resultados.filter((r) => r.resultado !== 'DECIDIDA').map((r) => (
                  <li key={r.id}>{r.case_id ? <a onClick={() => openCase(r.case_id)}>{r.id}</a> : r.id}: {RESULT_LABEL[r.resultado]}, {r.motivo}</li>
                ))}</ul>
              ) : null}
            </div>
          ) : null}
          {pending.length ? pending.map((a) => {
            const can = a.aprovadores.includes(persona)
            return (
              <div key={a.id}>
                <div className="row small mb gap-s">
                  {can ? <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggle(a.id)} aria-label="Selecionar para decisão em lote" /> : null}
                  <a onClick={() => openCase(a.case_id)}>{a.colaborador_nome || a.colaborador_id}</a>
                  <span className="muted">· {eventName(a.evento_tipo)}</span>
                </div>
                <ApprovalBox ap={a} onDone={load} />
              </div>
            )
          }) : <Empty>Nada pendente para esta persona.</Empty>}
        </div>
        <div>
          <h3 className="mb">Histórico de decisões</h3>
          <div className="panel">
            <table className="tbl">
              <thead><tr><th>Quando</th><th>Tipo</th><th>Caso</th><th>Decisão</th><th>Justificativa</th></tr></thead>
              <tbody>{history.slice(0, 150).map((a) => (
                <tr key={a.id} className="click" onClick={() => openCase(a.case_id)}>
                  <td className="small nowrap">{dateTime(a.decidido_em)}</td>
                  <td className="small">{a.tipo_rotulo}{a.regra ? <div><Badge tone="warn">{a.regra.id}</Badge></div> : null}</td>
                  <td className="small">{a.colaborador_nome}<div className="muted">{a.evento_tipo}</div></td>
                  <td><Status value={a.status} /><div className="small muted">{a.decidido_por?.pessoa}</div>{a.lote ? <div className="small muted">{a.lote}</div> : null}</td>
                  <td className="small">{a.justificativa}</td>
                </tr>
              ))}</tbody>
            </table>
            {!history.length ? <Empty>Nenhuma decisão ainda.</Empty> : null}
          </div>
        </div>
      </div>
      {confirming ? (
        <Modal title={`${confirming === 'APROVAR' ? 'Aprovar' : 'Rejeitar'} ${chosen.length} aprovação(ões) em lote`} onClose={() => !busy && setConfirming(null)}
          footer={<>
            <button className="btn" onClick={() => setConfirming(null)} disabled={busy}>Voltar</button>
            <button className={`btn ${confirming === 'APROVAR' ? 'ok' : 'danger'}`} onClick={run} disabled={busy}>{busy ? 'Registrando...' : `Confirmar ${confirming === 'APROVAR' ? 'aprovação' : 'rejeição'}`}</button>
          </>}>
          <p>Cada aprovação é decidida e registrada individualmente, como {meta.personas[persona]?.pessoa} ({persona}), com a mesma justificativa e o mesmo número de lote.</p>
          <p className="small">Recomendação do agente nas selecionadas: {recCount('APROVADO')} aprovar, {recCount('REPROVADO')} reprovar, {recCount('SEM')} sem recomendação.</p>
          {confirming === 'APROVAR' && recCount('REPROVADO') ? (
            <div className="callout warn small mb">{recCount('REPROVADO')} selecionada(s) têm recomendação do agente para reprovar.</div>
          ) : null}
          {confirming === 'REJEITAR' && sameCaseCount ? (
            <div className="callout warn small mb">Há mais de uma aprovação do mesmo caso. Rejeitar uma cancela as demais do mesmo estágio; elas aparecem como ignoradas no resultado.</div>
          ) : null}
          {meta.resultado_aprovacao ? (
            <ul className="small">{[...new Set(chosenItems.map((a) => a.estagio))].map((s) => meta.resultado_aprovacao[s] ? (
              <li key={s}>{meta.estagios.find((e) => e.id === s)?.nome || s}: {confirming === 'APROVAR' ? meta.resultado_aprovacao[s].aprovar : meta.resultado_aprovacao[s].rejeitar}</li>
            ) : null)}</ul>
          ) : null}
          <div className="small muted">Justificativa: {just.trim()}</div>
        </Modal>
      ) : null}
    </div>
  )
}
