import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { api, getPersona, setPersona as storePersona, subscribe } from './api.js'
import { AppCtx, Badge, useToasts } from './ui.jsx'
import Line from './pages/Line.jsx'
import CaseDetail from './pages/CaseDetail.jsx'
import Approvals from './pages/Approvals.jsx'
import Employees from './pages/Employees.jsx'
import Contracts from './pages/Contracts.jsx'
import Shelf from './pages/Shelf.jsx'
import Scenarios from './pages/Scenarios.jsx'
import Logs from './pages/Logs.jsx'
import Settings from './pages/Settings.jsx'
import Insights from './pages/Insights.jsx'
import Ask from './pages/Ask.jsx'
import Setup from './pages/Setup.jsx'
import Validity from './pages/Validity.jsx'
import Performance from './pages/Performance.jsx'
import { EXTERNAL, usd } from './pages/Spend.jsx'

const PAGES = [
  ['linha', 'Linha'],
  ['visao', 'Visão'],
  ['desempenho', 'Desempenho'],
  ['perguntar', 'Perguntar'],
  ['cenarios', 'Cenários'],
  ['aprovacoes', 'Aprovações'],
  ['colaboradores', 'Colaboradores'],
  ['vigencias', 'Vigências'],
  ['contratos', 'Contratos'],
  ['prateleira', 'Prateleira'],
  ['log', 'Log'],
  ['config', 'Configurações'],
]

const fmtIso = (iso) => (iso ? String(iso).slice(0, 10).split('-').reverse().join('/') : '')

export default function App() {
  const [meta, setMeta] = useState(null)
  const [page, setPage] = useState(() => (location.hash.slice(1) || 'linha'))
  const [persona, setPersonaState] = useState(getPersona())
  const [cases, setCases] = useState({})
  const [stats, setStats] = useState(null)
  const [openCase, setOpenCase] = useState(null)
  const [toast, toasts] = useToasts()
  const listeners = useRef(new Set())
  const [tick, setTick] = useState(0)
  // null: unknown yet; 'primeira': first run; 'reaberto': opened from Configurações
  const [setup, setSetup] = useState(null)

  const loadCases = useCallback(async () => {
    const list = await api.get('/cases?limit=400')
    const map = {}
    list.forEach((c) => { map[c.id] = c })
    setCases(map)
  }, [])

  const loadStats = useCallback(async () => {
    try { setStats(await api.get('/stats')) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    api.get('/meta').then(setMeta).catch((e) => toast(`Falha ao carregar: ${e.message}`, 'bad'))
    api.get('/setup').then((r) => setSetup(r.estado?.concluido ? false : 'primeira')).catch(() => setSetup(false))
    loadCases()
    loadStats()
    const unsub = subscribe((msg) => {
      if (msg.tipo === 'case') {
        setCases((prev) => ({ ...prev, [msg.case.id]: msg.case }))
      } else if (msg.tipo === 'reset') {
        loadCases()
      } else if (msg.tipo === 'clock') {
        loadStats()
      }
      listeners.current.forEach((fn) => fn(msg))
    })
    const iv = setInterval(() => { loadStats(); setTick((t) => t + 1) }, 3000)
    return () => { unsub(); clearInterval(iv) }
  }, [loadCases, loadStats, toast])

  useEffect(() => { location.hash = page }, [page])

  const onLive = useCallback((fn) => {
    listeners.current.add(fn)
    return () => listeners.current.delete(fn)
  }, [])

  const setPersona = (p) => { storePersona(p); setPersonaState(p) }

  const ctx = useMemo(() => ({
    meta, persona, setPersona, cases, stats, toast, onLive, openCase: setOpenCase, go: setPage, reloadCases: loadCases, reloadStats: loadStats, tick,
    openSetup: () => setSetup('reaberto'),
    // business date: the simulated clock when set, else the real calendar
    hoje: stats?.relogio?.hoje || meta?.hoje, relogio: stats?.relogio || meta?.relogio,
  }), [meta, persona, cases, stats, toast, onLive, loadCases, loadStats, tick])

  if (!meta || setup === null) return <div className="empty">Carregando laboratório...</div>
  const closeSetup = () => { setSetup(false); loadStats() }
  if (setup === 'primeira') return <AppCtx.Provider value={ctx}><Setup onDone={closeSetup} />{toasts}</AppCtx.Provider>
  const pending = stats?.aprovacoes_pendentes || 0
  const health = stats?.agente?.saude
  const paused = stats?.controle?.paused
  const relogio = stats?.relogio || meta.relogio
  const gastos = stats?.gastos
  const external = EXTERNAL.includes(health?.provedor) || EXTERNAL.includes(health?.provedor_embedding)
  const spendBlocked = gastos?.bloqueado && (external || gastos.bloqueio?.desde)

  const togglePause = async () => {
    await api.post('/control', { paused: !paused })
    loadStats()
  }

  return (
    <AppCtx.Provider value={ctx}>
      <div className="app">
        <header className="topbar">
          <div className="brand">
            <div className="logo">
              <svg width="16" height="16" viewBox="0 0 16 16"><path d="M2 12h12M2 8h8M2 4h5" stroke="var(--bg)" strokeWidth="2" /></svg>
            </div>
            <div>Novo RH <small>laboratório de eventos</small></div>
          </div>
          <nav className="nav">
            {PAGES.map(([k, label]) => (
              <button key={k} className={page === k ? 'active' : ''} onClick={() => setPage(k)}>
                {label}{k === 'aprovacoes' && pending ? <span className="count">{pending}</span> : null}
              </button>
            ))}
          </nav>
          <div className="spacer" />
          <button className={`btn sm clock-chip ${relogio?.simulado ? 'on' : ''}`} onClick={() => setPage('vigencias')}
            title={relogio?.simulado ? `Data simulada pelo relógio do laboratório; o calendário real está em ${fmtIso(relogio.data_real)}` : 'Data do calendário real'}>
            {fmtIso(relogio?.hoje || meta.hoje)}
          </button>
          {external && gastos ? (
            <button className={`btn sm spend-chip ${spendBlocked ? 'bad' : gastos.alerta ? 'warn' : ''}`} onClick={() => setPage('config')}
              title={`Gasto com LLM externa (${gastos.periodo_rotulo})${gastos.teto_usd > 0 ? ' e teto cadastrado' : ', sem teto'}`}>
              {usd(gastos.gasto_usd)}{gastos.teto_usd > 0 ? ` / ${usd(gastos.teto_usd)}` : ''}
            </button>
          ) : null}
          <span title={health?.ok ? (health.motor === 'jev' ? `Agente: JEV, ${health.jev?.modelo}` : `Agente: ${health.provedor_nome || 'Ollama'}, ${health.modelo}`) : (health?.erro || '')}>
            {health?.ok ? <Badge tone="ok">IA ok</Badge>
              : <Badge tone="warn">IA indisponível</Badge>}
          </span>
          <button className={`btn sm ${paused ? 'on' : ''}`} onClick={togglePause}>{paused ? 'Retomar linha' : 'Pausar linha'}</button>
          <label className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <select value={persona} onChange={(e) => setPersona(e.target.value)} style={{ width: 175 }} title="Persona: quem está usando a interface">
              {Object.entries(meta.personas).map(([k, p]) => <option key={k} value={k}>{p.nome} ({p.pessoa})</option>)}
            </select>
          </label>
        </header>
        {spendBlocked ? (
          <div className="spend-banner" role="alert">
            <b>Chamadas externas bloqueadas.</b>
            <span>{gastos.bloqueio?.mensagem || 'Nenhuma chamada nova é feita aos provedores externos.'}</span>
            <button className="btn sm" onClick={() => setPage('config')}>Ajustar teto</button>
          </div>
        ) : null}
        <main className="main">
          {page === 'linha' && <Line />}
          {page === 'visao' && <Insights />}
          {page === 'desempenho' && <Performance />}
          {page === 'perguntar' && <Ask />}
          {page === 'cenarios' && <Scenarios />}
          {page === 'aprovacoes' && <Approvals />}
          {page === 'colaboradores' && <Employees />}
          {page === 'vigencias' && <Validity />}
          {page === 'contratos' && <Contracts />}
          {page === 'prateleira' && <Shelf />}
          {page === 'log' && <Logs />}
          {page === 'config' && <Settings />}
        </main>
        {openCase ? <CaseDetail id={openCase} onClose={() => setOpenCase(null)} /> : null}
        {setup === 'reaberto' ? <Setup onDone={() => { closeSetup(); toast('Configuração salva e registrada no log') }} onCancel={() => setSetup(false)} /> : null}
        {toasts}
      </div>
    </AppCtx.Provider>
  )
}
