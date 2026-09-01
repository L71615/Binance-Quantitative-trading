import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CandlestickSeries,
  createChart,
  type CandlestickData,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts'
import { btcLevels, intervalOptions, symbolOptions } from '../data'
import { Card, CryptoIcon, SideBadge, inputCls } from '../ui'

type Ohlc = CandlestickData<Time>

// 60 hourly bars for BTCUSDT centred around 60,000 with a gentle up-trend + noise.
function genMockBars(): Ohlc[] {
  const bars: Ohlc[] = []
  const startSec = Math.floor(Date.UTC(2026, 7, 28, 0, 0, 0) / 1000) // 2026-08-28 00:00 UTC
  let price = 59500
  for (let i = 0; i < 60; i++) {
    // Deterministic pseudo-random so SSR + client produce the same shape.
    const r1 = Math.sin(i * 1.7) * 0.5 + 0.5
    const r2 = Math.cos(i * 0.9) * 0.5 + 0.5
    const drift = 120 // gentle up-trend
    const open = price
    const close = price + drift + (r1 - 0.5) * 800
    const high = Math.max(open, close) + r2 * 220
    const low = Math.min(open, close) - (1 - r2) * 220
    bars.push({
      time: (startSec + i * 3600) as Time,
      open: round2(open),
      high: round2(high),
      low: round2(low),
      close: round2(close),
    })
    price = close
  }
  return bars
}

function round2(n: number) {
  return Math.round(n * 100) / 100
}

export function Charts() {
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [interval, setInterval] = useState('1h')

  // 3 horizontal grid lines: lower / mid / upper (taken from btcLevels fixtures).
  const gridLines = useMemo(() => {
    const first = btcLevels[0]!.price
    const last = btcLevels[btcLevels.length - 1]!.price
    const mid = (first + last) / 2
    return [
      { price: first, label: 'lower', tone: 'buy' as const },
      { price: mid, label: 'mid', tone: 'neutral' as const },
      { price: last, label: 'upper', tone: 'sell' as const },
    ]
  }, [])

  // 2 stat panels below the chart.
  const range =
    btcLevels[btcLevels.length - 1]!.price - btcLevels[0]!.price
  const perGrid = range > 0 ? (range * 0.01).toFixed(2) : '0.00'
  // Pretend filled grids cover ~40% of the range.
  const filledCount = btcLevels.filter((l) => l.filled).length
  const totalCoveragePct = ((filledCount / btcLevels.length) * 100).toFixed(1)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <CryptoIcon symbol={symbol} size={28} />
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
          <Card
            title={`${symbol} · ${interval}`}
            right={
              <div className="flex gap-1 text-xs">
                <span className="px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-300 border border-emerald-800 font-mono">
                  +1.42%
                </span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 font-mono">
                  vol 12.4k
                </span>
              </div>
            }
          >
            <KlineChart symbol={symbol} gridLines={gridLines} />
          </Card>
        </div>

        <div className="lg:col-span-2">
          <Card
            title="网格层级"
            right={
              <span className="text-xs text-slate-500 font-mono">
                {btcLevels.length} levels
              </span>
            }
          >
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
                        (l.filled ? 'bg-emerald-400' : 'bg-rose-400')
                      }
                      title={l.filled ? 'filled' : 'open'}
                    />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <RangeStat
          label="Per-grid P&L est."
          value={`+${perGrid} USDT`}
          sub="按 1% 仓位估算"
          tone="ok"
        />
        <RangeStat
          label="Total range coverage"
          value={`${totalCoveragePct}%`}
          sub={`${filledCount} / ${btcLevels.length} grids filled`}
          tone={filledCount > 0 ? 'ok' : 'neutral'}
        />
      </div>
    </div>
  )
}

function KlineChart({
  symbol,
  gridLines,
}: {
  symbol: string
  gridLines: { price: number; label: string; tone: 'buy' | 'sell' | 'neutral' }[]
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const priceLineRefs = useRef<IPriceLine[]>([])
  const [error, setError] = useState<string | null>(null)

  // Bars are deterministic; safe to compute once outside effect.
  const bars = useMemo(() => genMockBars(), [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    let chart: IChartApi
    try {
      chart = createChart(el, {
        width: el.clientWidth,
        height: 400,
        layout: {
          background: { color: '#020617' }, // slate-950
          textColor: '#94a3b8', // slate-400
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        },
        grid: {
          vertLines: { color: '#1e293b' }, // slate-800
          horzLines: { color: '#1e293b' },
        },
        rightPriceScale: {
          borderColor: '#1e293b',
        },
        timeScale: {
          borderColor: '#1e293b',
          timeVisible: true,
          secondsVisible: false,
        },
        crosshair: {
          mode: 1,
        },
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return
    }

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981', // emerald-500
      downColor: '#f43f5e', // rose-500
      borderUpColor: '#10b981',
      borderDownColor: '#f43f5e',
      wickUpColor: '#10b981',
      wickDownColor: '#f43f5e',
    })

    try {
      series.setData(bars)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      chart.remove()
      return
    }

    chart.timeScale().fitContent()

    // 3 horizontal price lines for grid lower / mid / upper.
    const lines: IPriceLine[] = []
    for (const g of gridLines) {
      const color =
        g.tone === 'buy' ? '#10b981' : g.tone === 'sell' ? '#f43f5e' : '#38bdf8'
      const line = series.createPriceLine({
        price: g.price,
        color,
        lineWidth: 1,
        lineStyle: 2, // dashed
        axisLabelVisible: true,
        title: g.label,
      })
      lines.push(line)
    }

    chartRef.current = chart
    seriesRef.current = series
    priceLineRefs.current = lines

    // Resize observer for responsive width.
    const ro = new ResizeObserver(() => {
      if (chartRef.current && el) {
        chartRef.current.applyOptions({ width: el.clientWidth })
      }
    })
    ro.observe(el)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      priceLineRefs.current = []
    }
  }, [bars, gridLines])

  if (error) {
    return (
      <div className="w-full h-[400px] rounded border border-rose-800 bg-slate-950 flex items-center justify-center text-rose-400 text-sm font-mono p-4">
        lightweight-charts failed: {error}
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="w-full h-[400px] rounded border border-slate-800 bg-slate-950 overflow-hidden"
      data-symbol={symbol}
    />
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