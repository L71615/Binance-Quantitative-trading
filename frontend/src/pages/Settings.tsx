import { useEffect, useState } from 'react'

type Settings = {
  binance_testnet: boolean
  has_api_key: boolean
  has_api_secret: boolean
}

export function Settings() {
  const [testnet, setTestnet] = useState(true)
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [current, setCurrent] = useState<Settings | null>(null)
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
  }

  useEffect(() => {
    reload()
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
    </div>
  )
}

export default Settings