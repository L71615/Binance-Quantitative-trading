import { useState } from 'react'
import { btcLevels, intervalOptions, symbolOptions } from '../data'
import { Card, SideBadge, inputCls } from '../ui'

export function Charts() {
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [interval, setInterval] = useState('15m')

  const range = btcLevels[btcLevels.length - 1]!.price - btcLevels[0]!.price
  const perGrid = range > 0 ? (range * 0.01).toFixed(2) : '0.00'

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Symbol</label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className={inputCls('w-40')}
          >
            {symbolOptions.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Interval</label>
          <div className="flex gap-1">
            {intervalOptions.map((iv) => {
              const active = iv === interval
              return (
                <button
                  key={iv}
                  onClick={() => setInterval(iv)}
                  className={
                    'px-3 py-2 rounded text-xs font-mono border transition-colors ' +
                    (active
                      ? 'bg-slate-700 text-slate-100 border-slate-600'
                      : 'bg-slate-900 text-slate-400 border-slate-800 hover:bg-slate-800')
                  }
                >
                  {iv}
                </button>
              )
            })}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-slate-500 font-mono">last price</span>
          <span className="text-base font-mono tabular-nums text-emerald-400">
            67,242.18
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3">
          <Card title={`${symbol} · ${interval}`} right={
            <div className="flex gap-1 text-xs">
              <span className="px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-300 border border-emerald-800 font-mono">+1.42%</span>
              <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 font-mono">vol 12.4k</span>
            </div>
          }>
            <ChartPlaceholder symbol={symbol} interval={interval} />
          </Card>
        </div>

        <div className="lg:col-span-2">
          <Card title="网格层级" right={<span className="text-xs text-slate-500 font-mono">{btcLevels.length} levels</span>}>
            <div className="space-y-1 -mx-2">
              {btcLevels.map((l, i) => (
                <div
                  key={i}
                  className={
                    'flex items-center justify-between px-2 py-2 rounded font-mono text-xs ' +
                    (l.filled ? 'bg-slate-800/60' : '')
                  }
                >
                  <div className="flex items-center gap-3">
                    <span className="w-6 text-right text-slate-500">{i + 1}</span>
                    <SideBadge side={l.side} />
                    <span className="tabular-nums text-slate-200">
                      {l.price.toLocaleString('en-US')}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-slate-400">
                    <span className="tabular-nums">{l.qty.toFixed(4)}</span>
                    <span
                      className={
                        'inline-block w-2 h-2 rounded-full ' +
                        (l.filled ? 'bg-emerald-400' : 'bg-slate-600')
                      }
                    />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <RangeStat label="区间" value={`${btcLevels[0]!.price.toLocaleString('en-US')} – ${btcLevels[btcLevels.length - 1]!.price.toLocaleString('en-US')}`} sub={`跨度 ${range.toLocaleString('en-US')} USDT`} />
        <RangeStat label="格数" value={String(btcLevels.length)} sub="等差 (arithmetic)" />
        <RangeStat label="每格盈亏预估" value={`+${perGrid} USDT`} sub="按 1% 仓位估算" tone="ok" />
      </div>
    </div>
  )
}

function ChartPlaceholder({ symbol, interval }: { symbol: string; interval: string }) {
  // grid background via tailwind utilities — no chart library
  return (
    <div
      className="relative w-full h-[400px] rounded border border-slate-800 bg-slate-950 overflow-hidden"
      style={{
        backgroundImage:
          'linear-gradient(to right, rgba(51,65,85,0.4) 1px, transparent 1px), linear-gradient(to bottom, rgba(51,65,85,0.4) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}
    >
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center text-slate-500">
          <div className="text-xs uppercase tracking-wide">K-line chart (lightweight-charts)</div>
          <div className="text-lg font-mono mt-2 text-slate-400">{symbol} · {interval}</div>
          <div className="text-xs mt-1">假数据 · 宽度 100% · 高度 400px</div>
        </div>
      </div>
      {/* fake candle wicks */}
      <svg
        viewBox="0 0 800 400"
        className="absolute inset-0 w-full h-full pointer-events-none"
        preserveAspectRatio="none"
      >
        {Array.from({ length: 40 }).map((_, i) => {
          const x = 10 + i * 20
          const baseY = 180 + Math.sin(i * 0.6) * 40 + (i % 5) * 6
          const top = baseY - 20 - (i % 7) * 4
          const bot = baseY + 20 + (i % 6) * 3
          const up = i % 3 !== 0
          const color = up ? '#10b981' : '#f43f5e'
          return (
            <g key={i}>
              <line x1={x} y1={top} x2={x} y2={bot} stroke={color} strokeWidth="1" />
              <rect
                x={x - 4}
                y={top + 4}
                width={8}
                height={Math.max(2, bot - top - 8)}
                fill={color}
                opacity={0.85}
              />
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function RangeStat({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: string
  sub: string
  tone?: 'ok' | 'neutral'
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div
        className={
          'mt-2 text-xl font-semibold font-mono tabular-nums ' +
          (tone === 'ok' ? 'text-emerald-400' : 'text-slate-100')
        }
      >
        {value}
      </div>
      <div className="mt-1 text-xs text-slate-500 font-mono">{sub}</div>
    </div>
  )
}