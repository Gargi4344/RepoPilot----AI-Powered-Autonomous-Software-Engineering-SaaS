import { useEffect, useRef } from 'react'
import type { RunEvent } from '../types'

/** Subscribes to a backend SSE endpoint that emits named "run-event" frames. The browser's
 * EventSource reconnects automatically on a dropped connection, and the backend always
 * replays history before tailing live, so a reconnect never loses events. */
export function useEventStream(url: string | null, onEvent: (event: RunEvent) => void) {
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    if (!url) return

    // withCredentials so the session cookie rides along -- same-origin through the Vite
    // dev proxy today, but this also makes the stream work correctly if frontend/backend
    // are ever deployed on genuinely different origins.
    const source = new EventSource(url, { withCredentials: true })
    const handleMessage = (raw: MessageEvent) => {
      try {
        handlerRef.current(JSON.parse(raw.data) as RunEvent)
      } catch {
        // ignore a malformed frame rather than tearing down the whole stream
      }
    }
    source.addEventListener('run-event', handleMessage)

    return () => {
      source.removeEventListener('run-event', handleMessage)
      source.close()
    }
  }, [url])
}
