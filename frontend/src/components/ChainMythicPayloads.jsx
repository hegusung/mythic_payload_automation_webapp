import { useState } from 'react'
import { api } from '../api/client'
import { showToast } from './Toast'
import DeployLog from './DeployLog'

function BuildPhaseBadge({ phase }) {
  const colors = {
    success: 'bg-green-900/40 text-green-300 border-green-700/40',
    error: 'bg-red-900/40 text-red-300 border-red-700/40',
    building: 'bg-yellow-900/40 text-yellow-300 border-yellow-700/40',
    queued: 'bg-blue-900/40 text-blue-300 border-blue-700/40',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${colors[phase] || 'bg-gray-700/40 text-gray-300 border-gray-600/40'}`}>
      {phase}
    </span>
  )
}

function CallbackRow({ cb }) {
  const lastSeen = cb.last_checkin
    ? new Date(cb.last_checkin + 'Z').toLocaleString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
    : '—'
  return (
    <div className={`flex items-center gap-3 text-xs px-3 py-1.5 rounded ${cb.active ? 'bg-green-900/10' : 'bg-gray-800/20'}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cb.active ? 'bg-green-400' : 'bg-gray-600'}`} />
      <span className="font-mono text-gray-300">{cb.host || '?'}</span>
      <span className="text-gray-500">{cb.user || '?'}</span>
      <span className="text-gray-600 ml-auto">last seen {lastSeen}</span>
    </div>
  )
}

function PayloadCard({ payload }) {
  const [expanded, setExpanded] = useState(false)
  const activeCallbacks = payload.callbacks.filter(c => c.active)

  const handleDownload = () => {
    if (!payload.agent_file_id) return
    const url = api.getPayloadDownloadUrl(payload.agent_file_id, payload.filename)
    const a = document.createElement('a')
    a.href = url
    a.download = payload.filename || payload.agent_file_id
    a.click()
  }

  const createdAt = payload.creation_time
    ? new Date(payload.creation_time + 'Z').toLocaleString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—'

  return (
    <div className="rounded-lg border border-gray-700/40 bg-gray-800/20 overflow-hidden">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-700/10 transition"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-sm text-blue-300 truncate">{payload.filename}</span>
            <BuildPhaseBadge phase={payload.build_phase} />
            {activeCallbacks.length > 0 && (
              <span className="px-2 py-0.5 rounded text-xs bg-green-900/30 text-green-400 border border-green-700/30">
                {activeCallbacks.length} callback{activeCallbacks.length !== 1 ? 's' : ''} actif{activeCallbacks.length !== 1 ? 's' : ''}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
            <span>{payload.payload_type}</span>
            <span>·</span>
            <span>{payload.os || '?'}</span>
            <span>·</span>
            <span>{createdAt}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {payload.agent_file_id && payload.build_phase === 'success' && (
            <button
              onClick={e => { e.stopPropagation(); handleDownload() }}
              className="px-2.5 py-1 rounded text-xs bg-blue-900/30 hover:bg-blue-800/50 text-blue-300 border border-blue-700/40 transition"
              title="Télécharger le payload"
            >
              ↓ Download
            </button>
          )}
          <span className="text-gray-600 text-xs">{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-700/30 px-4 py-3 space-y-3">
          {/* Hash info */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-gray-500">UUID</span>
              <div className="font-mono text-gray-300 text-xs break-all mt-0.5">{payload.uuid}</div>
            </div>
            {payload.md5 && (
              <div>
                <span className="text-gray-500">MD5</span>
                <div className="font-mono text-gray-400 text-xs mt-0.5">{payload.md5}</div>
              </div>
            )}
            {payload.sha1 && (
              <div className="col-span-2">
                <span className="text-gray-500">SHA1</span>
                <div className="font-mono text-gray-400 text-xs mt-0.5">{payload.sha1}</div>
              </div>
            )}
          </div>

          {/* Callbacks */}
          {payload.callbacks.length > 0 ? (
            <div>
              <div className="text-xs text-gray-500 mb-1.5">
                Callbacks ({payload.callbacks.length})
              </div>
              <div className="space-y-1">
                {payload.callbacks.map(cb => (
                  <CallbackRow key={cb.agent_callback_id} cb={cb} />
                ))}
              </div>
            </div>
          ) : (
            <div className="text-xs text-gray-600 italic">Aucun callback enregistré pour ce payload.</div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ChainMythicPayloads({ chainId, chainName }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [deploying, setDeploying] = useState(false)
  const [deployResult, setDeployResult] = useState(null)
  const [showDeployLog, setShowDeployLog] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteResult, setDeleteResult] = useState(null)

  const loadPayloads = async () => {
    setLoading(true)
    try {
      const result = await api.getChainPayloads(chainId)
      setData(result)
    } catch (e) {
      showToast(`Erreur: ${e.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleDeploy = () => {
    setDeployResult(null)
    setShowDeployLog(true)
    setDeploying(true)
  }

  const handleDelete = async () => {
    const count = data?.payloads?.length || '?'
    if (!confirm(`Supprimer ${count} payload(s) de la chaine "${chainName}" dans Mythic ?\nCette action est irréversible.`)) return
    setDeleting(true)
    setDeleteResult(null)
    try {
      const result = await api.deleteChainPayloads(chainId)
      setDeleteResult(result)
      showToast(result.message, result.errors?.length ? 'warning' : 'success')
      await loadPayloads()
    } catch (e) {
      showToast(`Échec de la suppression: ${e.message}`, 'error')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Deploy log modal */}
      {showDeployLog && (
        <DeployLog
          chainId={chainId}
          onDone={(result) => {
            setDeploying(false)
            if (result) {
              setDeployResult(result)
              showToast(`Déployé : ${result.stages?.length || 0} stage(s) créés.`, 'success')
              loadPayloads()
            } else {
              setDeployResult({ ok: false, error: 'Deploy failed — see log above.' })
            }
          }}
          onClose={() => setShowDeployLog(false)}
        />
      )}
      {/* Deploy result */}
      {deployResult && (
        <div className={`rounded-xl border px-5 py-4 ${deployResult.ok ? 'border-green-700/40 bg-green-900/10' : 'border-red-700/40 bg-red-900/10'}`}>
          <div className={`font-semibold text-sm mb-2 ${deployResult.ok ? 'text-green-300' : 'text-red-300'}`}>
            {deployResult.ok ? `✓ Déploiement réussi — ${deployResult.stages?.length || 0} stage(s)` : `✗ Échec du déploiement`}
          </div>
          {deployResult.stages?.map((stage, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-gray-400 mt-1">
              <span className={stage.status === 'success' ? 'text-green-400' : 'text-red-400'}>
                {stage.status === 'success' ? '✓' : '✗'}
              </span>
              <span className="font-mono">{stage.label}</span>
              {stage.mythic_uuid && (
                <span className="text-gray-600">uuid: {stage.mythic_uuid.slice(0, 8)}…</span>
              )}
              {stage.detail && <span className="text-gray-500">— {stage.detail}</span>}
            </div>
          ))}
          {deployResult.error && (
            <div className="text-xs text-red-300 mt-1">{deployResult.error}</div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={loadPayloads}
          disabled={loading}
          className="px-4 py-2 rounded-lg bg-gray-700/40 hover:bg-gray-600/40 text-gray-200 text-sm font-medium border border-gray-600/30 disabled:opacity-50 transition"
        >
          {loading ? '↻ Loading…' : '↻ View Mythic payloads'}
        </button>
        <button
          onClick={handleDeploy}
          disabled={deploying}
          className="px-4 py-2 rounded-lg bg-red-700/30 hover:bg-red-700/50 text-red-200 text-sm font-medium border border-red-700/40 disabled:opacity-50 transition"
        >
          {deploying ? '⚡ Deploying…' : '⚡ Deploy'}
        </button>
        {data?.payloads?.length > 0 && (
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="px-4 py-2 rounded-lg bg-gray-700/20 hover:bg-red-900/30 text-gray-500 hover:text-red-300 text-sm font-medium border border-gray-700/30 hover:border-red-700/40 disabled:opacity-50 transition"
          >
            {deleting ? '⌛ Suppression…' : '🗑 Supprimer de Mythic'}
          </button>
        )}
      </div>

      {/* Delete result */}
      {deleteResult && (
        <div className={`rounded-xl border px-5 py-3 text-sm ${
          deleteResult.errors?.length
            ? 'border-yellow-700/40 bg-yellow-900/10 text-yellow-300'
            : 'border-green-700/40 bg-green-900/10 text-green-300'
        }`}>
          <div className="font-semibold">{deleteResult.message}</div>
          {deleteResult.errors?.map((e, i) => (
            <div key={i} className="text-xs mt-1 text-red-400">✗ {e}</div>
          ))}
        </div>
      )}

      {/* Payloads list */}
      {data && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">
              {data.payloads.length === 0
                ? 'Aucun payload trouvé dans Mythic pour cette chaine.'
                : `${data.payloads.length} payload(s) trouvé(s) dans Mythic`}
              {data.mythic_tag && (
                <span className="ml-2 font-mono text-gray-600">[chain:{data.mythic_tag}]</span>
              )}
            </span>
          </div>

          {data.warnings?.map((w, i) => (
            <div key={i} className="text-xs text-yellow-400 bg-yellow-900/10 border border-yellow-700/30 rounded px-3 py-2">
              ⚠ {w}
            </div>
          ))}

          {data.payloads.map(p => (
            <PayloadCard key={p.uuid} payload={p} />
          ))}
        </div>
      )}
    </div>
  )
}
