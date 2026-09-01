import { useEffect, useRef } from 'react'

/**
 * Subscribe to the backend realtime WebSocket (`/ws/realtime`).
 *
 * Behaviour matches the plan spec:
 *  - onmessage: parse JSON and invoke `onEvent`.
 *  - onclose:   wait 1s, then reload the page so the next mount re-establishes
 *               a fresh connection. This keeps the SPA in sync with backend
 *               restarts without any explicit reconnect state machine.
 *  - onerror:   log to console; close will follow.
 */
export function useWebSocket(onEvent: (data: unknown) => void) {
  // Keep the latest callback in a ref so we don't re-subscribe on every render.
  const ref = useRef(onEvent)
  ref.current = onEvent

  useEffect(() => {
    const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/realtime`
    const ws = new WebSocket(url)
    ws.onmessage = (ev) => {
      try {
        ref.current(JSON.parse(ev.data))
      } catch (e) {
        console.warn('[ws] non-JSON message', e)
      }
    }
    ws.onerror = (e) => {
      console.warn('[ws] error', e)
    }
    ws.onclose = () => {
      // Spec: reload after 1s so the next mount reconnects from a clean slate.
      setTimeout(() => location.reload(), 1000)
    }
    return () => ws.close()
  }, [])
}
