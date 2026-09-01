// Mock data for UI-only prototype. No backend fetches.

export type Status = 'running' | 'pending' | 'stopped' | 'error'

export type Balance = {
  asset: string
  free: number
  locked: number
  priceUsdt: number
}

export type Overview = {
  totalBalanceUsdt: number
  totalBalanceDeltaPct: number
  todayPnlUsdt: number
  todayPnlPct: number
  runningGrids: number
  totalGrids: number
  recentError: string | null
}

export type Grid = {
  id: number
  symbol: string
  lower: number
  upper: number
  count: number
  mode: 'arithmetic' | 'geometric'
  totalQuote: number
  status: Status
  pnl: number
  filledGrids: number
  startedAt: string
  errorMessage?: string | null
}

export type OrderSide = 'buy' | 'sell'
export type OrderType = 'limit' | 'market'
export type OrderStatus = 'filled' | 'open' | 'canceled' | 'partial'

export type Order = {
  id: string
  time: string
  gridId: number
  symbol: string
  side: OrderSide
  type: OrderType
  price: number
  qty: number
  filled: number
  status: OrderStatus
}

export type LogLevel = 'info' | 'warning' | 'error' | 'success'

export type LogEntry = {
  id: number
  time: string
  level: LogLevel
  message: string
}

export type GridLevel = {
  price: number
  side: OrderSide
  qty: number
  filled: boolean
}

export type Trade = {
  id: string
  time: string
  gridId: number
  symbol: string
  side: OrderSide
  price: number
  qty: number
  fee: number
  feeAsset: string
  realizedPnl: number
}

export type SettingsShape = {
  apiKey: string
  apiSecret: string
  hasApiKey: boolean
  hasApiSecret: boolean
  testnet: boolean
  defaultGridCount: number
  defaultMode: 'arithmetic' | 'geometric'
  pollingIntervalMs: number
  maxGrids: number
  maxPositionSizeUsdt: number
}

export const overview: Overview = {
  totalBalanceUsdt: 12345.67,
  totalBalanceDeltaPct: 0.5,
  todayPnlUsdt: 42.3,
  todayPnlPct: 0.34,
  runningGrids: 2,
  totalGrids: 3,
  recentError: null,
}

export const balances: Balance[] = [
  { asset: 'BTC', free: 0.04213, locked: 0.01, priceUsdt: 67230.5 },
  { asset: 'ETH', free: 1.254, locked: 0.2, priceUsdt: 3284.1 },
  { asset: 'USDT', free: 8420.55, locked: 1500.0, priceUsdt: 1 },
  { asset: 'BNB', free: 4.812, locked: 0.0, priceUsdt: 612.4 },
  { asset: 'SOL', free: 12.5, locked: 1.0, priceUsdt: 152.8 },
]

export const grids: Grid[] = [
  {
    id: 101,
    symbol: 'BTCUSDT',
    lower: 62000,
    upper: 70000,
    count: 10,
    mode: 'arithmetic',
    totalQuote: 2500,
    status: 'running',
    pnl: 87.42,
    filledGrids: 7,
    startedAt: '2026-08-29 10:14:21',
  },
  {
    id: 102,
    symbol: 'ETHUSDT',
    lower: 3000,
    upper: 3500,
    count: 12,
    mode: 'geometric',
    totalQuote: 1500,
    status: 'running',
    pnl: 31.05,
    filledGrids: 5,
    startedAt: '2026-08-28 22:08:00',
  },
  {
    id: 103,
    symbol: 'BNBUSDT',
    lower: 560,
    upper: 640,
    count: 8,
    mode: 'arithmetic',
    totalQuote: 800,
    status: 'pending',
    pnl: 0,
    filledGrids: 0,
    startedAt: '2026-08-30 09:01:12',
  },
  {
    id: 99,
    symbol: 'SOLUSDT',
    lower: 130,
    upper: 170,
    count: 10,
    mode: 'geometric',
    totalQuote: 500,
    status: 'stopped',
    pnl: -12.4,
    filledGrids: 4,
    startedAt: '2026-08-25 14:00:00',
  },
  {
    id: 88,
    symbol: 'BTCUSDT',
    lower: 58000,
    upper: 66000,
    count: 16,
    mode: 'geometric',
    totalQuote: 3000,
    status: 'stopped',
    pnl: 124.7,
    filledGrids: 16,
    startedAt: '2026-08-10 09:30:00',
  },
  {
    id: 77,
    symbol: 'ETHUSDT',
    lower: 2800,
    upper: 3200,
    count: 10,
    mode: 'arithmetic',
    totalQuote: 1200,
    status: 'error',
    pnl: -8.2,
    filledGrids: 2,
    startedAt: '2026-08-20 11:22:00',
    errorMessage: 'Insufficient balance: need 0.35 ETH',
  },
]

const syms = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']
const sides: OrderSide[] = ['buy', 'sell']
const types: OrderType[] = ['limit', 'market']
const statuses: OrderStatus[] = ['filled', 'filled', 'filled', 'open', 'canceled', 'partial']

export const orders: Order[] = Array.from({ length: 18 }, (_, i) => {
  const sym = syms[i % syms.length] ?? 'BTCUSDT'
  const side = sides[i % 2] ?? 'buy'
  const type = types[i % 2] ?? 'limit'
  const status = statuses[i % statuses.length] ?? 'filled'
  const basePrice =
    sym === 'BTCUSDT' ? 67200 : sym === 'ETHUSDT' ? 3280 : sym === 'BNBUSDT' ? 612 : 152
  const price = basePrice + (i - 9) * (basePrice * 0.001)
  const qty = type === 'market' ? 0.05 + (i % 5) * 0.01 : 0.02 + (i % 7) * 0.005
  const filled =
    status === 'filled' ? qty : status === 'partial' ? qty * 0.5 : status === 'open' ? 0 : 0
  const hour = 9 + Math.floor(i / 2)
  const min = (i * 7) % 60
  const sec = (i * 13) % 60
  return {
    id: 'O' + (100000 + i),
    time: `2026-08-30 ${String(hour).padStart(2, '0')}:${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`,
    gridId: i % 3 === 0 ? 101 : i % 3 === 1 ? 102 : 103,
    symbol: sym,
    side,
    type,
    price: Number(price.toFixed(2)),
    qty: Number(qty.toFixed(6)),
    filled: Number(filled.toFixed(6)),
    status,
  }
})

export const logs: LogEntry[] = [
  { id: 1, time: '09:01:12', level: 'info', message: 'Grid #103 created (BNBUSDT 560–640, 8 grids)' },
  { id: 2, time: '09:01:14', level: 'info', message: 'Grid #103 status -> pending' },
  { id: 3, time: '09:02:03', level: 'success', message: 'Grid #101 buy filled @ 63540.10 BTCUSDT (0.0123 BTC)' },
  { id: 4, time: '09:03:18', level: 'info', message: 'Polling binance spot @ 1s interval' },
  { id: 5, time: '09:05:42', level: 'warning', message: 'Grid #102 price nearing upper bound (3492.1 / 3500)' },
  { id: 6, time: '09:06:00', level: 'info', message: 'Order O100023 placed on grid #101' },
  { id: 7, time: '09:06:01', level: 'success', message: 'Order O100023 filled @ 63610.00' },
  { id: 8, time: '09:08:11', level: 'info', message: 'Balance refreshed (USDT: 8420.55 free / 1500.00 locked)' },
  { id: 9, time: '09:10:33', level: 'info', message: 'Grid #101 unrealized PnL: +42.18 USDT' },
  { id: 10, time: '09:11:02', level: 'error', message: 'Grid #77 cannot place order: insufficient balance' },
  { id: 11, time: '09:11:02', level: 'warning', message: 'Grid #77 status -> error' },
  { id: 12, time: '09:14:50', level: 'info', message: 'Order O100024 canceled (price out of range)' },
  { id: 13, time: '09:16:22', level: 'success', message: 'Grid #101 sell filled @ 64120.50 BTCUSDT (0.0100 BTC)' },
  { id: 14, time: '09:18:44', level: 'info', message: 'Grid #102 buy placed @ 3245.00' },
  { id: 15, time: '09:19:01', level: 'success', message: 'Grid #102 buy filled @ 3245.00 (0.18 ETH)' },
  { id: 16, time: '09:21:30', level: 'warning', message: 'Rate limit approaching: 1140/1200 weight used (5m)' },
  { id: 17, time: '09:22:10', level: 'info', message: 'Polling slowed to 2s for 60s' },
  { id: 18, time: '09:24:11', level: 'info', message: 'Polling restored to 1s' },
  { id: 19, time: '09:25:05', level: 'info', message: 'Grid #101 grid #5 refilled' },
  { id: 20, time: '09:26:44', level: 'success', message: 'Today realized PnL: +42.30 USDT' },
  { id: 21, time: '09:27:00', level: 'info', message: 'Account snapshot saved' },
  { id: 22, time: '09:28:18', level: 'warning', message: 'Grid #102 drawdown approaching -2%' },
  { id: 23, time: '09:29:30', level: 'info', message: 'Order O100026 partially filled (0.05 / 0.10)' },
  { id: 24, time: '09:30:01', level: 'error', message: 'Binance API: -1021 timestamp ahead of server time' },
  { id: 25, time: '09:30:03', level: 'info', message: 'Time sync re-established' },
]

// BTCUSDT grid around 67000 with 10 levels
export const btcLevels: GridLevel[] = Array.from({ length: 10 }, (_, i) => {
  const price = 63000 + i * 800
  const side: OrderSide = i % 2 === 0 ? 'buy' : 'sell'
  return {
    price,
    side,
    qty: 0.01 + (i % 4) * 0.005,
    filled: i < 4,
  }
})

// Derived from `orders` for the Trades page — one trade per filled order.
// `filled === qty` is treated as a single trade; partially-filled orders still
// show as one trade line with the actually-filled qty to keep the row count stable.
export const trades: Trade[] = orders
  .filter((o) => o.filled > 0)
  .map((o, i) => {
    const realizedPnl =
      o.side === 'sell' ? Number((o.filled * 1.5).toFixed(2)) : 0
    return {
      id: 'T' + (200000 + i),
      time: o.time,
      gridId: o.gridId,
      symbol: o.symbol,
      side: o.side,
      price: o.price,
      qty: o.filled,
      fee: Number((o.filled * 0.001).toFixed(6)),
      feeAsset: o.symbol.endsWith('USDT')
        ? 'USDT'
        : o.symbol.endsWith('BTC')
        ? 'BTC'
        : o.symbol.endsWith('BNB')
        ? 'BNB'
        : 'USDT',
      realizedPnl,
    }
  })

export const symbolOptions = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']
export const intervalOptions = ['1m', '5m', '15m', '1h', '1d']

export const initialSettings: SettingsShape = {
  apiKey: '',
  apiSecret: '',
  hasApiKey: true,
  hasApiSecret: true,
  testnet: true,
  defaultGridCount: 10,
  defaultMode: 'arithmetic',
  pollingIntervalMs: 1000,
  maxGrids: 10,
  maxPositionSizeUsdt: 5000,
}