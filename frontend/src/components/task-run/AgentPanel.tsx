import { Card } from '../ui/Card'
import { SegmentedProgressBar } from './SegmentedProgressBar'
import { RUN_STEPS, type StepStatus } from '../../lib/useRunProgress'
import { Bot, CheckCircle2, File as FileIcon, Code2 } from 'lucide-react'

export interface AgentPanelProps {
  progress: number
  stepStatuses: StepStatus[]
  currentStepIndex: number
  activeMessage?: string | null
}

export function AgentPanel({ progress, stepStatuses, currentStepIndex, activeMessage }: AgentPanelProps) {
  const activeIndex = stepStatuses.findIndex((s) => s === 'active')
  const currentStep = RUN_STEPS[currentStepIndex] ?? RUN_STEPS[0]

  return (
    <Card className="p-6">
      <p className="text-xs font-medium tracking-[0.15em] text-muted-foreground">AGENT</p>

      <div className="mt-4 flex items-start gap-4">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-accent/40 text-accent">
          <Bot className="h-6 w-6" />
        </div>
        <div className="min-w-0">
          <p className="font-medium text-accent">CODER</p>
          <p className="mt-0.5 text-foreground">{currentStep.label}</p>
          {activeIndex >= 0 && activeMessage && (
            <p className="mt-0.5 truncate text-sm text-muted-foreground">{activeMessage}</p>
          )}
        </div>

        <div className="relative ml-auto hidden h-24 w-24 shrink-0 sm:block">
          <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full" aria-hidden="true">
            <line x1="50" y1="18" x2="50" y2="38" stroke="var(--color-border-strong)" strokeWidth="1" />
            <line x1="50" y1="55" x2="30" y2="78" stroke="var(--color-border-strong)" strokeWidth="1" />
            <line x1="50" y1="55" x2="70" y2="78" stroke="var(--color-border-strong)" strokeWidth="1" />
          </svg>
          <div className="absolute left-1/2 top-[10%] flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full border border-border-strong bg-surface text-muted-foreground">
            <Code2 className="h-3.5 w-3.5" />
          </div>
          <div className="absolute left-1/2 top-[42%] flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full border border-border-strong bg-surface text-foreground shadow-[0_0_20px_rgba(255,255,255,0.1)]">
            <Code2 className="h-4 w-4" />
          </div>
          <div className="absolute bottom-0 left-[18%] flex h-8 w-8 items-center justify-center rounded-full border border-accent/40 bg-surface text-accent">
            <CheckCircle2 className="h-3.5 w-3.5" />
          </div>
          <div className="absolute bottom-0 right-[8%] flex h-8 w-8 items-center justify-center rounded-full border border-border-strong bg-surface text-muted-foreground">
            <FileIcon className="h-3.5 w-3.5" />
          </div>
        </div>
      </div>

      <div className="mt-6">
        <div className="mb-2 flex items-center justify-between text-xs font-medium tracking-wide text-muted-foreground">
          <span>PROGRESS</span>
        </div>
        <SegmentedProgressBar progress={progress} />
      </div>

      <ul className="mt-6 flex flex-col">
        {RUN_STEPS.map((step, i) => {
          const status = stepStatuses[i]
          const isLast = i === RUN_STEPS.length - 1
          return (
            <li key={step.phase} className="relative flex gap-3 pb-5 last:pb-0">
              {!isLast && (
                <span
                  className="absolute left-[9px] top-5 h-full w-px transition-colors duration-500"
                  style={{ backgroundColor: status === 'done' ? 'var(--color-accent)' : 'var(--color-border)' }}
                />
              )}
              <span className="relative z-10 mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center">
                {status === 'done' && <CheckCircle2 className="h-[18px] w-[18px] text-accent" />}
                {status === 'active' && (
                  <span className="relative flex h-[18px] w-[18px] items-center justify-center">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-50" />
                    <span className="relative inline-flex h-3 w-3 rounded-full bg-accent shadow-[0_0_10px_var(--color-accent)]" />
                  </span>
                )}
                {status === 'pending' && <span className="h-[14px] w-[14px] rounded-full border-2 border-border-strong" />}
              </span>
              <div>
                <p className={status === 'pending' ? 'text-sm text-muted-foreground' : 'text-sm text-foreground'}>{step.label}</p>
              </div>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
