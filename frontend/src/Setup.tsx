import { useEffect, useState } from 'react'

type Settings = {
  binance_testnet: boolean
  has_api_key: boolean
  has_api_secret: boolean
}

export function Setup() {
  const [testnet, setTestnet] = useState(true)
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [settings, setSettings] = useState<Settings | null>(null)
  const [msg, setMsg] = useState<string>('')
  const [busy, setBusy] = useState(false)

  // Load current settings on mount
  useEffect(() => {
    fetch('/api/settings')
      .then((r) => r.json())
      .then((d: Settings) => {
        setSettings(d)
        setTestnet(d.binance_testnet)
      })
      .catch(() => setMsg('加载设置失败 — 后端没启动?确保 uvicorn 在 8000'))
  }, [])

  const save = async () => {
    setBusy(true)
    setMsg('')
    try {
      const r = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          binance_testnet: testnet,
          binance_api_key: apiKey || '',
          binance_api_secret: apiSecret || '',
        }),
      })
      const d = await r.json()
      if (d.ok) {
        setMsg('✓ 保存成功 (密钥已加密存入 Windows 凭据管理器)')
        setApiKey('')
        setApiSecret('')
        const refreshed = await fetch('/api/settings').then((r) => r.json())
        setSettings(refreshed)
      } else {
        setMsg('保存失败: ' + JSON.stringify(d))
      }
    } catch (e) {
      setMsg('保存出错: ' + String(e))
    } finally {
      setBusy(false)
    }
  }

  const test = async () => {
    setBusy(true)
    setMsg('正在测试连接 Binance …')
    try {
      const r = await fetch('/api/settings/test-binance', { method: 'POST' })
      const d = await r.json()
      if (d.ok) {
        setMsg(`✓ 连通成功 (canTrade=${d.can_trade}, testnet=${d.testnet})`)
      } else {
        setMsg('✗ 失败: ' + (d.error || '未知错误'))
      }
    } catch (e) {
      setMsg('请求出错: ' + String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">币安现货网格交易平台</h1>
        <p className="text-slate-400 mb-8">第一步: 配置你的 Binance API Key</p>

        {settings && (
          <div className="mb-6 p-4 bg-slate-900 rounded-lg border border-slate-800">
            <div className="text-sm text-slate-400 mb-1">当前状态</div>
            <div className="flex gap-4 text-sm">
              <span>Testnet: <b>{settings.binance_testnet ? '✅' : '❌'}</b></span>
              <span>API Key: <b>{settings.has_api_key ? '✅ 已设置' : '❌ 未设置'}</b></span>
              <span>Secret: <b>{settings.has_api_secret ? '✅ 已设置' : '❌ 未设置'}</b></span>
            </div>
          </div>
        )}

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
            <label className="block text-sm text-slate-400 mb-1">API Key</label>
            <input
              type="text"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={settings?.has_api_key ? '已设置 (留空表示不修改)' : '64 字符的 API Key'}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 font-mono text-sm"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">API Secret</label>
            <input
              type="password"
              value={apiSecret}
              onChange={(e) => setApiSecret(e.target.value)}
              placeholder={settings?.has_api_secret ? '已设置 (留空表示不修改)' : '64 字符的 Secret'}
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
            <div className="mt-3 p-3 bg-slate-950 border border-slate-800 rounded text-sm font-mono">
              {msg}
            </div>
          )}
        </div>

        <details className="mt-8 text-sm text-slate-400">
          <summary className="cursor-pointer hover:text-slate-200">如何申请 Testnet API Key?</summary>
          <ol className="mt-3 space-y-1 list-decimal list-inside">
            <li>访问 https://testnet.binancefuture.com (注意是 spot testnet,实际是 testnet.binance.vision)</li>
            <li>用 GitHub 登录</li>
            <li>生成 HMAC SHA256 Key + Secret</li>
            <li>粘贴到上方表单,点击"测试连通"</li>
          </ol>
        </details>
      </div>
    </div>
  )
}