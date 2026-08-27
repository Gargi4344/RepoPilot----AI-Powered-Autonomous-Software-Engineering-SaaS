import { useEffect, useRef, useState } from 'react'
import { cn } from '../../lib/cn'
import { useInView, usePrefersReducedMotion } from '../../lib/motion'
import { Card, CardLabel } from '../ui/Card'
import { Container } from '../ui/Container'

const stages = [
  { label: 'analyze', detail: 'Reading the repo for real, low-risk work' },
  { label: 'approve', detail: 'Waiting for your explicit go-ahead' },
  { label: 'code', detail: 'Editing src/auth/session.ts' },
  { label: 'test', detail: '142 tests passing' },
  { label: 'draft PR', detail: 'Opened for your review' },
]

export function LiveCommit() {
  const reduced = usePrefersReducedMotion()
  const { ref, inView } = useInView<HTMLDivElement>(0.4)
  const [stage, setStage] = useState(0)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!inView || reduced) return
    timer.current = setInterval(() => setStage((s) => (s + 1) % stages.length), 2100)
    return () => {
      if (timer.current) clearInterval(timer.current)
    }
  }, [inView, reduced])

  const progress = ((stage + 0.5) / stages.length) * 100
  const current = stages[stage]!

  return (
    <section className="section-seam py-20 md:py-28" id="live-commit">
      <Container>
        <div ref={ref} className="mx-auto max-w-2xl text-center">
          <CardLabel tone="muted" className="justify-center">
            <span className="h-1 w-1 rounded-full bg-accent" />
            Live commit
          </CardLabel>
          <h2 className="mt-5 text-[clamp(1.9rem,4.6vw,3rem)] leading-[1.05] font-semibold tracking-[-0.02em]">
            Every change travels the same path
          </h2>
          <p className="mt-4 text-muted-foreground">
            Watch a single task move from analysis to a reviewable pull request.
          </p>
        </div>

        <Card glow="accent" className="mt-14 px-6 py-12 sm:px-12 sm:py-16">
          <div className="relative">
            <div className="h-px w-full bg-border" />
            <div
              className="absolute top-0 left-0 h-px bg-accent transition-[width] duration-700 ease-out"
              style={{ width: `${progress}%` }}
            />
            <div className="absolute -top-[5px] transition-[left] duration-700 ease-out" style={{ left: `calc(${progress}% - 5px)` }}>
              <span className="block h-2.5 w-2.5 rounded-full bg-accent shadow-[0_0_22px_6px_var(--color-accent)]" />
            </div>

            <div className="mt-0 flex justify-between">
              {stages.map((s, i) => {
                const done = i < stage
                const active = i === stage
                return (
                  <div key={s.label} className="flex flex-1 flex-col items-center gap-3">
                    <span
                      className={cn(
                        '-mt-[7px] h-3.5 w-3.5 rounded-full border transition-colors duration-500',
                        active ? 'border-accent bg-accent' : done ? 'border-accent/60 bg-accent/40' : 'border-border-strong bg-background',
                      )}
                    />
                    <span
                      className={cn(
                        'hidden font-mono text-[0.68rem] tracking-[0.16em] uppercase transition-colors sm:block',
                        active ? 'text-accent' : 'text-muted-foreground/70',
                      )}
                    >
                      {s.label}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="mt-12 flex flex-col items-center gap-2 text-center">
            <p className="font-mono text-xs tracking-[0.2em] text-accent uppercase">{current.label}</p>
            <p className="text-lg font-medium sm:text-xl">{current.detail}</p>
            <p className="font-mono text-xs text-muted-foreground">
              pr-engineer &middot; branch pr-engineer/rotate-session-tokens &middot; local model
            </p>
          </div>
        </Card>
      </Container>
    </section>
  )
}
