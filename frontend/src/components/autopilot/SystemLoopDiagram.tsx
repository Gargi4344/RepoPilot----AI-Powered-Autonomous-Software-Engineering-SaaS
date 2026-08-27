import { CardLabel } from '../ui/Card'
import { Repeat, Search, ListChecks, Play, FlaskConical, GitPullRequest } from 'lucide-react'

const STEPS = [
  { icon: Search, label: 'Analyze repo' },
  { icon: ListChecks, label: 'Filter by focus' },
  { icon: Play, label: 'Run agent' },
  { icon: FlaskConical, label: 'Run tests' },
  { icon: GitPullRequest, label: 'Open draft PR' },
]

export function SystemLoopDiagram() {
  return (
    <div>
      <CardLabel tone="muted">
        <Repeat className="h-3.5 w-3.5" />
        How each scheduled run works
      </CardLabel>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {STEPS.map((step, i) => (
          <div key={step.label} className="flex items-center gap-2">
            <div className="flex items-center gap-2 rounded-md border border-border bg-surface-2 px-3 py-2">
              <step.icon className="h-3.5 w-3.5 text-accent" />
              <span className="text-xs text-foreground">{step.label}</span>
            </div>
            {i < STEPS.length - 1 && <span className="text-muted-foreground/50">→</span>}
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Waits for the next scheduled time, then repeats — every step reuses the same pipeline as a manually started run.
      </p>
    </div>
  )
}
