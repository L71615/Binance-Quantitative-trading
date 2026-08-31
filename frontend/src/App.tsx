import { useEffect, useState } from 'react'
import { Setup } from './Setup'
import { Dashboard } from './pages/Dashboard'
import { Settings } from './pages/Settings'
import { Grids } from './pages/Grids'

type Tab = 'dashboard' | 'settings' | 'grids'

const TABS: { id: Tab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'settings', label: 'Settings' },
  { id: 'grids', label: 'Grids' },
]

function App() {
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null)
  const [tab, setTab] = useState<Tab>('dashboard')
  const [forbidden, setForbidden] = useState(false)

  useEffect(() => {
    fetch('/api/setup/state')
      .then((r) => {
        if (r.status === 403) {
          setForbidden(true)
          return { setup_required: true }
        }
        return r.json()
      })
      .then((d) => {
        if (d && typeof d.setup_required === 'boolean') {
          setSetupRequired(d.setup_required)
        } else {
          setSetupRequired(false)
        }
      })
      .catch(() => setSetupRequired(false))
  }, [])

  if (setupRequired === null) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center text-slate-400">
        加载中 …
      </div>
    )
  }

  if (forbidden || setupRequired) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100">
        <div className="bg-amber-900/30 border-b border-amber-800 text-amber-200 text-sm px-4 py-2 text-center">
          Please complete setup first
        </div>
        <Setup />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="bg-slate-900 border-b border-slate-800">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-6">
          <h1 className="text-lg font-semibold">币安现货网格</h1>
          <nav className="flex gap-1 ml-auto">
            {TABS.map((t) => {
              const active = tab === t.id
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={
                    'px-4 py-1.5 rounded text-sm font-medium transition-colors ' +
                    (active
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-800 text-slate-300 hover:bg-slate-700')
                  }
                >
                  {t.label}
                </button>
              )
            })}
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        {tab === 'dashboard' && <Dashboard />}
        {tab === 'settings' && <Settings />}
        {tab === 'grids' && <Grids />}
      </main>
    </div>
  )
}

export default App