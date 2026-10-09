import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { Badge, Empty, Json, Modal, Status, Tabs, dateTime, money, time, useApp } from '../ui.jsx'

const CARGOS = ['ESCRITURARIO', 'CAIXA', 'ANALISTA_JR', 'ANALISTA_PL', 'ANALISTA_SR', 'GERENTE_RELACIONAMENTO', 'COORDENADOR', 'GERENTE_AGENCIA', 'SUPERINTENDENTE', 'DIRETOR']
const SITUACOES = ['ATIVO', 'AFASTADO', 'GARDEN_LEAVE', 'DESLIGADO']
const ESCOLARIDADE = ['FUNDAMENTAL', 'MEDIO', 'TECNICO', 'SUPERIOR_INCOMPLETO', 'SUPERIOR', 'POS_GRADUACAO', 'MESTRADO', 'DOUTORADO']
const ESTAB = ['GESTANTE', 'ACIDENTE_TRABALHO', 'CIPA', 'DIRIGENTE_SINDICAL', 'PRE_APOSENTADORIA']
const UFS = ['SP', 'RJ', 'ES', 'MG', 'RS', 'SC', 'PR', 'PE', 'BA', 'CE', 'DF', 'GO']

export function EventComposer({ initialType, colaboradorId, onClose }) {
  const { meta, toast, openCase } = useApp()
  const [tipo, setTipo] = useState(initialType || meta.tipos_evento[0]?.evento)
  const [dados, setDados] = useState('')
  const [colab, setColab] = useState(colaboradorId || '')
  const [dataEf, setDataEf] = useState(meta.hoje)
  const [debug, setDebug] = useState(false)
  useEffect(() => { setDados(JSON.stringify(meta.templates_evento[tipo] || {}, null, 2)) }, [tipo, meta])
  const send = async () => {
    try {
      const ev = { tipo, colaborador_id: colab || null, data_efetiva: dataEf, origem: 'interface', dados: JSON.parse(dados || '{}') }
      const c = await api.post('/events', { evento: ev, depuracao: debug })
      toast('Evento enviado para a linha')
      onClose && onClose()
      openCase(c.id)
    } catch (e) { toast(e.message, 'bad') }
  }
  const t = meta.tipos_evento.find((x) => x.evento === tipo)
  return (
    <div className="col">
      <div className="form-grid">
        <label className="field">Tipo de evento
          <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
            {meta.tipos_evento.map((x) => <option key={x.evento} value={x.evento}>{x.nome} ({x.evento})</option>)}
          </select>
        </label>
        <label className="field">Colaborador (matrícula)<input value={colab} onChange={(e) => setColab(e.target.value)} placeholder="F00001" /></label>
        <label className="field">Data efetiva<input type="date" value={dataEf} onChange={(e) => setDataEf(e.target.value)} /></label>
      </div>
      {t ? <div className="small muted">{t.descricao} Campos obrigatórios: {(t.schema?.obrigatorios || []).join(', ') || 'nenhum'}.</div> : null}
      <label className="field">Dados do evento (JSON)<textarea rows={12} value={dados} onChange={(e) => setDados(e.target.value)} /></label>
      <div className="row">
        <label className="check"><input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} /> modo passo a passo (para antes de cada estágio)</label>
        <button className="btn primary right" onClick={send}>Enviar evento</button>
      </div>
    </div>
  )
}

function EmployeeEditor({ id, onChanged }) {
  const { toast, openCase, meta, onLive } = useApp()
  const [data, setData] = useState(null)
  const [form, setForm] = useState(null)
  const [tab, setTab] = useState('cadastro')
  const [raw, setRaw] = useState('')
  const [composer, setComposer] = useState(false)

  const load = useCallback(async () => {
    const d = await api.get(`/employees/${id}`)
    setData(d)
    setForm(d.colaborador)
    setRaw(JSON.stringify(d.colaborador, null, 2))
  }, [id])
  useEffect(() => { load() }, [load])
  useEffect(() => onLive((m) => { if (m.tipo === 'log' && m.entry.colaborador_id === id && m.entry.tipo === 'DECISAO_FINAL') load() }), [onLive, id, load])

  if (!data || !form) return <Empty>Carregando...</Empty>
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const save = async (patch) => {
    try {
      await api.put(`/employees/${id}`, patch)
      toast('Colaborador atualizado e alteração registrada no log')
      await load(); onChanged && onChanged()
    } catch (e) { toast(e.message, 'bad') }
  }
  const saveForm = () => {
    const keys = ['nome', 'cargo', 'data_admissao', 'data_inicio_cargo', 'data_inicio_unidade', 'data_nascimento', 'salario_base', 'jornada_horas', 'regime_jornada',
      'unidade', 'cidade', 'uf', 'sindicato', 'escolaridade', 'avaliacao_desempenho', 'genero', 'situacao', 'certificacoes', 'conduta', 'estabilidades', 'dependentes']
    const patch = {}
    keys.forEach((k) => { patch[k] = form[k] })
    patch.salario_base = Number(form.salario_base)
    patch.jornada_horas = Number(form.jornada_horas)
    patch.avaliacao_desempenho = Number(form.avaliacao_desempenho)
    save(patch)
  }
  const conf = data.conformidade
  const conduta = form.conduta || {}
  return (
    <div className="col">
      <div className="row">
        <div>
          <h2>{form.nome}</h2>
          <div className="muted small">{form.id} · versão {form.versao} · {form.cargo} · {form.unidade} {form.cidade}/{form.uf}</div>
        </div>
        <div className="right row">
          {conf.conforme ? <Badge tone="ok">Conforme aos contratos</Badge> : <Badge tone="bad">{conf.falhas.length + conf.pendencias_estado_alvo.length} pendência(s)</Badge>}
          <button className="btn" onClick={() => setComposer(true)}>Disparar evento</button>
          <button className="btn" onClick={async () => { try { await api.post(`/employees/${id}/drift`, {}); toast('Desvio injetado'); load() } catch (e) { toast(e.message, 'bad') } }}>Injetar desvio</button>
          <button className="btn" onClick={async () => {
            const c = await api.post('/events', { evento: { tipo: 'auditoria.conformidade_solicitada', colaborador_id: id, data_efetiva: meta.hoje, origem: 'interface', dados: { motivo: 'Conferência manual' } } })
            openCase(c.id)
          }}>Conferir conformidade</button>
        </div>
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[['cadastro', 'Cadastro'], ['estado', 'Benefícios, verbas e acessos'], ['conformidade', 'Conformidade'], ['casos', `Casos (${data.casos.length})`], ['log', 'Histórico'], ['json', 'JSON completo']]} />
      {tab === 'cadastro' && (
        <div className="col">
          <div className="form-grid">
            <label className="field">Nome<input value={form.nome || ''} onChange={(e) => set('nome', e.target.value)} /></label>
            <label className="field">Cargo<select value={form.cargo || ''} onChange={(e) => set('cargo', e.target.value)}>{CARGOS.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field">Situação<select value={form.situacao} onChange={(e) => set('situacao', e.target.value)}>{SITUACOES.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field">Salário base<input type="number" value={form.salario_base} onChange={(e) => set('salario_base', e.target.value)} /></label>
            <label className="field">Data de admissão<input type="date" value={form.data_admissao || ''} onChange={(e) => set('data_admissao', e.target.value)} /></label>
            <label className="field">Início no cargo<input type="date" value={form.data_inicio_cargo || ''} onChange={(e) => set('data_inicio_cargo', e.target.value)} /></label>
            <label className="field">Início na unidade<input type="date" value={form.data_inicio_unidade || ''} onChange={(e) => set('data_inicio_unidade', e.target.value)} /></label>
            <label className="field">Nascimento<input type="date" value={form.data_nascimento || ''} onChange={(e) => set('data_nascimento', e.target.value)} /></label>
            <label className="field">Gênero<select value={form.genero} onChange={(e) => set('genero', e.target.value)}><option>F</option><option>M</option></select></label>
            <label className="field">Jornada (h)<input type="number" value={form.jornada_horas || ''} onChange={(e) => set('jornada_horas', e.target.value)} /></label>
            <label className="field">Regime<select value={form.regime_jornada || ''} onChange={(e) => set('regime_jornada', e.target.value)}>{['NORMAL_224', 'CONFIANCA_224_2', 'GESTAO_62_II'].map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field">Unidade<input value={form.unidade || ''} onChange={(e) => set('unidade', e.target.value)} /></label>
            <label className="field">Cidade<input value={form.cidade || ''} onChange={(e) => set('cidade', e.target.value)} /></label>
            <label className="field">UF<select value={form.uf || ''} onChange={(e) => set('uf', e.target.value)}>{UFS.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field">Sindicato<input value={form.sindicato || ''} onChange={(e) => set('sindicato', e.target.value)} /></label>
            <label className="field">Escolaridade<select value={form.escolaridade} onChange={(e) => set('escolaridade', e.target.value)}>{ESCOLARIDADE.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field">Avaliação (1 a 5)<input type="number" min={1} max={5} value={form.avaliacao_desempenho} onChange={(e) => set('avaliacao_desempenho', e.target.value)} /></label>
            <label className="field">Certificações (separadas por vírgula)<input value={(form.certificacoes || []).join(', ')} onChange={(e) => set('certificacoes', e.target.value.split(',').map((x) => x.trim()).filter(Boolean))} /></label>
          </div>
          <div className="row">
            <label className="check"><input type="checkbox" checked={!!conduta.processo_disciplinar_aberto} onChange={(e) => set('conduta', { ...conduta, processo_disciplinar_aberto: e.target.checked })} /> processo disciplinar aberto</label>
            <label className="check"><input type="checkbox" checked={!!conduta.medida_restritiva_compliance} onChange={(e) => set('conduta', { ...conduta, medida_restritiva_compliance: e.target.checked })} /> medida restritiva de compliance</label>
            <button className="btn sm" onClick={() => set('conduta', { ...conduta, advertencias: [...(conduta.advertencias || []), { data: meta.hoje, motivo: 'Advertência registrada no laboratório' }] })}>Registrar advertência ({(conduta.advertencias || []).length})</button>
          </div>
          <div className="panel panel-pad">
            <div className="row mb"><h4>Estabilidades</h4>
              <select id="estab-add" defaultValue="GESTANTE">{ESTAB.map((e) => <option key={e}>{e}</option>)}</select>
              <button className="btn sm" onClick={() => {
                const tipo = document.getElementById('estab-add').value
                const fim = new Date(); fim.setMonth(fim.getMonth() + 12)
                set('estabilidades', [...(form.estabilidades || []), { tipo, inicio: meta.hoje, fim: fim.toISOString().slice(0, 10) }])
              }}>Adicionar</button>
            </div>
            {(form.estabilidades || []).map((e, i) => (
              <div key={i} className="row small mb">
                <Badge tone="warn">{e.tipo}</Badge>
                <input type="date" value={e.inicio || ''} onChange={(ev) => set('estabilidades', form.estabilidades.map((x, j) => j === i ? { ...x, inicio: ev.target.value } : x))} />
                até <input type="date" value={e.fim || ''} onChange={(ev) => set('estabilidades', form.estabilidades.map((x, j) => j === i ? { ...x, fim: ev.target.value } : x))} />
                <button className="btn sm danger" onClick={() => set('estabilidades', form.estabilidades.filter((_, j) => j !== i))}>Remover</button>
              </div>
            ))}
            {!(form.estabilidades || []).length ? <div className="small muted">Nenhuma.</div> : null}
          </div>
          <div className="panel panel-pad">
            <div className="row mb"><h4>Dependentes</h4>
              <button className="btn sm" onClick={() => set('dependentes', [...(form.dependentes || []), { nome: 'Novo dependente', parentesco: 'FILHO', data_nascimento: meta.hoje }])}>Adicionar</button></div>
            {(form.dependentes || []).map((d, i) => (
              <div key={i} className="row small mb">
                <input value={d.nome} onChange={(ev) => set('dependentes', form.dependentes.map((x, j) => j === i ? { ...x, nome: ev.target.value } : x))} />
                <input type="date" value={d.data_nascimento || ''} onChange={(ev) => set('dependentes', form.dependentes.map((x, j) => j === i ? { ...x, data_nascimento: ev.target.value } : x))} />
                <button className="btn sm danger" onClick={() => set('dependentes', form.dependentes.filter((_, j) => j !== i))}>Remover</button>
              </div>
            ))}
          </div>
          <div className="row"><span className="small muted">Alterações manuais mudam o estado sem passar pela linha (útil para preparar cenários) e ficam registradas no log.</span>
            <button className="btn primary right" onClick={saveForm}>Salvar alterações</button></div>
        </div>
      )}
      {tab === 'estado' && (
        <div className="grid2">
          <div className="panel panel-pad">
            <h4 className="mb">Atual</h4>
            <div className="small mb"><b>Benefícios:</b> {(form.beneficios || []).map((b) => <span key={b.codigo} className="chip">{b.codigo} {b.plano}{b.valor ? ` ${money(b.valor)}` : ''}</span>)}</div>
            <div className="small mb"><b>Verbas:</b> {(form.verbas || []).map((v, i) => <span key={i} className="chip">{v.codigo} {money(v.valor)}{v.recorrente ? '' : ' (pontual)'}</span>)}</div>
            <div className="small mb"><b>Acessos:</b> {(form.acessos || []).map((a) => <span key={a} className="chip">{a}</span>)}</div>
            <div className="small mb"><b>Equipamentos:</b> {(form.equipamentos || []).map((a) => <span key={a} className="chip">{a}</span>)}</div>
            <div className="small mb"><b>Cláusulas:</b> {(form.clausulas || []).map((a) => <span key={a.codigo} className="chip">{a.codigo}</span>)}</div>
            <div className="small"><b>Jornada:</b> {form.jornada_horas}h {form.regime_jornada} · <b>Sindicato:</b> {form.sindicato}</div>
          </div>
          <div className="panel panel-pad">
            <h4 className="mb">Estado alvo pelos contratos</h4>
            <div className="small mb"><b>Benefícios:</b> {(data.estado_alvo.beneficios || []).map((b) => <span key={b.codigo} className="chip">{b.codigo} {b.plano}</span>)}</div>
            <div className="small mb"><b>Verbas:</b> {(data.estado_alvo.verbas || []).map((v) => <span key={v.codigo} className="chip">{v.codigo} {money(v.valor)}</span>)}</div>
            <div className="small mb"><b>Acessos:</b> {(data.estado_alvo.acessos || []).map((a) => <span key={a.codigo} className="chip">{a.codigo}</span>)}</div>
            <div className="small mb"><b>Equipamentos:</b> {(data.estado_alvo.equipamentos || []).map((a) => <span key={a.codigo} className="chip">{a.codigo}</span>)}</div>
            <div className="small mb"><b>Cláusulas:</b> {(data.estado_alvo.clausulas || []).map((a) => <span key={a.codigo} className="chip">{a.codigo}</span>)}</div>
            <div className="small"><b>Jornada:</b> {data.estado_alvo.jornada_horas}h {data.estado_alvo.regime_jornada} · <b>Sindicato:</b> {data.estado_alvo.sindicato} · <b>Faixa:</b> {money(data.estado_alvo.faixa_salarial?.min)} a {money(data.estado_alvo.faixa_salarial?.max)}</div>
          </div>
        </div>
      )}
      {tab === 'conformidade' && (
        <div className="col">
          {conf.falhas.map((r, i) => <div key={i} className="callout bad"><b>{r.id}</b> {r.explicacao} <span className="small muted">({r.base_legal || r.origem})</span></div>)}
          {conf.pendencias_estado_alvo.map((p, i) => <div key={i} className="callout warn">{p}</div>)}
          {conf.conforme ? <div className="callout ok">Colaborador aderente às regras de compliance e ao estado alvo dos contratos vigentes.</div> : null}
        </div>
      )}
      {tab === 'casos' && (
        <table className="tbl panel"><thead><tr><th>Caso</th><th>Evento</th><th>Status</th><th>Resumo</th></tr></thead>
          <tbody>{data.casos.map((c) => <tr key={c.id} className="click" onClick={() => openCase(c.id)}><td className="small mono">{c.id}</td><td>{c.evento_tipo}</td><td><Status value={c.status} /></td><td className="small">{c.resumo}</td></tr>)}</tbody></table>
      )}
      {tab === 'log' && (
        <div className="panel panel-pad timeline">{data.log.slice().reverse().map((l, i) => (
          <div key={i} className="tl-item"><div className="when">{dateTime(l.ts)}</div><div><div className="kind">{l.tipo} · {l.ator}</div>{l.mensagem}</div></div>
        ))}</div>
      )}
      {tab === 'json' && (
        <div className="col">
          <textarea rows={24} value={raw} onChange={(e) => setRaw(e.target.value)} />
          <div className="row"><button className="btn primary right" onClick={() => { try { save(JSON.parse(raw)) } catch (e) { toast(e.message, 'bad') } }}>Salvar JSON</button></div>
        </div>
      )}
      {composer ? <Modal title="Disparar evento" onClose={() => setComposer(false)}><EventComposer colaboradorId={id} onClose={() => setComposer(false)} /></Modal> : null}
    </div>
  )
}

export default function Employees() {
  const { toast, onLive } = useApp()
  const [list, setList] = useState([])
  const [sel, setSel] = useState(null)
  const [q, setQ] = useState('')
  const [cargo, setCargo] = useState('')
  const [onlyBad, setOnlyBad] = useState(false)
  const [gen, setGen] = useState({ tamanho: 80, semente: 42, desvio_percentual: 15, substituir: true })
  const [showGen, setShowGen] = useState(false)

  const load = useCallback(async () => setList(await api.get('/employees')), [])
  useEffect(() => { load() }, [load])
  useEffect(() => onLive((m) => { if (m.tipo === 'employees') load() }), [onLive, load])

  const shown = useMemo(() => list.filter((e) => (!cargo || e.cargo === cargo) && (!onlyBad || !e.conforme)
    && (!q || `${e.nome} ${e.id} ${e.cidade}`.toLowerCase().includes(q.toLowerCase()))), [list, q, cargo, onlyBad])

  const generate = async () => {
    try {
      const r = await api.post('/employees/generate', { ...gen, tamanho: Number(gen.tamanho), semente: Number(gen.semente), desvio_percentual: Number(gen.desvio_percentual) })
      toast(`${r.gerados} colaboradores gerados`); setShowGen(false); setSel(null); load()
    } catch (e) { toast(e.message, 'bad') }
  }

  return (
    <div>
      <div className="page-head">
        <div><h2>Colaboradores</h2><p>Time artificial gerado a partir dos contratos de cargo, com desvios propositais para os agentes encontrarem.</p></div>
        <button className="btn primary right" onClick={() => setShowGen(true)}>Gerar novo time</button>
      </div>
      <div className="list-side">
        <div className="panel">
          <div className="panel-pad col" style={{ borderBottom: '1px solid var(--border)' }}>
            <input placeholder="Buscar" value={q} onChange={(e) => setQ(e.target.value)} />
            <div className="row">
              <select value={cargo} onChange={(e) => setCargo(e.target.value)} style={{ flex: 1 }}><option value="">Todos os cargos</option>{CARGOS.map((c) => <option key={c}>{c}</option>)}</select>
              <label className="check small"><input type="checkbox" checked={onlyBad} onChange={(e) => setOnlyBad(e.target.checked)} /> pendências</label>
            </div>
            <div className="small muted">{shown.length} de {list.length} · {list.filter((e) => !e.conforme).length} com pendências</div>
          </div>
          <div style={{ maxHeight: 'calc(100vh - 290px)', overflow: 'auto', padding: 6 }}>
            {shown.map((e) => (
              <div key={e.id} className={`side-item ${sel === e.id ? 'active' : ''}`} onClick={() => setSel(e.id)}>
                <div className="row gap-s"><b className="ellipsis" style={{ maxWidth: 170 }}>{e.nome}</b>
                  <span className="right">{e.conforme ? <Badge tone="ok">ok</Badge> : <Badge tone="bad">{e.pendencias}</Badge>}</span></div>
                <div className="small muted">{e.id} · {e.cargo} · {e.situacao}{e.estabilidades?.length ? ` · ${e.estabilidades.join(', ')}` : ''}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="panel panel-pad">{sel ? <EmployeeEditor key={sel} id={sel} onChanged={load} /> : <Empty>Selecione um colaborador para ver, editar ou disparar eventos.</Empty>}</div>
      </div>
      {showGen ? (
        <Modal title="Gerar composição de time" onClose={() => setShowGen(false)} footer={<button className="btn primary" onClick={generate}>Gerar</button>}>
          <div className="form-grid">
            <label className="field">Tamanho<input type="number" value={gen.tamanho} onChange={(e) => setGen({ ...gen, tamanho: e.target.value })} /></label>
            <label className="field">Semente aleatória<input type="number" value={gen.semente} onChange={(e) => setGen({ ...gen, semente: e.target.value })} /></label>
            <label className="field">% com desvios<input type="number" value={gen.desvio_percentual} onChange={(e) => setGen({ ...gen, desvio_percentual: e.target.value })} /></label>
          </div>
          <label className="check mt"><input type="checkbox" checked={gen.substituir} onChange={(e) => setGen({ ...gen, substituir: e.target.checked })} /> substituir o time atual (senão, adiciona)</label>
          <p className="small muted">A organização tem diretoria, superintendências, coordenações na sede e agências em várias bases sindicais. A mesma semente gera o mesmo time.</p>
        </Modal>
      ) : null}
    </div>
  )
}
