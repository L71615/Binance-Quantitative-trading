import { useState } from 'react'
import { grids as initialGrids, symbolOptions } from '../data'
import type { Grid, Status } from '../data'
import { Card, StatusBadge, btnDanger, btnPrimary, btnSecondary, inputCls } from '../ui'

export function Grids() {
  const [grids, setGrids] = useState<Grid[]>(initialGrids)
  const [showForm, setShowForm] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [msg, setMsg] = useState('')

  const [fSymbol, setFSymbol] = useState(symbolOptions[0]!)
  const [fLower, setFLower] = useState('60000')
  const [fUpper, setFUpper] = useState('68000')
  const [fCount, setFCount] = useState('10')
  const [fMode, setFMode] = useState<'arithmetic' | 'geometric'>('arithmetic')
  const [fTotal, setFTotal] = useState('1000')

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const lower = parseFloat(fLower)
    const upper = parseFloat(fUpper)
    const count = parseInt(fCount, 10)
    const total = parseFloat(fTotal)
    if (!(lower > 0) || !(upper > 0) || lower >= upper) {
      setMsg('价格区间必须 lower < upper')
      return
    }
    if (!(count >= 2 && count <= 200)) {
      setMsg('网格数 2 ~ 200')
      return
    }
    if (!(total > 0)) {
      setMsg('总投入必须 > 0')
      return
    }
    const newId = grids.length > 0 ? Math.max(...grids.map((g) => g.id)) + 1 : 1
    const ng: Grid = {
      id: newId,
      symbol: fSymbol,
      lower,
      upper,
      count,
      mode: fMode,
      totalQuote: total,
      status: 'pending',
      pnl: 0,
      filledGrids: 0,
      startedAt: new Date().toISOString().replace('T', ' ').slice(0, 19),
    }
    setGrids([ng, ...grids])
    setMsg(`已创建 grid #${newId} (mock,未发送请求)`)
    setShowForm(false)
  }

  const start = (id: number) => {
    setBusyId(id)
    setTimeout(() => {
      setGrids((prev) =>
        prev.map((g) => (g.id === id ? { ...g, status: 'running' as Status } : g)),
      )
      setBusyId(null)
    }, 250)
  }

  const stop = (id: number) => {
    setBusyId(id)
    setTimeout(() => {
      setGrids((prev) =>
        prev.map((g) => (g.id === id ? { ...g, status: 'stopped' as Status } : g)),
      )
      setBusyId(null)
    }, 250)
  }

  const del = (id: number) => {
    setGrids((prev) => prev.filter((g) => g.id !== id))
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">网格策略</h2>
          <p className="text-xs text-slate-500 mt-1 font-mono">{grids.length} grids total</p>
        </div>
        <button onClick={() => setShowForm((s) => !s)} className={btnPrimary()}>
          {showForm ? '关闭表单' : '+ 新建网格'}
        </button>
      </div>

      {msg && (
        <div className="p-3 bg-slate-900 border border-slate-800 rounded text-sm font-mono text-slate-300">
          {msg}
        </div>
      )}

      {showForm && (
        <Card title="新建网格">
          <form onSubmit={submit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="交易对">
                <select
                  value={fSymbol}
                  onChange={(e) => setFSymbol(e.target.value)}
                  className={inputCls()}
                >
                  {symbolOptions.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="网格模式">
                <select
                  value={fMode}
                  onChange={(e) => setFMode(e.target.value as 'arithmetic' | 'geometric')}
                  className={inputCls()}
                >
                  <option value="arithmetic">等差 (arithmetic)</option>
                  <option value="geometric">等比 (geometric)</option>
                </select>
              </Field>
              <Field label="下限价格">
                <input
                  type="number"
                  step="any"
                  value={fLower}
                  onChange={(e) => setFLower(e.target.value)}
                  className={inputCls('font-mono')}
                />
              </Field>
              <Field label="上限价格">
                <input
                  type="number"
                  step="any"
                  value={fUpper}
                  onChange={(e) => setFUpper(e.target.value)}
                  className={inputCls('font-mono')}
                />
              </Field>
              <Field label="网格数 (2–200)">
                <input
                  type="number"
                  min={2}
                  max={200}
                  value={fCount}
                  onChange={(e) => setFCount(e.target.value)}
                  className={inputCls('font-mono')}
                />
              </Field>
              <Field label="总投入 (quote)">
                <input
                  type="number"
                  step="any"
                  value={fTotal}
                  onChange={(e) => setFTotal(e.target.value)}
                  className={inputCls('font-mono')}
                />
              </Field>
            </div>
            <div className="flex items-center gap-3">
              <button type="submit" className={btnPrimary()}>
                创建
              </button>
              <button type="button" onClick={() => setShowForm(false)} className={btnSecondary()}>
                取消
              </button>
            </div>
          </form>
        </Card>
      )}

      <Card>
        <div className="overflow-x-auto -mx-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-xs uppercase tracking-wide">
                <th className="px-3 py-2 text-left font-medium">ID</th>
                <th className="px-3 py-2 text-left font-medium">Symbol</th>
                <th className="px-3 py-2 text-right font-medium">区间</th>
                <th className="px-3 py-2 text-right font-medium">格数</th>
                <th className="px-3 py-2 text-left font-medium">模式</th>
                <th className="px-3 py-2 text-right font-medium">投入</th>
                <th className="px-3 py-2 text-right font-medium">盈亏</th>
                <th className="px-3 py-2 text-left font-medium">状态</th>
                <th className="px-3 py-2 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {grids.map((g) => (
                <tr key={g.id} className="border-t border-slate-800">
                  <td className="px-3 py-2 font-mono">#{g.id}</td>
                  <td className="px-3 py-2 font-mono">{g.symbol}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {g.lower} – {g.upper}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{g.count}</td>
                  <td className="px-3 py-2 text-slate-300">{g.mode}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{g.totalQuote}</td>
                  <td
                    className={
                      'px-3 py-2 text-right font-mono tabular-nums ' +
                      (g.pnl > 0 ? 'text-emerald-400' : g.pnl < 0 ? 'text-rose-400' : 'text-slate-400')
                    }
                  >
                    {g.pnl >= 0 ? '+' : ''}
                    {g.pnl.toFixed(2)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="space-y-1">
                      <StatusBadge status={g.status} />
                      {g.errorMessage && (
                        <div className="text-xs text-rose-400 font-mono">{g.errorMessage}</div>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex gap-1">
                      {g.status !== 'running' && (
                        <button
                          onClick={() => start(g.id)}
                          disabled={busyId === g.id}
                          className={btnPrimary('disabled:bg-slate-700')}
                        >
                          Start
                        </button>
                      )}
                      {g.status === 'running' && (
                        <button
                          onClick={() => stop(g.id)}
                          disabled={busyId === g.id}
                          className="bg-amber-600 hover:bg-amber-500 disabled:bg-slate-700 text-white font-medium px-2 py-1 rounded text-xs transition-colors"
                        >
                          Stop
                        </button>
                      )}
                      <button
                        onClick={() => del(g.id)}
                        disabled={busyId === g.id || g.status === 'running'}
                        className={btnDanger('disabled:bg-slate-800 disabled:cursor-not-allowed')}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {grids.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-slate-400 text-sm">
                    暂无网格,点击右上角 "+ 新建网格" 创建
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      {children}
    </div>
  )
}