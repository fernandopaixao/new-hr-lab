import React, { useState } from 'react'
import { api } from '../api.js'
import { Badge, DiffTable, Modal, useApp } from '../ui.jsx'

function Invoke({ op, onClose }) {
  const { toast } = useApp()
  const [colab, setColab] = useState('F00001')
  const example = Object.fromEntries(op.parametros.map((p) => [p.nome, p.tipo === 'numero' ? 0 : p.tipo === 'lista' ? [] : p.tipo === 'booleano' ? true : p.tipo === 'objeto' ? {} : '']))
  const [params, setParams] = useState(JSON.stringify(example, null, 2))
  const [result, setResult] = useState(null)
  const run = async (simular) => {
    try {
      setResult(await api.post(`/shelf/${op.codigo}/invoke`, { colaborador_id: colab, parametros: JSON.parse(params), simular }))
      if (!simular) toast('Operação aplicada e registrada no log')
    } catch (e) { toast(e.message, 'bad') }
  }
  return (
    <Modal title={`Executar ${op.codigo} de forma avulsa`} onClose={onClose}
      footer={<><button className="btn" onClick={() => run(true)}>Simular</button><button className="btn primary" onClick={() => run(false)}>Aplicar</button></>}>
      <p className="small muted">A prateleira é desacoplada do processo: a mesma operação pode ser chamada por qualquer contrato ou diretamente, para testes. Simular não grava nada.</p>
      <label className="field">Colaborador<input value={colab} onChange={(e) => setColab(e.target.value)} /></label>
      <label className="field mt">Parâmetros (JSON)<textarea rows={8} value={params} onChange={(e) => setParams(e.target.value)} /></label>
      {result ? (
        <div className="col mt">
          <div className="callout">{result.simulado ? 'Simulação: ' : 'Aplicado: '}{result.descricao}</div>
          <DiffTable diff={result.alteracoes} />
          {result.conformidade_apos.conforme ? <div className="callout ok small">Após a operação o colaborador continua conforme.</div>
            : <div className="callout bad small">Após a operação: {[...result.conformidade_apos.falhas.map((f) => f.explicacao), ...result.conformidade_apos.pendencias_estado_alvo].join(' ')}</div>}
        </div>
      ) : null}
    </Modal>
  )
}

export default function Shelf() {
  const { meta } = useApp()
  const [op, setOp] = useState(null)
  const systems = [...new Set(meta.prateleira.map((o) => o.sistema))]
  return (
    <div>
      <div className="page-head">
        <div><h2>Prateleira de serviços</h2><p>Operações parametrizáveis e desacopladas, chamadas pelos contratos de processo ou derivadas do estado alvo. Cada uma declara o sistema, os parâmetros e os campos que altera, o que permite a compensação automática da saga.</p></div>
      </div>
      {systems.map((s) => (
        <div key={s} className="mb">
          <h4 className="mb">{s}</h4>
          <div className="grid3">
            {meta.prateleira.filter((o) => o.sistema === s).map((o) => (
              <div key={o.codigo} className="panel panel-pad col">
                <div className="row"><b>{o.nome}</b><span className="right">{o.compensavel ? <Badge tone="ok">compensável</Badge> : <Badge tone="warn">sem compensação</Badge>}</span></div>
                <div className="small mono muted">{o.codigo}</div>
                <div className="small">{o.descricao}</div>
                <div className="small"><b>Parâmetros:</b> {o.parametros.map((p) => <span key={p.nome} className="chip">{p.nome}{p.obrigatorio ? '*' : ''}: {p.tipo}</span>)}</div>
                <div className="small muted">Altera: {o.campos_afetados.join(', ') || 'nada no cadastro'}</div>
                <div className="row"><button className="btn sm right" onClick={() => setOp(o)}>Executar avulso</button></div>
              </div>
            ))}
          </div>
        </div>
      ))}
      {op ? <Invoke op={op} onClose={() => setOp(null)} /> : null}
    </div>
  )
}
