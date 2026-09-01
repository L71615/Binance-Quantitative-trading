import type { ReactNode } from 'react'
import type { LogLevel, OrderSide, OrderStatus, OrderType, Status } from './data'

export function Card({
  title,
  right,
  children,
  className,
}: {
  title?: string
  right?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={
        'bg-slate-900 border border-slate-800 rounded-lg ' + (className ?? '')
      }
    >
      {(title || right) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
          {title && <div className="text-sm font-medium">{title}</div>}
          {right}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  )
}

export function StatCard({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: string
  sub?: string
  tone?: 'ok' | 'err' | 'warn' | 'neutral'
}) {
  const valueColor =
    tone === 'ok'
      ? 'text-emerald-400'
      : tone === 'err'
      ? 'text-rose-400'
      : tone === 'warn'
      ? 'text-amber-400'
      : 'text-slate-100'
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={'mt-2 text-2xl font-semibold font-mono tabular-nums ' + valueColor}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-slate-500 font-mono">{sub}</div>}
    </div>
  )
}

const STATUS_STYLE: Record<Status, string> = {
  running: 'bg-emerald-900/50 text-emerald-300 border-emerald-800',
  pending: 'bg-amber-900/50 text-amber-300 border-amber-800',
  stopped: 'bg-slate-800 text-slate-300 border-slate-700',
  error: 'bg-rose-900/50 text-rose-300 border-rose-800',
}

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span
      className={
        'inline-block px-2 py-0.5 text-xs rounded border font-mono ' + STATUS_STYLE[status]
      }
    >
      {status}
    </span>
  )
}

const ORDER_STATUS_STYLE: Record<OrderStatus, string> = {
  filled: 'bg-emerald-900/50 text-emerald-300 border-emerald-800',
  open: 'bg-sky-900/50 text-sky-300 border-sky-800',
  canceled: 'bg-slate-800 text-slate-400 border-slate-700',
  partial: 'bg-amber-900/50 text-amber-300 border-amber-800',
}

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  return (
    <span
      className={
        'inline-block px-2 py-0.5 text-xs rounded border font-mono ' +
        ORDER_STATUS_STYLE[status]
      }
    >
      {status}
    </span>
  )
}

export function SideBadge({ side }: { side: OrderSide }) {
  const cls =
    side === 'buy'
      ? 'bg-emerald-900/40 text-emerald-300 border-emerald-800'
      : 'bg-rose-900/40 text-rose-300 border-rose-800'
  return (
    <span
      className={'inline-block px-2 py-0.5 text-xs rounded border font-mono ' + cls}
    >
      {side}
    </span>
  )
}

export function TypeBadge({ type }: { type: OrderType }) {
  return (
    <span className="inline-block px-2 py-0.5 text-xs rounded border font-mono bg-slate-800 text-slate-300 border-slate-700">
      {type}
    </span>
  )
}

const LEVEL_STYLE: Record<LogLevel, string> = {
  info: 'bg-slate-800 text-slate-300 border-slate-700',
  success: 'bg-emerald-900/50 text-emerald-300 border-emerald-800',
  warning: 'bg-amber-900/50 text-amber-300 border-amber-800',
  error: 'bg-rose-900/50 text-rose-300 border-rose-800',
}

export function LevelBadge({ level }: { level: LogLevel }) {
  return (
    <span
      className={
        'inline-block px-2 py-0.5 text-xs rounded border font-mono w-16 text-center ' +
        LEVEL_STYLE[level]
      }
    >
      {level}
    </span>
  )
}

export function btnPrimary(extra = '') {
  return (
    'bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-4 py-2 rounded text-sm transition-colors ' +
    extra
  )
}

export function btnSecondary(extra = '') {
  return (
    'bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium px-4 py-2 rounded text-sm transition-colors ' +
    extra
  )
}

export function btnDanger(extra = '') {
  return (
    'bg-slate-700 hover:bg-rose-600 text-slate-100 font-medium px-2 py-1 rounded text-xs transition-colors ' +
    extra
  )
}

export function inputCls(extra = '') {
  return (
    'w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-slate-500 ' +
    extra
  )
}

// Strip common quote-asset suffixes to get the base ticker.
// e.g. BTCUSDT -> BTC, ETHBTC -> ETH, BNBBUSD -> BNB
const QUOTE_SUFFIXES = ['USDT', 'BUSD', 'USDC', 'BTC', 'ETH', 'BNB', 'USD']

function baseSymbol(symbol: string): string {
  const upper = symbol.toUpperCase()
  for (const suf of QUOTE_SUFFIXES) {
    if (upper.endsWith(suf) && upper.length > suf.length) {
      return upper.slice(0, upper.length - suf.length)
    }
  }
  return upper
}

// Symbol -> icon path map (CC0 icons shipped under /public/icons/).
// If a symbol's base isn't in this map we fall back to a letter circle.
const ICON_BASES = new Set(['BTC', 'ETH', 'BNB', 'USDT', 'SOL', 'DOGE'])

export function CryptoIcon({
  symbol,
  size = 24,
  className = '',
}: {
  symbol: string
  size?: number
  className?: string
}) {
  const base = baseSymbol(symbol)
  if (ICON_BASES.has(base)) {
    return (
      <img
        src={`/icons/${base.toLowerCase()}.svg`}
        width={size}
        height={size}
        alt={symbol}
        className={'inline-block rounded-full ' + className}
      />
    )
  }
  // Fallback: a slate-700 circle with the first letter.
  const letter = (base[0] ?? '?').toUpperCase()
  return (
    <span
      className={
        'inline-flex items-center justify-center rounded-full bg-slate-700 text-slate-300 font-mono ' +
        className
      }
      style={{ width: size, height: size, fontSize: Math.max(10, Math.floor(size * 0.5)) }}
      aria-label={symbol}
    >
      {letter}
    </span>
  )
}