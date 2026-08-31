import { useMemo, useState } from 'react'
import { orders as initialOrders, symbolOptions } from '../data'
import type { OrderStatus } from '../data'
import { Card, OrderStatusBadge, SideBadge, TypeBadge, btnSecondary, inputCls } from '../ui'

const STATUS_OPTIONS: OrderStatus[] = ['filled', 'open', 'canceled', 'partial']

export function Orders() {
  const [symbol, setSymbol] = useState('')
  const [status, setStatus] = useState('')
  const [gridId, setGridId] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 8

  const filtered = useMemo(() => {
    return initialOrders.filter((o) => {
      if (symbol && o.symbol !== symbol) return false
      if (status && o.status !== status) return false
      if (gridId && String(o.gridId) !== gridId) return false
      if (search) {
        const q = search.toLowerCase()
        if (!o.id.toLowerCase().includes(q) && !o.symbol.toLowerCase().includes(q)) {
          return false
        }
      }
      return true
    })
  }, [symbol, status, gridId, search])

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const pageRows = filtered.slice((page - 1) * pageSize, page * pageSize)

  return (
    <div className="space-y-6">
      <Card title="筛选">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
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
            <label className="block text-xs text-slate-400 mb-1">Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputCls()}>
              <option value="">全部</option>
              {STATUS_OPTIONS.map((s) => (
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
              placeholder="O100023 / BTCUSDT"
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
          {(symbol || status || gridId || search) && (
            <button
              onClick={() => {
                setSymbol('')
                setStatus('')
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
                <th className="px-3 py-2 text-left font-medium">类型</th>
                <th className="px-3 py-2 text-right font-medium">价格</th>
                <th className="px-3 py-2 text-right font-medium">数量</th>
                <th className="px-3 py-2 text-right font-medium">成交</th>
                <th className="px-3 py-2 text-left font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((o) => (
                <tr key={o.id} className="border-t border-slate-800">
                  <td className="px-3 py-2 font-mono text-slate-300">{o.id}</td>
                  <td className="px-3 py-2 font-mono text-slate-400">{o.time}</td>
                  <td className="px-3 py-2 text-right font-mono">#{o.gridId}</td>
                  <td className="px-3 py-2 font-mono">{o.symbol}</td>
                  <td className="px-3 py-2">
                    <SideBadge side={o.side} />
                  </td>
                  <td className="px-3 py-2">
                    <TypeBadge type={o.type} />
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {o.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{o.qty}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    <span
                      className={
                        o.filled === o.qty
                          ? 'text-emerald-400'
                          : o.filled > 0
                          ? 'text-amber-400'
                          : 'text-slate-500'
                      }
                    >
                      {o.filled}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <OrderStatusBadge status={o.status} />
                  </td>
                </tr>
              ))}
              {pageRows.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-3 py-8 text-center text-slate-400 text-sm">
                    无匹配订单
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