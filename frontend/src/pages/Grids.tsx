import { useEffect, useRef, useState } from 'react'

type Grid = {
  id: number
  symbol: string
  lower_price: number
  upper_price: number
  grid_count: number
  grid_mode: string
  total_quote_amount: number
  status: string
  error_message?: string | null
  created_at?: string | null
  started_at?: string | null
  stopped_at?: string | null
}

type Symbol = {
  symbol: string
  base: string
  quote: string
}

const STATUS_STYLE: Record<string, string> = {
  running: 'bg-emerald-900/60 text-emerald-300 border-emerald-800',
  pending: 'bg-amber-900/60 text-amber-300 border-amber-800',
  stopped: 'bg-slate-800 text-slate-300 border-slate-700',
  error: 'bg-red-900/60 text-red-300 border-red-800',
}

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLE[status] ?? STATUS_STYLE.stopped
  return (
    <span
      className={`inline-block px-2 py-0.5 text-xs rounded border ${cls}`}
    >
      {status}
    </span>
  )
}

export function Grids() {
  const [grids, setGrids] = useState<Grid[]>([])
  const [symbols, setSymbols] = useState<Symbol[]>([])
  const [err, setErr] = useState<string>('')
  const [showForm, setShowForm] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)

  // form state
  const [fSymbol, setFSymbol] = useState('')
  const [fLower, setFLower] = useState('')
  const [fUpper, setFUpper] = useState('')
  const [fCount, setFCount] = useState('10')
  const [fMode, setFMode] = useState('arithmetic')
  const [fTotal, setFTotal] = useState('')
  const [formMsg, setFormMsg] = useState<string>('')

  const loadRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch('/api/grids')
        if (!r.ok) {
          setErr('加载 grids 失败: HTTP ' + r.status)
          return
        }
        const d: Grid[] = await r.json()
        setGrids(d ?? [])
        setErr('')
      } catch (e) {
        setErr('加载 grids 出错: ' + String(e))
      }
    }
    loadRef.current = load
    load()

    fetch('/api/symbols')
      .then((r) => r.json())
      .then((d: Symbol[]) => {
        setSymbols(d ?? [])
        if (d.length > 0 && !fSymbol) setFSymbol(d[0].symbol)
      })
      .catch(() => {})

    const id = setInterval(() => loadRef.current?.(), 5000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormMsg('')
    const lower = parseFloat(fLower)
    const upper = parseFloat(fUpper)
    const count = parseInt(fCount, 10)
    const total = parseFloat(fTotal)
    if (!fSymbol) return setFormMsg('请选择交易对')
    if (!(lower > 0) || !(upper > 0) || lower >= upper)
      return setFormMsg('价格区间必须满足 lower < upper 且大于 0')
    if (!(count >= 2 && count <= 200))
      return setFormMsg('网格数必须在 2 ~ 200 之间')
    if (!(total >= 0)) return setFormMsg('总投入金额无效')

    try {
      const r = await fetch('/api/grids', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          symbol: fSymbol,
          lower_price: lower,
          upper_price: upper,
          grid_count: count,
          grid_mode: fMode,
          total_quote_amount: total,
        }),
      })
      const d = await r.json()
      if (!r.ok) {
        setFormMsg('创建失败: ' + JSON.stringify(d))
        return
      }
      setFormMsg('✓ 已创建 grid #' + d.id)
      setFLower('')
      setFUpper('')
      setFTotal('')
      loadRef.current?.()
    } catch (e) {
      setFormMsg('创建出错: ' + String(e))
    }
  }

  const start = async (id: number) => {
    setBusyId(id)
    try {
      const r = await fetch(`/api/grids/${id}/start`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok || !d.ok) setErr('启动失败: ' + JSON.stringify(d))
    } catch (e) {
      setErr('启动出错: ' + String(e))
    } finally {
      setBusyId(null)
      loadRef.current?.()
    }
  }

  const stop = async (id: number) => {
    setBusyId(id)
    try {
      const r = await fetch(`/api/grids/${id}/stop`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok || !d.ok) setErr('停止失败: ' + JSON.stringify(d))
    } catch (e) {
      setErr('停止出错: ' + String(e))
    } finally {
      setBusyId(null)
      loadRef.current?.()
    }
  }

  const del = async (id: number) => {
    if (!confirm('确认删除 grid #' + id + '?')) return
    setBusyId(id)
    try {
      const r = await fetch(`/api/grids/${id}`, { method: 'DELETE' })
      if (!r.ok && r.status !== 204) {
        const d = await r.json().catch(() => ({}))
        setErr('删除失败: ' + JSON.stringify(d))
      }
    } catch (e) {
      setErr('删除出错: ' + String(e))
    } finally {
      setBusyId(null)
      loadRef.current?.()
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">网格策略</h2>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="bg-emerald-600 hover:bg-emerald-500 px-4 py-2 rounded font-medium text-sm"
        >
          {showForm ? '关闭表单' : '+ New Grid'}
        </button>
      </div>

      {err && (
        <div className="p-3 bg-red-950/30 border border-red-900/60 rounded text-sm">
          {err}
        </div>
      )}

      {showForm && (
        <form
          onSubmit={submit}
          className="bg-slate-900 p-5 rounded-lg border border-slate-800 space-y-4"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">
                交易对
              </label>
              <select
                value={fSymbol}
                onChange={(e) => setFSymbol(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm"
              >
                <option value="">-- 选择 --</option>
                {symbols.map((s) => (
                  <option key={s.symbol} value={s.symbol}>
                    {s.symbol}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm text-slate-400 mb-1">
                网格模式
              </label>
              <select
                value={fMode}
                onChange={(e) => setFMode(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm"
              >
                <option value="arithmetic">等差 (arithmetic)</option>
                <option value="geometric">等比 (geometric)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm text-slate-400 mb-1">
                下限价格
              </label>
              <input
                type="number"
                step="any"
                value={fLower}
                onChange={(e) => setFLower(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 font-mono text-sm"
              />
            </div>

            <div>
              <label className="block text-sm text-slate-400 mb-1">
                上限价格
              </label>
              <input
                type="number"
                step="any"
                value={fUpper}
                onChange={(e) => setFUpper(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 font-mono text-sm"
              />
            </div>

            <div>
              <label className="block text-sm text-slate-400 mb-1">
                网格数
              </label>
              <input
                type="number"
                min={2}
                max={200}
                value={fCount}
                onChange={(e) => setFCount(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 font-mono text-sm"
              />
            </div>

            <div>
              <label className="block text-sm text-slate-400 mb-1">
                总投入 (quote)
              </label>
              <input
                type="number"
                step="any"
                value={fTotal}
                onChange={(e) => setFTotal(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 font-mono text-sm"
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              className="bg-emerald-600 hover:bg-emerald-500 px-4 py-2 rounded font-medium text-sm"
            >
              创建
            </button>
            {formMsg && (
              <span className="text-sm text-slate-300 font-mono">
                {formMsg}
              </span>
            )}
          </div>
        </form>
      )}

      <div className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden">
        {grids.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-sm">
            暂无网格,点击右上角 "+ New Grid" 创建
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-950 text-slate-400">
              <tr>
                <th className="text-left px-3 py-2 font-medium">ID</th>
                <th className="text-left px-3 py-2 font-medium">Symbol</th>
                <th className="text-right px-3 py-2 font-medium">Range</th>
                <th className="text-right px-3 py-2 font-medium">Count</th>
                <th className="text-left px-3 py-2 font-medium">Mode</th>
                <th className="text-right px-3 py-2 font-medium">Total</th>
                <th className="text-left px-3 py-2 font-medium">Status</th>
                <th className="text-right px-3 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {grids.map((g) => (
                <tr key={g.id} className="border-t border-slate-800">
                  <td className="px-3 py-2 font-mono">#{g.id}</td>
                  <td className="px-3 py-2 font-mono">{g.symbol}</td>
                  <td className="px-3 py-2 text-right font-mono">
                    {g.lower_price} – {g.upper_price}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {g.grid_count}
                  </td>
                  <td className="px-3 py-2">{g.grid_mode}</td>
                  <td className="px-3 py-2 text-right font-mono">
                    {g.total_quote_amount}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={g.status} />
                    {g.error_message && (
                      <div className="mt-1 text-xs text-red-400">
                        {g.error_message}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex gap-1">
                      {g.status !== 'running' && (
                        <button
                          onClick={() => start(g.id)}
                          disabled={busyId === g.id}
                          className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 px-2 py-1 rounded text-xs"
                        >
                          Start
                        </button>
                      )}
                      {g.status === 'running' && (
                        <button
                          onClick={() => stop(g.id)}
                          disabled={busyId === g.id}
                          className="bg-amber-600 hover:bg-amber-500 disabled:bg-slate-700 px-2 py-1 rounded text-xs"
                        >
                          Stop
                        </button>
                      )}
                      <button
                        onClick={() => del(g.id)}
                        disabled={
                          busyId === g.id ||
                          g.status === 'running' ||
                          g.status === 'pending'
                        }
                        className="bg-slate-700 hover:bg-red-600 disabled:bg-slate-800 px-2 py-1 rounded text-xs"
                      >
                        Delete
                      </button>
                    </div>
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

export default Grids