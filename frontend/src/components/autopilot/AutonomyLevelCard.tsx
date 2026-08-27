import { Card, CardLabel } from '../ui/Card'
import { Gauge } from 'lucide-react'
import { AUTONOMY_LEVEL_INFO } from '../../lib/autopilotLabels'
import { cn } from '../../lib/cn'
import type { AutonomyLevel } from '../../types'

const LEVELS: AutonomyLevel[] = ['conservative', 'balanced', 'autopilot']

export function AutonomyLevelCard({
  value,
  disabled,
  onChange,
}: {
  value: AutonomyLevel
  disabled?: boolean
  onChange: (next: AutonomyLevel) => void
}) {
  return (
    <Card className="p-6">
      <CardLabel>
        <Gauge className="h-3.5 w-3.5" />
        Autonomy level
      </CardLabel>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        {LEVELS.map((level) => {
          const info = AUTONOMY_LEVEL_INFO[level]
          const active = value === level
          return (
            <button
              key={level}
              type="button"
              disabled={disabled}
              onClick={() => onChange(level)}
              className={cn(
                'flex flex-col items-start rounded-lg border p-4 text-left transition-colors disabled:pointer-events-none disabled:opacity-60',
                active ? 'border-accent/50 bg-accent/5' : 'border-border hover:border-border-strong',
              )}
            >
              <span className="flex w-full items-center justify-between gap-2">
                <span className={cn('text-sm font-medium', active ? 'text-foreground' : 'text-muted-foreground')}>{info.label}</span>
                {info.recommended && (
                  <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium tracking-wide text-accent">
                    RECOMMENDED
                  </span>
                )}
              </span>
              <span className="mt-2 text-xs leading-relaxed text-muted-foreground">{info.description}</span>
            </button>
          )
        })}
      </div>
    </Card>
  )
}
