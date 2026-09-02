import { useState } from 'react'
import {
  aiDecisions,
  aiStatus as initialAIStatus,
  symbolOptions,
  type AIDecisionRow,
  type AISettings,
  type AIStatus,
} from '../data'
import { Card, btnPrimary, btnSecondary, btnDanger, inputCls } from '../ui'

// Backend compares this string with plain == (no trim, no upper-casing).
// Must match exactly. The mock shell re-implements that gate in component state.
const LIVE_ARM_PHRASE = 'I UNDERSTAND REAL MONEY'

// Spec §11 phase 3: "conservative live tier" defaults that the user starts at
// after arming for live, and "normal defaults" they can explicitly raise to.
const CONSERVATIVE_CAPS = {
  max_order_quote_usdt: 20,
  daily_loss_cap_usdt: -10,
  daily_max_trades: 10,
} as const
const NORMAL_CAPS = {
  max_order_quote_usdt: 50,
  daily_loss_cap_usdt: -30,
  daily_max_trades: 20,
} as const

export function AITrader() {
  const [armed, setArmed] = useState(initialAIStatus.armed_for_live_at !== null)
  const [confirmText, setConfirmText] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [stopStep, setStopStep] = useState<'idle' | 'confirm'>('idle')
  const [caps, setCaps] = useState({
    max_order_quote_usdt: initialAIStatus.max_order_quote_usdt,
    daily_loss_cap_usdt: initialAIStatus.daily_loss_cap_usdt,
    daily_max_trades: initialAIStatus.daily_max_trades,
    max_position_per_symbol_usdt: initialAIStatus.max_position_per_symbol_usdt,
  })
  const [tier, setTier] = useState<'conservative' | 'normal'>(
    initialAIStatus.max_order_quote_usdt === CONSERVATIVE_CAPS.max_order_quote_usdt
      ? 'conservative'
      : 'normal',
  )
  const [symbols, setSymbols] = useState<string[]>(initialAIStatus.symbols)
  const [newSymbol, setNewSymbol] = useState('')

  const s: AISettings = { ...initialAIStatus, ...caps, symbols }
  const status: AIStatus = armed ? 'running' : initialAIStatus.status
  const isLive = !s.testnet

  // Exact-string comparison. No trim, no normalize. Mirrors backend `==`.
  const confirmMatches = confirmText === LIVE_ARM_PHRASE

  const addSymbol = () => {
    const v = newSymbol.trim().toUpperCase()
    if (!v) return
    if (symbols.includes(v)) {
      setNewSymbol('')
      return
    }
    setSymbols([...symbols, v])
    setNewSymbol('')
  }

  const removeSymbol = (sym: string) => {
    setSymbols(symbols.filter((x) => x !== sym))
  }

  const raiseToNormalDefaults = () => {
    setCaps({
      max_order_quote_usdt: NORMAL_CAPS.max_order_quote_usdt,
      daily_loss_cap_usdt: NORMAL_CAPS.daily_loss_cap_usdt,
      daily_max_trades: NORMAL_CAPS.daily_max_trades,
      max_position_per_symbol_usdt: caps.max_position_per_symbol_usdt,
    })
    setTier('normal')
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">AI Trader</h2>
          <p className="text-xs text-slate-500 mt-1 font-mono">
            模拟界面 · 每 60s 一次 LLM 决策,六个硬性风控把关,通过则实盘下单
          </p>
        </div>
        <span
          className={
            'inline-block px-3 py-1 rounded border font-mono text-xs ' +
            (status === 'running'
              ? 'bg-emerald-900/40 text-emerald-300 border-emerald-800'
              : status === 'paused'
                ? 'bg-amber-900/40 text-amber-300 border-amber-800'
                : status === 'error'
                  ? 'bg-rose-900/40 text-rose-300 border-rose-800'
                  : status === 'stopped'
                    ? 'bg-slate-800 text-slate-300 border-slate-700'
                    : 'bg-slate-800 text-slate-300 border-slate-700')
          }
        >
          status: {status}
        </span>
      </div>

      <div className="p-3 bg-amber-950/30 border border-amber-900/60 rounded text-xs font-mono text-amber-200">
        Connect real backend — this mock page renders from static fixtures and
        makes no network calls. Buttons below are stubs that only update local
        component state.
      </div>

      <Card title="状态">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat
            label="Last tick"
            value={s.last_tick_at ?? '—'}
            sub={armed ? '12s ago' : '未启动'}
          />
          <Stat
            label="Trades today"
            value={`${s.trades_today ?? 0} / ${caps.daily_max_trades}`}
            sub="已用 / 上限"
          />
          <Stat
            label="P&L (今日)"
            value={`${s.realized_pnl_today_usdt >= 0 ? '+' : ''}${s.realized_pnl_today_usdt.toFixed(2)} USDT`}
            sub="已实现"
            tone={s.realized_pnl_today_usdt > 0 ? 'ok' : s.realized_pnl_today_usdt < 0 ? 'err' : 'neutral'}
          />
          <Stat
            label="Loss budget"
            value={`${caps.daily_loss_cap_usdt} USDT`}
            sub={`已消耗 ${s.loss_consumed_usdt.toFixed(2)}`}
          />
          <Stat
            label="Symbols"
            value={s.symbols.join(', ') || '—'}
            sub={`${s.symbols.length} 个`}
          />
          <Stat label="Poll interval" value={`${s.poll_interval_sec}s`} />
          <Stat
            label="Mode"
            value={isLive ? 'LIVE 实盘' : 'Testnet'}
            sub={isLive ? '已 arm' : '未 arm'}
            tone={isLive ? 'warn' : 'ok'}
          />
          <Stat
            label="Tier"
            value={tier === 'conservative' ? '保守默认' : '正常默认'}
            sub={tier === 'conservative' ? 'phase 2' : 'phase 3'}
          />
        </div>
        <div className="mt-4">
          <div className="flex justify-between text-xs font-mono text-slate-400 mb-1">
            <span>Loss budget consumed</span>
            <span>
              {s.loss_consumed_usdt.toFixed(2)} / {Math.abs(caps.daily_loss_cap_usdt)} USDT
            </span>
          </div>
          <div className="h-2 bg-slate-800 rounded overflow-hidden">
            <div
              className="h-full bg-rose-500"
              style={{
                width: `${Math.min(100, (s.loss_consumed_usdt / Math.abs(caps.daily_loss_cap_usdt)) * 100)}%`,
              }}
            />
          </div>
        </div>
      </Card>

      <Card title="控制">
        <div className="flex flex-wrap gap-3 items-center">
          {(status === 'idle' || status === 'stopped') && (
            <button
              onClick={() => {
                setConfirmText('')
                setShowConfirm(true)
              }}
              className={btnPrimary()}
            >
              ENABLE AI TRADER
            </button>
          )}
          {status === 'running' && (
            <button
              onClick={() => alert('would POST /pause')}
              className={btnSecondary()}
            >
              Pause
            </button>
          )}
          {status === 'paused' && (
            <button
              onClick={() => alert('would POST /resume')}
              className={btnPrimary()}
            >
              Resume
            </button>
          )}
          {status !== 'stopped' && status !== 'idle' && (
            <>
              {stopStep === 'idle' ? (
                <button
                  onClick={() => setStopStep('confirm')}
                  className={btnDanger('text-base px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white')}
                >
                  EMERGENCY STOP
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-rose-300">
                    确认停止所有未来的 AI ticks?
                  </span>
                  <button
                    onClick={() => {
                      setArmed(false)
                      setStopStep('idle')
                      alert('would POST /emergency-stop')
                    }}
                    className={btnDanger('text-base px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white')}
                  >
                    CONFIRM STOP
                  </button>
                  <button
                    onClick={() => setStopStep('idle')}
                    className={btnSecondary('text-xs')}
                  >
                    取消
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        {showConfirm && (
          <div className="mt-4 bg-slate-950 border border-amber-800 rounded p-4">
            <div className="text-amber-300 text-sm mb-2">
              {isLive
                ? '在 live (非 testnet) 模式下启用 AI Trader,需逐字输入以下确认短语:'
                : '当前为 testnet 模式 — 此处输入仅为示意,正式上线后 live 启用时会强制要求以下短语:'}
              <span className="font-mono ml-2 text-amber-100">{LIVE_ARM_PHRASE}</span>
            </div>
            <input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              className={inputCls('font-mono mb-2')}
              placeholder="type the phrase exactly"
              autoFocus
              spellCheck={false}
              autoComplete="off"
            />
            <div className="flex gap-2">
              <button
                disabled={!confirmMatches}
                onClick={() => {
                  if (!confirmMatches) return
                  setArmed(true)
                  setShowConfirm(false)
                  setConfirmText('')
                  // Apply conservative defaults on first live arm.
                  if (tier !== 'normal') {
                    setCaps({
                      max_order_quote_usdt: CONSERVATIVE_CAPS.max_order_quote_usdt,
                      daily_loss_cap_usdt: CONSERVATIVE_CAPS.daily_loss_cap_usdt,
                      daily_max_trades: CONSERVATIVE_CAPS.daily_max_trades,
                      max_position_per_symbol_usdt: caps.max_position_per_symbol_usdt,
                    })
                    setTier('conservative')
                  }
                }}
                className={btnPrimary('disabled:bg-slate-700 disabled:text-slate-500')}
              >
                ARM &amp; ENABLE
              </button>
              <button
                onClick={() => setShowConfirm(false)}
                className={btnSecondary()}
              >
                取消
              </button>
            </div>
            {confirmText.length > 0 && !confirmMatches && (
              <div className="mt-2 text-xs font-mono text-rose-400">
                输入必须严格等于 "{LIVE_ARM_PHRASE}"(无空格 / 大小写调整)
              </div>
            )}
          </div>
        )}
      </Card>

      <Card
        title="阈值"
        right={
          <span className="text-xs text-slate-500 font-mono">
            {isLive ? 'live · 锁定为保守默认' : 'testnet · 可编辑'}
          </span>
        }
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm font-mono">
          <ThresholdField
            label="Per-order cap (USDT)"
            value={caps.max_order_quote_usdt}
            disabled={isLive}
            onChange={(v) =>
              setCaps({ ...caps, max_order_quote_usdt: Number(v) || 0 })
            }
          />
          <ThresholdField
            label="Per-symbol position cap (USDT)"
            value={caps.max_position_per_symbol_usdt}
            disabled={isLive}
            onChange={(v) =>
              setCaps({
                ...caps,
                max_position_per_symbol_usdt: Number(v) || 0,
              })
            }
          />
          <ThresholdField
            label="Daily loss cap (USDT, 负数)"
            value={caps.daily_loss_cap_usdt}
            disabled={isLive}
            onChange={(v) =>
              setCaps({ ...caps, daily_loss_cap_usdt: Number(v) || 0 })
            }
          />
          <ThresholdField
            label="Daily max trades"
            value={caps.daily_max_trades}
            disabled={isLive}
            onChange={(v) =>
              setCaps({ ...caps, daily_max_trades: Number(v) || 0 })
            }
          />
        </div>
        {isLive && (
          <div className="mt-4 p-3 bg-slate-950 border border-amber-900/60 rounded flex items-center justify-between gap-4">
            <div className="text-xs font-mono text-slate-300">
              当前为保守默认 (per-order{' '}
              <span className="text-amber-300">
                {CONSERVATIVE_CAPS.max_order_quote_usdt}
              </span>{' '}
              USDT · daily loss{' '}
              <span className="text-amber-300">
                {CONSERVATIVE_CAPS.daily_loss_cap_usdt}
              </span>{' '}
              USDT · daily trades{' '}
              <span className="text-amber-300">
                {CONSERVATIVE_CAPS.daily_max_trades}
              </span>
              )。spec §11 phase 3 明确把"提高至正常默认"视为一次显式的人工操作。
            </div>
            {tier === 'conservative' && (
              <button
                onClick={raiseToNormalDefaults}
                className="bg-amber-600 hover:bg-amber-500 text-white font-medium px-3 py-2 rounded text-xs transition-colors whitespace-nowrap"
              >
                提升至正常默认
              </button>
            )}
            {tier === 'normal' && (
              <span className="text-xs font-mono text-emerald-400 whitespace-nowrap">
                已切换至正常默认 (per-order{' '}
                {NORMAL_CAPS.max_order_quote_usdt} · loss{' '}
                {NORMAL_CAPS.daily_loss_cap_usdt} · trades{' '}
                {NORMAL_CAPS.daily_max_trades})
              </span>
            )}
          </div>
        )}
        {!isLive && (
          <p className="mt-3 text-xs text-slate-500">
            正式接入后端后,此处阈值会通过 <code>/api/ai-trader/settings</code> 保存。
          </p>
        )}
      </Card>

      <Card title="Decisions (recent)">
        <div className="overflow-x-auto -mx-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-xs uppercase tracking-wide">
                <th className="px-3 py-2 text-left font-medium">Time</th>
                <th className="px-3 py-2 text-left font-medium">Symbol</th>
                <th className="px-3 py-2 text-left font-medium">Action</th>
                <th className="px-3 py-2 text-left font-medium">Outcome</th>
                <th className="px-3 py-2 text-right font-medium">Order</th>
                <th className="px-3 py-2 text-right font-medium">P&L</th>
                <th className="px-3 py-2 text-left font-medium">Note</th>
              </tr>
            </thead>
            <tbody>
              {aiDecisions.map((d) => {
                const expanded = expandedId === d.id
                return [
                  <tr
                    key={d.id}
                    className="border-t border-slate-800 cursor-pointer hover:bg-slate-800/40"
                    onClick={() => setExpandedId(expanded ? null : d.id)}
                  >
                    <td className="px-3 py-2 font-mono text-slate-400">
                      {d.ts}
                    </td>
                    <td className="px-3 py-2 font-mono">{d.symbol}</td>
                    <td className="px-3 py-2 font-mono">{d.action}</td>
                    <td className="px-3 py-2 font-mono">
                      <OutcomeBadge outcome={d.outcome} />
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {d.order_id ?? '—'}
                    </td>
                    <td
                      className={
                        'px-3 py-2 text-right font-mono ' +
                        (d.pnl_usdt == null
                          ? 'text-slate-500'
                          : d.pnl_usdt > 0
                            ? 'text-emerald-400'
                            : d.pnl_usdt < 0
                              ? 'text-rose-400'
                              : 'text-slate-400')
                      }
                    >
                      {d.pnl_usdt == null
                        ? '—'
                        : `${d.pnl_usdt >= 0 ? '+' : ''}${d.pnl_usdt.toFixed(2)}`}
                    </td>
                    <td className="px-3 py-2 text-slate-400 font-mono text-xs">
                      {d.error ??
                        (d.filled_qty
                          ? `${d.filled_qty} @ ${d.filled_price}`
                          : '—')}
                    </td>
                  </tr>,
                  expanded ? (
                    <tr
                      key={`${d.id}-detail`}
                      className="border-t border-slate-800 bg-slate-950"
                    >
                      <td colSpan={7} className="px-3 py-3">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
                          <DetailBlock label="Prompt" body={d.prompt} />
                          <DetailBlock label="Raw LLM response" body={d.raw_response} />
                          <DetailBlock label="Parsed JSON" body={d.parsed_json} />
                          <DetailBlock
                            label="Guard results"
                            body={d.guard_results
                              .map((g) => {
                                const mark = g.passed ? 'PASS' : 'FAIL'
                                return `[${mark}] ${g.name}: ${g.detail}`
                              })
                              .join('\n')}
                          />
                        </div>
                      </td>
                    </tr>
                  ) : null,
                ]
              })}
              {aiDecisions.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-3 py-8 text-center text-slate-400 text-sm"
                  >
                    暂无决策记录
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          点击行展开:prompt · raw LLM response · parsed JSON · guard results
        </p>
      </Card>

      <Card title="Symbols">
        <div className="flex flex-wrap gap-2 mb-3">
          {symbols.map((sym) => (
            <span
              key={sym}
              className="inline-flex items-center gap-1 px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs font-mono text-slate-200"
            >
              {sym}
              <button
                onClick={() => removeSymbol(sym)}
                className="text-slate-500 hover:text-rose-400 ml-1"
                title="移除"
              >
                ×
              </button>
            </span>
          ))}
          {symbols.length === 0 && (
            <span className="text-xs text-slate-500 font-mono">
              尚未添加任何交易对
            </span>
          )}
        </div>
        <div className="flex gap-2 items-center max-w-md">
          <select
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value)}
            className={inputCls('font-mono')}
          >
            <option value="">— 选择交易对 —</option>
            {symbolOptions
              .filter((s) => !symbols.includes(s))
              .map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
          </select>
          <button
            onClick={addSymbol}
            disabled={!newSymbol}
            className={btnPrimary('disabled:bg-slate-700 disabled:text-slate-500')}
          >
            添加
          </button>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          交易对白名单 — 仅这些交易对会被 LLM 评估
        </p>
      </Card>

      <div className="text-xs text-slate-500 font-mono">
        Mock shell — buttons above do not yet call the real{' '}
        <code>/api/ai-trader/*</code> routes.
      </div>
    </div>
  )
}

function Stat({
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
    <div className="bg-slate-950 border border-slate-800 rounded p-3">
      <div className="text-xs uppercase tracking-wide text-slate-400">
        {label}
      </div>
      <div
        className={'mt-1 text-base font-mono tabular-nums ' + valueColor}
      >
        {value}
      </div>
      {sub && (
        <div className="mt-0.5 text-[10px] text-slate-500 font-mono">{sub}</div>
      )}
    </div>
  )
}

function ThresholdField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string
  value: number
  disabled: boolean
  onChange: (v: string) => void
}) {
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1 font-sans">
        {label}
      </label>
      <input
        type="number"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className={
          inputCls('font-mono disabled:bg-slate-900 disabled:text-slate-500 disabled:cursor-not-allowed')
        }
      />
    </div>
  )
}

function OutcomeBadge({ outcome }: { outcome: AIDecisionRow['outcome'] }) {
  // placed blue · rejected yellow · error/no_trade grey
  const styles =
    outcome === 'placed'
      ? 'bg-sky-900/40 text-sky-300 border-sky-800'
      : outcome === 'rejected'
        ? 'bg-amber-900/40 text-amber-300 border-amber-800'
        : outcome === 'error'
          ? 'bg-rose-900/40 text-rose-300 border-rose-800'
          : 'bg-slate-800 text-slate-300 border-slate-700'
  return (
    <span
      className={
        'inline-block px-2 py-0.5 text-xs rounded border font-mono ' + styles
      }
    >
      {outcome}
    </span>
  )
}

function DetailBlock({ label, body }: { label: string; body: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">
        {label}
      </div>
      <pre className="bg-slate-900 border border-slate-800 rounded p-2 text-[11px] text-slate-300 whitespace-pre-wrap break-words max-h-40 overflow-auto">
        {body}
      </pre>
    </div>
  )
}
