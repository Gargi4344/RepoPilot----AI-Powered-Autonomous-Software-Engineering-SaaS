import { Link } from 'react-router-dom'
import { ChevronRight, X } from 'lucide-react'
import { SCHEDULED_RUN_STATUS_COLOR, SCHEDULED_RUN_STATUS_LABEL } from '../../lib/autopilotLabels'
import type { ScheduledRun } from '../../types'

const CANCELLABLE = new Set(['scheduled', 'waiting'])

export function ScheduledRunItem({
  scheduledRun,
  onCancel,
  cancelling,
}: {
  scheduledRun: ScheduledRun
  onCancel?: (id: string) => void
  cancelling?: boolean
}) {
  const color = SCHEDULED_RUN_STATUS_COLOR[scheduledRun.status]

  return (
    <div className="flex items-center justify-between gap-3 border-b border-border py-3 last:border-b-0">
      <div className="min-w-0">
        <p className="text-sm text-foreground">{new Date(scheduledRun.scheduled_at).toLocaleString()}</p>
        {scheduledRun.result_message && (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{scheduledRun.result_message}</p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <span className="flex items-center gap-1.5 text-xs" style={{ color }}>
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
          {SCHEDULED_RUN_STATUS_LABEL[scheduledRun.status]}
        </span>
        {scheduledRun.run_id && (
          <Link
            to={`/runs/${scheduledRun.run_id}`}
            className="flex items-center gap-0.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            View run
            <ChevronRight className="h-3 w-3" />
          </Link>
        )}
        {onCancel && CANCELLABLE.has(scheduledRun.status) && (
          <button
            type="button"
            onClick={() => onCancel(scheduledRun.id)}
            disabled={cancelling}
            aria-label="Cancel this scheduled run"
            className="text-muted-foreground transition-colors hover:text-destructive disabled:pointer-events-none disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  )
}
