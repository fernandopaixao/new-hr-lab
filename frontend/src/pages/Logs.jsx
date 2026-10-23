import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, Empty, dateTime, useApp } from '../ui.jsx'

const TIPOS = ['EVENTO_RECEBIDO', 'EVENTO_REJEITADO', 'EVENTO_DUPLICADO', 'REGRA_AVALIADA', 'DECISAO_ELEGIBILIDADE', 'PLANO_GERADO', 'OPERACAO_ESCOLHIDA',
  'OPERACAO_DESCARTADA', 'OPERACAO_EXECUTADA', 'OPERACAO_FALHOU', 'COMPENSACAO', 'AGENTE_RECOMENDACAO', 'AGENTE_INDISPONIVEL', 'APROVACAO_SOLICITADA',
  'APROVACAO_DECIDIDA', 'APROVACAO_LOTE', 'AUDITORIA', 'DECISAO_FINAL', 'COLABORADOR_ALTERADO', 'CONTRATO_ALTERADO', 'CONFIG_ALTERADA', 'CONTROLE', 'DEPURACAO', 'REPLANEJAMENTO']
const TONE = { OPERACAO_FALHOU: 'bad', COMPENSACAO: 'violet', AGENTE_RECOMENDACAO: 'info', APROVACAO_DECIDIDA: 'warn', APROVACAO_LOTE: 'warn', APROVACAO_SOLICITADA: 'warn', DECISAO_FINAL: 'accent',
  OPERACAO_EXECUTADA: 'ok', REGRA_AVALIADA: 'warn', AGENTE_INDISPONIVEL: 'bad', CONTRATO_ALTERADO: 'violet', COLABORADOR_ALTERADO: 'violet' }

export default function Logs() {
  const { onLive, openCase } = useApp()
  const [items, setItems] = useState([])
  const [tipo, setTipo] = useState('')
  const [texto, setTexto] = useState('')
  const [live, setLive] = useState(true)
  const [open, setOpen] = useState(null)

  const load = useCallback(async () => {
    const qs = new URLSearchParams({ limit: '400' })
    if (tipo) qs.set('tipo', tipo)
    if (texto) qs.set('texto', texto)
    setItems((await api.get(`/logs?${qs}`)).reverse())
  }, [tipo, texto])
  useEffect(() => { load() }, [load])
  useEffect(() => onLive((m) => {
    if (!live || m.tipo !== 'log') return
    if (tipo && m.entry.tipo !== tipo) return
    if (texto && !m.entry.mensagem.toLowerCase().includes(texto.toLowerCase())) return
    setItems((l) => [m.entry, ...l].slice(0, 600))
  }), [onLive, live, tipo, texto])

  return (
    <div>
      <div className="page-head">
        <div><h2>Log de alterações e decisões</h2><p>Registro append-only: cada regra, escolha de operação, execução, compensação, recomendação do agente, aprovação e alteração de contrato ou cadastro, com a explicação. Também gravado em arquivo JSONL no volume de dados.</p></div>
        <a className="btn right" href="/api/logs/export">Exportar JSONL</a>
      </div>
      <div className="row mb">
        <select value={tipo} onChange={(e) => setTipo(e.target.value)}><option value="">Todos os tipos</option>{TIPOS.map((t) => <option key={t}>{t}</option>)}</select>
        <input placeholder="Filtrar texto" value={texto} onChange={(e) => setTexto(e.target.value)} style={{ width: 300 }} />
        <label className="check"><input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> ao vivo</label>
        <span className="small muted">{items.length} registros</span>
      </div>
      <div className="panel">
        <table className="tbl">
          <thead><tr><th>Quando</th><th>Tipo</th><th>Ator</th><th>Mensagem</th><th>Caso</th></tr></thead>
          <tbody>{items.map((l) => (
            <React.Fragment key={l.id}>
              <tr className="click" onClick={() => setOpen(open === l.id ? null : l.id)}>
                <td className="small nowrap mono">{dateTime(l.ts)}</td>
                <td><Badge tone={TONE[l.tipo] || ''}>{l.tipo}</Badge><div className="small muted">{l.estagio}</div></td>
                <td className="small">{l.ator}</td>
                <td className="small">{l.mensagem}</td>
                <td className="small">{l.case_id ? <a onClick={(e) => { e.stopPropagation(); openCase(l.case_id) }}>{l.case_id}</a> : '-'}<div className="muted">{l.colaborador_id}</div></td>
              </tr>
              {open === l.id ? <tr><td colSpan={5}><pre className="small">{JSON.stringify(l.dados, null, 2)}</pre></td></tr> : null}
            </React.Fragment>
          ))}</tbody>
        </table>
        {!items.length ? <Empty>Sem registros.</Empty> : null}
      </div>
    </div>
  )
}
