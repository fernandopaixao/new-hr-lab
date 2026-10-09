import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, Empty, Json, Modal, Status, Tabs, dateTime, useApp } from '../ui.jsx'
import { EventComposer } from './Employees.jsx'

const CAT = { PADRAO: 'Fluxo padrão', EXCECAO: 'Exige exceção', BLOQUEIO: 'Deve bloquear', COLETIVO: 'Eventos coletivos', ESTRESSE: 'Estresse e robustez' }

export default function Scenarios() {
  const { meta, toast, openCase, onLive } = useApp()
  const [tab, setTab] = useState('cenarios')
  const [debug, setDebug] = useState(false)
  const [preview, setPreview] = useState(null)
  const [burst, setBurst] = useState({ quantidade: 30, intervalo_ms: 100 })
  const [suites, setSuites] = useState([])
  const [suite, setSuite] = useState(null)

  const loadSuites = useCallback(async () => setSuites(await api.get('/scenarios/suite')), [])
  useEffect(() => { loadSuites() }, [loadSuites])
  useEffect(() => onLive(async (m) => {
    if (m.tipo === 'suite') {
      loadSuites()
      if (suite && m.id === suite.id) setSuite(await api.get(`/scenarios/suite/${m.id}`))
    }
  }), [onLive, loadSuites, suite])

  const gen = async (id) => {
    try {
      const r = await api.post(`/scenarios/${id}/generate`, { depuracao: debug })
      toast(`${r.casos.length} evento(s) enviados`)
      if (r.casos.length === 1) openCase(r.casos[0].id)
    } catch (e) { toast(e.message, 'bad') }
  }
  const prev = async (id) => {
    try { setPreview((await api.post(`/scenarios/${id}/generate`, { enviar: false })).previa) } catch (e) { toast(e.message, 'bad') }
  }
  const runSuite = async () => {
    const s = await api.post('/scenarios/suite', {})
    setSuite(s); setTab('suite'); toast('Suíte iniciada: todos os cenários foram enviados')
  }

  return (
    <div>
      <div className="page-head">
        <div><h2>Cenários e eventos</h2><p>Gerador artificial de eventos com cenários reais, de exceção, de bloqueio e de estresse. Cada cenário prepara um colaborador adequado e declara o resultado esperado.</p></div>
        <button className="btn primary right" onClick={runSuite}>Rodar suíte completa</button>
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[['cenarios', 'Catálogo de cenários'], ['manual', 'Evento manual'], ['estresse', 'Rajada de eventos'], ['suite', 'Resultados da suíte']]} />
      {tab === 'cenarios' && (
        <div>
          <label className="check mb"><input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} /> enviar em modo passo a passo (o caso para antes de cada estágio)</label>
          {Object.entries(CAT).map(([k, label]) => (
            <div key={k} className="mb">
              <h4 className="mb">{label}</h4>
              <div className="grid3">
                {meta.cenarios.filter((s) => s.categoria === k).map((s) => (
                  <div key={s.id} className="panel panel-pad col">
                    <b>{s.nome}</b>
                    <div className="small">{s.descricao}</div>
                    <div className="small muted">Esperado: {s.esperado.map((e) => <Status key={e} value={e} />)}</div>
                    <div className="row"><button className="btn sm" onClick={() => prev(s.id)}>Pré-visualizar</button><button className="btn sm primary right" onClick={() => gen(s.id)}>Gerar e enviar</button></div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {tab === 'manual' && <div className="panel panel-pad"><EventComposer /></div>}
      {tab === 'estresse' && (
        <div className="panel panel-pad col" style={{ maxWidth: 640 }}>
          <p>Envia uma rajada de eventos aleatórios (todas as categorias exceto coletivos) para estressar filas, travas por colaborador, replanejamento por concorrência e o agente de IA.</p>
          <div className="form-grid">
            <label className="field">Quantidade<input type="number" value={burst.quantidade} onChange={(e) => setBurst({ ...burst, quantidade: Number(e.target.value) })} /></label>
            <label className="field">Intervalo entre eventos (ms)<input type="number" value={burst.intervalo_ms} onChange={(e) => setBurst({ ...burst, intervalo_ms: Number(e.target.value) })} /></label>
          </div>
          <div className="row"><button className="btn primary" onClick={async () => { const r = await api.post('/scenarios/burst', burst); toast(`${r.agendados} cenários agendados`) }}>Disparar rajada</button></div>
          <p className="small muted">Dica: aumente a injeção de falhas e diminua o atraso visual nas configurações; escale os workers com docker compose up --scale worker=3.</p>
        </div>
      )}
      {tab === 'suite' && (
        <div className="list-side">
          <div className="panel panel-pad">
            <h4 className="mb">Execuções</h4>
            {suites.map((s) => (
              <div key={s.id} className={`side-item ${suite?.id === s.id ? 'active' : ''}`} onClick={async () => setSuite(await api.get(`/scenarios/suite/${s.id}`))}>
                <div className="row"><b className="small">{dateTime(s.criado_em)}</b><span className="right"><Status value={s.status} /></span></div>
                <div className="small muted">{s.resumo ? `${s.resumo.OK} ok · ${s.resumo.DIVERGENTE} divergentes · ${s.resumo.DIVERGENCIA_AGENTE} agente` : 'executando'}</div>
              </div>
            ))}
            {!suites.length ? <Empty>Nenhuma execução.</Empty> : null}
          </div>
          <div className="panel panel-pad">
            {!suite ? <Empty>Selecione uma execução ou rode a suíte.</Empty> : (
              <div className="col">
                <div className="row"><h3>Suíte de {dateTime(suite.criado_em)}</h3><span className="right"><Status value={suite.status} /></span></div>
                {suite.resumo ? <div className="row">{Object.entries(suite.resumo).filter(([, v]) => v).map(([k, v]) => <span key={k}><Status value={k} /> {v}</span>)}</div> : null}
                <p className="small muted">"Agente mais rigoroso" significa que as regras aprovaram, mas o agente de IA recomendou reprovar e o caso foi para revisão humana. Isso é esperado de uma segunda linha de defesa e vale analisar.</p>
                <table className="tbl">
                  <thead><tr><th>Cenário</th><th>Esperado</th><th>Obtido</th><th>Resultado</th></tr></thead>
                  <tbody>{(suite.resultados || []).map((r, i) => (
                    <tr key={i} className={r.resultado === 'DIVERGENTE' ? 'fail' : r.resultado === 'DIVERGENCIA_AGENTE' ? 'warnrow' : ''}>
                      <td><b>{r.cenario.nome}</b><div className="small muted">{r.cenario.descricao}</div></td>
                      <td>{r.cenario.esperado.map((e) => <div key={e}><Status value={e} /></div>)}</td>
                      <td>{(r.casos || []).map((c, j) => <div key={c}><a onClick={() => openCase(c)}><Status value={r.status_casos?.[j]} /></a></div>)}</td>
                      <td><Status value={r.resultado} /></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
      {preview ? (
        <Modal title={`Pré-visualização: ${preview.cenario.nome}`} onClose={() => setPreview(null)}>
          <h4 className="mb">Preparação do colaborador</h4>
          {preview.preparacao ? <Json value={preview.preparacao} max={200} /> : <div className="small muted">Nenhuma.</div>}
          <h4 className="mb mt">Eventos</h4>
          <Json value={preview.eventos} max={360} />
        </Modal>
      ) : null}
    </div>
  )
}

export { Badge }
