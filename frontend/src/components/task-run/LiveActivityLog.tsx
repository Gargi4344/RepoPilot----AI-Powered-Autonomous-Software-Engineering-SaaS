import { useEffect, useRef } from 'react'
import { Card } from '../ui/Card'
import { formatEventTime, isEventLevelAttention, splitToolMessage } from '../../lib/eventFormat'
import type { RunEvent } from '../../types'

export function LiveActivityLog({ events, isLive }: { events: RunEvent[]; isLive: boolean }) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [events.length])

  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <span className="text-xs font-medium tracking-[0.15em] text-muted-foreground">LIVE ACTIVITY</span>
        {isLive && (
          <span className="flex items-center gap-1.5 text-xs text-accent">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-70" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
            </span>
            LIVE
          </span>
        )}
      </div>

      <div ref={scrollRef} className="max-h-[560px] flex-1 overflow-y-auto px-6 py-5 font-mono text-[13px] leading-relaxed">
        {events.length === 0 ? (
          <p className="text-muted-foreground">Waiting for activity…</p>
        ) : (
          events.map((event) => {
            const { command, output } = splitToolMessage(event.message)
            const isError = isEventLevelAttention(event.level)
            return (
              <div key={event.id} className="mb-5 flex gap-4 last:mb-0">
                <span className="w-16 shrink-0 pt-0.5 text-muted-foreground">{formatEventTime(event.ts)}</span>
                <div className="min-w-0 flex-1">
                  <span
                    className={`inline-block rounded px-1.5 py-0.5 text-[10.5px] font-medium tracking-wide ${
                      isError ? 'bg-warn/10 text-warn' : 'bg-accent/10 text-accent'
                    }`}
                  >
                    {event.phase.toUpperCase()}
                  </span>
                  <div className="mt-1.5 space-y-0.5">
                    {command && <p className="text-accent">$ {command}</p>}
                    <p className={command ? 'whitespace-pre-wrap text-muted-foreground' : 'text-muted-foreground'}>{output}</p>
                  </div>
                </div>
              </div>
            )
          })
        )}
        {isLive && <span className="ml-[80px] inline-block h-4 w-2 bg-foreground animate-blink" />}
      </div>
    </Card>
  )
}
