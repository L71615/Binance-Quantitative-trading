import { useMemo, useState } from 'react'
import { trades as initialTrades, symbolOptions } from '../data'
import type { Trade } from '../data'
import { Card, SideBadge, btnSecondary, inputCls } from '../ui'

export function Trades() {
  const [symbol, setSymbol] = useState('')
  const [gridId, setGridId] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 8

  const filtered = useMemo<Trade[]>(() => {
    return initialTrades.filter((t) => {
      if (symbol && t.symbol !== symbol) return false
      if (gridId && String(t.gridId) !== gridId) return false
      if (search) {
        const q = search.toLowerCase()
        if (!t.id.toLowerCase().includes(q) && !t.symbol.toLowerCase().includes(q)) {
          return false
        }
      }
      return true
    })
  }, [symbol, gridId, search])

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const pageRows = filtered.slice((page - 1) * pageSize, page * pageSize)

  // Top-of-page summary across the *full* set of trades (not the paginated slice).
  const summary = useMemo(() => {
    let buyCount = 0
    let sellCount = 0
    let totalPnl = 0
    let totalFeesUsdt = 0
    for (const t of initialTrades) {
      if (t.side === 'buy') buyCount++
      else sellCount++
      totalPnl += t.realizedPnl
      // Naive USDT-equivalent fee conversion: USDT/BUSD-tagged fees are 1:1,
      // everything else uses 0 for the summary row. Real backend will price it.
      totalFeesUsdt +=
        t.feeAsset === 'USDT' || t.feeAsset === 'BUSD' ? t.fee : 0
    }
    return { buyCount, sellCount, totalPnl, totalFeesUsdt }
  }, [])

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <SummaryStat label="总成交笔数" value={String(initialTrades.length)} sub={`buy ${summary.buyCount} · sell ${summary.sellCount}`} />
        <SummaryStat
          label="已实现盈亏"
          value={`${summary.totalPnl >= 0 ? '+' : ''}${summary.totalPnl.toFixed(2)} USDT`}
          sub="realized"
          tone={summary.totalPnl >= 0 ? 'ok' : 'err'}
        />
        <SummaryStat
          label="累计手续费 (USDT 计)"
          value={summary.totalFeesUsdt.toFixed(4)}
          sub="USDT 计价"
        />
        <SummaryStat label="活跃网格" value="3" sub="101 · 102 · 103" />
      </div>

      <Card title="筛选">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Symbol</label>
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className={inputCls()}>
              <option value="">全部</option>
              {symbolOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Grid ID</label>
            <input
              type="text"
              placeholder="如 101"
              value={gridId}
              onChange={(e) => setGridId(e.target.value)}
              className={inputCls('font-mono')}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">搜索 (id / symbol)</label>
            <input
              type="text"
              placeholder="T200001 / BTCUSDT"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className={inputCls('font-mono')}
            />
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
          <span>
            匹配 <span className="text-slate-300 font-mono">{filtered.length}</span> 条结果
          </span>
          {(symbol || gridId || search) && (
            <button
              onClick={() => {
                setSymbol('')
                setGridId('')
                setSearch('')
              }}
              className="text-sky-400 hover:text-sky-300"
            >
              清除筛选
            </button>
          )}
        </div>
      </Card>

      <Card>
        <div className="overflow-x-auto -mx-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-xs uppercase tracking-wide">
                <th className="px-3 py-2 text-left font-medium">ID</th>
                <th className="px-3 py-2 text-left font-medium">时间</th>
                <th className="px-3 py-2 text-right font-medium">网格</th>
                <th className="px-3 py-2 text-left font-medium">交易对</th>
                <th className="px-3 py-2 text-left font-medium">方向</th>
                <th className="px-3 py-2 text-right font-medium">价格</th>
                <th className="px-3 py-2 text-right font-medium">数量</th>
                <th className="px-3 py-2 text-right font-medium">手续费</th>
                <th className="px-3 py-2 text-right font-medium">已实现 PnL</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((t) => (
                <tr key={t.id} className="border-t border-slate-800">
                  <td className="px-3 py-2 font-mono text-slate-300">{t.id}</td>
                  <td className="px-3 py-2 font-mono text-slate-400">{t.time}</td>
                  <td className="px-3 py-2 text-right font-mono">#{t.gridId}</td>
                  <td className="px-3 py-2 font-mono">{t.symbol}</td>
                  <td className="px-3 py-2">
                    <SideBadge side={t.side} />
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {t.price.toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{t.qty}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {t.fee} <span className="text-slate-500">{t.feeAsset}</span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {t.side === 'buy' ? (
                      <span className="text-slate-500">—</span>
                    ) : (
                      <span className={t.realizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                        {t.realizedPnl >= 0 ? '+' : ''}
                        {t.realizedPnl.toFixed(2)}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              {pageRows.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-slate-400 text-sm">
                    无匹配成交
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-4 flex items-center justify-between text-xs">
          <div className="text-slate-500 font-mono">
            第 {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filtered.length)} 条 / 共 {filtered.length}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className={btnSecondary('text-xs disabled:bg-slate-900 disabled:text-slate-600')}
            >
              上一页
            </button>
            <span className="text-slate-400 font-mono">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className={btnSecondary('text-xs disabled:bg-slate-900 disabled:text-slate-600')}
            >
              下一页
            </button>
          </div>
        </div>
      </Card>
    </div>
  )
}

function SummaryStat({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: string
  sub?: string
  tone?: 'ok' | 'err'
}) {
  const valueColor = tone === 'ok' ? 'text-emerald-400' : tone === 'err' ? 'text-rose-400' : 'text-slate-100'
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={'mt-2 text-xl font-semibold font-mono tabular-nums ' + valueColor}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-slate-500 font-mono">{sub}</div>}
    </div>
  )
}
