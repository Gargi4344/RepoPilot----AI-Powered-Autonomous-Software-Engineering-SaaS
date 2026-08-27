import { Card, CardLabel } from '../ui/Card'
import { Calendar } from 'lucide-react'
import { SCHEDULE_TYPE_LABEL, WEEKDAY_LABEL } from '../../lib/autopilotLabels'
import { cn } from '../../lib/cn'
import type { AutopilotPlanRequest, ScheduleType } from '../../types'

const SCHEDULE_TYPES: ScheduleType[] = ['daily', 'weekdays', 'weekly', 'custom']

const inputClass =
  'h-10 w-full rounded-md border border-border bg-surface-2 px-3 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent'

export function ScheduleCard({
  draft,
  disabled,
  onChange,
}: {
  draft: AutopilotPlanRequest
  disabled?: boolean
  onChange: (next: AutopilotPlanRequest) => void
}) {
  function toggleCustomDay(day: number) {
    const has = draft.custom_days?.includes(day)
    const next = has ? (draft.custom_days ?? []).filter((d) => d !== day) : [...(draft.custom_days ?? []), day]
    onChange({ ...draft, custom_days: next.sort() })
  }

  return (
    <Card className="p-6">
      <CardLabel>
        <Calendar className="h-3.5 w-3.5" />
        Schedule
      </CardLabel>
      <p className="mt-2 text-sm text-muted-foreground">
        Plans the next 7 days of runs up front. Nothing runs beyond that window until you save again.
      </p>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs text-muted-foreground">Frequency</span>
          <select
            className={cn(inputClass, 'mt-1.5')}
            value={draft.schedule_type}
            disabled={disabled}
            onChange={(e) => onChange({ ...draft, schedule_type: e.target.value as ScheduleType })}
          >
            {SCHEDULE_TYPES.map((type) => (
              <option key={type} value={type}>
                {SCHEDULE_TYPE_LABEL[type]}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-xs text-muted-foreground">Run time</span>
          <input
            type="time"
            className={cn(inputClass, 'mt-1.5')}
            value={draft.run_time}
            disabled={disabled}
            onChange={(e) => onChange({ ...draft, run_time: e.target.value })}
          />
        </label>

        <label className="block">
          <span className="text-xs text-muted-foreground">Timezone</span>
          <input
            type="text"
            className={cn(inputClass, 'mt-1.5')}
            value={draft.timezone}
            disabled={disabled}
            onChange={(e) => onChange({ ...draft, timezone: e.target.value })}
            placeholder="e.g. America/New_York"
          />
        </label>

        <label className="block">
          <span className="text-xs text-muted-foreground">Max runs per day</span>
          <input
            type="number"
            min={1}
            max={5}
            className={cn(inputClass, 'mt-1.5')}
            value={draft.max_runs_per_day ?? 1}
            disabled={disabled}
            onChange={(e) => onChange({ ...draft, max_runs_per_day: Number(e.target.value) })}
          />
        </label>

        {draft.schedule_type === 'weekly' && (
          <label className="block sm:col-span-2">
            <span className="text-xs text-muted-foreground">Day of week</span>
            <select
              className={cn(inputClass, 'mt-1.5')}
              value={draft.weekly_day ?? 0}
              disabled={disabled}
              onChange={(e) => onChange({ ...draft, weekly_day: Number(e.target.value) })}
            >
              {WEEKDAY_LABEL.map((label, i) => (
                <option key={label} value={i}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}

        {draft.schedule_type === 'custom' && (
          <div className="sm:col-span-2">
            <span className="text-xs text-muted-foreground">Days</span>
            <div className="mt-1.5 flex flex-wrap gap-2">
              {WEEKDAY_LABEL.map((label, i) => {
                const active = draft.custom_days?.includes(i)
                return (
                  <button
                    key={label}
                    type="button"
                    disabled={disabled}
                    onClick={() => toggleCustomDay(i)}
                    className={cn(
                      'rounded-full border px-3 py-1.5 text-xs transition-colors',
                      active ? 'border-accent/50 bg-accent/10 text-accent' : 'border-border text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {label.slice(0, 3)}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}
