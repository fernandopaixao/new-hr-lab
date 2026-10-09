import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, Empty, Status, dateTime, useApp } from '../ui.jsx'
import { ApprovalBox } from './CaseDetail.jsx'

export default function Approvals() {
  const { persona, meta, onLive, openCase } = useApp()
  const [items, setItems] = useState([])
  const [onlyMine, setOnlyMine] = useState(true)

  const load = useCallback(async () => setItems(await api.get('/approvals?limit=400')), [])
  useEffect(() => { load() }, [load])
  useEffect(() => onLive((m) => { if (m.tipo === 'approval') load() }), [onLive, load])

  const pending = items.filter((a) => a.status === 'PENDENTE' && (!onlyMine || a.aprovadores.includes(persona)))
  const history = items.filter((a) => a.status !== 'PENDENTE')

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
          {pending.length ? pending.map((a) => (
            <div key={a.id}>
              <div className="row small mb gap-s">
                <a onClick={() => openCase(a.case_id)}>{a.colaborador_nome || a.colaborador_id}</a>
                <span className="muted">· {meta.tipos_evento.find((t) => t.evento === a.evento_tipo)?.nome || a.evento_tipo}</span>
              </div>
              <ApprovalBox ap={a} onDone={load} />
            </div>
          )) : <Empty>Nada pendente para esta persona.</Empty>}
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
                  <td><Status value={a.status} /><div className="small muted">{a.decidido_por?.pessoa}</div></td>
                  <td className="small">{a.justificativa}</td>
                </tr>
              ))}</tbody>
            </table>
            {!history.length ? <Empty>Nenhuma decisão ainda.</Empty> : null}
          </div>
        </div>
      </div>
    </div>
  )
}
