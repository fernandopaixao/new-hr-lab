let persona = localStorage.getItem('persona') || 'OPERADOR'

export function setPersona(p) {
  persona = p
  try { localStorage.setItem('persona', p) } catch { /* ignore */ }
}

export function getPersona() {
  return persona
}

async function request(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Persona': persona },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    const msg = (data && data.detail) ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : `Erro ${res.status}`
    throw new Error(msg)
  }
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b = {}) => request('POST', p, b),
  put: (p, b = {}) => request('PUT', p, b),
  del: (p) => request('DELETE', p),
}

export function subscribe(onMessage) {
  let es
  let closed = false
  const open = () => {
    es = new EventSource('/api/stream')
    es.onmessage = (ev) => {
      try { onMessage(JSON.parse(ev.data)) } catch { /* ignore */ }
    }
    es.onerror = () => {
      es.close()
      if (!closed) setTimeout(open, 2000)
    }
  }
  open()
  return () => { closed = true; es && es.close() }
}
