const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

function headers(body) {
  const h = {}
  if (body && typeof body === 'string') h['Content-Type'] = 'application/json'
  const token = localStorage.getItem('siq_token')
  if (token) h.Authorization = `Bearer ${token}`
  return h
}

export async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, { ...opts, headers: { ...headers(opts.body), ...opts.headers } })
  let data
  try {
    data = await r.json()
  } catch {
    data = {}
  }
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed')
  return data
}

export { API }
