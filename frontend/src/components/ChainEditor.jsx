import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { showToast } from './Toast'
import ChainMythicPayloads from './ChainMythicPayloads'

// ── Helpers ──────────────────────────────────────────────────────────────────

const uid = () => Math.random().toString(36).slice(2, 9)

function emptyNode() {
  return {
    id: uid(),
    type: 'default',
    position: { x: 0, y: 0 },
    data: {
      label: 'New Stage',
      payload: null,
      stage_type: 'base',
      os: 'Windows',
      parameters: {},
      commands: [],
      c2_profiles: [],
      wrapped_payload: null,
      downloaded_payload: null,
      c2_profile: null,
      profile_url: null,
      url_parameter: null,
    },
  }
}

function graphFromChain(chain) {
  if (!chain?.graph) {
    return { nodes: [], edges: [] }
  }
  return chain.graph
}

// ── Stage Card ────────────────────────────────────────────────────────────────

function CommandTag({ cmd, onRemove }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-gray-700/50 text-gray-300 border border-gray-600/30">
      {cmd}
      <button onClick={onRemove} className="text-gray-500 hover:text-red-400 ml-0.5">×</button>
    </span>
  )
}

// ── Typed Parameter Field ────────────────────────────────────────────────────

function TypedParamField({ name, value, meta, onChange, onRemove, displayName }) {
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const fileInputRef = useRef(null)

  const type = (meta?.parameter_type || 'String').toLowerCase()
  const choices = meta?.choices || []
  const required = meta?.required || false
  const description = meta?.description || ''

  const inputClass = 'flex-1 bg-gray-900/60 border border-gray-600/30 rounded px-2 py-1 text-xs text-gray-100 focus:outline-none focus:border-blue-500/60'

  let control
  if (type === 'boolean') {
    const checked = value === true || value === 'true' || value === 'True'
    control = (
      <button
        onClick={() => onChange(!checked)}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium border transition ${
          checked
            ? 'bg-green-900/30 border-green-700/40 text-green-300'
            : 'bg-gray-800/40 border-gray-600/30 text-gray-400'
        }`}
      >
        <span className={`w-3 h-3 rounded-full border ${ checked ? 'bg-green-400 border-green-400' : 'border-gray-500' }`} />
        {checked ? 'true' : 'false'}
      </button>
    )
  } else if (type === 'chooseone') {
    control = (
      <select
        value={value ?? ''}
        onChange={e => onChange(e.target.value)}
        className={inputClass}
      >
        {choices.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    )
  } else if (type === 'choosemultiple') {
    const selected = (() => {
      if (Array.isArray(value)) return value
      try { return JSON.parse(value || '[]') } catch { return [] }
    })()
    control = (
      <div className="flex flex-wrap gap-1 flex-1">
        {choices.map(c => {
          const active = selected.includes(c)
          return (
            <button
              key={c}
              onClick={() => {
                const next = active ? selected.filter(x => x !== c) : [...selected, c]
                onChange(JSON.stringify(next))
              }}
              className={`px-2 py-0.5 rounded text-xs border transition ${
                active
                  ? 'bg-blue-900/40 border-blue-700/40 text-blue-300'
                  : 'bg-gray-800/30 border-gray-600/30 text-gray-500 hover:text-gray-300'
              }`}
            >
              {c}
            </button>
          )
        })}
      </div>
    )
  } else if (type === 'number') {
    control = (
      <input
        type="number"
        value={value ?? ''}
        onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        className={inputClass}
      />
    )
  } else if (type === 'date') {
    // Mythic date = number of days from now
    control = (
      <div className="flex items-center gap-2 flex-1">
        <input
          type="number"
          value={value ?? ''}
          onChange={e => onChange(Number(e.target.value))}
          className="w-24 bg-gray-900/60 border border-gray-600/30 rounded px-2 py-1 text-xs text-gray-100 focus:outline-none focus:border-blue-500/60"
        />
        <span className="text-xs text-gray-600">days from now</span>
      </div>
    )
  } else if (type === 'file') {
    const handleFileUpload = async (e) => {
      const file = e.target.files?.[0]
      if (!file) return
      setUploading(true)
      setUploadError(null)
      try {
        const result = await api.uploadFileToMythic(file)
        onChange(result.file_id, result.filename)
      } catch (err) {
        setUploadError(err.message)
      } finally {
        setUploading(false)
        if (fileInputRef.current) fileInputRef.current.value = ''
      }
    }

    // Determine what label to show: prefer displayName, never show raw local:/UUID
    const isRef = value && (value.startsWith('local:') || /^[0-9a-f-]{36}$/i.test(value))
    const shownName = displayName || (isRef ? null : value)

    control = (
      <div className="flex-1 space-y-1.5">
        <div className="flex items-center gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="px-3 py-1 rounded text-xs font-medium bg-gray-700/40 hover:bg-gray-700/60 text-gray-300 border border-gray-600/40 disabled:opacity-50 transition shrink-0"
          >
            {uploading ? '↻ Saving…' : '📁 Select file'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileUpload}
          />
          {value ? (
            <span className={`text-xs truncate ${shownName ? 'text-green-400' : 'text-yellow-600 italic'}`} title={shownName || value}>
              📄 {shownName || 'Resolving…'}
            </span>
          ) : (
            <span className="text-xs text-gray-600 italic">No file selected</span>
          )}
          {value && (
            <button onClick={() => onChange('', null)} className="text-gray-600 hover:text-red-400 text-xs transition">✕</button>
          )}
        </div>
        {uploadError && (
          <div className="text-xs text-red-400">✗ {uploadError}</div>
        )}
      </div>
    )
  } else if (type === 'array') {
    control = (
      <input
        value={typeof value === 'string' ? value : JSON.stringify(value ?? [])}
        onChange={e => onChange(e.target.value)}
        placeholder='["value1", "value2"]'
        className={inputClass}
      />
    )
  } else {
    // String fallback
    control = (
      <input
        value={value ?? ''}
        onChange={e => onChange(e.target.value)}
        className={inputClass}
      />
    )
  }

  return (
    <div className="flex items-start gap-2">
      <div className="w-36 shrink-0 pt-1">
        <span className="font-mono text-xs text-blue-300 truncate block" title={name}>{name}</span>
        {meta && (
          <span className={`text-xs ${ required ? 'text-orange-400' : 'text-gray-600' }`}>
            {type}{required ? ' *' : ''}
          </span>
        )}
        {description && (
          <span className="text-xs text-gray-600 block truncate" title={description}>{description}</span>
        )}
      </div>
      {control}
      {onRemove && (
        <button onClick={onRemove} className="text-gray-600 hover:text-red-400 transition text-xs pt-1 shrink-0">✕</button>
      )}
    </div>
  )
}

function VariablesEditor({ variables, onChange }) {
  const [newKey, setNewKey] = useState('')
  const [newVal, setNewVal] = useState('')

  const add = () => {
    const k = newKey.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '_')
    if (!k) return
    onChange({ ...variables, [k]: newVal })
    setNewKey('')
    setNewVal('')
  }

  const remove = (k) => {
    const next = { ...variables }
    delete next[k]
    onChange(next)
  }

  const update = (k, v) => onChange({ ...variables, [k]: v })

  return (
    <div className="space-y-2">
      {Object.entries(variables).map(([k, v]) => (
        <div key={k} className="flex items-center gap-2">
          <code className="text-xs text-yellow-400 bg-gray-900/60 border border-gray-700/30 rounded px-2 py-1 min-w-[120px] font-mono shrink-0">{'{{'}{k}{'}}'}</code>
          <input
            value={v}
            onChange={e => update(k, e.target.value)}
            className="flex-1 bg-gray-900/60 border border-gray-600/30 rounded px-2 py-1 text-xs text-gray-100 font-mono focus:outline-none focus:border-yellow-500/60"
            placeholder="value"
          />
          <button onClick={() => remove(k)} className="text-gray-600 hover:text-red-400 text-xs transition">✕</button>
        </div>
      ))}
      <div className="flex items-center gap-2 mt-1">
        <input
          value={newKey}
          onChange={e => setNewKey(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && add()}
          placeholder="VAR_NAME"
          className="bg-gray-900/60 border border-gray-600/30 rounded px-2 py-1 text-xs text-yellow-400 font-mono focus:outline-none focus:border-yellow-500/60 w-32"
        />
        <input
          value={newVal}
          onChange={e => setNewVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && add()}
          placeholder="value"
          className="flex-1 bg-gray-900/60 border border-gray-600/30 rounded px-2 py-1 text-xs text-gray-300 font-mono focus:outline-none focus:border-yellow-500/60"
        />
        <button
          onClick={add}
          disabled={!newKey.trim()}
          className="px-2 py-1 rounded bg-yellow-700/30 hover:bg-yellow-700/50 text-yellow-300 text-xs border border-yellow-700/40 disabled:opacity-30 transition"
        >+ Add</button>
      </div>
    </div>
  )
}


function CommandsSection({ commands, availableCommands, onChange }) {
  const [cmdInput, setCmdInput] = useState('')
  const selected = new Set(commands)

  const toggle = (cmd) => {
    const next = new Set(selected)
    if (next.has(cmd)) next.delete(cmd)
    else next.add(cmd)
    onChange([...next].sort())
  }

  const selectAll = () => onChange(availableCommands.map(c => c.cmd).sort())
  const selectNone = () => onChange([])

  const addCustom = () => {
    if (!cmdInput.trim()) return
    const next = new Set(selected)
    next.add(cmdInput.trim())
    onChange([...next].sort())
    setCmdInput('')
  }

  const hasAvailable = availableCommands.length > 0

  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <label className="text-xs text-gray-500">Commands</label>
        <span className="text-xs text-gray-600">{selected.size} / {hasAvailable ? availableCommands.length : '?'} selected</span>
        {hasAvailable && (
          <>
            <button onClick={selectAll} className="text-xs text-blue-400 hover:text-blue-300">All</button>
            <button onClick={selectNone} className="text-xs text-gray-500 hover:text-gray-300">None</button>
          </>
        )}
      </div>

      {hasAvailable ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-1 max-h-56 overflow-y-auto pr-1 mb-2">
          {availableCommands.map(c => {
            const on = selected.has(c.cmd)
            return (
              <label
                key={c.cmd}
                title={[c.description, c.needs_admin ? '(needs admin)' : ''].filter(Boolean).join(' — ')}
                className={`flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer border transition text-xs ${
                  on
                    ? 'bg-blue-900/30 border-blue-700/40 text-blue-200'
                    : 'bg-gray-800/40 border-gray-700/20 text-gray-400 hover:border-gray-500/40'
                }`}
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => toggle(c.cmd)}
                  className="accent-blue-500 shrink-0"
                />
                <span className="font-mono truncate">{c.cmd}</span>
                {c.needs_admin && <span className="text-red-400 shrink-0" title="Needs admin">⚠️</span>}
              </label>
            )
          })}
        </div>
      ) : (
        // Fallback: Mythic not connected or commands not loaded — show tags
        <div className="flex flex-wrap gap-1.5 mb-2">
          {[...selected].map(cmd => (
            <CommandTag key={cmd} cmd={cmd} onRemove={() => {
              const next = new Set(selected)
              next.delete(cmd)
              onChange([...next])
            }} />
          ))}
        </div>
      )}

      {/* Custom command input (always shown) */}
      <div className="flex gap-2 mt-1">
        <input
          value={cmdInput}
          onChange={e => setCmdInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addCustom()}
          placeholder={hasAvailable ? 'Add unlisted command…' : 'Add command…'}
          className="flex-1 bg-gray-900/60 border border-gray-600/30 rounded px-2.5 py-1 text-xs text-gray-100 focus:outline-none focus:border-blue-500/60"
        />
        <button onClick={addCustom}
          className="px-3 py-1 rounded bg-gray-700/40 hover:bg-gray-600/40 text-gray-300 text-xs border border-gray-600/30 transition">
          Add
        </button>
      </div>
    </div>
  )
}


function ParametersSection({ parameters, buildParamsMeta, onChange, fileNames, onFileChange }) {
  const [newKey, setNewKey] = useState('')
  const [newVal, setNewVal] = useState('')

  const metaByName = Object.fromEntries((buildParamsMeta || []).map(m => [m.name, m]))
  const knownKeys = new Set((buildParamsMeta || []).map(m => m.name))

  // Split: known params (have metadata) vs extra params added manually
  const knownParams = (buildParamsMeta || []).filter(m => m.name in parameters)
  const extraParams = Object.entries(parameters).filter(([k]) => !knownKeys.has(k))
  const orphanCount = extraParams.filter(([k]) => !k.startsWith('downloader_')).length

  const syncWithMythic = () => {
    // Remove orphan params (not in Mythic meta, not downloader_* specials)
    const cleaned = Object.fromEntries(
      Object.entries(parameters).filter(([k]) => knownKeys.has(k) || k.startsWith('downloader_'))
    )
    onChange(cleaned)
  }
  // Known params not yet in parameters (available to add)
  const availableToAdd = (buildParamsMeta || []).filter(m => !(m.name in parameters))

  const updateParam = (key, val, filename) => {
    if (filename !== undefined && onFileChange) {
      onFileChange({ ...parameters, [key]: val }, { key, filename })
    } else {
      onChange({ ...parameters, [key]: val })
    }
  }
  const removeParam = (key) => { const p = { ...parameters }; delete p[key]; onChange(p) }

  const addManual = () => {
    if (!newKey.trim()) return
    onChange({ ...parameters, [newKey.trim()]: newVal })
    setNewKey(''); setNewVal('')
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs text-gray-500">Parameters</label>
        {orphanCount > 0 && (
          <button
            onClick={syncWithMythic}
            className="text-xs text-amber-400 hover:text-amber-300 border border-amber-700/40 hover:border-amber-500/60 rounded px-2 py-0.5 transition"
            title="Remove parameters that no longer exist in Mythic"
          >
            ⚠ Sync with Mythic ({orphanCount} orphan{orphanCount > 1 ? 's' : ''})
          </button>
        )}
      </div>
      <div className="space-y-2">
        {/* Known typed params */}
        {knownParams.map(meta => (
          <TypedParamField
            key={meta.name}
            name={meta.name}
            value={parameters[meta.name]}
            meta={meta}
            onChange={(val, filename) => updateParam(meta.name, val, filename)}
            onRemove={!meta.required ? () => removeParam(meta.name) : null}
            displayName={fileNames?.[meta.name]}
            onFileChange={onFileChange}
            paramKey={meta.name}
          />
        ))}

        {/* Extra / orphan params — split between downloader_* specials and unknown */}
        {extraParams.map(([key, val]) => {
          const isSpecial = key.startsWith('downloader_')
          return (
            <div key={key}>
              {!isSpecial && (
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className="text-xs text-amber-500/80 font-mono">⚠ not in Mythic</span>
                  <button
                    onClick={() => removeParam(key)}
                    className="text-xs text-red-500 hover:text-red-400 underline"
                  >remove</button>
                </div>
              )}
              <TypedParamField
                name={key}
                value={val}
                meta={null}
                onChange={(v, filename) => updateParam(key, v, filename)}
                onRemove={() => removeParam(key)}
                displayName={fileNames?.[key]}
                onFileChange={onFileChange}
                paramKey={key}
              />
            </div>
          )
        })}
      </div>

      {/* Add known param that was removed */}
      {availableToAdd.length > 0 && (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs text-gray-600">Add param:</span>
          <div className="flex flex-wrap gap-1">
            {availableToAdd.map(m => (
              <button
                key={m.name}
                onClick={() => updateParam(m.name, m.default_value_decoded ?? m.default_value ?? '')}
                className="px-2 py-0.5 rounded text-xs bg-gray-800/40 border border-gray-600/30 text-gray-500 hover:text-blue-300 hover:border-blue-700/40 transition"
              >
                + {m.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Manual key/val add */}
      <div className="flex gap-2 mt-2">
        <input
          value={newKey}
          onChange={e => setNewKey(e.target.value)}
          placeholder="custom key"
          className="w-28 bg-gray-900/60 border border-gray-600/30 rounded px-2 py-1 text-xs text-gray-100 focus:outline-none focus:border-blue-500/60 font-mono"
        />
        <input
          value={newVal}
          onChange={e => setNewVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addManual()}
          placeholder="value"
          className="flex-1 bg-gray-900/60 border border-gray-600/30 rounded px-2 py-1 text-xs text-gray-100 focus:outline-none focus:border-blue-500/60"
        />
        <button
          onClick={addManual}
          className="px-3 py-1 rounded bg-gray-700/40 hover:bg-gray-600/40 text-gray-300 text-xs border border-gray-600/30 transition"
        >+</button>
      </div>
    </div>
  )
}

// ── Stage Card ────────────────────────────────────────────────────────────────

function StageCard({ node, index, total, components, c2Profiles, allNodes, onChange, onRemove, onMoveUp, onMoveDown, payloadServerUrl }) {
  const [cmdInput, setCmdInput] = useState('')
  const [collapsed, setCollapsed] = useState(true)

  const d = node.data
  const comp = components.find(c => c.type === d.payload)
  const otherNodes = allNodes.filter(n => n.id !== node.id)

  const update = (patch) => onChange(node.id, { ...d, ...patch })

  const addCmd = () => {
    if (!cmdInput.trim()) return
    const cmds = [...new Set([...d.commands, cmdInput.trim()])]
    update({ commands: cmds })
    setCmdInput('')
  }

  const typeColors = {
    base: 'border-blue-700/40 bg-blue-900/10',
    wrapper: 'border-purple-700/40 bg-purple-900/10',
    downloader: 'border-orange-700/40 bg-orange-900/10',
  }

  const typeLabels = {
    base: '◉ Base',
    wrapper: '⬡ Wrapper',
    downloader: '↓ Downloader',
  }

  return (
    <div className={`rounded-xl border ${collapsed ? 'p-3' : 'p-5 space-y-4'} ${typeColors[d.stage_type] || typeColors.base}`}>
      {/* Header row — always visible */}
      <div className="flex items-center gap-3">
        {/* Move + index */}
        <div className="flex flex-col gap-1 shrink-0">
          <button onClick={onMoveUp} disabled={index === 0}
            className="w-6 h-6 flex items-center justify-center rounded text-gray-500 hover:text-gray-200 disabled:opacity-20 hover:bg-gray-700/40 transition text-xs"
          >▲</button>
          <span className="w-6 text-center text-xs text-gray-600 font-mono">{index + 1}</span>
          <button onClick={onMoveDown} disabled={index === total - 1}
            className="w-6 h-6 flex items-center justify-center rounded text-gray-500 hover:text-gray-200 disabled:opacity-20 hover:bg-gray-700/40 transition text-xs"
          >▼</button>
        </div>

        {/* Summary row (always visible) or full form (expanded) */}
        {collapsed ? (
          // ─ Collapsed summary
          <div
            className="flex-1 min-w-0 cursor-pointer"
            onClick={() => setCollapsed(false)}
          >
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-sm text-gray-100 font-medium truncate">{d.label || '(unnamed)'}</span>
              <span className={`px-2 py-0.5 rounded text-xs border font-medium ${
                d.stage_type === 'base' ? 'bg-blue-900/30 text-blue-300 border-blue-700/30' :
                d.stage_type === 'wrapper' ? 'bg-purple-900/30 text-purple-300 border-purple-700/30' :
                'bg-orange-900/30 text-orange-300 border-orange-700/30'
              }`}>{d.stage_type}</span>
              {d.payload && <span className="text-xs text-gray-500 font-mono">{d.payload}</span>}
              {d.os && <span className="text-xs text-gray-600">{d.os}</span>}
              {d.c2_profile && <span className="text-xs text-indigo-400 font-mono">{d.c2_profile}</span>}
            </div>
            {(comp?.description || comp?.note) && (
              <div className="text-xs text-gray-500 italic mt-0.5 truncate" title={[comp?.description, comp?.note].filter(Boolean).join(' — ')}>
                {comp?.note || comp?.description}
              </div>
            )}
          </div>
        ) : (
          // ─ Expanded form fields
          <div className="flex-1 min-w-0 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="lg:col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Stage name</label>
              <input
                value={d.label}
                onChange={e => update({ label: e.target.value })}
                placeholder="e.g. apollo.exe"
                className="w-full bg-gray-900/60 border border-gray-600/30 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500/60"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Type</label>
              <select
                value={d.stage_type}
                onChange={e => update({ stage_type: e.target.value, payload: null, wrapped_payload: null, downloaded_payload: null, c2_profile: null, c2_profiles: [], parameters: {}, commands: [] })}
                className="w-full bg-gray-900/60 border border-gray-600/30 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500/60"
              >
                <option value="base">Base</option>
                <option value="wrapper">Wrapper</option>
                <option value="downloader">Downloader</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">OS</label>
              <select
                value={d.os}
                onChange={e => update({ os: e.target.value })}
                className="w-full bg-gray-900/60 border border-gray-600/30 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500/60"
              >
                <option>Windows</option>
                <option>Linux</option>
                <option>macOS</option>
              </select>
            </div>
          </div>
        )}

        {/* Collapse + Remove buttons */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => setCollapsed(c => !c)}
            className="w-7 h-7 flex items-center justify-center rounded text-gray-500 hover:text-gray-200 hover:bg-gray-700/40 transition text-xs"
            title={collapsed ? 'Expand' : 'Collapse'}
          >{collapsed ? '▼' : '▲'}</button>
          <button
            onClick={onRemove}
            className="w-7 h-7 flex items-center justify-center rounded text-gray-600 hover:text-red-400 hover:bg-red-900/20 transition"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4" style={collapsed ? {display:'none'} : {}}>
        {/* Payload type */}
        <div>
          <label className="block text-xs text-gray-500 mb-1">Payload type</label>
          <select
            value={d.payload || ''}
            onChange={e => {
              const selected = components.find(c => c.type === e.target.value)
              const defaultProfileName = selected?.default_c2_profile?.c2_profile || null
              let defaultC2Profiles = []
              if (defaultProfileName && selected?.c2_profiles_metadata) {
                const profileMeta = selected.c2_profiles_metadata.find(m => m.name === defaultProfileName)
                const defaultParams = {}
                if (profileMeta) {
                  profileMeta.parameters.forEach(p => {
                    defaultParams[p.name] = p.default_value_decoded ?? p.default_value ?? ''
                  })
                }
                defaultC2Profiles = [{ c2_profile: defaultProfileName, c2_profile_parameters: defaultParams }]
              }
              // Auto-fill url_parameter from component metadata
              const autoUrlParam = selected?.url_parameter || null
              update({
                payload: e.target.value || null,
                parameters: selected?.default_parameters || {},
                commands: selected?.default_commands || [],
                c2_profile: defaultProfileName,
                c2_profiles: defaultC2Profiles,
                url_parameter: autoUrlParam,
              })
            }}
            className="w-full bg-gray-900/60 border border-gray-600/30 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500/60"
          >
            <option value="">— Select payload type —</option>
            {components.filter(c => {
              if (d.stage_type === 'base') return c.stage_type === 'base'
              if (d.stage_type === 'wrapper') return c.stage_type === 'wrapper'
              if (d.stage_type === 'downloader') return c.stage_type === 'downloader'
              return true
            }).map(c => (
              <option key={c.type} value={c.type}>{c.label || c.type}</option>
            ))}
          </select>
          {comp?.description && (
            <div className="text-xs text-blue-300/60 mt-1.5 italic leading-snug">{comp.description}</div>
          )}
          {comp?.note && (
            <div className="mt-1.5 text-xs text-gray-400 leading-relaxed border-l-2 border-gray-600/50 pl-2">{comp.note}</div>
          )}
        </div>

        {/* Wrapped/downloaded reference */}
        {(d.stage_type === 'wrapper' || d.stage_type === 'downloader') && (
          <div>
            <label className="block text-xs text-gray-500 mb-1">
              {d.stage_type === 'wrapper' ? 'Wraps payload' : 'Downloads payload'}
            </label>
            <select
              value={d.stage_type === 'wrapper' ? (d.wrapped_payload || '') : (d.downloaded_payload || '')}
              onChange={e => {
                const val = e.target.value || null
                if (d.stage_type === 'wrapper') update({ wrapped_payload: val })
                else update({ downloaded_payload: val })
              }}
              className="w-full bg-gray-900/60 border border-gray-600/30 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500/60"
            >
              <option value="">— Select stage —</option>
              {otherNodes.map(n => (
                <option key={n.id} value={n.data.label}>{n.data.label}</option>
              ))}
            </select>
          </div>
        )}

        {/* C2 profile selector (base only) */}
        {d.stage_type === 'base' && comp?.available_c2_profiles?.length > 0 && (
          <div>
            <label className="block text-xs text-gray-500 mb-1">C2 Profile</label>
            <select
              value={d.c2_profile || ''}
              onChange={e => {
                const profileName = e.target.value || null
                // Init c2_profiles with default params for this profile
                const profileMeta = comp.c2_profiles_metadata?.find(m => m.name === profileName)
                const defaultParams = {}
                if (profileMeta) {
                  profileMeta.parameters.forEach(p => {
                    defaultParams[p.name] = p.default_value_decoded ?? p.default_value ?? ''
                  })
                }
                update({
                  c2_profile: profileName,
                  c2_profiles: profileName ? [{ c2_profile: profileName, c2_profile_parameters: defaultParams }] : [],
                })
              }}
              className="w-full bg-gray-900/60 border border-gray-600/30 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500/60"
            >
              <option value="">— None —</option>
              {comp.available_c2_profiles.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        )}

        {/* Downloader config */}
        {d.stage_type === 'downloader' && (
          <>
            <div className="sm:col-span-2">
              <div className="rounded-lg border border-orange-700/30 bg-orange-900/10 px-3 py-2 text-xs text-orange-300">
                ⚡ <strong>Downloader</strong> : URL injectée dans
                {d.url_parameter && <code className="ml-1 text-orange-200 bg-orange-900/30 px-1 rounded">{d.url_parameter}</code>}.
                {(d.base_url || d.profile_url) && (
                  <span className="ml-1 text-orange-300/70 font-mono text-xs">
                    → {d.base_url || '…'}{d.profile_url || ''}
                  </span>
                )}
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">
                C2 Profile <span className="text-orange-400">(hosting)</span>
              </label>
              <select
                value={d.c2_profile || ''}
                onChange={e => update({ c2_profile: e.target.value || null })}
                className="w-full bg-gray-900/60 border border-gray-600/30 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-orange-500/60"
              >
                <option value="">— Select C2 —</option>
                <option value="payload-server">📦 payload-server</option>
                {c2Profiles.length > 0 && <option disabled>──────────────</option>}
                {c2Profiles.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              {d.c2_profile === 'payload-server' && !payloadServerUrl && (
                <p className="text-xs text-yellow-500/80 mt-1">⚠️ payload-server URL not configured in Settings</p>
              )}
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Base URL</label>
              <input
                value={d.base_url || ''}
                onChange={e => update({ base_url: e.target.value || null })}
                placeholder="https://{{DOMAIN1}}"
                className="w-full bg-gray-900/60 border border-gray-600/30 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-orange-500/60 font-mono text-xs"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Profile URL <span className="text-gray-600">(URI)</span></label>
              <input
                value={d.profile_url || ''}
                onChange={e => update({ profile_url: e.target.value || null })}
                placeholder="/jquery.js"
                className="w-full bg-gray-900/60 border border-gray-600/30 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500/60 font-mono text-xs"
              />
            </div>
          </>
        )}
      </div>

      {/* C2 Profile parameters (base only, when a profile is selected) */}
      {!collapsed && d.stage_type === 'base' && d.c2_profile && (() => {
        const profileMeta = comp?.c2_profiles_metadata?.find(m => m.name === d.c2_profile)
        const currentC2 = d.c2_profiles?.[0] || {}
        const c2Params = currentC2.c2_profile_parameters || {}

        const updateC2Param = (key, val, filename) => {
          const updated = { ...c2Params, [key]: val }
          const patch = { c2_profiles: [{ c2_profile: d.c2_profile, c2_profile_parameters: updated }] }
          if (filename !== undefined) {
            const names = { ...(d.file_names || {}) }
            if (filename) names['c2:' + key] = filename
            else delete names['c2:' + key]
            patch.file_names = names
          }
          update(patch)
        }

        return (
          <div className="rounded-lg border border-indigo-700/30 bg-indigo-900/10 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-indigo-300 uppercase tracking-wider">C2 Parameters</span>
              <span className="font-mono text-xs text-indigo-400 bg-indigo-900/30 px-2 py-0.5 rounded">{d.c2_profile}</span>
            </div>
            {profileMeta ? (
              <div className="space-y-2">
                {profileMeta.parameters.map(paramMeta => (
                  <TypedParamField
                    key={paramMeta.name}
                    name={paramMeta.name}
                    value={c2Params[paramMeta.name] ?? paramMeta.default_value_decoded ?? paramMeta.default_value ?? ''}
                    meta={paramMeta}
                    onChange={(val, filename) => updateC2Param(paramMeta.name, val, filename)}
                    onRemove={null}
                    displayName={(d.file_names || {})['c2:' + paramMeta.name]}
                  />
                ))}
              </div>
            ) : (
              <div className="text-xs text-gray-500">No parameter metadata available for this profile.</div>
            )}
          </div>
        )
      })()}

      {/* Commands (base only) */}
      {!collapsed && d.stage_type === 'base' && (
        <CommandsSection
          commands={d.commands}
          availableCommands={comp?.available_commands || []}
          onChange={cmds => update({ commands: cmds })}
        />
      )}

      {/* Parameters — for downloaders, hide the url_parameter (auto-managed) */}
      {!collapsed && (Object.keys(d.parameters).length > 0 || d.stage_type !== 'wrapper') && (() => {
        const urlParamName = comp?.url_parameter || null
        const filteredParams = urlParamName
          ? Object.fromEntries(Object.entries(d.parameters).filter(([k]) => k !== urlParamName))
          : d.parameters
        const filteredMeta = (comp?.build_parameters_metadata || []).filter(
          m => !urlParamName || m.name !== urlParamName
        )
        return (
          <ParametersSection
            parameters={filteredParams}
            buildParamsMeta={filteredMeta}
            fileNames={d.file_names || {}}
            onFileChange={(newParams, fileUpdate) => {
              // Atomic update: parameters + file_names in one shot
              const full = urlParamName
                ? { ...newParams, [urlParamName]: d.parameters[urlParamName] ?? '' }
                : newParams
              const names = { ...(d.file_names || {}) }
              if (fileUpdate) {
                if (fileUpdate.filename) names[fileUpdate.key] = fileUpdate.filename
                else delete names[fileUpdate.key]
              }
              update({ parameters: full, file_names: names })
            }}
            onChange={params => {
              // Re-inject the url param with its current value when saving
              const full = urlParamName
                ? { ...params, [urlParamName]: d.parameters[urlParamName] ?? '' }
                : params
              update({ parameters: full })
            }}
          />
        )
      })()}
    </div>
  )
}

// ── Main Editor ───────────────────────────────────────────────────────────────

export default function ChainEditor({ chain, onBack, onSaved }) {
  const [name, setName] = useState(chain?.name || '')
  const [description, setDescription] = useState(chain?.description || '')
  const [mythicTag, setMythicTag] = useState(chain?.mythic_tag || '')
  const [variables, setVariables] = useState(chain?.variables || {})  // {name: value}
  const [graph, setGraph] = useState(() => graphFromChain(chain))
  const [components, setComponents] = useState([])
  const [c2Profiles, setC2Profiles] = useState([]) // active C2 profiles from Mythic
  const [saving, setSaving] = useState(false)
  const [validationErrors, setValidationErrors] = useState([])
  const [activeTab, setActiveTab] = useState('builder') // 'builder' | 'mythic'
  const [savedChainId, setSavedChainId] = useState(chain?.id || null)
  const validateTimeout = useRef(null)

  const [syncingMythic, setSyncingMythic] = useState(false)
  const [payloadServerUrl, setPayloadServerUrl] = useState('')

  // Load components + C2 profiles
  const refreshComponents = () => {
    setSyncingMythic(true)
    Promise.all([
      api.getComponents().then(data => setComponents(data.components || [])),
      api.getC2Profiles().then(data => setC2Profiles((data.profiles || []).map(p => p.name))),
    ])
      .catch(() => {})
      .finally(() => setSyncingMythic(false))
  }
  useEffect(() => {
    refreshComponents()
    api.getSettings().then(s => setPayloadServerUrl(s.payload_server_url || '')).catch(() => {})
  }, [])

  // Resolve missing file_names for any file refs in parameters + c2_profile_parameters
  useEffect(() => {
    const isRef = v => typeof v === 'string' && v && (v.startsWith('local:') || /^[0-9a-f-]{36}$/i.test(v))
    const allRefs = new Set()
    graph.nodes.forEach(node => {
      const d = node.data || {}
      const fileNames = d.file_names || {}
      // build params
      Object.entries(d.parameters || {}).forEach(([key, val]) => {
        if (isRef(val) && !fileNames[key]) allRefs.add(val)
      })
      // c2 params
      ;(d.c2_profiles || []).forEach(prof => {
        Object.entries(prof.c2_profile_parameters || {}).forEach(([key, val]) => {
          if (isRef(val) && !fileNames['c2:' + key]) allRefs.add(val)
        })
      })
    })
    if (allRefs.size === 0) return
    api.resolveFileNames([...allRefs]).then(resolved => {
      if (!resolved || Object.keys(resolved).length === 0) return
      setGraph(prev => ({
        ...prev,
        nodes: prev.nodes.map(node => {
          const d = node.data || {}
          const updates = {}
          // build params
          Object.entries(d.parameters || {}).forEach(([key, val]) => {
            if (isRef(val) && resolved[val] && !(d.file_names || {})[key])
              updates[key] = resolved[val]
          })
          // c2 params (prefixed with 'c2:' to avoid collisions)
          ;(d.c2_profiles || []).forEach(prof => {
            Object.entries(prof.c2_profile_parameters || {}).forEach(([key, val]) => {
              if (isRef(val) && resolved[val] && !(d.file_names || {})['c2:' + key])
                updates['c2:' + key] = resolved[val]
            })
          })
          if (Object.keys(updates).length === 0) return node
          return { ...node, data: { ...d, file_names: { ...(d.file_names || {}), ...updates } } }
        }),
      }))
    }).catch(() => {})
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-validate graph on change
  const validateAndUpdate = useCallback((g) => {
    clearTimeout(validateTimeout.current)
    validateTimeout.current = setTimeout(async () => {
      if (g.nodes.length === 0) {
        setValidationErrors([])
        return
      }
      try {
        const result = await api.validateChain({ name: name || 'chain', description, graph: g })
        setValidationErrors(result.errors || [])
      } catch (e) {
        setValidationErrors([e.message])
      }
    }, 600)
  }, [name, description])

  // Rebuild edges from wrapped/downloaded references
  const rebuildEdges = useCallback((nodes) => {
    const edges = []
    nodes.forEach(node => {
      const d = node.data
      let targetLabel = null
      if (d.stage_type === 'wrapper' && d.wrapped_payload) targetLabel = d.wrapped_payload
      if (d.stage_type === 'downloader' && d.downloaded_payload) targetLabel = d.downloaded_payload
      if (targetLabel) {
        const upstream = nodes.find(n => n.data.label === targetLabel)
        if (upstream) {
          // Edge: upstream (base/wrapper) → current node (wrapper/downloader)
          // upstream is the parent that must be built first
          edges.push({
            id: `${upstream.id}->${node.id}`,
            source: upstream.id,
            target: node.id,
          })
        }
      }
    })
    return edges
  }, [])

  const updateNodes = useCallback((nodes) => {
    const edges = rebuildEdges(nodes)
    const g = { nodes, edges }
    setGraph(g)
    validateAndUpdate(g)
  }, [rebuildEdges, validateAndUpdate])

  const handleNodeChange = useCallback((id, newData) => {
    setGraph(prev => {
      const nodes = prev.nodes.map(n => n.id === id ? { ...n, data: newData } : n)
      const edges = rebuildEdges(nodes)
      const g = { nodes, edges }
      validateAndUpdate(g)
      return g
    })
  }, [rebuildEdges, validateAndUpdate])

  const addStage = () => {
    const node = emptyNode()
    updateNodes([...graph.nodes, node])
  }

  const removeStage = (id) => {
    updateNodes(graph.nodes.filter(n => n.id !== id))
  }

  const moveUp = (index) => {
    if (index === 0) return
    const nodes = [...graph.nodes]
    ;[nodes[index - 1], nodes[index]] = [nodes[index], nodes[index - 1]]
    updateNodes(nodes)
  }

  const moveDown = (index) => {
    if (index === graph.nodes.length - 1) return
    const nodes = [...graph.nodes]
    ;[nodes[index], nodes[index + 1]] = [nodes[index + 1], nodes[index]]
    updateNodes(nodes)
  }

  const handleSave = async () => {
    if (!name.trim()) {
      showToast('Chain name is required.', 'error')
      return
    }
    setSaving(true)
    try {
      const payload = { name: name.trim(), description: description.trim() || null, mythic_tag: mythicTag.trim() || null, graph, variables }
      let saved
      if (savedChainId) {
        saved = await api.updateChain(savedChainId, payload)
      } else {
        saved = await api.createChain(payload)
        setSavedChainId(saved.id)
      }
      showToast('Chain saved.', 'success')
      onSaved(saved)
    } catch (e) {
      showToast(`Save failed: ${e.message}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleExport = async () => {
    if (!chain?.id) { showToast('Save the chain first before exporting.', 'warning'); return }
    try {
      const res = await fetch(`/api/chains/${chain.id}/export`)
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${(name || 'chain').replace(/[^\w\-.]/g, '_')}.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      showToast(`Export failed: ${e.message}`, 'error')
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex items-center gap-3 mb-5">
        <button
          onClick={onBack}
          className="text-gray-500 hover:text-gray-200 transition text-sm"
        >
          ← Back
        </button>
        <h2 className="text-lg font-semibold text-gray-100 flex-1 min-w-0 truncate">
          {chain?.id ? `Edit: ${name || '(unnamed)'}` : 'New Chain'}
        </h2>
        <button
          onClick={refreshComponents}
          disabled={syncingMythic}
          title="Reload payload types from Mythic"
          className="px-3 py-1.5 rounded-lg bg-gray-700/40 hover:bg-gray-600/40 text-gray-400 hover:text-gray-200 text-xs font-medium border border-gray-600/30 transition shrink-0 disabled:opacity-50"
        >
          {syncingMythic ? '↻ Syncing…' : '↻ Sync Mythic'}
        </button>
        <button
          onClick={handleExport}
          className="px-3 py-1.5 rounded-lg bg-gray-700/40 hover:bg-gray-600/40 text-gray-200 text-xs font-medium border border-gray-600/30 transition shrink-0"
        >
          📦 Export ZIP
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed text-white text-xs font-medium transition shrink-0"
        >
          {saving ? 'Saving…' : 'Save Chain'}
        </button>
      </div>

      {/* Chain meta */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
        <div className="sm:col-span-2">
          <label className="block text-xs text-gray-500 mb-1">Chain name *</label>
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. scenario1"
            className="w-full bg-gray-900/60 border border-gray-600/40 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500/60"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">
            Mythic tag
            <span className="ml-1 text-gray-600 font-normal">(identifies payloads in Mythic)</span>
          </label>
          <input
            value={mythicTag}
            onChange={e => setMythicTag(e.target.value)}
            placeholder="e.g. red-team-op1"
            className="w-full bg-gray-900/60 border border-gray-600/40 rounded-lg px-3 py-2 text-sm text-gray-100 font-mono focus:outline-none focus:border-red-500/60"
          />
        </div>
        <div className="sm:col-span-3">
          <label className="block text-xs text-gray-500 mb-1">Description</label>
          <input
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Optional description"
            className="w-full bg-gray-900/60 border border-gray-600/40 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500/60"
          />
        </div>
        <div className="sm:col-span-4">
          <label className="block text-xs text-gray-500 mb-1">
            Variables
            <span className="ml-1 text-gray-600 font-normal">— use <code className="text-gray-400">{'{{'}'VAR_NAME{'}}'}</code> in any parameter value</span>
          </label>
          <VariablesEditor variables={variables} onChange={setVariables} />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-gray-700/40">
        <button
          onClick={() => setActiveTab('builder')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
            activeTab === 'builder'
              ? 'border-blue-500 text-blue-300'
              : 'border-transparent text-gray-500 hover:text-gray-300'
          }`}
        >
          ⛶ Builder
        </button>
        <button
          onClick={() => setActiveTab('mythic')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
            activeTab === 'mythic'
              ? 'border-red-500 text-red-300'
              : 'border-transparent text-gray-500 hover:text-gray-300'
          }`}
        >
          ⚡ Mythic Payloads
          {savedChainId && <span className="ml-1.5 text-xs text-gray-600">→ deploy or inspect</span>}
        </button>
      </div>

      {/* Builder tab */}
      {activeTab === 'builder' && (
        <>
          {/* Validation errors */}
          {validationErrors.length > 0 && (
            <div className="mb-4 rounded-lg border border-red-700/40 bg-red-900/20 px-4 py-3 space-y-1">
              {validationErrors.map((e, i) => (
                <div key={i} className="text-xs text-red-300">✗ {e}</div>
              ))}
            </div>
          )}

          {/* Main content: stages + yaml */}
          <div className="flex gap-5 flex-1 min-h-0">
            {/* Stages column */}
            <div className="flex-1 min-w-0 overflow-y-auto space-y-3 pr-1">
              {graph.nodes.length === 0 ? (
                <div className="text-center py-10 rounded-xl border border-dashed border-gray-700/40 text-gray-500">
                  No stages yet. Click "Add Stage" to start.
                </div>
              ) : (
                graph.nodes.map((node, i) => (
                  <StageCard
                    key={node.id}
                    node={node}
                    index={i}
                    total={graph.nodes.length}
                    components={components}
                    c2Profiles={c2Profiles}
                    allNodes={graph.nodes}
                    onChange={handleNodeChange}
                    onRemove={() => removeStage(node.id)}
                    onMoveUp={() => moveUp(i)}
                    onMoveDown={() => moveDown(i)}
                    payloadServerUrl={payloadServerUrl}
                  />
                ))
              )}
              <button
                onClick={addStage}
                className="w-full py-3 rounded-xl border border-dashed border-gray-700/40 hover:border-gray-500/60 text-gray-500 hover:text-gray-300 text-sm transition"
              >
                + Add Stage
              </button>
            </div>


          </div>
        </>
      )}

      {/* Mythic Payloads tab */}
      {activeTab === 'mythic' && (
        <div className="flex-1 overflow-y-auto">
          {savedChainId ? (
            <ChainMythicPayloads chainId={savedChainId} chainName={name} />
          ) : (
            <div className="text-center py-16 rounded-xl border border-dashed border-gray-700/30 text-gray-500">
              <div className="text-2xl mb-2">⚡</div>
              <div className="font-medium text-gray-400">Sauvegarde requise</div>
              <div className="text-sm mt-1">Save the chain first, then deploy or inspect Mythic payloads.</div>
              <button
                onClick={handleSave}
                className="mt-4 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition"
              >
                Save Chain
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
