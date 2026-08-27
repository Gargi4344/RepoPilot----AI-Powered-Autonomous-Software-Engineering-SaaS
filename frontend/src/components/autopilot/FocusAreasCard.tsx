import { Card, CardLabel } from '../ui/Card'
import { Target } from 'lucide-react'
import { FOCUS_AREA_LABEL } from '../../lib/autopilotLabels'
import { cn } from '../../lib/cn'
import type { FocusArea } from '../../types'

const ALL_FOCUS_AREAS = Object.keys(FOCUS_AREA_LABEL) as FocusArea[]

export function FocusAreasCard({
  selected,
  disabled,
  onChange,
}: {
  selected: FocusArea[]
  disabled?: boolean
  onChange: (next: FocusArea[]) => void
}) {
  function toggle(area: FocusArea) {
    onChange(selected.includes(area) ? selected.filter((a) => a !== area) : [...selected, area])
  }

  return (
    <Card className="p-6">
      <CardLabel>
        <Target className="h-3.5 w-3.5" />
        Focus areas
      </CardLabel>
      <p className="mt-2 text-sm text-muted-foreground">
        Autopilot only picks tasks that match at least one checked area. Leave everything unchecked and it will never find work.
      </p>

      <div className="mt-5 grid gap-2.5 sm:grid-cols-2">
        {ALL_FOCUS_AREAS.map((area) => {
          const checked = selected.includes(area)
          return (
            <label
              key={area}
              className={cn(
                'flex cursor-pointer items-center gap-2.5 rounded-md border px-3 py-2.5 text-sm transition-colors',
                checked ? 'border-accent/40 bg-accent/5 text-foreground' : 'border-border text-muted-foreground hover:text-foreground',
                disabled && 'pointer-events-none opacity-60',
              )}
            >
              <input
                type="checkbox"
                className="h-3.5 w-3.5 accent-[var(--color-accent)]"
                checked={checked}
                disabled={disabled}
                onChange={() => toggle(area)}
              />
              {FOCUS_AREA_LABEL[area]}
            </label>
          )
        })}
      </div>
    </Card>
  )
}
