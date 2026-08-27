import { Card } from '../ui/Card'
import { STAGES } from '../../lib/useRunProgress'
import { RotateCw, FlaskConical, GitCommitHorizontal, Users, GitPullRequest, Check, X, Square } from 'lucide-react'
import type { RunStatus } from '../../types'

const STAGE_ICONS = [RotateCw, RotateCw, FlaskConical, GitCommitHorizontal, Users, GitPullRequest]
const RUNNING_STATUSES = new Set<RunStatus>(['queued', 'running'])
const FAILURE_STATUSES = new Set<RunStatus>(['failed', 'cancelled'])

export function StageStepper({ stageIndex, status }: { stageIndex: number; status: RunStatus }) {
  const isTerminal = !RUNNING_STATUSES.has(status)
  const isFailure = FAILURE_STATUSES.has(status)
  const isCancelled = status === 'cancelled'

  return (
    <Card className="mt-5 px-8 py-8">
      <div className="flex items-center">
        {STAGES.map((stage, i) => {
          const Icon = STAGE_ICONS[i]
          // A stage is only "reached" if the run actually got there -- a failed/cancelled
          // run that stopped early never touches later stages, and stops (rather than
          // succeeds) at the one it was on, so that one gets a stop/failure mark, not a
          // check. Cancelled is a deliberate stop, not an error, so it gets a neutral
          // square rather than the same red X a genuine failure gets.
          const reached = i < stageIndex || (i === stageIndex && isTerminal)
          const isStoppedHere = i === stageIndex && isTerminal && isFailure
          const done = reached && !isStoppedHere
          const active = i === stageIndex && !isTerminal
          const color = isStoppedHere ? (isCancelled ? 'var(--color-muted-foreground)' : 'var(--color-destructive)') : 'var(--color-accent)'
          const isLastNode = i === STAGES.length - 1

          return (
            <div key={stage} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center gap-2.5">
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all duration-500"
                  style={{
                    borderColor: done || active || isStoppedHere ? color : 'var(--color-border-strong)',
                    backgroundColor: active ? 'oklch(0.78 0.17 152 / 12%)' : 'transparent',
                    boxShadow: active ? '0 0 20px oklch(0.78 0.17 152 / 35%)' : 'none',
                    color: done || active || isStoppedHere ? color : 'var(--color-muted-foreground)',
                  }}
                >
                  {done ? (
                    <Check className="h-4 w-4" />
                  ) : isStoppedHere ? (
                    isCancelled ? <Square className="h-3.5 w-3.5" /> : <X className="h-4 w-4" />
                  ) : (
                    <Icon className={`h-4 w-4 ${active ? 'animate-pulse' : ''}`} />
                  )}
                </div>
                <span
                  className="text-[11px] font-medium tracking-wide"
                  style={{ color: done || active || isStoppedHere ? 'var(--color-foreground)' : 'var(--color-muted-foreground)' }}
                >
                  {stage.toUpperCase()}
                </span>
              </div>

              {!isLastNode && (
                <div className="mx-2 h-px flex-1 bg-white/[0.08]">
                  <div
                    className="h-full transition-all duration-700 ease-out"
                    style={{ width: done ? '100%' : active ? '50%' : '0%', backgroundColor: 'var(--color-accent)' }}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}
