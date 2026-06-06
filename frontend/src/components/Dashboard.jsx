import { useEffect, useState } from 'react'
import { api } from '../api/client'

function StatCard({ label, value, sub, color = 'blue' }) {
  const colors = {
    blue: 'from-blue-900/40 to-blue-800/20 border-blue-700/40',
    red: 'from-red-900/40 to-red-800/20 border-red-700/40',
    green: 'from-green-900/40 to-green-800/20 border-green-700/40',
    orange: 'from-orange-900/40 to-orange-800/20 border-orange-700/40',
    purple: 'from-purple-900/40 to-purple-800/20 border-purple-700/40',
  }
  return (
    <div className={`bg-gradient-to-br ${colors[color] || colors.blue} border rounded-xl p-5`}>
      <div className="text-3xl font-bold text-white">{value}</div>
      <div className="text-sm font-semibold text-gray-300 mt-1">{label}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  )
}

function StatusBadge({ running }) {
  if (running === null || running === undefined) return <span className="text-gray-500 text-xs">—</span>
  return running
    ? <span className="px-2 py-0.5 rounded text-xs bg-green-900/40 text-green-400 border border-green-700/40">running</span>
    : <span className="px-2 py-0.5 rounded text-xs bg-red-900/40 text-red-400 border border-red-700/40">stopped</span>
}

export default function Dashboard({ onGoToSettings }) {
  const [stats, setStats] = useState(null)
  const isNotConfigured = !stats || stats.source === 'not_configured' || stats.source === 'error'
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadStats = () => {
    setLoading(true)
    setError(null)
    api.getStats()
      .then(setStats)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadStats() }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <div className="text-center">
          <div className="text-2xl mb-2 animate-pulse">⟳</div>
          Loading stats from Mythic...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-700/40 bg-red-900/20 p-6 text-red-300">
        <div className="font-semibold mb-1">⚠ Failed to load stats</div>
        <div className="text-sm">{error}</div>
      </div>
    )
  }


  return (
    <div className="space-y-6">
      {/* Header with source badge + refresh */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded text-xs font-medium border ${
            isNotConfigured
              ? 'bg-yellow-900/30 text-yellow-400 border-yellow-700/40'
              : 'bg-green-900/30 text-green-400 border-green-700/40'
          }`}>
            {'✓ Live from Mythic'}
          </span>
          {stats?.payload_types?.length > 0 && (
            <span className="text-xs text-gray-500">{stats.payload_types.length} payload type{stats.payload_types.length !== 1 ? 's' : ''}</span>
          )}
        </div>
        <button
          onClick={loadStats}
          className="px-3 py-1.5 rounded-lg bg-gray-700/30 hover:bg-gray-600/30 text-gray-400 hover:text-gray-200 text-xs border border-gray-600/30 transition"
        >
          ↻ Refresh
        </button>
      </div>
      {isNotConfigured && (
        <div className="flex items-center justify-between rounded-xl border border-yellow-700/40 bg-yellow-900/20 px-5 py-4">
          <div>
            <div className="font-semibold text-yellow-300">Mythic not connected</div>

          </div>
          <div className="flex gap-2 ml-4 shrink-0">
            <button
              onClick={loadStats}
              className="px-3 py-2 rounded-lg bg-yellow-800/30 hover:bg-yellow-700/40 text-yellow-300 text-sm font-medium transition"
            >
              ↻ Refresh
            </button>
            <button
              onClick={onGoToSettings}
              className="px-4 py-2 rounded-lg bg-yellow-700/40 hover:bg-yellow-700/60 text-yellow-200 text-sm font-medium transition"
            >
              Open Settings →
            </button>
          </div>
        </div>
      )}

      {stats?.warnings?.length > 0 && (
        <div className="rounded-xl border border-yellow-700/30 bg-yellow-900/10 px-5 py-3 text-yellow-400 text-sm space-y-1">
          {stats.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <StatCard label="Total Payload Types" value={stats?.total ?? '—'} color="blue" />
        <StatCard label="Base Payloads" value={stats?.base ?? '—'} color="purple" />
        <StatCard label="Wrappers" value={stats?.wrapper ?? '—'} color="orange" />
        <StatCard label="Containers Running" value={stats?.running ?? '—'} color="green" />
        <StatCard label="Containers Stopped" value={stats?.stopped ?? '—'} color="red" />
      </div>

      {/* OS distribution */}
      {stats?.os_distribution && Object.keys(stats.os_distribution).length > 0 && (
        <div className="rounded-xl border border-gray-700/40 bg-gray-800/20 p-5">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">OS Distribution</h3>
          <div className="flex flex-wrap gap-3">
            {Object.entries(stats.os_distribution).map(([os, count]) => (
              <div key={os} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-700/30 border border-gray-600/30">
                <span className="text-sm text-gray-200 font-medium">{os}</span>
                <span className="text-xs text-gray-400 bg-gray-600/40 px-1.5 py-0.5 rounded">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Payload types table */}
      {stats?.payload_types?.length > 0 && (
        <div className="rounded-xl border border-gray-700/40 bg-gray-800/20 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-700/40">
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Payload Types</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 uppercase tracking-wider">
                  <th className="text-left px-5 py-3">Name</th>
                  <th className="text-left px-5 py-3">Type</th>
                  <th className="text-left px-5 py-3">OS</th>
                  <th className="text-left px-5 py-3">Container</th>
                  <th className="text-left px-5 py-3">Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/30">
                {stats.payload_types.map((pt, i) => (
                  <tr key={i} className="hover:bg-gray-700/10 transition">
                    <td className="px-5 py-3 font-mono text-blue-300">{pt.name}</td>
                    <td className="px-5 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        pt.stage_type === 'base'
                          ? 'bg-blue-900/40 text-blue-300 border border-blue-700/40'
                          : pt.stage_type === 'wrapper'
                          ? 'bg-purple-900/40 text-purple-300 border border-purple-700/40'
                          : 'bg-orange-900/40 text-orange-300 border border-orange-700/40'
                      }`}>{pt.stage_type}</span>
                    </td>
                    <td className="px-5 py-3 text-gray-300">
                      {pt.supported_os.join(', ') || '—'}
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge running={pt.container_running} />
                    </td>
                    <td className="px-5 py-3 text-gray-400 truncate max-w-xs" title={pt.description}>
                      {pt.description}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
