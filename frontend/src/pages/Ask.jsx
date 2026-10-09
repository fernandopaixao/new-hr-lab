import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, Empty, Json, Tabs, dateTime, dur, useApp } from '../ui.jsx'

const SUGGESTIONS = [
  'Quantas promoções ficaram não elegíveis e por quê?',
  'Quais regras mais barraram eventos?',
  'O que aconteceu nos desligamentos de executivos?',
  'Quem aprovou exceções? Agrupe por persona.',
  'Qual estágio da linha está mais lento?',
  'Houve falha com compensação da saga? Explique.',
  'Casos por status na última hora',
  'Quais admissões foram rejeitadas na entrada?',
]

function linkify(text, openCase) {
  const parts = String(text || '').split(/(caso-[0-9a-f]{6,})/g)
  return parts.map((p, i) => (/^caso-[0-9a-f]{6,}$/.test(p) ? <a key={i} onClick={() => openCase(p)}>{p}</a> : <React.Fragment key={i}>{p}</React.Fragment>))
}

function Docs({ docs, openCase }) {
  if (!docs?.length) return <Empty>Nenhum documento recuperado.</Empty>
  return (
    <div className="col">
      {docs.map((d) => (
        <div key={d.id} className="doc">
          <div className="row small">
            <Badge tone={d.meta?.fonte === 'caso' ? 'accent' : 'violet'}>{d.meta?.fonte === 'caso' ? 'caso' : d.meta?.tipo || 'log'}</Badge>
            {d.meta?.case_id ? <a onClick={() => openCase(d.meta.case_id)}>{d.meta.case_id}</a> : <span className="mono">{d.id}</span>}
            {d.meta?.evento_tipo ? <span className="muted">{d.meta.evento_tipo}</span> : null}
            {d.meta?.colaborador_nome ? <span className="muted">{d.meta.colaborador_nome}</span> : null}
            <span className="score right" title="similaridade de cosseno mais bônus lexical">relevância {d.score}</span>
          </div>
          <pre>{d.texto}</pre>
        </div>
      ))}
    </div>
  )
}

function Answer({ a, openCase }) {
  const [tab, setTab] = useState('fontes')
  return (
    <div className="panel panel-pad col">
      <div className="row">
        <b>{a.pergunta}</b>
        <span className="right row small">
          {a.simulado ? <Badge tone="warn">agente simulado</Badge> : <Badge tone="ok">{a.rastro?.resposta?.modelo || 'Ollama'}</Badge>}
          <span className="muted">confiança {Math.round((a.confianca || 0) * 100)}% · {dur(a.duracao_ms)}</span>
        </span>
      </div>
      <div className="answer">{linkify(a.resposta, openCase)}</div>
      {a.limitacoes ? <div className="small muted"><b>Limitações:</b> {a.limitacoes}</div> : null}
      {a.citacoes_descartadas?.length ? <div className="small" style={{ color: 'var(--warn)' }}>Citações descartadas por não estarem nas evidências: {a.citacoes_descartadas.join(', ')}</div> : null}
      <Tabs value={tab} onChange={setTab} tabs={[['fontes', `Fontes (${a.documentos?.length || 0})`], ['numeros', 'Números exatos'], ['consulta', 'Como entendi a pergunta'], ['rastro', 'Rastro completo']]} />
      {tab === 'fontes' && <Docs docs={a.documentos} openCase={openCase} />}
      {tab === 'numeros' && (
        <div className="col">
          <div>{a.estatisticas.casos_que_atendem_aos_filtros} de {a.estatisticas.total_casos_no_laboratorio} casos atendem aos filtros.</div>
          {a.estatisticas.agrupamento ? (
            <table className="tbl"><thead><tr><th>{a.estatisticas.agrupamento.campo}</th><th>Casos</th></tr></thead>
              <tbody>{a.estatisticas.agrupamento.linhas.map((r) => <tr key={r.valor}><td>{r.rotulo}</td><td>{r.quantidade}</td></tr>)}</tbody></table>
          ) : null}
          <table className="tbl"><thead><tr><th>Situação</th><th>Casos</th></tr></thead>
            <tbody>{a.estatisticas.por_status.map((r) => <tr key={r.valor}><td>{r.rotulo}</td><td>{r.quantidade}</td></tr>)}</tbody></table>
          {a.estatisticas.tempo_por_estagio_ms ? <Json value={{ tempo_total_ms: a.estatisticas.tempo_total_ms, tempo_por_estagio_ms: a.estatisticas.tempo_por_estagio_ms, agente_ms: a.estatisticas.agente_ms }} /> : null}
          <h4>Casos mais recentes que atendem</h4>
          <table className="tbl"><tbody>{a.estatisticas.exemplos.map((e) => (
            <tr key={e.id} className="click" onClick={() => openCase(e.id)}><td className="mono small">{e.id}</td><td className="small">{e.evento_tipo}</td><td className="small">{e.colaborador}</td><td className="small">{e.explicacao}</td></tr>
          ))}</tbody></table>
        </div>
      )}
      {tab === 'consulta' && (
        <div className="col small">
          <div>Intenção: <b>{a.rastro.consulta.intencao}</b>{a.rastro.consulta.agrupar_por ? <> · agrupar por <b>{a.rastro.consulta.agrupar_por}</b></> : null}</div>
          <div>Filtros: {Object.keys(a.rastro.consulta.filtros).length ? Object.entries(a.rastro.consulta.filtros).map(([k, v]) => <span key={k} className="chip">{k} = {String(v)}</span>) : 'nenhum'}</div>
          <div>Busca semântica: "{a.rastro.consulta.consulta_semantica}"</div>
          <div className="muted">Interpretação feita por {a.rastro.interpretacao.agente}{a.rastro.interpretacao.modelo ? ` (${a.rastro.interpretacao.modelo}, ${dur(a.rastro.interpretacao.duracao_ms)})` : ''}{a.rastro.interpretacao.motivo ? `: ${a.rastro.interpretacao.motivo}` : ''}.</div>
          <div className="muted">Busca: modelo {a.rastro.busca?.modelo || '-'}, {a.rastro.busca?.candidatos ?? 0} candidatos, {dur(a.rastro.busca?.duracao_ms)}. {a.rastro.busca?.aviso || ''}</div>
        </div>
      )}
      {tab === 'rastro' && <Json value={a.rastro} max={480} />}
    </div>
  )
}

export default function Ask() {
  const { toast, openCase, onLive, persona } = useApp()
  const [tab, setTab] = useState('perguntar')
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [current, setCurrent] = useState(null)
  const [hist, setHist] = useState([])
  const [idx, setIdx] = useState(null)
  const [sq, setSq] = useState('')
  const [sfonte, setSfonte] = useState('')
  const [sres, setSres] = useState(null)

  const loadHist = useCallback(async () => setHist(await api.get('/ask/history?limite=30')), [])
  const loadIdx = useCallback(async () => setIdx(await api.get('/index/status')), [])
  useEffect(() => { loadHist(); loadIdx(); const t = setInterval(loadIdx, 4000); return () => clearInterval(t) }, [loadHist, loadIdx])
  useEffect(() => onLive((m) => { if (m.tipo === 'indice') loadIdx() }), [onLive, loadIdx])

  const send = async (text) => {
    const pergunta = (text ?? q).trim()
    if (!pergunta) return
    setQ(pergunta); setBusy(true)
    try { setCurrent(await api.post('/ask', { pergunta })); loadHist() } catch (e) { toast(e.message, 'bad') } finally { setBusy(false) }
  }
  const search = async () => {
    if (!sq.trim()) return
    try { setSres(await api.post('/search', { texto: sq, k: 12, filtros: sfonte ? { fonte: sfonte } : {} })) } catch (e) { toast(e.message, 'bad') }
  }

  return (
    <div>
      <div className="page-head">
        <div><h2>Perguntar aos eventos</h2><p>Agente de linguagem natural sobre todos os eventos do laboratório. Números exatos vêm das consultas; explicações vêm dos eventos mais parecidos, recuperados por embeddings. Toda resposta mostra as fontes.</p></div>
        <div className="right row small">
          <Badge tone={idx?.estado === 'EM_DIA' ? 'ok' : idx?.estado === 'AGUARDANDO_OLLAMA' || idx?.estado === 'ERRO' ? 'bad' : 'info'}>índice: {idx?.estado || '-'}</Badge>
          <span className="muted">{idx?.documentos ?? 0} docs · {idx?.pendentes ?? 0} na fila</span>
        </div>
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[['perguntar', 'Perguntar'], ['busca', 'Busca semântica'], ['historico', `Histórico (${hist.length})`]]} />
      {tab === 'perguntar' && (
        <div className="col">
          <div className="panel panel-pad col">
            <div className="ask-box">
              <textarea placeholder="Ex.: Por que as promoções para gerente foram barradas?" value={q} onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send() }} />
              <button className="btn primary" onClick={() => send()} disabled={busy}>{busy ? 'Pensando...' : 'Perguntar'}</button>
            </div>
            <div className="suggest">{SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} disabled={busy}>{s}</button>)}</div>
            <div className="small muted">Você pergunta como {persona}. Ctrl+Enter envia. Com o Ollama fora do ar a pergunta é recusada, a menos que o modo simulado esteja ligado nas configurações.</div>
          </div>
          {current ? <Answer a={current} openCase={openCase} /> : null}
        </div>
      )}
      {tab === 'busca' && (
        <div className="col">
          <div className="panel panel-pad row">
            <input style={{ flex: 1 }} placeholder="Descreva o que procura: ex. transferência sem anuência do empregado" value={sq} onChange={(e) => setSq(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') search() }} />
            <select value={sfonte} onChange={(e) => setSfonte(e.target.value)}><option value="">Casos e decisões</option><option value="caso">Só casos</option><option value="log">Só decisões do log</option></select>
            <button className="btn primary" onClick={search}>Buscar</button>
            <button className="btn" onClick={async () => { const r = await api.post('/index/rebuild', {}); toast(`${r.marcados} documentos marcados para reindexar`); loadIdx() }}>Reindexar tudo</button>
          </div>
          {sres ? (
            <div className="col">
              <div className="small muted">Modelo {sres.modelo}{sres.simulado ? ' (simulado)' : ''} · {sres.candidatos} candidatos · {dur(sres.duracao_ms)} {sres.aviso ? `· ${sres.aviso}` : ''}</div>
              <Docs docs={sres.resultados} openCase={openCase} />
            </div>
          ) : <Empty>A busca compara o significado do texto com o embedding de cada evento e de cada decisão registrada.</Empty>}
        </div>
      )}
      {tab === 'historico' && (
        <div className="col">
          {!hist.length ? <Empty>Nenhuma pergunta ainda.</Empty> : hist.map((h) => (
            <div key={h.id} className="panel panel-pad click" style={{ cursor: 'pointer' }} onClick={() => { setCurrent(h); setQ(h.pergunta); setTab('perguntar') }}>
              <div className="row"><b>{h.pergunta}</b><span className="right small muted">{h.persona} · {dateTime(h.criado_em)}</span></div>
              <div className="small muted">{(h.resposta || '').slice(0, 220)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
