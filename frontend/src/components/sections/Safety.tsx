import { GitBranch, Lock, ScrollText, ShieldCheck, Undo2, UserCheck } from 'lucide-react'
import { Card, CardLabel } from '../ui/Card'
import { Container } from '../ui/Container'

const guarantees = [
  { icon: Lock, title: 'No direct push', body: 'PR Engineer never touches your default branch. It only ever pushes its own pr-engineer/* branches.' },
  { icon: UserCheck, title: 'Human in the loop', body: 'Every change lands as a draft PR. A human approves and merges -- always. There is no merge button anywhere in this app.' },
  { icon: GitBranch, title: 'Isolated worktrees', body: 'Each run works in its own git worktree and branch -- your checked-out code is never touched.' },
  { icon: ScrollText, title: 'Full audit trail', body: 'Every tool call, test run and decision is logged and streamed live, replayable per run.' },
  { icon: Undo2, title: 'Reversible by default', body: 'Close the PR and nothing remains. No hidden state, no lingering branches, no auto-merge.' },
  { icon: ShieldCheck, title: 'Scoped credentials', body: 'public_repo OAuth scope only -- private repos are never visible, and access is revocable anytime from GitHub.' },
]

export function Safety() {
  return (
    <section className="section-seam py-20 md:py-28" id="safety">
      <Container>
        <div className="max-w-2xl">
          <CardLabel tone="muted">
            <span className="h-1 w-1 rounded-full bg-accent" />
            Safety model
          </CardLabel>
          <h2 className="mt-5 text-[clamp(1.9rem,4.6vw,3rem)] leading-[1.05] font-semibold tracking-[-0.02em]">
            Autonomy with hard boundaries
          </h2>
          <p className="mt-4 leading-relaxed text-muted-foreground">
            Autonomous does not mean unsupervised. Every boundary below is enforced in code, not just prompted for.
          </p>
        </div>

        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {guarantees.map((g) => (
            <Card key={g.title} className="group p-5 transition-colors hover:border-border-strong">
              <span className="grid h-9 w-9 place-items-center rounded-md border border-border bg-surface-2">
                <g.icon className="h-4 w-4" />
              </span>
              <h3 className="mt-4 text-[0.98rem] font-medium tracking-tight">{g.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{g.body}</p>
            </Card>
          ))}
        </div>
      </Container>
    </section>
  )
}
