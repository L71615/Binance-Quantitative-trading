import { useEffect, useState } from 'react'

type Overview = {
  running_grids?: number
  today_pnl?: number
  total_balance?: number
  recent_error?: string | null
}

type Balance = {
  asset: string
  free: number
  locked: number
}

function StatCard({ label, value, tone }: { label: string; value: string; tone?: 'ok' | 'warn' | 'err' }) {
  const toneClass =
    tone === 'err'
      ? 'border-red-900/60'
      : tone === 'warn'
      ? 'border-amber-900/60'
      : 'border-slate-800'
  return (
    <div className={`p-4 bg-slate-900 rounded-lg border ${toneClass}`}>
      <div className="text-xs text-slate-400 uppercase tracking-wide">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  )
}

export function Dashboard() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [balances, setBalances] = useState<Balance[]>([])
  const [err, setErr] = useState<string>('')

  useEffect(() => {
    let cancelled = false
    const load = () => {
      fetch('/api/dashboard/overview')
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`)
          return r.json()
        })
        .then((d: Overview) => {
          if (!cancelled) setOverview(d)
        })
        .catch((e) => {
          if (!cancelled) setErr('overview 加载失败: ' + String(e))
        })
      fetch('/api/dashboard/balances')
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`)
          return r.json()
        })
        .then((d: Balance[]) => {
          if (!cancelled) setBalances(d ?? [])
        })
        .catch((e) => {
          if (!cancelled) setErr('balances 加载失败: ' + String(e))
        })
    }
    load()
    const id = setInterval(load, 5000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  const fmt = (n: number | undefined) =>
    typeof n === 'number' ? n.toFixed(2) : '0.00'

  const total = overview?.total_balance ?? 0
  const pnl = overview?.today_pnl ?? 0
  const running = overview?.running_grids ?? 0
  const recentErr = overview?.recent_error ?? null

  return (
    <div className="space-y-6">
      {err && (
        <div className="p-3 bg-red-950/30 border border-red-900/60 rounded text-sm">
          {err}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="运行中网格数" value={String(running)} />
        <StatCard
          label="今日盈亏"
          value={fmt(pnl)}
          tone={pnl < 0 ? 'err' : pnl > 0 ? 'ok' : undefined}
        />
        <StatCard label="总余额 (USDT)" value={fmt(total)} />
        <StatCard
          label="最近错误"
          value={recentErr ? String(recentErr) : '无'}
          tone={recentErr ? 'err' : undefined}
        />
      </div>

      <div className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 text-sm font-medium">
          余额
        </div>
        {balances.length === 0 ? (
          <div className="p-6 text-center text-slate-400 text-sm">
            暂无余额数据
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-950 text-slate-400">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Asset</th>
                <th className="text-right px-4 py-2 font-medium">Free</th>
                <th className="text-right px-4 py-2 font-medium">Locked</th>
                <th className="text-right px-4 py-2 font-medium">Total</th>
              </tr>
            </thead>
            <tbody>
              {balances.map((b) => (
                <tr key={b.asset} className="border-t border-slate-800">
                  <td className="px-4 py-2 font-mono">{b.asset}</td>
                  <td className="px-4 py-2 text-right font-mono">
                    {b.free.toFixed(8)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {b.locked.toFixed(8)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {(b.free + b.locked).toFixed(8)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default Dashboard