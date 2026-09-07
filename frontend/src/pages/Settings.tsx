import { useEffect, useState } from 'react'

type Settings = {
  binance_testnet: boolean
  has_api_key: boolean
  has_api_secret: boolean
}

type AISettings = {
  market_type: 'spot' | 'futures'
  leverage: number | null
  margin_type: 'ISOLATED' | 'CROSSED'
}

export function Settings() {
  const [testnet, setTestnet] = useState(true)
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [current, setCurrent] = useState<Settings | null>(null)
  const [aiSettings, setAISettings] = useState<AISettings | null>(null)
  const [marketType, setMarketType] = useState<'spot' | 'futures'>('spot')
  const [leverage, setLeverage] = useState<number>(5)
  const [marginType, setMarginType] = useState<'ISOLATED' | 'CROSSED'>('ISOLATED')
  const [msg, setMsg] = useState<string>('')
  const [msgTone, setMsgTone] = useState<'ok' | 'err' | 'info'>('info')
  const [busy, setBusy] = useState(false)

  const reload = async () => {
    try {
      const r = await fetch('/api/settings')
      const d: Settings = await r.json()
      setCurrent(d)
      setTestnet(d.binance_testnet)
    } catch (e) {
      setMsg('加载设置失败: ' + String(e))
      setMsgTone('err')
    }
    try {
      const r = await fetch('/api/ai-trader/status')
      if (r.ok) {
        const d = await r.json()
        if (d.market_type) {
          setMarketType(d.market_type)
          setAISettings({
            market_type: d.market_type,
            leverage: d.leverage ?? null,
            margin_type: d.margin_type ?? 'ISOLATED',
          })
        }
        if (d.leverage) setLeverage(d.leverage)
        if (d.margin_type) setMarginType(d.margin_type)
      }
    } catch {
      // AI Trader settings are optional — silent fallback.
    }
  }

  useEffect(() => {
    reload()
  }, [])

  const save = async () => {
    setBusy(true)
    setMsg('')
    // Only send fields the user actually touched. Empty string = "clear".
    // Without this guard, saving just the testnet toggle would wipe stored
    // credentials (backend treats "" as delete).
    const body: Record<string, unknown> = { binance_testnet: testnet }
    if (apiKey.length > 0) body.binance_api_key = apiKey
    else if (apiKey === '__clear__') body.binance_api_key = ''
    if (apiSecret.length > 0) body.binance_api_secret = apiSecret
    else if (apiSecret === '__clear__') body.binance_api_secret = ''
    try {
      const r = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json()
      if (d.ok) {
        setMsg('✓ 保存成功 (密钥已加密存入 Windows 凭据管理器)')
        setMsgTone('ok')
        setApiKey('')
        setApiSecret('')
        await reload()
      } else {
        setMsg('保存失败: ' + JSON.stringify(d))
        setMsgTone('err')
      }
    } catch (e) {
      setMsg('保存出错: ' + String(e))
      setMsgTone('err')
    } finally {
      setBusy(false)
    }
  }

  const saveAISettings = async () => {
    setBusy(true)
    setMsg('')
    try {
      const r = await fetch('/api/ai-trader/settings', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          market_type: marketType,
          leverage: marketType === 'futures' ? leverage : null,
          margin_type: marginType,
        }),
      })
      const d = await r.json()
      if (d.ok) {
        setMsg('✓ AI Trader 模式已更新')
        setMsgTone('ok')
        await reload()
      } else {
        setMsg('保存失败: ' + JSON.stringify(d))
        setMsgTone('err')
      }
    } catch (e) {
      setMsg('保存出错: ' + String(e))
      setMsgTone('err')
    } finally {
      setBusy(false)
    }
  }

  const test = async () => {
    setBusy(true)
    setMsg('正在测试连接 Binance …')
    setMsgTone('info')
    try {
      const r = await fetch('/api/settings/test-binance', { method: 'POST' })
      const d = await r.json()
      if (d.ok) {
        setMsg(`✓ 连通成功 (canTrade=${d.can_trade}, testnet=${d.testnet})`)
        setMsgTone('ok')
      } else {
        setMsg('✗ 失败: ' + (d.error || '未知错误'))
        setMsgTone('err')
      }
    } catch (e) {
      setMsg('请求出错: ' + String(e))
      setMsgTone('err')
    } finally {
      setBusy(false)
    }
  }

  const msgClass =
    msgTone === 'ok'
      ? 'border-emerald-900/60 text-emerald-300'
      : msgTone === 'err'
      ? 'border-red-900/60 text-red-300'
      : 'border-slate-800 text-slate-300'

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold">设置</h2>
        <p className="text-slate-400 text-sm mt-1">
          配置 Binance API Key 与 Testnet 模式
        </p>
      </div>

      {current && (
        <div className="p-4 bg-slate-900 rounded-lg border border-slate-800">
          <div className="text-sm text-slate-400 mb-2">当前状态</div>
          <div className="flex flex-wrap gap-4 text-sm">
            <span>
              Testnet:{' '}
              <b>{current.binance_testnet ? '✅ 启用' : '❌ 未启用'}</b>
            </span>
            <span>
              API Key:{' '}
              <b>{current.has_api_key ? '✅ 已设置' : '❌ 未设置'}</b>
            </span>
            <span>
              Secret:{' '}
              <b>{current.has_api_secret ? '✅ 已设置' : '❌ 未设置'}</b>
            </span>
            {aiSettings && (
              <>
                <span>
                  Market:{' '}
                  <b>{aiSettings.market_type === 'futures' ? '⚡ USDⓈ-M 期货' : '💰 现货'}</b>
                </span>
                {aiSettings.market_type === 'futures' && aiSettings.leverage != null && (
                  <span>
                    Leverage:{' '}
                    <b>{aiSettings.leverage}x</b>
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      )}

      <div className="space-y-5 bg-slate-900 p-6 rounded-lg border border-slate-800">
        <h3 className="text-base font-semibold">Binance 凭据</h3>

      <div className="space-y-5 bg-slate-900 p-6 rounded-lg border border-slate-800">
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={testnet}
            onChange={(e) => setTestnet(e.target.checked)}
            className="w-4 h-4"
          />
          <span>使用 Testnet (推荐,不影响真实资金)</span>
        </label>

        <div>
          <label className="block text-sm text-slate-400 mb-1">
            API Key
          </label>
          <input
            type="text"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              current?.has_api_key
                ? '已设置 (留空表示不修改)'
                : '64 字符的 API Key'
            }
            className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 font-mono text-sm"
          />
        </div>

        <div>
          <label className="block text-sm text-slate-400 mb-1">
            API Secret
          </label>
          <input
            type="password"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            placeholder={
              current?.has_api_secret
                ? '已设置 (留空表示不修改)'
                : '64 字符的 Secret'
            }
            className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 font-mono text-sm"
          />
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={save}
            disabled={busy}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 px-4 py-2 rounded font-medium"
          >
            保存
          </button>
          <button
            onClick={test}
            disabled={busy}
            className="bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 px-4 py-2 rounded font-medium"
          >
            测试连通
          </button>
        </div>

        {msg && (
          <div
            className={`mt-3 p-3 bg-slate-950 border rounded text-sm font-mono ${msgClass}`}
          >
            {msg}
          </div>
        )}
      </div>

      <div className="space-y-5 bg-slate-900 p-6 rounded-lg border border-slate-800">
        <div>
          <h3 className="text-base font-semibold">AI Trader 模式</h3>
          <p className="text-slate-400 text-xs mt-1">
            现货模式无杠杆;期货模式启用固定杠杆 + 3 个额外风控 (杠杆验证 / 保证金检查 / 强平距离)
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">市场</label>
          <div className="flex gap-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="market_type"
                value="spot"
                checked={marketType === 'spot'}
                onChange={() => setMarketType('spot')}
              />
              <span>现货 (Spot)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="market_type"
                value="futures"
                checked={marketType === 'futures'}
                onChange={() => setMarketType('futures')}
              />
              <span>USDⓈ-M 期货</span>
            </label>
          </div>
        </div>

        {marketType === 'futures' && (
          <>
            <div>
              <label className="block text-sm font-medium mb-1">
                杠杆倍数 (1-125)
              </label>
              <input
                type="number"
                min={1}
                max={125}
                value={leverage}
                onChange={(e) => setLeverage(parseInt(e.target.value || '5', 10))}
                className="w-32 bg-slate-800 border border-slate-700 rounded px-3 py-2 font-mono"
              />
              <p className="text-slate-500 text-xs mt-1">
                ⚠️ 高杠杆放大收益也放大亏损;建议先在 Testnet 验证
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">保证金模式</label>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="margin_type"
                    value="ISOLATED"
                    checked={marginType === 'ISOLATED'}
                    onChange={() => setMarginType('ISOLATED')}
                  />
                  <span>逐仓 (ISOLATED)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="margin_type"
                    value="CROSSED"
                    checked={marginType === 'CROSSED'}
                    onChange={() => setMarginType('CROSSED')}
                  />
                  <span>全仓 (CROSSED)</span>
                </label>
              </div>
            </div>
          </>
        )}

        <div className="flex gap-3 pt-2">
          <button
            onClick={saveAISettings}
            disabled={busy}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 px-4 py-2 rounded font-medium"
          >
            保存 AI Trader 设置
          </button>
        </div>
      </div>
    </div>
  )
}

export default Settings