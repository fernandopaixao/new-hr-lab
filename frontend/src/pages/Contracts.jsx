import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Empty, Tabs, useApp } from '../ui.jsx'

const KIND_LABEL = { NORMA: 'Normas regulatórias', POLITICA: 'Políticas internas', CARGO: 'Contratos de cargo', PROCESSO: 'Contratos de processo' }

function getPath(obj, path) {
  return path.split('.').reduce((o, k) => (o ? o[k] : undefined), obj)
}
function setPath(obj, path, value) {
  const copy = structuredClone(obj)
  const keys = path.split('.')
  let cur = copy
  keys.slice(0, -1).forEach((k) => { if (cur[k] === undefined || cur[k] === null) cur[k] = {}; cur = cur[k] })
  cur[keys[keys.length - 1]] = value
  return copy
}

function JsonField({ label, value, onChange, rows = 10 }) {
  const [text, setText] = useState(JSON.stringify(value ?? null, null, 2))
  const [err, setErr] = useState(null)
  useEffect(() => { setText(JSON.stringify(value ?? null, null, 2)) }, [value])
  return (
    <div className="col">
      <h4>{label}</h4>
      <textarea rows={rows} value={text} onChange={(e) => {
        setText(e.target.value)
        try { onChange(JSON.parse(e.target.value)); setErr(null) } catch (ex) { setErr(ex.message) }
      }} />
      {err ? <div className="small" style={{ color: 'var(--bad)' }}>JSON inválido: {err}</div> : null}
    </div>
  )
}

function RulesEditor({ label, rules, onChange, personas }) {
  const list = rules || []
  const upd = (i, k, v) => onChange(list.map((r, j) => (j === i ? { ...r, [k]: v } : r)))
  return (
    <div className="panel panel-pad">
      <div className="row mb">
        <h4>{label} ({list.length})</h4>
        <button className="btn sm right" onClick={() => onChange([...list, { id: `NOVA-${list.length + 1}`, descricao: 'Nova regra', expressao: 'True', tipo: 'BLOQUEANTE', explicacao_falha: '' }])}>Adicionar regra</button>
      </div>
      {list.map((r, i) => (
        <div key={i} className="panel panel-pad mb" style={{ background: 'var(--panel-2)' }}>
          <div className="form-grid">
            <label className="field">Id<input value={r.id || ''} onChange={(e) => upd(i, 'id', e.target.value)} /></label>
            <label className="field">Tipo<select value={r.tipo || 'BLOQUEANTE'} onChange={(e) => upd(i, 'tipo', e.target.value)}>
              <option>BLOQUEANTE</option><option>EXCECIONAVEL</option><option>ALERTA</option></select></label>
            <label className="field">Base legal<input value={r.base_legal || ''} onChange={(e) => upd(i, 'base_legal', e.target.value)} /></label>
            {r.tipo === 'EXCECIONAVEL' ? (
              <label className="field">Aprovadores<select multiple value={r.aprovadores || []} onChange={(e) => upd(i, 'aprovadores', [...e.target.selectedOptions].map((o) => o.value))} style={{ height: 70 }}>
                {Object.keys(personas).map((p) => <option key={p}>{p}</option>)}</select></label>
            ) : null}
          </div>
          <label className="field mt">Descrição<input value={r.descricao || ''} onChange={(e) => upd(i, 'descricao', e.target.value)} /></label>
          <label className="field mt">Expressão (deve ser verdadeira para atender)<input className="mono" value={r.expressao || ''} onChange={(e) => upd(i, 'expressao', e.target.value)} /></label>
          <label className="field mt">Explicação quando falha (use {'{expressão}'} para valores)<input value={r.explicacao_falha || ''} onChange={(e) => upd(i, 'explicacao_falha', e.target.value)} /></label>
          <div className="row mt"><button className="btn sm danger right" onClick={() => onChange(list.filter((_, j) => j !== i))}>Remover regra</button></div>
        </div>
      ))}
      {!list.length ? <div className="small muted">Nenhuma regra.</div> : null}
    </div>
  )
}

function OpsEditor({ ops, onChange, shelf }) {
  const list = ops || []
  const upd = (i, k, v) => onChange(list.map((r, j) => (j === i ? { ...r, [k]: v } : r)))
  return (
    <div className="panel panel-pad">
      <div className="row mb">
        <h4>Operações da prateleira ({list.length})</h4>
        <button className="btn sm right" onClick={() => onChange([...list, { operacao: 'NOTIFICAR', parametros: { destinatarios: ['GESTOR'], assunto: 'Comunicado' }, motivo: 'Nova operação' }])}>Adicionar operação</button>
      </div>
      <p className="small muted">Operações explícitas do processo. Além delas, se "derivar estado alvo" estiver ligado, o planejador inclui as operações necessárias para chegar ao estado alvo do contrato do cargo. Parâmetros que começam com "=" são expressões.</p>
      {list.map((o, i) => {
        const spec = shelf.find((s) => s.codigo === o.operacao)
        return (
          <div key={i} className="panel panel-pad mb" style={{ background: 'var(--panel-2)' }}>
            <div className="form-grid">
              <label className="field">Operação<select value={o.operacao} onChange={(e) => upd(i, 'operacao', e.target.value)}>
                {shelf.map((s) => <option key={s.codigo} value={s.codigo}>{s.codigo} ({s.sistema})</option>)}</select></label>
              <label className="field">Base legal<input value={o.base_legal || ''} onChange={(e) => upd(i, 'base_legal', e.target.value)} /></label>
            </div>
            {spec ? <div className="small muted mt">{spec.descricao} Parâmetros: {spec.parametros.map((p) => `${p.nome}${p.obrigatorio ? '*' : ''}`).join(', ')}</div> : null}
            <label className="field mt">Quando (condição opcional)<input className="mono" value={o.quando || ''} onChange={(e) => upd(i, 'quando', e.target.value || undefined)} /></label>
            <label className="field mt">Motivo (aparece na explicação do plano)<input value={o.motivo || ''} onChange={(e) => upd(i, 'motivo', e.target.value)} /></label>
            <div className="mt"><JsonField label="Parâmetros" value={o.parametros || {}} onChange={(v) => upd(i, 'parametros', v)} rows={4} /></div>
            <div className="row mt">
              <button className="btn sm" disabled={i === 0} onClick={() => { const l = [...list]; [l[i - 1], l[i]] = [l[i], l[i - 1]]; onChange(l) }}>Subir</button>
              <button className="btn sm danger right" onClick={() => onChange(list.filter((_, j) => j !== i))}>Remover operação</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function Contracts() {
  const { meta, toast } = useApp()
  const [list, setList] = useState([])
  const [sel, setSel] = useState(null)
  const [doc, setDoc] = useState(null)
  const [yaml, setYaml] = useState('')
  const [tab, setTab] = useState('estruturado')
  const [problems, setProblems] = useState([])
  const [versao, setVersao] = useState(null)
  const [comment, setComment] = useState('')

  const loadList = useCallback(async () => setList(await api.get('/contracts')), [])
  useEffect(() => { loadList() }, [loadList])
  const open = useCallback(async (code, v) => {
    const d = await api.get(`/contracts/${code}${v ? `?versao=${v}` : ''}`)
    setSel(code); setDoc(d.contrato); setYaml(d.yaml); setVersao(d.contrato.versao); setProblems([])
  }, [])

  const save = async (nova) => {
    try {
      const body = tab === 'yaml' ? { yaml, nova_versao: nova, comentario: comment } : { contrato: doc, nova_versao: nova, comentario: comment }
      const saved = await api.post('/contracts', body)
      toast(`Contrato salvo como versão ${saved.versao}`)
      setComment('')
      await loadList(); await open(saved.codigo, saved.versao)
    } catch (e) { toast(e.message, 'bad'); setProblems(e.message.split('; ')) }
  }
  const check = async () => {
    const r = await api.post('/contracts/validate', tab === 'yaml' ? { yaml } : { contrato: doc })
    setProblems(r.problemas)
    toast(r.valido ? 'Contrato válido' : 'Contrato com problemas', r.valido ? '' : 'bad')
  }
  const syncTab = async (t) => {
    if (t === 'estruturado' && tab === 'yaml') {
      const r = await api.post('/contracts/validate', { yaml })
      if (r.contrato) setDoc(r.contrato)
    }
    if (t === 'yaml' && tab === 'estruturado') {
      const r = await api.post('/contracts/validate', { contrato: doc })
      setProblems(r.problemas)
      if (r.yaml) setYaml(r.yaml)
    }
    setTab(t)
  }
  const meta_ = list.find((c) => c.codigo === sel)
  const groups = ['NORMA', 'POLITICA', 'CARGO', 'PROCESSO']
  const up = (path) => (v) => setDoc((d) => setPath(d, path, v))

  return (
    <div>
      <div className="page-head">
        <div><h2>Contratos</h2><p>Normas, políticas, contratos de cargo (estado alvo e compliance) e contratos de processo (elegibilidade, orquestração e auditoria antes da execução). Toda alteração gera versão e entra no log.</p></div>
        <button className="btn right" onClick={async () => { await api.post('/contracts/reset'); toast('Contratos restaurados'); loadList(); setSel(null); setDoc(null) }}>Restaurar exemplos</button>
      </div>
      <div className="list-side">
        <div className="panel panel-pad" style={{ maxHeight: 'calc(100vh - 200px)', overflow: 'auto' }}>
          {groups.map((g) => (
            <div key={g} className="mb">
              <h4 className="mb">{KIND_LABEL[g]}</h4>
              {list.filter((c) => c.tipo === g).map((c) => (
                <div key={c.codigo} className={`side-item ${sel === c.codigo ? 'active' : ''}`} onClick={() => open(c.codigo)}>
                  <div className="row gap-s"><b className="ellipsis" style={{ maxWidth: 190 }}>{c.nome}</b><span className="right small muted">v{c.versao}</span></div>
                  <div className="small muted">{c.evento || c.cargo || c.codigo}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className="panel panel-pad">
          {!doc ? <Empty>Selecione um contrato.</Empty> : (
            <div className="col">
              <div className="row">
                <div><h2>{doc.nome}</h2><div className="small muted">{doc.codigo} · {doc.tipo}{doc.evento ? ` · evento ${doc.evento}` : ''}</div></div>
                <div className="right row">
                  <span className="small muted">Versão</span>
                  <select value={versao || ''} onChange={(e) => open(sel, e.target.value)}>
                    {(meta_?.versoes || []).map((v) => <option key={v.versao} value={v.versao}>v{v.versao} · {v.vigencia?.inicio} a {v.vigencia?.fim || 'indeterminado'} · {v.salvo_por}</option>)}
                  </select>
                </div>
              </div>
              {doc.aviso ? <div className="callout warn small">{doc.aviso}</div> : null}
              <Tabs value={tab} onChange={syncTab} tabs={[['estruturado', 'Editor estruturado'], ['yaml', 'YAML']]} />
              {tab === 'estruturado' ? (
                <div className="col">
                  <div className="form-grid">
                    <label className="field">Nome<input value={doc.nome || ''} onChange={(e) => setDoc({ ...doc, nome: e.target.value })} /></label>
                    <label className="field">Vigência início<input type="date" value={doc.vigencia?.inicio || ''} onChange={(e) => setDoc(setPath(doc, 'vigencia.inicio', e.target.value))} /></label>
                    <label className="field">Vigência fim<input type="date" value={doc.vigencia?.fim || ''} onChange={(e) => setDoc(setPath(doc, 'vigencia.fim', e.target.value || null))} /></label>
                  </div>
                  <label className="field">Descrição<input value={doc.descricao || ''} onChange={(e) => setDoc({ ...doc, descricao: e.target.value })} /></label>
                  {doc.tipo === 'NORMA' && <>
                    <JsonField label="Parâmetros (pisos, valores, prazos, sindicatos)" value={doc.parametros} onChange={up('parametros')} rows={14} />
                    <JsonField label="Benefícios garantidos pela norma" value={doc.beneficios} onChange={up('beneficios')} rows={10} />
                    <JsonField label="Estado alvo por situação do vínculo" value={doc.estado_por_situacao} onChange={up('estado_por_situacao')} rows={8} />
                    <RulesEditor label="Regras de compliance" rules={doc.compliance} onChange={up('compliance')} personas={meta.personas} />
                  </>}
                  {doc.tipo === 'POLITICA' && <JsonField label="Parâmetros da política" value={doc.parametros} onChange={up('parametros')} rows={20} />}
                  {doc.tipo === 'CARGO' && <>
                    <div className="form-grid">
                      <label className="field">Nível<input type="number" value={doc.nivel || 0} onChange={(e) => setDoc({ ...doc, nivel: Number(e.target.value) })} /></label>
                      <label className="field">Segmento<select value={doc.segmento} onChange={(e) => setDoc({ ...doc, segmento: e.target.value })}>{['OPERACIONAL', 'TECNICO', 'NEGOCIOS', 'MEDIA_GESTAO', 'EXECUTIVO'].map((s) => <option key={s}>{s}</option>)}</select></label>
                      <label className="check"><input type="checkbox" checked={!!doc.cargo_confianca} onChange={(e) => setDoc({ ...doc, cargo_confianca: e.target.checked })} /> cargo de confiança</label>
                    </div>
                    <JsonField label="Estado alvo (to-be): jornada, faixa, verbas, benefícios, acessos, equipamentos, cláusulas" value={doc.estado_alvo} onChange={up('estado_alvo')} rows={22} />
                    <RulesEditor label="Elegibilidade para entrar no cargo" rules={doc.elegibilidade_entrada} onChange={up('elegibilidade_entrada')} personas={meta.personas} />
                    <RulesEditor label="Compliance de quem ocupa o cargo" rules={doc.compliance} onChange={up('compliance')} personas={meta.personas} />
                  </>}
                  {doc.tipo === 'PROCESSO' && <>
                    {doc.coletivo ? <JsonField label="Evento coletivo: seleção e desdobramento" value={doc.coletivo} onChange={up('coletivo')} rows={8} /> : <>
                      <JsonField label="Esquema do evento" value={doc.evento_schema} onChange={up('evento_schema')} rows={5} />
                      <label className="field">Cargo alvo (expressão)<input className="mono" value={doc.cargo_alvo || ''} onChange={(e) => setDoc({ ...doc, cargo_alvo: e.target.value || undefined })} /></label>
                      <div className="row">
                        <label className="check"><input type="checkbox" checked={!!doc.elegibilidade?.incluir_entrada_cargo_alvo} onChange={(e) => setDoc(setPath(doc, 'elegibilidade.incluir_entrada_cargo_alvo', e.target.checked))} /> incluir elegibilidade de entrada do cargo alvo</label>
                        <label className="check"><input type="checkbox" checked={doc.orquestracao?.derivar_estado_alvo !== false} onChange={(e) => setDoc(setPath(doc, 'orquestracao.derivar_estado_alvo', e.target.checked))} /> derivar operações do estado alvo</label>
                        <label className="check"><input type="checkbox" checked={doc.auditoria?.incluir_compliance !== false} onChange={(e) => setDoc(setPath(doc, 'auditoria.incluir_compliance', e.target.checked))} /> auditoria inclui compliance</label>
                      </div>
                      <RulesEditor label="Elegibilidade" rules={doc.elegibilidade?.regras} onChange={up('elegibilidade.regras')} personas={meta.personas} />
                      <OpsEditor ops={doc.orquestracao?.operacoes} onChange={up('orquestracao.operacoes')} shelf={meta.prateleira} />
                      <RulesEditor label="Auditoria: regras do plano (antes da execução)" rules={doc.conferencia_plano?.regras} onChange={up('conferencia_plano.regras')} personas={meta.personas} />
                      <RulesEditor label="Auditoria: verificações do contrato de serviço (antes da execução)" rules={doc.auditoria?.verificacoes} onChange={up('auditoria.verificacoes')} personas={meta.personas} />
                    </>}
                  </>}
                </div>
              ) : (
                <textarea rows={36} value={yaml} onChange={(e) => setYaml(e.target.value)} />
              )}
              {problems.length ? <div className="callout bad small">{problems.map((p, i) => <div key={i}>{p}</div>)}</div> : null}
              <div className="row">
                <input placeholder="Comentário da alteração (vai para o log)" value={comment} onChange={(e) => setComment(e.target.value)} style={{ flex: 1 }} />
                <button className="btn" onClick={check}>Validar</button>
                <button className="btn" onClick={() => save(false)}>Sobrescrever v{versao}</button>
                <button className="btn primary" onClick={() => save(true)}>Salvar como nova versão</button>
              </div>
              <div className="small muted">Para mudar a vigência de uma regra a partir de uma data, salve uma nova versão com a nova data de início e feche a vigência da anterior. Eventos usam a versão vigente na data efetiva.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
