import { cn } from '../../lib/cn'
import { usePrefersReducedMotion } from '../../lib/motion'
import { CardLabel } from '../ui/Card'
import { Container } from '../ui/Container'

const orbits = [
  { r: 96, dur: '26s', items: ['todos', 'tests'] },
  { r: 140, dur: '38s', items: ['readme', 'lint', 'ci'] },
  { r: 184, dur: '52s', items: ['docs', 'manifests'] },
]

const findings = [
  { sev: 'med', text: 'No test coverage for src/pages/SearchCards.tsx' },
  { sev: 'low', text: 'Missing README.md at the repo root' },
  { sev: 'low', text: 'TODO left in src/api/client.ts' },
  { sev: 'med', text: 'eslint config present but never run in CI' },
]

export function RepositoryRadar() {
  const reduced = usePrefersReducedMotion()

  return (
    <section className="section-seam py-20 md:py-28" id="radar">
      <Container size="wide">
        <div className="grid items-center gap-14 lg:grid-cols-2 lg:gap-20">
          <div className="min-w-0">
            <CardLabel tone="muted">
              <span className="h-1 w-1 rounded-full bg-info" />
              Repository scan
            </CardLabel>
            <h2 className="mt-5 text-[clamp(1.9rem,4.6vw,3rem)] leading-[1.05] font-semibold tracking-[-0.02em]">
              It knows where the work is
            </h2>
            <p className="mt-5 max-w-lg leading-relaxed text-muted-foreground">
              PR Engineer reads your repo's languages, manifests, tests and TODOs, then proposes a
              backlog of small, low-risk candidate tasks &mdash; ranked, not just listed.
            </p>

            <ul className="mt-9 space-y-2.5">
              {findings.map((f) => (
                <li key={f.text} className="flex items-center gap-3 rounded-md border border-border bg-card/70 px-4 py-3">
                  <span
                    className={cn(
                      'shrink-0 rounded-sm border px-1.5 py-0.5 font-mono text-[0.62rem] tracking-widest uppercase',
                      f.sev === 'high' && 'border-destructive/40 text-destructive',
                      f.sev === 'med' && 'border-warn/40 text-warn',
                      f.sev === 'low' && 'border-border-strong text-muted-foreground',
                    )}
                  >
                    {f.sev}
                  </span>
                  <span className="min-w-0 truncate text-sm text-muted-foreground">{f.text}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="relative mx-auto aspect-square w-full max-w-[440px]">
            <div className="absolute inset-0 rounded-full bg-[radial-gradient(circle_at_center,oklch(0.75_0.13_230/12%),transparent_65%)]" />
            <svg viewBox="0 0 440 440" className="absolute inset-0 h-full w-full" aria-hidden="true">
              {orbits.map((o) => (
                <circle key={o.r} cx="220" cy="220" r={o.r} fill="none" stroke="var(--color-border)" strokeDasharray="2 6" />
              ))}
              <circle cx="220" cy="220" r="212" fill="none" stroke="var(--color-border)" />
              <line x1="220" y1="8" x2="220" y2="432" stroke="var(--color-border)" opacity="0.5" />
              <line x1="8" y1="220" x2="432" y2="220" stroke="var(--color-border)" opacity="0.5" />
              {!reduced && (
                <g className="origin-center animate-orbit-slow" style={{ animationDuration: '9s' }}>
                  <path d="M220 220 L220 12 A208 208 0 0 1 366 78 Z" fill="var(--color-info)" opacity="0.07" />
                </g>
              )}
            </svg>

            {orbits.map((o) => (
              <div key={o.r} className="absolute inset-0 animate-orbit-slow" style={{ animationDuration: o.dur }}>
                {o.items.map((label, i) => {
                  const angle = (360 / o.items.length) * i
                  return (
                    <span
                      key={label}
                      className="absolute top-1/2 left-1/2 font-mono text-[0.62rem] tracking-widest text-muted-foreground uppercase"
                      style={{ transform: `rotate(${angle}deg) translateX(${o.r}px) rotate(-${angle}deg) translate(-50%,-50%)` }}
                    >
                      <span className="flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1">
                        <span className="h-1 w-1 rounded-full bg-info" />
                        {label}
                      </span>
                    </span>
                  )
                })}
              </div>
            ))}

            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
              <span className="grid h-20 w-20 place-items-center rounded-full border border-border-strong bg-surface-2 font-mono text-[0.6rem] tracking-[0.2em] uppercase shadow-[0_0_60px_-20px_var(--color-info)]">
                repo
              </span>
            </div>
          </div>
        </div>
      </Container>
    </section>
  )
}
