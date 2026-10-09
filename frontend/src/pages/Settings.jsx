import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, Json, dateTime, useApp } from '../ui.jsx'

const FIELDS = [
  ['ollama_base_url', 'URL do Ollama', 'text', 'Local (http://host.docker.internal:11434), na rede (http://192.168.0.10:11434) ou o container (http://ollama:11434).'],
  ['ollama_model', 'Modelo', 'text', 'Recomendado: qwen2.5:7b. Modelos menores (qwen2.5:3b) respondem mais rápido.'],
  ['ollama_timeout_s', 'Tempo limite (s)', 'number', ''],
  ['ollama_num_ctx', 'Contexto (tokens)', 'number', 'Janela de contexto; 8192 cobre plano e contrato.'],
  ['ollama_num_predict', 'Máximo de tokens na resposta', 'number', ''],
  ['ollama_keep_alive', 'Manter modelo carregado', 'text', 'Evita recarregar o modelo entre casos (ex.: 30m).'],
  ['ollama_max_concurrency', 'Chamadas simultâneas por worker', 'number', 'Use 1 para GPU local; aumente para servidores na rede.'],
  ['ollama_temperature', 'Temperatura', 'number', '0 deixa as auditorias reprodutíveis.'],
  ['stage_delay_ms', 'Atraso visual por estágio (ms)', 'number', 'Deixa o movimento na linha observável. Use 0 em testes de estresse.'],
  ['failure_rate_percent', 'Falhas injetadas por operação (%)', 'number', 'Simula sistemas instáveis para exercitar a saga.'],
]

export default function Settings() {
  const { toast, stats, reloadStats } = useApp()
  const [vals, setVals] = useState(null)
  const [health, setHealth] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.get('/settings').then((r) => setVals(r.valores)); api.get('/agent/health').then(setHealth) }, [])
  if (!vals) return null
  const set = (k, v) => setVals({ ...vals, [k]: v })
  const save = async () => {
    try { setVals((await api.put('/settings', vals)).valores); toast('Configurações salvas e registradas no log') } catch (e) { toast(e.message, 'bad') }
  }
  const check = async () => { setHealth(await api.post('/agent/check')); reloadStats() }
  const pull = async (modelo) => {
    setBusy(true)
    try { await api.post('/agent/pull', modelo ? { modelo } : {}); toast(`Modelo ${modelo || vals.ollama_model} baixado`); check() } catch (e) { toast(e.message, 'bad') } finally { setBusy(false) }
  }
  return (
    <div>
      <div className="page-head"><div><h2>Configurações</h2><p>Parâmetros do agente de IA (Ollama) e do comportamento da linha. Alterações valem na hora e ficam no log.</p></div></div>
      <div className="grid2">
        <div className="panel panel-pad col">
          <h3>Agente de conferência</h3>
          <div className="form-grid">
            {FIELDS.slice(0, 8).map(([k, label, type, help]) => (
              <label key={k} className="field" title={help}>{label}<input type={type} value={vals[k]} onChange={(e) => set(k, type === 'number' ? Number(e.target.value) : e.target.value)} /></label>
            ))}
          </div>
          <label className="check"><input type="checkbox" checked={vals.heuristic_fallback_enabled} onChange={(e) => set('heuristic_fallback_enabled', e.target.checked)} />
            Usar agente simulado (heurístico) quando o Ollama estiver indisponível</label>
          <div className="small muted">Desligado (padrão): os casos param em "Aguardando agente de IA" e são retomados sozinhos quando o Ollama volta. Ligado: um agente heurístico responde, marcado como simulado em cada decisão.</div>
          <label className="check"><input type="checkbox" checked={vals.agent_cache_enabled} onChange={(e) => set('agent_cache_enabled', e.target.checked)} /> Reaproveitar respostas idênticas (cache)</label>
          <label className="field">Revisão humana
            <select value={vals.human_review_mode} onChange={(e) => set('human_review_mode', e.target.value)}>
              <option value="SE_REPROVADO">Somente quando o agente ou as regras reprovarem</option>
              <option value="SEMPRE">Sempre (todo plano e toda auditoria passam por uma pessoa)</option>
            </select>
          </label>
          <h3 className="mt">Embeddings e perguntas</h3>
          <div className="form-grid">
            <label className="field" title="Modelo do Ollama que gera os embeddings dos eventos. Trocar o modelo reindexa tudo.">Modelo de embedding
              <input value={vals.embedding_model} onChange={(e) => set('embedding_model', e.target.value)} /></label>
            <label className="field" title="Vazio usa o mesmo modelo do agente de conferência.">Modelo do agente de perguntas
              <input value={vals.ask_model} placeholder={vals.ollama_model} onChange={(e) => set('ask_model', e.target.value)} /></label>
            <label className="field" title="Quantos eventos parecidos entram como evidência em cada resposta.">Documentos por resposta
              <input type="number" value={vals.ask_top_k} onChange={(e) => set('ask_top_k', Number(e.target.value))} /></label>
          </div>
          <label className="check"><input type="checkbox" checked={vals.indexing_enabled} onChange={(e) => set('indexing_enabled', e.target.checked)} /> Indexar eventos continuamente</label>
          <div className="row"><button className="btn primary" onClick={save}>Salvar</button></div>
        </div>
        <div className="col">
          <div className="panel panel-pad col">
            <div className="row"><h3>Saúde do Ollama</h3><span className="right">{health?.ok ? <Badge tone="ok">disponível</Badge> : <Badge tone="bad">indisponível</Badge>}</span></div>
            <dl className="kv">
              <dt>URL</dt><dd className="mono">{health?.url}</dd>
              <dt>Modelo</dt><dd>{health?.modelo} {health?.modelo_disponivel ? <Badge tone="ok">instalado</Badge> : <Badge tone="warn">não instalado</Badge>}</dd>
              <dt>Embedding</dt><dd>{health?.modelo_embedding} {health?.modelo_embedding_disponivel ? <Badge tone="ok">instalado</Badge> : <Badge tone="warn">não instalado</Badge>}</dd>
              <dt>Modelos no servidor</dt><dd className="small">{(health?.modelos || []).join(', ') || '-'}</dd>
              <dt>Verificado</dt><dd>{dateTime(health?.verificado_em)}</dd>
              {health?.erro ? <><dt>Erro</dt><dd className="small" style={{ color: 'var(--bad)' }}>{health.erro}</dd></> : null}
            </dl>
            <div className="row">
              <button className="btn" onClick={check}>Verificar agora</button>
              <button className="btn" onClick={() => pull()} disabled={busy}>{busy ? 'Baixando...' : 'Baixar modelo do agente'}</button>
              <button className="btn" onClick={() => pull(vals.embedding_model)} disabled={busy}>Baixar modelo de embedding</button>
              <button className="btn" onClick={async () => { const r = await api.post('/agent/cache/clear'); toast(`${r.removidos} respostas removidas do cache`) }}>Limpar cache</button>
            </div>
            <div className="small muted">Estatísticas: {stats?.agente?.chamadas || 0} chamadas, média {stats?.agente?.duracao_media_ms ?? '-'} ms, recomendações {JSON.stringify(stats?.agente?.recomendacoes || {})}.</div>
          </div>
          <div className="panel panel-pad col">
            <h3>Linha de produção</h3>
            <div className="form-grid">
              {FIELDS.slice(8).map(([k, label, type, help]) => (
                <label key={k} className="field" title={help}>{label}<input type={type} value={vals[k]} onChange={(e) => set(k, Number(e.target.value))} /></label>
              ))}
            </div>
            <div className="row"><button className="btn primary" onClick={save}>Salvar</button></div>
          </div>
          <div className="panel panel-pad col">
            <h3>Reiniciar laboratório</h3>
            <p className="small muted">Limpa casos, aprovações, filas, log e embeddings. Opcionalmente gera um novo time.</p>
            <div className="row">
              <button className="btn danger" onClick={async () => { await api.post('/reset', {}); toast('Laboratório reiniciado'); reloadStats() }}>Limpar execução</button>
              <button className="btn danger" onClick={async () => { await api.post('/reset', { colaboradores: true }); toast('Laboratório reiniciado com novo time'); reloadStats() }}>Limpar e gerar novo time</button>
            </div>
          </div>
          <details><summary>Filas (Redis Streams)</summary><Json value={stats?.filas} /></details>
        </div>
      </div>
    </div>
  )
}
