import { useState } from 'react'
import { initialSettings } from '../data'
import type { SettingsShape } from '../data'
import { Card, btnPrimary, btnSecondary, inputCls } from '../ui'

export function Settings() {
  const [s, setS] = useState<SettingsShape>(initialSettings)
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  // LLM API key follows the same convention as the Binance secret above:
  // the value never round-trips from the fixture, it lives in a write-only
  // local field and `hasLlmApiKey` is the only thing persisted/rendered.
  const [llmApiKey, setLlmApiKey] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const save = () => {
    setBusy(true)
    setMsg('')
    setTimeout(() => {
      setBusy(false)
      const updated = {
        ...s,
        hasApiKey: s.hasApiKey || apiKey.length > 0,
        hasApiSecret: s.hasApiSecret || apiSecret.length > 0,
        hasLlmApiKey: s.hasLlmApiKey || llmApiKey.length > 0,
      }
      setS(updated)
      setApiKey('')
      setApiSecret('')
      setLlmApiKey('')
      setMsg('✓ 已保存 (mock,未实际写入凭据管理器)')
    }, 300)
  }

  const test = () => {
    setBusy(true)
    setMsg('正在测试连接 Binance (mock) …')
    setTimeout(() => {
      setBusy(false)
      setMsg('✓ 连通成功 (canTrade=true, testnet=' + s.testnet + ')')
    }, 500)
  }

  // Backend lifespan only constructs the LLM client when BOTH base_url and
  // api_key are present, so the wired flag mirrors that conjunction.
  const hasLlmBaseUrl = (s.llmBaseUrl ?? '').trim().length > 0
  const llmWired = (s.hasLlmApiKey ?? false) && hasLlmBaseUrl

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between sticky top-0 bg-slate-950/80 backdrop-blur -mx-6 px-6 py-3 -mt-6 z-10 border-b border-slate-800">
        <div>
          <h2 className="text-xl font-semibold">设置</h2>
          <p className="text-xs text-slate-500 mt-1 font-mono">仅本地保存 (mock) · 不发送请求</p>
        </div>
        <button onClick={save} disabled={busy} className={btnPrimary('disabled:bg-slate-700')}>
          {busy ? '保存中 …' : '保存'}
        </button>
      </div>

      {msg && (
        <div className="p-3 bg-slate-900 border border-slate-800 rounded text-sm font-mono text-slate-300">
          {msg}
        </div>
      )}

      <Card title="API Key">
        <div className="space-y-4">
          <div className="flex gap-4 text-xs font-mono">
            <Badge ok={s.hasApiKey}>API Key {s.hasApiKey ? '已设置' : '未设置'}</Badge>
            <Badge ok={s.hasApiSecret}>Secret {s.hasApiSecret ? '已设置' : '未设置'}</Badge>
            <Badge ok={s.testnet}>Testnet</Badge>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                API Key
                <span className="text-slate-600 ml-1">(留空表示不修改)</span>
              </label>
              <input
                type="text"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={s.hasApiKey ? '•••••••• 已设置' : '64 字符的 API Key'}
                className={inputCls('font-mono')}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                API Secret
                <span className="text-slate-600 ml-1">(留空表示不修改)</span>
              </label>
              <input
                type="password"
                value={apiSecret}
                onChange={(e) => setApiSecret(e.target.value)}
                placeholder={s.hasApiSecret ? '•••••••• 已设置' : '64 字符的 Secret'}
                className={inputCls('font-mono')}
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={test} disabled={busy} className={btnSecondary('disabled:bg-slate-900')}>
              测试连通
            </button>
          </div>
        </div>
      </Card>

      <Card
        title="LLM Configuration"
        right={
          <span className="text-xs font-mono text-slate-500">
            AI Trader · /api/ai/analyze 共用同一份配置
          </span>
        }
      >
        <div className="space-y-4">
          <div className="flex flex-wrap gap-4 text-xs font-mono">
            <Badge ok={s.hasLlmApiKey ?? false}>
              API Key {s.hasLlmApiKey ? '已设置' : '未设置'}
            </Badge>
            <Badge ok={hasLlmBaseUrl}>
              Base URL {hasLlmBaseUrl ? '已设置' : '未设置'}
            </Badge>
            <Badge ok={llmWired}>llm_wired {llmWired ? 'true' : 'false'}</Badge>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                LLM API Key
                <span className="text-slate-600 ml-1">(留空表示不修改)</span>
              </label>
              <input
                type="password"
                value={llmApiKey}
                onChange={(e) => setLlmApiKey(e.target.value)}
                placeholder={s.hasLlmApiKey ? '•••••••• 已设置' : 'sk-...'}
                className={inputCls('font-mono')}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Base URL
                <span className="text-slate-600 ml-1">(必填 · 需与 API Key 同时提供)</span>
              </label>
              <input
                type="text"
                value={s.llmBaseUrl ?? ''}
                onChange={(e) => setS({ ...s, llmBaseUrl: e.target.value })}
                placeholder="https://api.example.com/v1"
                className={inputCls('font-mono')}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Model
                <span className="text-slate-600 ml-1">(留空则使用后端默认值)</span>
              </label>
              <input
                type="text"
                value={s.llmModel ?? ''}
                onChange={(e) => setS({ ...s, llmModel: e.target.value })}
                placeholder="deepseek-chat"
                className={inputCls('font-mono')}
              />
            </div>
          </div>

          {!llmWired && (
            <div className="p-3 bg-amber-950/30 border border-amber-900/60 rounded text-xs font-mono text-amber-200">
              LLM 未接通 — 后端只有在 <code>llm_base_url</code> 与{' '}
              <code>llm_api_key</code> 两者都存在时才会创建 LLM 客户端,缺一不可。
              当前 <code>broker_wired: true</code> · <code>llm_wired: false</code> ·{' '}
              <code>wiring_ok: false</code>,<code>GET /api/ai-trader/dry-run</code>{' '}
              会返回 503,直到这两项都补齐。
            </div>
          )}

          <p className="text-xs text-slate-500">
            凭据由后端写入 OS keyring (service <code>binance-spot-grid-bot</code>,slug{' '}
            <code>llm_api_key</code> / <code>llm_base_url</code> /{' '}
            <code>llm_model</code>) — 全局只有一份 LLM 配置,AI Trader 与{' '}
            <code>/api/ai/analyze</code> 共用,不区分两套。
          </p>
        </div>
      </Card>

      <Card title="Testnet">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={s.testnet}
            onChange={(e) => setS({ ...s, testnet: e.target.checked })}
            className="w-4 h-4"
          />
          <div>
            <div className="text-sm">使用 Testnet</div>
            <div className="text-xs text-slate-500">
              推荐用于开发与测试,不影响真实资金
            </div>
          </div>
        </label>
      </Card>

      <Card title="默认参数">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">网格默认值</label>
            <input
              type="number"
              min={2}
              max={200}
              value={s.defaultGridCount}
              onChange={(e) =>
                setS({ ...s, defaultGridCount: parseInt(e.target.value || '0', 10) || 0 })
              }
              className={inputCls('font-mono')}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">默认模式</label>
            <select
              value={s.defaultMode}
              onChange={(e) => setS({ ...s, defaultMode: e.target.value as 'arithmetic' | 'geometric' })}
              className={inputCls()}
            >
              <option value="arithmetic">等差 (arithmetic)</option>
              <option value="geometric">等比 (geometric)</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Polling interval (ms)</label>
            <input
              type="number"
              min={500}
              max={60000}
              step={100}
              value={s.pollingIntervalMs}
              onChange={(e) =>
                setS({ ...s, pollingIntervalMs: parseInt(e.target.value || '0', 10) || 0 })
              }
              className={inputCls('font-mono')}
            />
          </div>
        </div>
      </Card>

      <Card title="风险">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">最大网格数</label>
            <input
              type="number"
              min={1}
              max={50}
              value={s.maxGrids}
              onChange={(e) => setS({ ...s, maxGrids: parseInt(e.target.value || '0', 10) || 0 })}
              className={inputCls('font-mono')}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">每网格最大仓位 (USDT)</label>
            <input
              type="number"
              min={0}
              step={100}
              value={s.maxPositionSizeUsdt}
              onChange={(e) =>
                setS({ ...s, maxPositionSizeUsdt: parseFloat(e.target.value || '0') || 0 })
              }
              className={inputCls('font-mono')}
            />
          </div>
        </div>
      </Card>
    </div>
  )
}

function Badge({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span
      className={
        'inline-flex items-center gap-1.5 px-2 py-1 rounded border ' +
        (ok
          ? 'bg-emerald-900/40 text-emerald-300 border-emerald-800'
          : 'bg-slate-800 text-slate-400 border-slate-700')
      }
    >
      <span
        className={
          'inline-block w-1.5 h-1.5 rounded-full ' + (ok ? 'bg-emerald-400' : 'bg-slate-500')
        }
      />
      {children}
    </span>
  )
}