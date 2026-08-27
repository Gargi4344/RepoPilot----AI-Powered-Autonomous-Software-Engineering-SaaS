import { Card, CardLabel } from '../ui/Card'
import { Button } from '../ui/Button'
import { ScheduledRunItem } from './ScheduledRunItem'
import { SystemLoopDiagram } from './SystemLoopDiagram'
import { Pause, Play, ShieldCheck, XCircle } from 'lucide-react'
import type { AutopilotPlan, ScheduledRun } from '../../types'

const STATUS_COLOR = {
  active: 'var(--color-accent)',
  paused: 'var(--color-warn)',
  cancelled: 'var(--color-muted-foreground)',
} as const

const STATUS_LABEL = {
  active: 'Active',
  paused: 'Paused',
  cancelled: 'Cancelled',
} as const

export function StatusPanel({
  plan,
  upcoming,
  recent,
  busy,
  onPause,
  onResume,
  onCancelPlan,
  onCancelRun,
}: {
  plan: AutopilotPlan | null
  upcoming: ScheduledRun[]
  recent: ScheduledRun[]
  busy?: boolean
  onPause: () => void
  onResume: () => void
  onCancelPlan: () => void
  onCancelRun: (id: string) => void
}) {
  const nextRun = upcoming[0] ?? null

  return (
    <div className="flex flex-col gap-5">
      <Card className="p-6">
        <CardLabel>Autopilot status</CardLabel>

        {plan === null ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Not configured yet. Set a schedule and save to activate Autopilot for this repository.
          </p>
        ) : (
          <>
            <div className="mt-3 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: STATUS_COLOR[plan.status] }} />
              <span className="text-sm text-foreground">{STATUS_LABEL[plan.status]}</span>
            </div>

            {plan.status !== 'cancelled' && (
              <p className="mt-2 text-sm text-muted-foreground">
                {nextRun
                  ? `Next run: ${new Date(nextRun.scheduled_at).toLocaleString()}`
                  : plan.status === 'active'
                    ? 'No upcoming runs are scheduled right now.'
                    : 'Resume to schedule upcoming runs again.'}
              </p>
            )}

            {plan.status !== 'cancelled' && (
              <div className="mt-5 flex flex-wrap items-center gap-2">
                {plan.status === 'active' ? (
                  <Button variant="secondary" size="sm" onClick={onPause} disabled={busy}>
                    <Pause className="h-3.5 w-3.5" />
                    Pause
                  </Button>
                ) : (
                  <Button variant="secondary" size="sm" onClick={onResume} disabled={busy}>
                    <Play className="h-3.5 w-3.5" />
                    Resume
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={onCancelPlan} disabled={busy} className="text-destructive hover:text-destructive">
                  <XCircle className="h-3.5 w-3.5" />
                  Cancel plan
                </Button>
              </div>
            )}
          </>
        )}
      </Card>

      {plan !== null && upcoming.length > 0 && (
        <Card className="p-6">
          <CardLabel>Upcoming runs</CardLabel>
          <div className="mt-3">
            {upcoming.map((run) => (
              <ScheduledRunItem key={run.id} scheduledRun={run} onCancel={onCancelRun} cancelling={busy} />
            ))}
          </div>
        </Card>
      )}

      {plan !== null && recent.length > 0 && (
        <Card className="p-6">
          <CardLabel tone="muted">Recent activity</CardLabel>
          <div className="mt-3">
            {recent.map((run) => (
              <ScheduledRunItem key={run.id} scheduledRun={run} />
            ))}
          </div>
        </Card>
      )}

      <Card className="p-6">
        <SystemLoopDiagram />
      </Card>

      <div className="flex items-start gap-2.5 rounded-md border border-accent/25 bg-accent/5 px-4 py-3.5 text-xs text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
        <span>Autopilot never merges. Every change lands on its own branch as a draft PR, waiting for your review.</span>
      </div>
    </div>
  )
}
