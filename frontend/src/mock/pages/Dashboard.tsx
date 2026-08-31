import { balances, grids, overview } from '../data'
import { Card, StatCard, StatusBadge, btnSecondary } from '../ui'

export function Dashboard() {
  const pnl = overview.todayPnlUsdt
  const recentErr = overview.recentError
  const runningGrids = grids.filter((g) => g.status === 'running')

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="总余额 (USDT)"
          value={overview.totalBalanceUsdt.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
          sub={`+${overview.totalBalanceDeltaPct.toFixed(2)}%  24h`}
          tone="ok"
        />
        <StatCard
          label="今日盈亏"
          value={`${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} USDT`}
          sub={`${pnl >= 0 ? '+' : ''}${overview.todayPnlPct.toFixed(2)}%`}
          tone={pnl >= 0 ? 'ok' : 'err'}
        />
        <StatCard
          label="运行中网格"
          value={`${overview.runningGrids} / ${overview.totalGrids}`}
          sub="2 running, 1 pending"
        />
        <StatCard
          label="最近错误"
          value={recentErr ?? '无'}
          tone={recentErr ? 'err' : 'neutral'}
          sub={recentErr ? '2 分钟前' : '过去 24h 无异常'}
        />
      </div>

      <Card title="持仓" right={<span className="text-xs text-slate-500 font-mono">{balances.length} assets</span>}>
        <div className="overflow-x-auto -mx-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-xs uppercase tracking-wide">
                <th className="px-4 py-2 text-left font-medium">Asset</th>
                <th className="px-4 py-2 text-right font-medium">Free</th>
                <th className="px-4 py-2 text-right font-medium">Locked</th>
                <th className="px-4 py-2 text-right font-medium">Price</th>
                <th className="px-4 py-2 text-right font-medium">Value (USDT)</th>
              </tr>
            </thead>
            <tbody>
              {balances.map((b) => {
                const total = b.free + b.locked
                const value = total * b.priceUsdt
                return (
                  <tr key={b.asset} className="border-t border-slate-800">
                    <td className="px-4 py-2 font-mono">{b.asset}</td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">
                      {b.free.toFixed(b.asset === 'USDT' ? 2 : 6)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">
                      {b.locked.toFixed(b.asset === 'USDT' ? 2 : 6)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">
                      {b.priceUsdt.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">
                      {value.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="运行中网格摘要" right={<button className={btnSecondary('text-xs')}>查看全部</button>}>
        {runningGrids.length === 0 ? (
          <div className="text-sm text-slate-400 text-center py-6">当前无运行中网格</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {runningGrids.map((g) => (
              <div
                key={g.id}
                className="bg-slate-950 border border-slate-800 rounded-lg p-4"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm">#{g.id}</span>
                    <span className="font-mono text-sm text-slate-300">{g.symbol}</span>
                  </div>
                  <StatusBadge status={g.status} />
                </div>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between text-slate-400">
                    <span>区间</span>
                    <span className="font-mono text-slate-200">
                      {g.lower} – {g.upper}
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>已成交</span>
                    <span className="font-mono text-slate-200">
                      {g.filledGrids} / {g.count}
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>已实现盈亏</span>
                    <span
                      className={
                        'font-mono ' +
                        (g.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400')
                      }
                    >
                      {g.pnl >= 0 ? '+' : ''}
                      {g.pnl.toFixed(2)} USDT
                    </span>
                  </div>
                </div>
                <div className="mt-3 h-1.5 bg-slate-800 rounded overflow-hidden">
                  <div
                    className="h-full bg-emerald-500"
                    style={{ width: `${(g.filledGrids / g.count) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}