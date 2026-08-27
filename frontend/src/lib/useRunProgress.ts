import type { Run, RunEvent } from '../types'

export interface RunStep {
  phase: string
  label: string
}

// Mirrors the real phases app/orchestrator.py logs, in pipeline order.
export const RUN_STEPS: RunStep[] = [
  { phase: 'setup', label: 'Start run' },
  { phase: 'worktree', label: 'Create isolated worktree' },
  { phase: 'baseline', label: 'Run baseline checks' },
  { phase: 'coding', label: 'Write changes' },
  { phase: 'test', label: 'Run tests' },
  { phase: 'commit', label: 'Create commit' },
  { phase: 'review', label: 'Automated review' },
  { phase: 'pr', label: 'Open pull request' },
]

export const STAGES = ['Setup', 'Code', 'Test', 'Commit', 'Review', 'Pull Request'] as const

const PHASE_TO_STAGE: Record<string, number> = {
  setup: 0,
  worktree: 0,
  baseline: 0,
  coding: 1,
  test: 2,
  commit: 3,
  review: 4,
  pr: 5,
}

const TERMINAL_RUN_STATUSES = new Set(['needs_human_review', 'pr_open', 'failed', 'cancelled'])

export type StepStatus = 'done' | 'active' | 'pending'

export function useRunProgress(run: Run | null, events: RunEvent[]) {
  const seenPhases = new Set(events.map((e) => e.phase))
  const isTerminal = run ? TERMINAL_RUN_STATUSES.has(run.status) : false

  let lastSeenIndex = -1
  RUN_STEPS.forEach((step, i) => {
    if (seenPhases.has(step.phase)) lastSeenIndex = i
  })

  const stepStatuses: StepStatus[] = RUN_STEPS.map((_step, i) => {
    if (i < lastSeenIndex) return 'done'
    if (i === lastSeenIndex) return isTerminal ? 'done' : 'active'
    return 'pending'
  })

  // Terminal progress is never forced to 100 -- a run that failed or was cancelled partway
  // through genuinely didn't reach every step (e.g. it never ran tests or opened a PR), and
  // the bar should say so rather than implying the whole pipeline completed.
  const completedSteps = stepStatuses.filter((s) => s === 'done').length
  const progress =
    lastSeenIndex < 0
      ? 0
      : isTerminal
        ? (completedSteps / RUN_STEPS.length) * 100
        : Math.min(99, ((completedSteps + 0.5) / RUN_STEPS.length) * 100)

  const currentStepIndex = Math.max(lastSeenIndex, 0)
  const stageIndex = lastSeenIndex >= 0 ? PHASE_TO_STAGE[RUN_STEPS[lastSeenIndex].phase] : 0
  const lastEvent = events.length > 0 ? events[events.length - 1] : null

  return { stepStatuses, progress, stageIndex, currentStepIndex, lastEvent, isTerminal }
}
