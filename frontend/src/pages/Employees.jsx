import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { Badge, Empty, Json, Modal, Status, Tabs, dateTime, money, time, useApp } from '../ui.jsx'

const CARGOS = ['ESCRITURARIO', 'CAIXA', 'ANALISTA_JR', 'ANALISTA_PL', 'ANALISTA_SR', 'GERENTE_RELACIONAMENTO', 'COORDENADOR', 'GERENTE_AGENCIA', 'SUPERINTENDENTE', 'DIRETOR']
const SITUACOES = ['ATIVO', 'AFASTADO', 'GARDEN_LEAVE', 'DESLIGADO']
const ESCOLARIDADE = ['FUNDAMENTAL', 'MEDIO', 'TECNICO', 'SUPERIOR_INCOMPLETO', 'SUPERIOR', 'POS_GRADUACAO', 'MESTRADO', 'DOUTORADO']
const ESTAB = ['GESTANTE', 'ACIDENTE_TRABALHO', 'CIPA', 'DIRIGENTE_SINDICAL', 'PRE_APOSENTADORIA']
const UFS = ['SP', 'RJ', 'ES', 'MG', 'RS', 'SC', 'PR', 'PE', 'BA', 'CE', 'DF', 'GO']

export function EventComposer({ initialType, colaboradorId, onClose }) {
  const { meta, hoje, toast, openCase } = useApp()
  const [tipo, setTipo] = useState(initialType || meta.tipos_evento[0]?.evento)
  const [dados, setDados] = useState('')
  const [colab, setColab] = useState(colaboradorId || '')
  const [dataEf, setDataEf] = useState(hoje)
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

const ESCOLARIDADE_LABEL = {
  FUNDAMENTAL: 'Ensino fundamental', MEDIO: 'Ensino médio', TECNICO: 'Curso técnico', SUPERIOR_INCOMPLETO: 'Superior incompleto',
  SUPERIOR: 'Ensino superior', POS_GRADUACAO: 'Pós-graduação', MESTRADO: 'Mestrado', DOUTORADO: 'Doutorado',
}
const REGIME_LABEL = { NORMAL_224: 'jornada bancária', CONFIANCA_224_2: 'cargo de confiança', GESTAO_62_II: 'cargo de gestão, sem controle de jornada' }
const SITUACAO_LABEL = { ATIVO: 'Ativo', AFASTADO: 'Afastado', GARDEN_LEAVE: 'Em garden leave', DESLIGADO: 'Desligado' }
const SITUACAO_TONE = { ATIVO: 'ok', AFASTADO: 'warn', GARDEN_LEAVE: 'violet', DESLIGADO: 'bad' }
const HIST_LABEL = { ADMISSAO: 'Admissão', CARGO: 'Mudança de cargo', LOTACAO: 'Mudança de lotação', SITUACAO: 'Situação', SINDICATO: 'Sindicato', PROGRAMA: 'Programa' }

const humanize = (code) => {
  const t = String(code || '').replace(/_/g, ' ').toLowerCase()
  return t.charAt(0).toUpperCase() + t.slice(1)
}
const fmtDate = (iso) => (iso ? String(iso).slice(0, 10).split('-').reverse().join('/') : '-')
function monthsBetween(from, to) {
  if (!from || !to) return 0
  const [a, b] = [new Date(`${String(from).slice(0, 10)}T00:00:00`), new Date(`${String(to).slice(0, 10)}T00:00:00`)]
  let m = (b.getFullYear() - a.getFullYear()) * 12 + (b.getMonth() - a.getMonth())
  if (b.getDate() < a.getDate()) m -= 1
  return Math.max(0, m)
}
function span(from, to) {
  const m = monthsBetween(from, to)
  const y = Math.floor(m / 12)
  const r = m % 12
  if (!y) return `${r} ${r === 1 ? 'mês' : 'meses'}`
  return `${y} ${y === 1 ? 'ano' : 'anos'}${r ? ` e ${r} ${r === 1 ? 'mês' : 'meses'}` : ''}`
}
function initials(nome) {
  const p = String(nome || '?').split(' ').filter(Boolean)
  return ((p[0]?.[0] || '') + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase()
}
function hue(text) {
  let h = 0
  for (const ch of String(text)) h = (h * 31 + ch.charCodeAt(0)) % 360
  return h
}

export function Avatar({ nome, size = 56 }) {
  return <div className="avatar" style={{ width: size, height: size, fontSize: size * 0.38, background: `hsl(${hue(nome)} 55% 45%)` }}>{initials(nome)}</div>
}

function PersonChip({ p, onSelect, note }) {
  return (
    <button className="person-chip" onClick={() => onSelect(p.id)} title={`${p.id} · ${p.unidade}`}>
      <Avatar nome={p.nome} size={28} />
      <span><b>{p.nome}</b><span className="small muted">{p.cargo_nome || humanize(p.cargo)}{note ? ` · ${note}` : ''}</span></span>
      {p.situacao && p.situacao !== 'ATIVO' ? <Badge tone={SITUACAO_TONE[p.situacao]}>{SITUACAO_LABEL[p.situacao]}</Badge> : null}
    </button>
  )
}

function Rating({ value }) {
  const v = Number(value) || 0
  return <span className="rating" title={`${v} de 5`}>{[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= v ? 'on' : ''} />)}<span className="small muted">{v} de 5</span></span>
}

// Career timeline: hires, position and unit changes, situation changes and salary history, newest first.
function careerTimeline(e, cargoNames) {
  const nomeCargo = (c) => cargoNames[c] || humanize(c)
  const items = []
  ;(e.historico || []).forEach((h) => {
    let texto = h.descricao
    if (h.tipo === 'CARGO') texto = String(h.descricao).replace(/[A-Z_]{4,}/g, (c) => nomeCargo(c))
    items.push({ data: h.data, titulo: HIST_LABEL[h.tipo] || humanize(h.tipo), texto })
  })
  ;(e.historico_salarial || []).forEach((h) => {
    if (!h.de) return
    const pct = h.de ? ((h.para / h.de - 1) * 100).toFixed(1).replace('.', ',') : null
    items.push({ data: h.data, titulo: 'Remuneração', texto: `Salário de ${money(h.de)} para ${money(h.para)}${pct ? ` (${pct}%)` : ''}, ${h.motivo}.` })
  })
  if (e.data_inicio_cargo && !items.some((i) => i.titulo === 'Mudança de cargo' && i.data === e.data_inicio_cargo) && e.data_inicio_cargo !== e.data_admissao) {
    items.push({ data: e.data_inicio_cargo, titulo: 'Cargo atual', texto: `Assumiu como ${nomeCargo(e.cargo)}.` })
  }
  if (e.data_inicio_unidade && e.data_inicio_unidade !== e.data_admissao && !items.some((i) => i.titulo === 'Mudança de lotação' && i.data === e.data_inicio_unidade)) {
    items.push({ data: e.data_inicio_unidade, titulo: 'Lotação atual', texto: `Chegou a ${e.unidade} (${e.cidade}/${e.uf}).` })
  }
  ;(e.historico_cargos || []).forEach((h) => {
    items.push({ data: h.inicio, titulo: 'Cargo anterior', texto: `${nomeCargo(h.cargo)} até ${fmtDate(h.fim)}.` })
  })
  return items.filter((i) => i.data).sort((a, b) => String(b.data).localeCompare(String(a.data)))
}

const PROGRAMA_STATUS = { ATIVO: ['ok', 'Vigente'], EXPIRADO: ['', 'Vencido'], ENCERRADO: ['warn', 'Encerrado antes do fim'] }

function remaining(dias) {
  if (dias === null || dias === undefined) return ''
  if (dias <= 0) return 'vence hoje'
  if (dias < 60) return `faltam ${dias} dia${dias === 1 ? '' : 's'}`
  const m = Math.floor(dias / 30.4)
  return `faltam cerca de ${m} meses`
}

// Programs with a validity period: what they grant, how much time is left and what the agenda will emit.
function Programs({ data }) {
  const progs = [...(data.programas || [])].sort((a, b) => (a.status === 'ATIVO' ? -1 : 1) - (b.status === 'ATIVO' ? -1 : 1) || String(b.inicio).localeCompare(String(a.inicio)))
  if (!progs.length) return null
  const agenda = data.agenda || []
  return (
    <section className="panel panel-pad">
      <h4 className="section-title">Programas com vigência</h4>
      {progs.map((p, i) => {
        const [tone, label] = PROGRAMA_STATUS[p.status] || ['', p.status]
        const total = Math.max(1, (new Date(`${p.fim}T00:00:00`) - new Date(`${p.inicio}T00:00:00`)) / 86400000)
        const pct = p.status === 'ATIVO' ? Math.min(100, Math.max(0, 100 - (p.dias_restantes / total) * 100)) : 100
        const conc = p.concessoes || {}
        const proximos = agenda.filter((a) => a.programa === p.codigo && p.status === 'ATIVO')
        return (
          <div key={i} className={`program ${p.status === 'ATIVO' ? 'active' : ''}`}>
            <div className="row">
              <b>{p.nome || humanize(p.codigo)}</b>
              <Badge tone={tone}>{label}</Badge>
              {p.status === 'ATIVO' ? <span className="small right">{remaining(p.dias_restantes)}</span> : null}
            </div>
            <div className="small muted">
              De {fmtDate(p.inicio)} a {fmtDate(p.fim)}
              {(p.renovacoes || []).length ? `, renovado ${p.renovacoes.length} vez(es)` : ''}
              {p.encerrado_em ? `; ${p.status === 'EXPIRADO' ? 'venceu' : 'encerrado'} em ${fmtDate(p.encerrado_em)}${p.motivo_encerramento ? ` (${p.motivo_encerramento})` : ''}` : ''}
            </div>
            {p.status === 'ATIVO' ? <div className="program-bar"><i style={{ width: `${pct}%` }} /></div> : null}
            <div className="mt-s">
              {(conc.verbas || []).map((v) => <span key={v.codigo} className="chip">{v.nome || humanize(v.codigo)} {money(v.valor)}</span>)}
              {(conc.beneficios || []).map((b) => <span key={b.codigo} className="chip">{b.nome || humanize(b.codigo)}</span>)}
              {(conc.acessos || []).map((a) => <span key={a} className="chip">{humanize(a)}</span>)}
            </div>
            {proximos.length ? (
              <div className="small mt-s">
                {proximos.map((a) => (
                  <div key={a.evento_id} className="muted">
                    {a.tipo === 'aviso' ? 'Aviso de vencimento' : 'Vencimento'} em {fmtDate(a.data)}{a.emitido ? ' (já emitido)' : ' (agendado)'}
                  </div>
                ))}
              </div>
            ) : null}
            {p.aviso_em && p.status === 'ATIVO' ? <div className="small muted">Aviso enviado em {fmtDate(p.aviso_em)}.</div> : null}
          </div>
        )
      })}
    </section>
  )
}

function Profile({ data, cargoNames, onSelect }) {
  const app = useApp()
  const e = data.colaborador
  const h = data.hierarquia || { cadeia: [], subordinados: [] }
  const hoje = data.hoje || app.hoje
  const conduta = e.conduta || {}
  const timeline = careerTimeline(e, cargoNames)
  const cadeia = [...(h.cadeia || [])].reverse()
  return (
    <div className="col">
      <div className="profile-grid">
        <div className="col">
          <section className="panel panel-pad">
            <h4 className="section-title">Trajetória</h4>
            <div className="career">
              {timeline.map((t, i) => (
                <div key={i} className="career-item">
                  <div className="when">{fmtDate(t.data)}</div>
                  <div><b>{t.titulo}</b><div className="small">{t.texto}</div></div>
                </div>
              ))}
              <div className="career-item first">
                <div className="when">{fmtDate(e.data_admissao)}</div>
                <div><b>Entrada no banco</b><div className="small">Admitido(a) há {span(e.data_admissao, hoje)}.</div></div>
              </div>
            </div>
          </section>
          <section className="panel panel-pad">
            <h4 className="section-title">Hierarquia</h4>
            {cadeia.length ? (
              <div className="chain">
                {cadeia.map((p, i) => <div key={p.id} className="chain-row" style={{ paddingLeft: i * 14 }}><PersonChip p={p} onSelect={onSelect} note={i === cadeia.length - 1 ? 'gestor imediato' : null} /></div>)}
                <div className="chain-row self" style={{ paddingLeft: cadeia.length * 14 }}>
                  <div className="person-chip current"><Avatar nome={e.nome} size={28} /><span><b>{e.nome}</b><span className="small muted">{data.cargo_contrato?.nome || humanize(e.cargo)}</span></span></div>
                </div>
              </div>
            ) : <div className="small muted">Topo da organização: não tem gestor imediato.</div>}
            <div className="small muted mt">{h.pares ? `${h.pares} colega(s) com o mesmo gestor.` : ''}</div>
            {h.subordinados?.length ? (
              <>
                <h4 className="mt mb">Equipe direta ({h.subordinados.length})</h4>
                <div className="reports">{h.subordinados.map((p) => <PersonChip key={p.id} p={p} onSelect={onSelect} />)}</div>
              </>
            ) : null}
          </section>
        </div>
        <div className="col">
          <Programs data={data} />
          <section className="panel panel-pad">
            <h4 className="section-title">Formação</h4>
            <div>{ESCOLARIDADE_LABEL[e.escolaridade] || humanize(e.escolaridade)}</div>
            <div className="mt">{(e.certificacoes || []).length ? e.certificacoes.map((c) => <span key={c} className="chip strong">{c}</span>) : <span className="small muted">Sem certificações registradas.</span>}</div>
            {(e.treinamentos || []).length ? <div className="small mt">Treinamentos: {e.treinamentos.map((t) => t.nome || t.codigo || t).join(', ')}</div> : null}
          </section>
          <section className="panel panel-pad">
            <h4 className="section-title">Desempenho e conduta</h4>
            <Rating value={e.avaliacao_desempenho} />
            <div className="small mt">
              {conduta.processo_disciplinar_aberto ? <div className="callout bad small mb-s">Processo disciplinar em aberto.</div> : null}
              {conduta.medida_restritiva_compliance ? <div className="callout bad small mb-s">Medida restritiva de compliance.</div> : null}
              {(conduta.advertencias || []).length ? (conduta.advertencias.map((a, i) => <div key={i} className="muted">Advertência em {fmtDate(a.data)}: {a.motivo}</div>))
                : (!conduta.processo_disciplinar_aberto && !conduta.medida_restritiva_compliance ? <span className="muted">Sem ocorrências de conduta.</span> : null)}
            </div>
          </section>
          <section className="panel panel-pad">
            <h4 className="section-title">Remuneração e benefícios</h4>
            <div className="big">{money(e.salario_base)} <span className="small muted">salário base</span></div>
            {(e.verbas || []).map((v, i) => <div key={i} className="small">{v.nome || humanize(v.codigo)}: {money(v.valor)}{v.recorrente === false ? ' (pontual)' : ''}</div>)}
            <div className="mt">{(e.beneficios || []).map((b) => <span key={b.codigo} className="chip" title={b.plano ? `Plano ${b.plano}` : ''}>{b.nome || humanize(b.codigo)}</span>)}</div>
          </section>
          <section className="panel panel-pad">
            <h4 className="section-title">Vida pessoal</h4>
            <div className="small">{e.data_nascimento ? `${span(e.data_nascimento, hoje).split(' e ')[0]} de idade` : ''}{e.cidade ? ` · mora em ${e.cidade}/${e.uf}` : ''}</div>
            {(e.dependentes || []).length ? e.dependentes.map((d, i) => (
              <div key={i} className="small">{d.nome} <span className="muted">({humanize(d.parentesco).toLowerCase()}, {span(d.data_nascimento, hoje).split(' e ')[0]})</span></div>
            )) : <div className="small muted">Sem dependentes registrados.</div>}
            {(e.estabilidades || []).length ? <div className="mt">{e.estabilidades.map((s, i) => <Badge key={i} tone="warn">Estabilidade: {humanize(s.tipo).toLowerCase()} até {fmtDate(s.fim)}</Badge>)}</div> : null}
          </section>
          <section className="panel panel-pad">
            <h4 className="section-title">Acessos e equipamentos</h4>
            <div>{(e.acessos || []).map((a) => <span key={a} className="chip">{humanize(a)}</span>)}</div>
            <div className="mt">{(e.equipamentos || []).map((a) => <span key={a} className="chip">{humanize(a)}</span>)}</div>
            {(e.clausulas || []).length ? <div className="small mt">Cláusulas: {e.clausulas.map((c) => c.nome || humanize(c.codigo)).join(', ')}</div> : null}
          </section>
        </div>
      </div>
    </div>
  )
}

function EmployeeView({ id, onChanged, onSelect, cargoNames }) {
  const { toast, openCase, meta, hoje, onLive } = useApp()
  const [data, setData] = useState(null)
  const [form, setForm] = useState(null)
  const [tab, setTab] = useState('perfil')
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
  const cargoNome = data.cargo_contrato?.nome || cargoNames[form.cargo] || form.cargo
  const gestor = (data.hierarquia?.cadeia || [])[0]
  return (
    <div className="col">
      <div className="profile-hero">
        <Avatar nome={form.nome} size={64} />
        <div className="hero-main">
          <h2>{form.nome}</h2>
          <div className="hero-role">{cargoNome} <span className="muted">em {form.unidade}, {form.cidade}/{form.uf}</span></div>
          <div className="hero-facts">
            <span><b>{span(form.data_admissao, hoje)}</b> de banco</span>
            <span><b>{span(form.data_inicio_cargo || form.data_admissao, hoje)}</b> no cargo</span>
            <span>{form.jornada_horas}h, {REGIME_LABEL[form.regime_jornada] || form.regime_jornada}</span>
            {gestor ? <span>reporta a <a onClick={() => onSelect(gestor.id)}>{gestor.nome}</a></span> : <span>topo da organização</span>}
          </div>
          <div className="row gap-s mt">
            <Badge tone={SITUACAO_TONE[form.situacao]}>{SITUACAO_LABEL[form.situacao] || form.situacao}</Badge>
            {(data.programas || []).filter((p) => p.status === 'ATIVO').map((p) => <Badge key={p.codigo} tone="info">{p.nome || humanize(p.codigo)} até {fmtDate(p.fim)}</Badge>)}
            {conf.conforme ? <Badge tone="ok">Conforme aos contratos</Badge> : <Badge tone="bad">{conf.falhas.length + conf.pendencias_estado_alvo.length} pendência(s) de conformidade</Badge>}
            <span className="small muted mono">{form.id} · versão {form.versao}</span>
          </div>
        </div>
        <div className="hero-actions">
          <button className="btn primary" onClick={() => setComposer(true)}>Disparar evento</button>
          <button className="btn" onClick={async () => {
            const c = await api.post('/events', { evento: { tipo: 'auditoria.conformidade_solicitada', colaborador_id: id, data_efetiva: hoje, origem: 'interface', dados: { motivo: 'Conferência manual' } } })
            openCase(c.id)
          }}>Conferir conformidade</button>
          <button className="btn ghost" onClick={async () => { try { await api.post(`/employees/${id}/drift`, {}); toast('Desvio injetado'); load() } catch (e) { toast(e.message, 'bad') } }}>Injetar desvio</button>
        </div>
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[['perfil', 'Perfil'], ['casos', `Casos (${data.casos.length})`], ['conformidade', `Conformidade${conf.conforme ? '' : ' (pendências)'}`],
        ['log', 'Trilha de alterações'], ['cadastro', 'Editar cadastro'], ['estado', 'Estado alvo'], ['json', 'JSON']]} />
      {tab === 'perfil' && <Profile data={data} cargoNames={cargoNames} onSelect={onSelect} />}
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
            <button className="btn sm" onClick={() => set('conduta', { ...conduta, advertencias: [...(conduta.advertencias || []), { data: hoje, motivo: 'Advertência registrada no laboratório' }] })}>Registrar advertência ({(conduta.advertencias || []).length})</button>
          </div>
          <div className="panel panel-pad">
            <div className="row mb"><h4>Estabilidades</h4>
              <select id="estab-add" defaultValue="GESTANTE">{ESTAB.map((e) => <option key={e}>{e}</option>)}</select>
              <button className="btn sm" onClick={() => {
                const tipo = document.getElementById('estab-add').value
                const fim = new Date(); fim.setMonth(fim.getMonth() + 12)
                set('estabilidades', [...(form.estabilidades || []), { tipo, inicio: hoje, fim: fim.toISOString().slice(0, 10) }])
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
              <button className="btn sm" onClick={() => set('dependentes', [...(form.dependentes || []), { nome: 'Novo dependente', parentesco: 'FILHO', data_nascimento: hoje }])}>Adicionar</button></div>
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
            <h4 className="mb">Atual (parâmetros do cadastro)</h4>
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
        <table className="tbl panel"><thead><tr><th>Caso</th><th>Evento</th><th>Situação</th><th>Resumo ou próximo passo</th></tr></thead>
          <tbody>{data.casos.map((c) => <tr key={c.id} className="click" onClick={() => openCase(c.id)}><td className="small mono">{c.id}</td><td>{meta.tipos_evento.find((t) => t.evento === c.evento_tipo)?.nome || c.evento_tipo}</td><td><Status value={c.status} /></td>
            <td className="small">{c.proximo_passo && !c.proximo_passo.encerrado ? <><b>Próximo passo:</b> {c.proximo_passo.texto}</> : c.resumo}</td></tr>)}</tbody></table>
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

// Org chart: indented, collapsible tree built from gestor_id. The path to the selected person is always open.
function OrgTree({ list, sel, onSelect, q }) {
  const byId = useMemo(() => Object.fromEntries(list.map((e) => [e.id, e])), [list])
  const children = useMemo(() => {
    const m = {}
    list.forEach((e) => {
      const g = e.gestor_id && byId[e.gestor_id] ? e.gestor_id : 'raiz'
      ;(m[g] = m[g] || []).push(e)
    })
    Object.values(m).forEach((arr) => arr.sort((a, b) => (b.nivel || 0) - (a.nivel || 0) || String(a.nome).localeCompare(String(b.nome))))
    return m
  }, [list, byId])
  const [open, setOpen] = useState(() => new Set())
  const roots = children.raiz || []
  useEffect(() => {
    // first load: show the board (top two levels) open
    if (!roots.length) return
    setOpen((prev) => (prev.size ? prev : new Set(roots.flatMap((r) => [r.id, ...(children[r.id] || []).map((k) => k.id)]))))
  }, [roots, children])
  useEffect(() => {
    if (!sel) return
    setOpen((prev) => {
      const next = new Set(prev)
      let cur = byId[sel]
      while (cur && cur.gestor_id && byId[cur.gestor_id]) { next.add(cur.gestor_id); cur = byId[cur.gestor_id] }
      return next
    })
  }, [sel, byId])
  const query = q.trim().toLowerCase()
  const matches = (e) => !query || `${e.nome} ${e.id} ${e.cargo_nome} ${e.unidade}`.toLowerCase().includes(query)
  const subtreeMatches = (e) => matches(e) || (children[e.id] || []).some(subtreeMatches)
  const toggle = (id) => setOpen((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  const node = (e, depth) => {
    if (!subtreeMatches(e)) return null
    const kids = children[e.id] || []
    const isOpen = open.has(e.id) || (query && kids.some(subtreeMatches))
    return (
      <div key={e.id} className="org-node" style={{ '--depth': depth }}>
        <div className={`org-row ${sel === e.id ? 'active' : ''} ${matches(e) ? '' : 'dim'}`}>
          {kids.length ? <button className="org-toggle" onClick={() => toggle(e.id)} title={isOpen ? 'Recolher equipe' : 'Abrir equipe'}>{isOpen ? '-' : '+'}</button> : <span className="org-toggle empty" />}
          <div className="org-card" onClick={() => onSelect(e.id)}>
            <Avatar nome={e.nome} size={26} />
            <div className="org-text">
              <div className="ellipsis"><b>{e.nome}</b></div>
              <div className="small muted ellipsis">{e.cargo_nome || e.cargo} · {e.unidade}</div>
            </div>
            <div className="org-side">
              {kids.length ? <span className="small muted">{kids.length}</span> : null}
              <span className={`dot-status ${e.conforme ? 'ok' : 'bad'}`} title={e.conforme ? 'conforme' : `${e.pendencias} pendência(s)`} />
            </div>
          </div>
        </div>
        {isOpen && kids.length ? <div className="org-children">{kids.map((k) => node(k, depth + 1))}</div> : null}
      </div>
    )
  }
  return <div className="org-tree">{roots.map((e) => node(e, 0))}</div>
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
  const [view, setView] = useState('organograma')
  const cargoNames = useMemo(() => Object.fromEntries(list.filter((e) => e.cargo_nome).map((e) => [e.cargo, e.cargo_nome])), [list])

  const load = useCallback(async () => setList(await api.get('/employees')), [])
  useEffect(() => { load() }, [load])
  useEffect(() => onLive((m) => { if (m.tipo === 'employees') load() }), [onLive, load])

  const shown = useMemo(() => list.filter((e) => (!cargo || e.cargo === cargo) && (!onlyBad || !e.conforme)
    && (!q || `${e.nome} ${e.id} ${e.cidade} ${e.cargo_nome} ${e.unidade}`.toLowerCase().includes(q.toLowerCase()))), [list, q, cargo, onlyBad])

  const generate = async () => {
    try {
      const r = await api.post('/employees/generate', { ...gen, tamanho: Number(gen.tamanho), semente: Number(gen.semente), desvio_percentual: Number(gen.desvio_percentual) })
      toast(`${r.gerados} colaboradores gerados`); setShowGen(false); setSel(null); load()
    } catch (e) { toast(e.message, 'bad') }
  }

  return (
    <div>
      <div className="page-head">
        <div><h2>Colaboradores</h2><p>Time artificial gerado a partir dos contratos de cargo, organizado em hierarquia (diretoria, superintendências, coordenações e agências), com desvios propositais para os agentes encontrarem.</p></div>
        <button className="btn primary right" onClick={() => setShowGen(true)}>Gerar novo time</button>
      </div>
      <div className="list-side">
        <div className="panel">
          <div className="panel-pad col" style={{ borderBottom: '1px solid var(--border)' }}>
            <div className="seg">
              <button className={view === 'organograma' ? 'active' : ''} onClick={() => setView('organograma')}>Organograma</button>
              <button className={view === 'lista' ? 'active' : ''} onClick={() => setView('lista')}>Lista</button>
            </div>
            <input placeholder="Buscar por nome, matrícula, cargo ou unidade" value={q} onChange={(e) => setQ(e.target.value)} />
            {view === 'lista' ? <div className="row">
              <select value={cargo} onChange={(e) => setCargo(e.target.value)} style={{ flex: 1 }}><option value="">Todos os cargos</option>{CARGOS.map((c) => <option key={c} value={c}>{cargoNames[c] || c}</option>)}</select>
              <label className="check small"><input type="checkbox" checked={onlyBad} onChange={(e) => setOnlyBad(e.target.checked)} /> pendências</label>
            </div> : null}
            <div className="small muted">{shown.length} de {list.length} · {list.filter((e) => !e.conforme).length} com pendências</div>
          </div>
          <div style={{ maxHeight: 'calc(100vh - 290px)', overflow: 'auto', padding: 6 }}>
            {view === 'organograma' ? <OrgTree list={list} sel={sel} onSelect={setSel} q={q} /> : shown.map((e) => (
              <div key={e.id} className={`side-item ${sel === e.id ? 'active' : ''}`} onClick={() => setSel(e.id)}>
                <div className="row gap-s"><Avatar nome={e.nome} size={22} /><b className="ellipsis" style={{ maxWidth: 150 }}>{e.nome}</b>
                  <span className="right">{e.conforme ? <Badge tone="ok">ok</Badge> : <Badge tone="bad">{e.pendencias}</Badge>}</span></div>
                <div className="small muted">{e.cargo_nome || e.cargo} · {e.unidade}{e.situacao !== 'ATIVO' ? ` · ${SITUACAO_LABEL[e.situacao] || e.situacao}` : ''}{(e.programas || []).length ? ` · em programa até ${fmtDate(e.programas[0].fim)}` : ''}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="panel panel-pad">{sel ? <EmployeeView key={sel} id={sel} onChanged={load} onSelect={setSel} cargoNames={cargoNames} /> : <Empty>Selecione um colaborador no organograma ou na lista para ver o perfil.</Empty>}</div>
      </div>
      {showGen ? (
        <Modal title="Gerar composição de time" onClose={() => setShowGen(false)} footer={<button className="btn primary" onClick={generate}>Gerar</button>}>
          <div className="form-grid">
            <label className="field">Tamanho<input type="number" value={gen.tamanho} onChange={(e) => setGen({ ...gen, tamanho: e.target.value })} /></label>
            <label className="field">Semente aleatória<input type="number" value={gen.semente} onChange={(e) => setGen({ ...gen, semente: e.target.value })} /></label>
            <label className="field">% com desvios<input type="number" value={gen.desvio_percentual} onChange={(e) => setGen({ ...gen, desvio_percentual: e.target.value })} /></label>
          </div>
          <label className="check mt"><input type="checkbox" checked={gen.substituir} onChange={(e) => setGen({ ...gen, substituir: e.target.checked })} /> substituir o time atual (senão, adiciona)</label>
          <p className="small muted">A organização tem diretoria, superintendências, coordenações na sede e agências em várias bases sindicais; cada pessoa tem um gestor imediato. A mesma semente gera o mesmo time.</p>
        </Modal>
      ) : null}
    </div>
  )
}
