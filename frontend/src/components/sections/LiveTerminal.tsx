import { useEffect, useState } from 'react'
import { cn } from '../../lib/cn'
import { useInView, usePrefersReducedMotion } from '../../lib/motion'
import { Card, CardLabel } from '../ui/Card'
import { Container } from '../ui/Container'

type Line = { tone: 'cmd' | 'ok' | 'info' | 'warn' | 'dim'; text: string }

const lines: Line[] = [
  { tone: 'cmd', text: 'pr-engineer analyze github.com/acme/checkout' },
  { tone: 'dim', text: 'worktree: created isolated branch pr-engineer/rotate-session-tokens' },
  { tone: 'info', text: 'baseline: running checks before any changes' },
  { tone: 'dim', text: 'baseline: eslint exited 1 (pre-existing, not required to fix)' },
  { tone: 'dim', text: 'coding: attempt 1/3 -- editing src/auth/session.ts' },
  { tone: 'ok', text: 'test: pytest exited 0 -- 142 passing' },
  { tone: 'warn', text: 'review: flagged (low) -- diff stays within task scope' },
  { tone: 'ok', text: 'commit: a9f2c1 feat(auth): rotate session tokens' },
  { tone: 'info', text: 'pr: opened draft PR #482 -- awaiting human review' },
  { tone: 'dim', text: 'complete: run finished with status pr_open' },
]

export function LiveTerminal() {
  const reduced = usePrefersReducedMotion()
  const { ref, inView } = useInView<HTMLDivElement>(0.3)
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!inView) return
    if (reduced) {
      setCount(lines.length)
      return
    }
    const id = setInterval(() => {
      setCount((c) => (c >= lines.length ? c : c + 1))
    }, 700)
    return () => clearInterval(id)
  }, [inView, reduced])

  return (
    <section className="section-seam py-20 md:py-28" id="terminal">
      <Container>
        <div className="mx-auto max-w-2xl text-center">
          <CardLabel tone="muted" className="justify-center">
            <span className="h-1 w-1 rounded-full bg-accent" />
            Live logs
          </CardLabel>
          <h2 className="mt-5 text-[clamp(1.9rem,4.6vw,3rem)] leading-[1.05] font-semibold tracking-[-0.02em]">
            Fully auditable, line by line
          </h2>
          <p className="mt-4 text-muted-foreground">
            Every decision, edit and test run is streamed live to the dashboard as it happens.
          </p>
        </div>

        <Card className="mt-14 overflow-hidden bg-background/90">
          <div className="flex items-center gap-3 border-b border-border bg-surface/60 px-4 py-3">
            <div className="flex gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-muted" />
              <span className="h-2.5 w-2.5 rounded-full bg-muted" />
              <span className="h-2.5 w-2.5 rounded-full bg-muted" />
            </div>
            <p className="min-w-0 flex-1 truncate text-center font-mono text-[0.7rem] text-muted-foreground">
              pr-engineer &mdash; acme/checkout &mdash; run activity
            </p>
            <span className="font-mono text-[0.65rem] tracking-widest text-accent uppercase">live</span>
          </div>

          <div ref={ref} className="min-h-[340px] space-y-2 px-5 py-6 font-mono text-[0.78rem] leading-relaxed sm:px-7 sm:text-[0.83rem]">
            {lines.slice(0, count).map((l, i) => (
              <p key={i} className="animate-rise">
                <span className="mr-3 text-muted-foreground/40 select-none">{String(i + 1).padStart(2, '0')}</span>
                {l.tone === 'cmd' && <span className="mr-2 text-accent">&#10095;</span>}
                <span
                  className={cn(
                    l.tone === 'cmd' && 'text-foreground',
                    l.tone === 'ok' && 'text-accent',
                    l.tone === 'info' && 'text-info',
                    l.tone === 'warn' && 'text-warn',
                    l.tone === 'dim' && 'text-muted-foreground',
                  )}
                >
                  {l.text}
                </span>
              </p>
            ))}
            {count < lines.length && (
              <p>
                <span className="mr-3 text-muted-foreground/40 select-none">{String(count + 1).padStart(2, '0')}</span>
                <span className="inline-block h-3.5 w-2 translate-y-0.5 bg-accent animate-blink" />
              </p>
            )}
          </div>
        </Card>
      </Container>
    </section>
  )
}
