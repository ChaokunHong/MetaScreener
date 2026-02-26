import { useEffect, useRef, useState, useCallback } from 'react'

interface ScreeningProgress {
  current: number
  total: number
  decision?: string
  record_id?: string
}

export function useScreeningProgress(sessionId: string | null) {
  const [progress, setProgress] = useState<ScreeningProgress | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  const connect = useCallback(() => {
    if (!sessionId) return

    const protocol =
      window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(
      `${protocol}//${window.location.host}/api/screening/progress/${sessionId}`,
    )

    ws.onopen = () => setIsConnected(true)
    ws.onclose = () => setIsConnected(false)
    ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data as string) as ScreeningProgress
        setProgress(data)
      } catch {
        // ignore malformed messages
      }
    }

    wsRef.current = ws
  }, [sessionId])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    setIsConnected(false)
  }, [])

  useEffect(() => {
    return () => {
      wsRef.current?.close()
    }
  }, [])

  return { progress, isConnected, connect, disconnect }
}
