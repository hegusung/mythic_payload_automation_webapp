import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { showToast } from './Toast'

export default function Settings() {
  const [form, setForm] = useState({ mythic_url: '', mythic_username: '', mythic_password: '', payload_server_url: '', payload_server_token: '' })
  const [passwordSet, setPasswordSet] = useState(false)
  const [psTokenSet, setPsTokenSet] = useState(false)

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [savingPs, setSavingPs] = useState(false)
  const [testingPs, setTestingPs] = useState(false)
  const [testResultPs, setTestResultPs] = useState(null)

  useEffect(() => {
    api.getSettings()
      .then(data => {
        setForm({
          mythic_url: data.mythic_url || '',
          mythic_username: data.mythic_username || '',
          mythic_password: '',
          payload_server_url: data.payload_server_url || '',
          payload_server_token: '',
        })
        setPasswordSet(data.mythic_password_set || false)
        setPsTokenSet(data.payload_server_token_set || false)
      })
      .catch(e => showToast(`Failed to load settings: ${e.message}`, 'error'))
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = {
        mythic_url: form.mythic_url || null,
        mythic_username: form.mythic_username || null,
        mythic_password: form.mythic_password || null,
      }
      const data = await api.updateSettings(payload)
      setPasswordSet(data.mythic_password_set)
      setForm(f => ({ ...f, mythic_password: '' }))
      showToast('Mythic settings saved.', 'success')
    } catch (e) {
      showToast(`Save failed: ${e.message}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleSavePs = async () => {
    setSavingPs(true)
    try {
      const payload = {
        payload_server_url: form.payload_server_url || null,
        payload_server_token: form.payload_server_token || null,
      }
      const data = await api.updateSettings(payload)
      setPsTokenSet(data.payload_server_token_set)
      setForm(f => ({ ...f, payload_server_token: '' }))
      showToast('Payload server settings saved.', 'success')
    } catch (e) {
      showToast(`Save failed: ${e.message}`, 'error')
    } finally {
      setSavingPs(false)
    }
  }

  const handleTestPs = async () => {
    setTestingPs(true)
    setTestResultPs(null)
    try {
      const payload = {
        payload_server_url: form.payload_server_url || null,
        payload_server_token: form.payload_server_token || null,
      }
      const result = await api.testPayloadServer(payload)
      setTestResultPs(result)
      showToast(result.message, result.ok ? 'success' : 'error')
    } catch (e) {
      setTestResultPs({ ok: false, message: e.message })
      showToast(`Test failed: ${e.message}`, 'error')
    } finally {
      setTestingPs(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const payload = {
        mythic_url: form.mythic_url || null,
        mythic_username: form.mythic_username || null,
        mythic_password: form.mythic_password || null,
      }
      const result = await api.testConnection(payload)
      setTestResult(result)
      showToast(result.message, result.ok ? 'success' : 'error')
    } catch (e) {
      setTestResult({ ok: false, message: e.message })
      showToast(`Test failed: ${e.message}`, 'error')
    } finally {
      setTesting(false)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-40 text-gray-400">Loading settings...</div>
  )

  return (
    <div className="max-w-xl space-y-6">
      <div className="rounded-xl border border-gray-700/40 bg-gray-800/20 p-6 space-y-5">
        <h2 className="text-base font-semibold text-gray-200">Mythic C2 Connection</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
              Mythic URL
            </label>
            <input
              type="url"
              value={form.mythic_url}
              onChange={e => setForm(f => ({ ...f, mythic_url: e.target.value }))}
              placeholder="https://192.168.1.100:7443"
              className="w-full bg-gray-900/60 border border-gray-600/40 rounded-lg px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500/60 transition"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
              Username
            </label>
            <input
              type="text"
              value={form.mythic_username}
              onChange={e => setForm(f => ({ ...f, mythic_username: e.target.value }))}
              placeholder="mythic_admin"
              className="w-full bg-gray-900/60 border border-gray-600/40 rounded-lg px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500/60 transition"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
              Password {passwordSet && !form.mythic_password && (
                <span className="ml-2 text-xs text-green-500 font-normal normal-case">● saved</span>
              )}
            </label>
            <input
              type="password"
              value={form.mythic_password}
              onChange={e => setForm(f => ({ ...f, mythic_password: e.target.value }))}
              placeholder={passwordSet ? '(leave blank to keep current)' : 'Enter password'}
              className="w-full bg-gray-900/60 border border-gray-600/40 rounded-lg px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500/60 transition"
            />
          </div>
        </div>

        {testResult && (
          <div className={`rounded-lg px-4 py-3 text-sm border ${
            testResult.ok
              ? 'bg-green-900/20 border-green-700/40 text-green-300'
              : 'bg-red-900/20 border-red-700/40 text-red-300'
          }`}>
            <span className="font-semibold">{testResult.ok ? '✓ ' : '✗ '}</span>
            {testResult.message}
          </div>
        )}

        <div className="flex gap-3 pt-1">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed text-white text-sm font-medium transition"
          >
            {saving ? 'Saving…' : 'Save Settings'}
          </button>
          <button
            onClick={handleTest}
            disabled={testing}
            className="px-5 py-2.5 rounded-lg bg-gray-700/50 hover:bg-gray-600/50 disabled:opacity-50 disabled:cursor-not-allowed text-gray-200 text-sm font-medium border border-gray-600/40 transition"
          >
            {testing ? 'Testing…' : 'Test Connection'}
          </button>
        </div>
      </div>



      {/* Payload Server */}
      <div className="rounded-xl border border-gray-700/40 bg-gray-800/20 p-6 space-y-5">
        <div>
          <h2 className="text-base font-semibold text-gray-200">Payload Server</h2>
          <p className="text-xs text-gray-500 mt-1">
            Optional — if configured, downloader stages will upload payloads here instead of using Mythic's c2HostFile.
            Enables <code className="text-orange-300">downloader_contenttype</code> and <code className="text-orange-300">downloader_prepend</code> stage parameters.
          </p>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
              Server URL
            </label>
            <input
              type="url"
              value={form.payload_server_url}
              onChange={e => setForm(f => ({ ...f, payload_server_url: e.target.value }))}
              placeholder="http://192.168.1.100:8080"
              className="w-full bg-gray-900/60 border border-gray-600/40 rounded-lg px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-orange-500/60 transition"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
              Token {psTokenSet && !form.payload_server_token && (
                <span className="ml-2 text-xs text-green-500 font-normal normal-case">● saved</span>
              )}
            </label>
            <input
              type="password"
              value={form.payload_server_token}
              onChange={e => setForm(f => ({ ...f, payload_server_token: e.target.value }))}
              placeholder={psTokenSet ? '(leave blank to keep current)' : 'MGMT_TOKEN'}
              className="w-full bg-gray-900/60 border border-gray-600/40 rounded-lg px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-orange-500/60 transition"
            />
          </div>
        </div>

        {testResultPs && (
          <div className={`rounded-lg px-4 py-3 text-sm border ${
            testResultPs.ok
              ? 'bg-green-900/20 border-green-700/40 text-green-300'
              : 'bg-red-900/20 border-red-700/40 text-red-300'
          }`}>
            <span className="font-semibold">{testResultPs.ok ? '✓ ' : '✗ '}</span>
            {testResultPs.message}
          </div>
        )}

        <div className="flex gap-3 pt-1">
          <button
            onClick={handleSavePs}
            disabled={savingPs}
            className="px-5 py-2.5 rounded-lg bg-orange-700 hover:bg-orange-600 disabled:bg-orange-900 disabled:cursor-not-allowed text-white text-sm font-medium transition"
          >
            {savingPs ? 'Saving…' : 'Save Settings'}
          </button>
          <button
            onClick={handleTestPs}
            disabled={testingPs}
            className="px-5 py-2.5 rounded-lg bg-gray-700/50 hover:bg-gray-600/50 disabled:opacity-50 disabled:cursor-not-allowed text-gray-200 text-sm font-medium border border-gray-600/40 transition"
          >
            {testingPs ? 'Testing…' : 'Test Connection'}
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-gray-700/30 bg-gray-800/10 p-5 text-sm text-gray-400">
        <div className="font-semibold text-gray-300 mb-2">About Mythic integration</div>
        <ul className="space-y-1.5 list-disc list-inside">
          <li>Settings are stored in the local SQLite database</li>
          <li>The password is stored as plaintext — use a dedicated local account</li>
          <li>Default Mythic port: 7443 (HTTPS)</li>
        </ul>
      </div>
    </div>
  )
}
