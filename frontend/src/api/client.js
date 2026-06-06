const BASE = '/api'

async function request(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body !== undefined) opts.body = JSON.stringify(body)
  const res = await fetch(`${BASE}${path}`, opts)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const data = await res.json()
      detail = data.detail || JSON.stringify(data)
    } catch (_) {}
    throw new Error(detail)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // Stats
  getStats: () => request('GET', '/stats'),

  // Settings
  getSettings: () => request('GET', '/settings'),
  updateSettings: (data) => request('PUT', '/settings', data),
  testConnection: (data) => request('POST', '/settings/test', data),
  testPayloadServer: (data) => request('POST', '/settings/test-payload-server', data),

  // Components / payload types
  getComponents: () => request('GET', '/components'),
  getC2Profiles: () => request('GET', '/c2profiles'),

  // Chains
  getChains: () => request('GET', '/chains'),
  createChain: (data) => request('POST', '/chains', data),
  updateChain: (id, data) => request('PUT', `/chains/${id}`, data),
  deleteChain: (id) => request('DELETE', `/chains/${id}`),

  // Import / validate

  validateChain: (data) => request('POST', '/validate', data),

  // File upload — store locally only, Mythic upload deferred to deploy
  uploadFileToMythic: async (file) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/files/local`, { method: 'POST', body: form })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try { const d = await res.json(); detail = d.detail || JSON.stringify(d) } catch (_) {}
      throw new Error(detail)
    }
    const data = await res.json()
    // Return in the same shape as before but use filename as the identifier
    return { file_id: data.filename, filename: data.filename, size: data.size }
  },

  // Deploy & live Mythic payloads
  deployChain: (id) => request('POST', `/chains/${id}/deploy`),
  getChainPayloads: (id) => request('GET', `/chains/${id}/payloads`),
  deleteChainPayloads: (id) => request('DELETE', `/chains/${id}/payloads`),
  getChainStatus: (id) => request('GET', `/chains/${id}/status`),

  // Download payload from Mythic
  getPayloadDownloadUrl: (agentFileId, filename) => `${BASE}/payloads/${agentFileId}/download${filename ? '?filename=' + encodeURIComponent(filename) : ''}`,

  // Samples
}
