import type { ReactNode } from 'react'

export type PageId =
  | 'dashboard'
  | 'charts'
  | 'grids'
  | 'orders'
  | 'trades'
  | 'logs'
  | 'settings'

export const NAV: { id: PageId; label: string; sub: string }[] = [
  { id: 'dashboard', label: 'Dashboard', sub: '总览' },
  { id: 'charts', label: 'Charts', sub: 'K线 / 网格' },
  { id: 'grids', label: 'Grids', sub: '网格策略' },
  { id: 'orders', label: 'Orders', sub: '订单' },
  { id: 'trades', label: 'Trades', sub: '成交' },
  { id: 'logs', label: 'Logs', sub: '日志' },
  { id: 'settings', label: 'Settings', sub: '设置' },
]

const PAGE_TITLE: Record<PageId, string> = {
  dashboard: 'Dashboard',
  charts: 'Charts',
  grids: 'Grids',
  orders: 'Orders',
  trades: 'Trades',
  logs: 'Logs',
  settings: 'Settings',
}

export function Layout({
  page,
  onNav,
  status,
  children,
}: {
  page: PageId
  onNav: (p: PageId) => void
  status: { label: string; tone: 'ok' | 'warn' | 'err' | 'idle' }
  children: ReactNode
}) {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex font-sans">
      <aside className="w-60 shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col">
        <div className="px-4 py-5 border-b border-slate-800">
          <div className="text-base font-semibold tracking-tight">币安现货网格</div>
          <div className="text-xs text-slate-500 mt-1 font-mono">v0.1.0 · mock</div>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {NAV.map((n) => {
            const active = n.id === page
            return (
              <button
                key={n.id}
                onClick={() => onNav(n.id)}
                className={
                  'w-full text-left px-3 py-2 rounded text-sm transition-colors flex items-center gap-3 ' +
                  (active
                    ? 'bg-slate-800 text-slate-100 border border-slate-700'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 border border-transparent')
                }
              >
                <span
                  className={
                    'inline-block w-1.5 h-1.5 rounded-full ' +
                    (active ? 'bg-emerald-400' : 'bg-slate-600')
                  }
                />
                <span className="flex-1">{n.label}</span>
                <span className="text-[10px] text-slate-500">{n.sub}</span>
              </button>
            )
          })}
        </nav>
        <div className="p-3 border-t border-slate-800 text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400" />
            <span>testnet</span>
          </div>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-14 px-6 border-b border-slate-800 bg-slate-900/40 flex items-center justify-between">
          <div className="flex items-baseline gap-3">
            <h1 className="text-base font-semibold">{PAGE_TITLE[page]}</h1>
            <span className="text-xs text-slate-500 font-mono">/{page}</span>
          </div>
          <StatusPill label={status.label} tone={status.tone} />
        </header>
        <div className="flex-1 p-6 overflow-auto">{children}</div>
      </main>
    </div>
  )
}

function StatusPill({
  label,
  tone,
}: {
  label: string
  tone: 'ok' | 'warn' | 'err' | 'idle'
}) {
  const styles =
    tone === 'ok'
      ? 'bg-emerald-900/40 text-emerald-300 border-emerald-800'
      : tone === 'warn'
      ? 'bg-amber-900/40 text-amber-300 border-amber-800'
      : tone === 'err'
      ? 'bg-rose-900/40 text-rose-300 border-rose-800'
      : 'bg-slate-800 text-slate-300 border-slate-700'
  const dot =
    tone === 'ok'
      ? 'bg-emerald-400'
      : tone === 'warn'
      ? 'bg-amber-400'
      : tone === 'err'
      ? 'bg-rose-400'
      : 'bg-slate-400'
  return (
    <span
      className={
        'inline-flex items-center gap-2 px-2.5 py-1 text-xs rounded-full border ' + styles
      }
    >
      <span className={'inline-block w-1.5 h-1.5 rounded-full ' + dot} />
      <span className="font-mono">{label}</span>
    </span>
  )
}