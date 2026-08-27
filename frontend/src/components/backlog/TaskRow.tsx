import { Link } from 'react-router-dom'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { Sparkles, Check, Play, ChevronRight } from 'lucide-react'
import type { RiskLevel, Task, TaskStatus } from '../../types'

const RISK_COLOR: Record<RiskLevel, string> = {
  low: 'var(--color-accent)',
  medium: 'var(--color-warn)',
  high: 'var(--color-destructive)',
}

const STATUS_LABEL: Record<TaskStatus, string> = {
  backlog: 'Backlog',
  approved: 'Approved',
  running: 'Running',
  needs_human_review: 'Needs review',
  pr_open: 'PR open',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

const STATUS_COLOR: Record<TaskStatus, string> = {
  backlog: 'var(--color-muted-foreground)',
  approved: 'var(--color-info)',
  running: 'var(--color-warn)',
  needs_human_review: 'var(--color-violet)',
  pr_open: 'var(--color-accent)',
  failed: 'var(--color-destructive)',
  cancelled: 'var(--color-muted-foreground)',
}

const SOURCE_LABEL: Record<string, string> = {
  'repository-todo': 'tracked TODO',
  'repository-analysis': 'repository check',
  'llm-backlog': 'AI proposed',
}

export function TaskRow({
  task,
  runId,
  runTriggeredBy,
  busy,
  onApprove,
  onStartRun,
}: {
  task: Task
  runId?: string
  runTriggeredBy?: string | null
  busy?: boolean
  onApprove?: (id: string) => void
  onStartRun?: (id: string) => void
}) {
  return (
    <Card className="flex flex-col gap-5 p-6 transition-colors duration-200 hover:border-border-strong md:flex-row md:items-center md:justify-between">
      <div className="flex gap-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-violet/30 bg-violet/5 text-violet">
          <Sparkles className="h-4 w-4" />
        </div>

        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <p className="font-medium text-foreground">{task.title}</p>
            {task.source === 'llm-backlog' && (
              <span className="rounded-full bg-violet/10 px-2 py-0.5 text-[10px] font-medium tracking-wide text-violet">
                AI PROPOSED
              </span>
            )}
          </div>
          <p className="mt-1.5 max-w-xl text-sm text-muted-foreground">{task.description}</p>
          {task.affected_files.length > 0 && (
            <p className="mt-1 max-w-xl truncate font-mono text-xs text-muted-foreground/70">
              {task.affected_files.join(', ')}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 md:justify-end">
        <div className="flex gap-8 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Priority</p>
            <p className="mt-1 flex items-center gap-1.5 text-foreground">
              <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
              {task.priority}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Risk</p>
            <p className="mt-1 flex items-center gap-1.5 text-foreground uppercase">
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: RISK_COLOR[task.risk] }} />
              {task.risk}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Source</p>
            <p className="mt-1 text-foreground">{SOURCE_LABEL[task.source] ?? task.source}</p>
          </div>
        </div>

        <div className="hidden items-center gap-1.5 text-xs text-muted-foreground lg:flex">
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: STATUS_COLOR[task.status] }} />
          {STATUS_LABEL[task.status]}
        </div>

        <div className="flex items-center gap-2">
          {task.status === 'backlog' && (
            <Button variant="secondary" size="sm" onClick={() => onApprove?.(task.id)} disabled={busy}>
              {busy ? 'Approving…' : 'Approve'}
              {!busy && <Check className="h-3.5 w-3.5" />}
            </Button>
          )}
          {task.status === 'approved' && (
            <Button variant="secondary" size="sm" onClick={() => onStartRun?.(task.id)} disabled={busy}>
              {busy ? 'Starting…' : 'Start run'}
              {!busy && <Play className="h-3.5 w-3.5" />}
            </Button>
          )}
          {runId && (
            <>
              {runTriggeredBy === 'autopilot' && (
                <span className="rounded-full bg-violet/10 px-2 py-0.5 text-[10px] font-medium tracking-wide text-violet">
                  AUTOPILOT RUN
                </span>
              )}
              <Link
                to={`/runs/${runId}`}
                className="flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                View run
                <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            </>
          )}
        </div>
      </div>
    </Card>
  )
}
