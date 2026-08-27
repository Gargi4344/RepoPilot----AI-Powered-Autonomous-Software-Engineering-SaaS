import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Container } from '../components/ui/Container'
import { Card } from '../components/ui/Card'
import { DashboardNav } from '../components/dashboard/DashboardNav'
import { useEventStream } from '../hooks/useEventStream'
import { formatEventTime, isEventLevelAttention, splitToolMessage } from '../lib/eventFormat'
import { ArrowUpRight } from 'lucide-react'
import type { RunEvent } from '../types'

const MAX_EVENTS = 300

export function ActivityPage() {
  const [events, setEvents] = useState<RunEvent[]>([])
  const seenEventIds = useRef(new Set<number>())
  const logRef = useRef<HTMLDivElement>(null)

  useEventStream('/api/v1/activity/stream', (event) => {
    if (seenEventIds.current.has(event.id)) return
    seenEventIds.current.add(event.id)
    setEvents((prev) => [...prev, event].slice(-MAX_EVENTS))
  })

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [events.length])

  return (
    <div className="landing-theme min-h-screen bg-background font-sans text-foreground">
      <DashboardNav />

      <main className="py-10">
        <Container>
          <div className="flex items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-foreground">Activity</h1>
              <p className="mt-1.5 text-sm text-muted-foreground">Live feed across every run, as it happens.</p>
            </div>
            <span className="flex items-center gap-1.5 text-xs text-accent">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-70" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
              </span>
              LIVE
            </span>
          </div>

          <div className="mt-8">
            {events.length === 0 ? (
              <div className="rounded-md border border-dashed border-border px-6 py-16 text-center text-sm text-muted-foreground">
                No activity yet. Start a run to see it here in real time.
              </div>
            ) : (
              <Card className="overflow-hidden">
                <div
                  ref={logRef}
                  className="max-h-[calc(100vh-260px)] overflow-y-auto px-6 py-5 font-mono text-[13px] leading-relaxed"
                >
                  {events.map((event) => {
                    const { command, output } = splitToolMessage(event.message)
                    const isError = isEventLevelAttention(event.level)
                    return (
                      <div key={event.id} className="mb-5 flex gap-4 border-b border-border pb-5 last:mb-0 last:border-b-0 last:pb-0">
                        <span className="w-16 shrink-0 pt-0.5 text-muted-foreground">{formatEventTime(event.ts)}</span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span
                              className={`inline-block rounded px-1.5 py-0.5 text-[10.5px] font-medium tracking-wide ${
                                isError ? 'bg-warn/10 text-warn' : 'bg-accent/10 text-accent'
                              }`}
                            >
                              {event.phase.toUpperCase()}
                            </span>
                            <Link
                              to={`/runs/${event.run_id}`}
                              className="flex shrink-0 items-center gap-1 font-sans text-xs text-muted-foreground transition-colors hover:text-foreground"
                            >
                              run {event.run_id.slice(0, 8)}
                              <ArrowUpRight className="h-3 w-3" />
                            </Link>
                          </div>
                          <div className="mt-1.5 space-y-0.5">
                            {command && <p className="text-accent">$ {command}</p>}
                            <p className={command ? 'whitespace-pre-wrap text-muted-foreground' : 'text-muted-foreground'}>{output}</p>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </Card>
            )}
          </div>
        </Container>
      </main>
    </div>
  )
}
