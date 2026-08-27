import { cn } from '../../lib/cn'
import { useInView } from '../../lib/motion'
import { CardLabel } from '../ui/Card'
import { Container } from '../ui/Container'

const steps = [
  { n: '01', title: 'Connect', body: 'Sign in with GitHub. Scope is public_repo only -- private repos are never visible to it.', meta: 'oauth · public_repo' },
  { n: '02', title: 'Pick a repo', body: 'Choose any of your repos from the list. It clones (or updates) the checkout and scans it.', meta: 'read-only scan' },
  { n: '03', title: 'Approve a task', body: 'Every task sits in a backlog until you approve it. Nothing is written, run, or pushed before that.', meta: 'human gate' },
  { n: '04', title: 'Write & test', body: 'A local model edits the code in an isolated git worktree and runs your repo’s own checks -- no shell access, ever.', meta: 'no shell access' },
  { n: '05', title: 'Self-review', body: 'A second model pass reviews the diff and flags risk before you do. Advisory only -- it never blocks.', meta: 'advisory only' },
  { n: '06', title: 'Draft pull request', body: 'A commit-clean draft PR opens for your review. Merging is always a human decision, on GitHub.', meta: 'draft only' },
  { n: '07', title: 'Turn on Autopilot', body: 'Once you trust the loop, plan up to 7 days of runs on a schedule, filtered by focus area. It keeps working in the background -- even after you close the tab -- through these exact same steps.', meta: 'runs while you\'re away · draft only' },
]

export function Workflow() {
  return (
    <section className="section-seam py-20 md:py-28" id="how-it-works">
      <Container>
        <div className="max-w-2xl">
          <CardLabel tone="muted">
            <span className="h-1 w-1 rounded-full bg-accent" />
            How it works
          </CardLabel>
          <h2 className="mt-5 text-[clamp(1.9rem,4.6vw,3rem)] leading-[1.05] font-semibold tracking-[-0.02em]">
            Seven steps from repo to pull request
          </h2>
        </div>

        <ol className="relative mt-16 border-l border-border pl-6 sm:pl-10">
          {steps.map((s, i) => (
            <Step key={s.n} {...s} last={i === steps.length - 1} />
          ))}
        </ol>
      </Container>
    </section>
  )
}

function Step({ n, title, body, meta, last }: { n: string; title: string; body: string; meta: string; last: boolean }) {
  const { ref, inView } = useInView<HTMLLIElement>(0.5)
  return (
    <li ref={ref} className={cn('relative transition-all duration-700', last ? 'pb-0' : 'pb-12 sm:pb-16', inView ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-30')}>
      <span
        className={cn(
          'absolute top-1.5 -left-[27px] h-2.5 w-2.5 rounded-full border transition-colors duration-500 sm:-left-[43px]',
          inView ? 'border-accent bg-accent shadow-[0_0_18px_2px_var(--color-accent)]' : 'border-border-strong bg-background',
        )}
      />
      <div className="grid gap-3 sm:grid-cols-[auto_minmax(0,1fr)] sm:gap-8">
        <span className="font-mono text-sm text-muted-foreground/60">{n}</span>
        <div className="min-w-0">
          <h3 className="text-lg font-medium tracking-tight sm:text-xl">{title}</h3>
          <p className="mt-2 max-w-xl leading-relaxed text-muted-foreground">{body}</p>
          <p className="mt-3 font-mono text-[0.7rem] tracking-[0.14em] text-accent/80 uppercase">{meta}</p>
        </div>
      </div>
    </li>
  )
}
