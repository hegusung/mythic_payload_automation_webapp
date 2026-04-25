import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { showToast } from './Toast'
import DeployLog from './DeployLog'

function ChainCard({ chain, onOpen, onDelete, onDeploy, onExport }) {
  const [confirming, setConfirming] = useState(false)
  const [status, setStatus] = useState(null) // null = not loaded, {deployed, payload_count, active_callbacks}
  const [loadingStatus, setLoadingStatus] = useState(false)
  const [deploying, setDeploying] = useState(false)
  const [showDeployLog, setShowDeployLog] = useState(false)

  const stageCount = chain.graph?.nodes?.length ?? 0
  const createdAt = chain.created_at
    ? new Date(chain.created_at + 'Z').toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' })
    : '—'

  useEffect(() => {
    setLoadingStatus(true)
    api.getChainStatus(chain.id)
      .then(s => setStatus(s))
      .catch(() => {})
      .finally(() => setLoadingStatus(false))
  }, [chain.id])

  const handleQuickDeploy = () => {
    setShowDeployLog(true)
    setDeploying(true)
  }

  return (
    <>
    {showDeployLog && (
      <DeployLog
        chainId={chain.id}
        onDone={async (result) => {
          setDeploying(false)
          if (result) {
            showToast(`Déployé : ${result.stages?.length || 0} stage(s) créés.`, 'success')
            const s = await api.getChainStatus(chain.id)
            setStatus(s)
          }
        }}
        onClose={() => { setShowDeployLog(false); setDeploying(false) }}
      />
    )}
    <div className="rounded-xl border border-gray-700/40 bg-gray-800/20 hover:border-gray-600/50 transition p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-gray-100 truncate">{chain.name}</h3>
            {chain.mythic_tag && (
              <span className="px-2 py-0.5 rounded text-xs bg-red-900/30 text-red-300 border border-red-700/30 font-mono shrink-0">
                tag: {chain.mythic_tag}
              </span>
            )}
            {/* Deployed status badge */}
            {loadingStatus ? (
              <span className="px-2 py-0.5 rounded text-xs bg-gray-800/40 text-gray-600 border border-gray-700/30">...</span>
            ) : status ? (
              status.deployed ? (
                <span className="px-2 py-0.5 rounded text-xs bg-green-900/30 text-green-400 border border-green-700/30">
                  ✓ {status.payload_count} payload{status.payload_count !== 1 ? 's' : ''}
                  {status.active_callbacks > 0 && ` · ${status.active_callbacks} callback${status.active_callbacks !== 1 ? 's' : ''}`}
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded text-xs bg-gray-800/30 text-gray-600 border border-gray-700/20">not deployed</span>
              )
            ) : null}
          </div>
          {chain.description && (
            <p className="text-sm text-gray-400 mt-1 truncate">{chain.description}</p>
          )}
          <div className="flex items-center gap-3 mt-3 text-xs text-gray-500">
            <span>{stageCount} stage{stageCount !== 1 ? 's' : ''}</span>
            <span>·</span>
            <span>Created {createdAt}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => onOpen(chain)}
            className="px-3 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 text-xs font-medium border border-blue-700/30 transition"
          >
            Edit
          </button>
          <button
            onClick={() => onExport(chain)}
            className="px-3 py-1.5 rounded-lg bg-gray-700/20 hover:bg-gray-700/40 text-gray-300 text-xs font-medium border border-gray-600/30 transition"
            title="Export as ZIP"
          >
            📦 ZIP
          </button>
          <button
            onClick={handleQuickDeploy}
            disabled={deploying || stageCount === 0}
            className="px-3 py-1.5 rounded-lg bg-red-700/20 hover:bg-red-700/40 text-red-300 text-xs font-medium border border-red-700/30 disabled:opacity-30 disabled:cursor-not-allowed transition"
            title={stageCount === 0 ? 'No stages to deploy' : 'Deploy to Mythic'}
          >
            {deploying ? '⚡…' : '⚡ Deploy'}
          </button>
          {confirming ? (
            <div className="flex gap-1">
              <button
                onClick={() => { onDelete(chain.id); setConfirming(false) }}
                className="px-3 py-1.5 rounded-lg bg-red-600/30 hover:bg-red-600/50 text-red-300 text-xs font-medium border border-red-700/40 transition"
              >
                Confirm
              </button>
              <button
                onClick={() => setConfirming(false)}
                className="px-3 py-1.5 rounded-lg bg-gray-700/30 hover:bg-gray-700/50 text-gray-300 text-xs font-medium border border-gray-600/30 transition"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              className="px-3 py-1.5 rounded-lg bg-gray-700/30 hover:bg-red-900/30 text-gray-400 hover:text-red-300 text-xs font-medium border border-gray-600/30 hover:border-red-700/30 transition"
            >
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
    </>
  )
}

export default function ChainList({ onEdit, onNew }) {
  const [chains, setChains] = useState([])
  const [loading, setLoading] = useState(true)
  const zipImportRef = useRef(null)

  const loadChains = () => {
    setLoading(true)
    api.getChains()
      .then(setChains)
      .catch(e => showToast(`Failed to load chains: ${e.message}`, 'error'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadChains() }, [])

  const handleDelete = async (id) => {
    try {
      await api.deleteChain(id)
      setChains(prev => prev.filter(c => c.id !== id))
      showToast('Chain deleted.', 'success')
    } catch (e) {
      showToast(`Delete failed: ${e.message}`, 'error')
    }
  }

  const handleZipImport = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/chains/import', { method: 'POST', body: formData })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        showToast(`Import failed: ${err.detail || res.statusText}`, 'error')
        return
      }
      const result = await res.json()
      showToast(`Chain "${result.name}" imported!`, 'success')
      loadChains()
    } catch (e) {
      showToast(`Import failed: ${e.message}`, 'error')
    }
  }

  const handleZipExport = async (chain) => {
    try {
      const res = await fetch(`/api/chains/${chain.id}/export`)
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${chain.name.replace(/[^\w\-.]/g, '_')}.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      showToast(`Export failed: ${e.message}`, 'error')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-100">Chains</h2>
        <div className="flex gap-2">
          <button
            onClick={() => zipImportRef.current?.click()}
            className="px-4 py-2 rounded-lg bg-gray-700/40 hover:bg-gray-700/60 text-gray-200 text-sm font-medium border border-gray-600/30 transition"
            title="Import a chain from a ZIP file"
          >
            📥 Import ZIP
          </button>
          <input ref={zipImportRef} type="file" accept=".zip" className="hidden" onChange={handleZipImport} />

          <button
            onClick={() => onNew(null)}
            className="px-4 py-2 rounded-lg bg-red-700/30 hover:bg-red-700/50 text-red-200 text-sm font-medium border border-red-700/40 transition"
          >
            + New Chain
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">Loading chains…</div>
      ) : chains.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-gray-700/30 bg-gray-800/10">
          <div className="text-4xl mb-3">🔗</div>
          <div className="text-gray-400 font-medium">No chains yet</div>
          <div className="text-gray-500 text-sm mt-1">Create a new chain or import a YAML file</div>
          <button
            onClick={() => onNew(null)}
            className="mt-4 px-5 py-2 rounded-lg bg-red-700/30 hover:bg-red-700/50 text-red-200 text-sm font-medium border border-red-700/40 transition"
          >
            + New Chain
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {chains.map(chain => (
            <ChainCard
              key={chain.id}
              chain={chain}
              onOpen={onEdit}
              onDelete={handleDelete}
              onExport={handleZipExport}
            />
          ))}
        </div>
      )}
    </div>
  )
}
