import type { RiskLevel, RunStatus, TaskStatus } from '../types'

const LABELS: Record<TaskStatus | RunStatus, string> = {
  backlog: 'Backlog',
  approved: 'Approved',
  running: 'Running',
  needs_human_review: 'Needs review',
  pr_open: 'PR open',
  failed: 'Failed',
  cancelled: 'Cancelled',
  queued: 'Queued',
}

export function StatusBadge({ status }: { status: TaskStatus | RunStatus }) {
  return (
    <span
      className={`badge badge-${status}`}
      style={{
        background: `var(--status-${status}-bg)`,
        color: `var(--status-${status}-fg)`,
      }}
    >
      <span className="badge-dot" />
      {LABELS[status]}
    </span>
  )
}

export function RiskLabel({ risk }: { risk: RiskLevel }) {
  return <span className="risk-label" style={{ color: `var(--risk-${risk}-fg)` }}>{risk}</span>
}
