import { useState } from 'react'
import Dashboard from './components/Dashboard'
import ChainList from './components/ChainList'
import ChainEditor from './components/ChainEditor'
import Settings from './components/Settings'
import { ToastContainer } from './components/Toast'

const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: '◈' },
  { id: 'chains', label: 'Chains', icon: '⬡' },
  { id: 'settings', label: 'Settings', icon: '⚙' },
]

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [editingChain, setEditingChain] = useState(null) // null = list, chain = editor

  const goTo = (p) => {
    setPage(p)
    setEditingChain(null)
  }

  const handleEditChain = (chain) => {
    setPage('chains')
    setEditingChain(chain)
  }

  const handleNewChain = (prefilled) => {
    setPage('chains')
    setEditingChain(prefilled || {
      id: null,
      name: '',
      description: '',
      mythic_tag: null,
      graph: { nodes: [], edges: [] },
      yaml_content: '',
    })
  }

  const handleSavedChain = (saved) => {
    // Stay on the editor after save
    setEditingChain(c => ({ ...c, id: saved.id }))
  }

  return (
    <div className="min-h-screen flex" style={{ backgroundColor: '#0d0f18' }}>
      {/* Sidebar */}
      <aside className="w-56 shrink-0 flex flex-col border-r border-gray-800/60 bg-gray-900/30">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-gray-800/40">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-red-700/30 border border-red-700/50 flex items-center justify-center text-red-400 font-bold text-sm">M</div>
            <div>
              <div className="text-sm font-semibold text-gray-100">Mythic Builder</div>
              <div className="text-xs text-gray-500">Payload Chains</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV.map(n => (
            <button
              key={n.id}
              onClick={() => goTo(n.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                page === n.id && !editingChain
                  ? 'bg-red-700/20 text-red-300 border border-red-700/30'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700/30'
              }`}
            >
              <span className="text-base">{n.icon}</span>
              {n.label}
            </button>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-800/40">
          <div className="text-xs text-gray-600">
            <a
              href="https://github.com/hegusung/mythic_payload_automation"
              target="_blank"
              rel="noreferrer"
              className="hover:text-gray-400 transition"
            >
              mythic_payload_automation
            </a>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 flex flex-col">
        {/* Top bar */}
        <header className="px-8 py-4 border-b border-gray-800/40 bg-gray-900/20">
          <div className="flex items-center gap-2">
            {page === 'chains' && editingChain ? (
              <>
                <button
                  onClick={() => setEditingChain(null)}
                  className="text-xs text-gray-500 hover:text-gray-300 transition"
                >
                  Chains
                </button>
                <span className="text-gray-700">/</span>
                <span className="text-sm text-gray-300 font-medium">
                  {editingChain?.id ? editingChain.name || 'Edit Chain' : 'New Chain'}
                </span>
              </>
            ) : (
              <h1 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
                {NAV.find(n => n.id === page)?.label || page}
              </h1>
            )}
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-auto px-8 py-6">
          {page === 'dashboard' && (
            <Dashboard onGoToSettings={() => goTo('settings')} />
          )}

          {page === 'chains' && !editingChain && (
            <ChainList
              onEdit={handleEditChain}
              onNew={handleNewChain}
            />
          )}

          {page === 'chains' && editingChain && (
            <div className="h-full flex flex-col" style={{ minHeight: 'calc(100vh - 110px)' }}>
              <ChainEditor
                chain={editingChain}
                onBack={() => setEditingChain(null)}
                onSaved={handleSavedChain}
              />
            </div>
          )}

          {page === 'settings' && (
            <Settings />
          )}
        </div>
      </main>

      <ToastContainer />
    </div>
  )
}
