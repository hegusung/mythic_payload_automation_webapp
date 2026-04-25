import { useEffect, useState } from 'react'

let toastListeners = []
let toastId = 0

export function showToast(message, type = 'info') {
  const id = ++toastId
  toastListeners.forEach(fn => fn({ id, message, type }))
  return id
}

export function useToasts() {
  const [toasts, setToasts] = useState([])

  useEffect(() => {
    const listener = (toast) => {
      setToasts(prev => [...prev, toast])
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== toast.id))
      }, 4000)
    }
    toastListeners.push(listener)
    return () => { toastListeners = toastListeners.filter(l => l !== listener) }
  }, [])

  return toasts
}

export function ToastContainer() {
  const toasts = useToasts()

  const colors = {
    success: 'border-green-500 bg-green-900/30 text-green-300',
    error: 'border-red-500 bg-red-900/30 text-red-300',
    info: 'border-blue-500 bg-blue-900/30 text-blue-300',
    warning: 'border-yellow-500 bg-yellow-900/30 text-yellow-300',
  }

  const icons = {
    success: '✓',
    error: '✗',
    info: 'ℹ',
    warning: '⚠',
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`flex items-start gap-2 px-4 py-3 rounded-lg border text-sm font-medium shadow-lg transition-all ${colors[t.type] || colors.info}`}
        >
          <span className="shrink-0 text-base">{icons[t.type] || icons.info}</span>
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  )
}
