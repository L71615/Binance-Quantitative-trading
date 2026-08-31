import { useEffect, useMemo, useRef, useState } from 'react'
import { logs as initialLogs } from '../data'
import type { LogLevel } from '../data'
import { Card, LevelBadge, btnSecondary, inputCls } from '../ui'

const LEVELS: LogLevel[] = ['info', 'success', 'warning', 'error']

export function Logs() {
  const [level, setLevel] = useState('')
  const [search, setSearch] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const containerRef = useRef<HTMLDivElement | null>(null)

  const filtered = useMemo(() => {
    return initialLogs.filter((l) => {
      if (level && l.level !== level) return false
      if (search && !l.message.toLowerCase().includes(search.toLowerCase())) return false
      return true
    })
  }, [level, search])

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [filtered.length, autoScroll])

  return (
    <div className="space-y-6">
      <Card title="筛选">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Level</label>
            <select value={level} onChange={(e) => setLevel(e.target.value)} className={inputCls()}>
              <option value="">全部</option>
              {LEVELS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs text-slate-400 mb-1">搜索消息</label>
            <input
              type="text"
              placeholder="grid / order / binance ..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className={inputCls('font-mono')}
            />
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
          <span>
            匹配 <span className="text-slate-300 font-mono">{filtered.length}</span> 条 / 共 {initialLogs.length}
          </span>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="w-3.5 h-3.5"
            />
            <span>自动滚动到底部</span>
          </label>
        </div>
      </Card>

      <Card
        title="实时日志"
        right={
          <button onClick={() => { setLevel(''); setSearch('') }} className={btnSecondary('text-xs')}>
            清除筛选
          </button>
        }
      >
        <div
          ref={containerRef}
          className="bg-slate-950 border border-slate-800 rounded p-3 h-[460px] overflow-y-auto font-mono text-xs"
        >
          {filtered.length === 0 ? (
            <div className="text-slate-400 text-center py-8">无匹配日志</div>
          ) : (
            <ul className="space-y-1">
              {filtered.map((l) => (
                <li
                  key={l.id}
                  className="flex items-start gap-3 hover:bg-slate-900/40 rounded px-1"
                >
                  <span className="text-slate-500 tabular-nums w-16 shrink-0">{l.time}</span>
                  <span className="shrink-0">
                    <LevelBadge level={l.level} />
                  </span>
                  <span className="text-slate-200 break-all">{l.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </div>
  )
}