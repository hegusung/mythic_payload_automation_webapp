import { useState, useRef, useEffect, useCallback } from 'react'

const LEVEL_STYLE = {
  info: 'text-gray-300',
  success: 'text-green-400',
  warning: 'text-yellow-400',
  error: 'text-red-400',
}

const LEVEL_PREFIX = {
  info: '  ',
  success: '✓ ',
  warning: '⚠ ',
  error: '✗ ',
}

/**
 * DeployLog — streams deploy progress via SSE.
 * Props:
 *   chainId: number
 *   onDone(result): called when deploy finishes (result = ApplyResult or null on error)
 *   onClose(): called when user dismisses the panel
 */
export default function DeployLog({ chainId, onDone, onClose }) {
  const [lines, setLines] = useState([])
  const [running, setRunning] = useState(true)
  const [failed, setFailed] = useState(false)
  const bottomRef = useRef(null)
  const esRef = useRef(null)

  const addLine = useCallback((level, msg) => {
    setLines(prev => [...prev, { level, msg, ts: Date.now() }])
  }, [])

  useEffect(() => {
    const es = new EventSource(`/api/chains/${chainId}/deploy/stream`)
    esRef.current = es

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        if (event.type === 'log' || event.type === 'stage_start' || event.type === 'stage_done') {
          addLine(event.level || 'info', event.msg)
        } else if (event.type === 'error') {
          addLine('error', event.msg)
          setRunning(false)
          setFailed(true)
          es.close()
          if (onDone) onDone(null)
        } else if (event.type === 'done') {
          setRunning(false)
          es.close()
          if (onDone) onDone(event.result)
        }
      } catch (_) {}
    }

    es.onerror = () => {
      addLine('error', 'Connection lost.')
      setRunning(false)
      setFailed(true)
      es.close()
    }

    return () => es.close()
  }, [chainId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl mx-4 rounded-xl border border-gray-700/50 bg-gray-900 shadow-2xl flex flex-col" style={{maxHeight: '80vh'}}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700/40">
          <div className="flex items-center gap-2">
            {running ? (
              <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
            ) : failed ? (
              <span className="inline-block w-2 h-2 rounded-full bg-red-400" />
            ) : (
              <span className="inline-block w-2 h-2 rounded-full bg-green-400" />
            )}
            <span className="text-sm font-semibold text-gray-100">
              {running ? 'Deploying…' : failed ? 'Deploy failed' : 'Deploy complete'}
            </span>
          </div>
          {!running && (
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-200 text-xs transition"
            >
              ✕ Close
            </button>
          )}
        </div>

        {/* Log */}
        <div className="flex-1 overflow-y-auto p-4 font-mono text-xs space-y-0.5 bg-gray-950/60">
          {lines.map((line, i) => (
            <div key={i} className={LEVEL_STYLE[line.level] || 'text-gray-300'}>
              {LEVEL_PREFIX[line.level] || ''}{line.msg}
            </div>
          ))}
          {running && (
            <div className="text-gray-600 animate-pulse">…</div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Footer */}
        {!running && (
          <div className="px-4 py-3 border-t border-gray-700/40 flex justify-end">
            <button
              onClick={onClose}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition ${
                failed
                  ? 'bg-red-700/30 hover:bg-red-700/50 text-red-200 border border-red-700/40'
                  : 'bg-green-700/30 hover:bg-green-700/50 text-green-200 border border-green-700/40'
              }`}
            >
              {failed ? 'Dismiss' : 'Done'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
