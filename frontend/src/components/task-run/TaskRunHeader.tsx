import { Button } from '../ui/Button'
import { GithubMark } from '../brand/Marks'
import { ArrowLeft, ChevronRight, Square } from 'lucide-react'
import type { RunStatus } from '../../types'

const STATUS_LABEL: Record<RunStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  needs_human_review: 'Needs review',
  pr_open: 'PR open',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

const STATUS_COLOR: Record<RunStatus, string> = {
  queued: 'var(--color-muted-foreground)',
  running: 'var(--color-accent)',
  needs_human_review: 'var(--color-violet)',
  pr_open: 'var(--color-accent)',
  failed: 'var(--color-destructive)',
  cancelled: 'var(--color-muted-foreground)',
}

const CANCELLABLE = new Set<RunStatus>(['queued', 'running'])

export function TaskRunHeader({
  title,
  status,
  repoName,
  branch,
  baseBranch,
  triggeredBy,
  cancelling,
  onBack,
  onCancel,
}: {
  title: string
  status: RunStatus
  repoName: string
  branch: string | null
  baseBranch: string | null
  triggeredBy?: string | null
  cancelling?: boolean
  onBack?: () => void
  onCancel?: () => void
}) {
  const color = STATUS_COLOR[status]
  const isLive = status === 'running'

  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-2 text-sm text-accent transition-colors hover:text-accent/80"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to backlog
      </button>

      <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{title}</h1>
            <span
              className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
              style={{ backgroundColor: `color-mix(in oklch, ${color} 12%, transparent)`, color }}
            >
              {isLive && (
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-70" style={{ backgroundColor: color }} />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
                </span>
              )}
              {STATUS_LABEL[status]}
            </span>
            {triggeredBy === 'autopilot' && (
              <span className="rounded-full bg-violet/10 px-2.5 py-1 text-[10px] font-medium tracking-wide text-violet">
                AUTOPILOT RUN
              </span>
            )}
          </div>

          <div className="mt-2.5 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <GithubMark className="h-3.5 w-3.5" />
              {repoName}
            </span>
            {branch && (
              <>
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-mono text-muted-foreground">{branch}</span>
              </>
            )}
            {baseBranch && (
              <>
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-mono text-muted-foreground">{baseBranch}</span>
              </>
            )}
          </div>
        </div>

        {CANCELLABLE.has(status) && (
          <Button variant="secondary" onClick={onCancel} disabled={cancelling} className="shrink-0">
            <Square className="h-3.5 w-3.5" />
            {cancelling ? 'Cancelling…' : 'Cancel run'}
          </Button>
        )}
      </div>
    </div>
  )
}
