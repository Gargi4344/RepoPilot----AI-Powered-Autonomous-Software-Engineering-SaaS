import type { AutonomyLevel, FocusArea, ScheduledRunStatus, ScheduleType } from '../types'

export const FOCUS_AREA_LABEL: Record<FocusArea, string> = {
  bug_fixes: 'Bug fixes',
  tests: 'Tests',
  documentation: 'Documentation',
  code_cleanup: 'Code cleanup',
  dependencies: 'Dependencies',
  security: 'Security',
  performance: 'Performance',
  major_features: 'Major features',
}

// Areas riskier to leave fully unattended stay unchecked until a user opts in.
export const DEFAULT_FOCUS_AREAS: FocusArea[] = [
  'bug_fixes',
  'tests',
  'documentation',
  'code_cleanup',
  'dependencies',
]

export const AUTONOMY_LEVEL_INFO: Record<AutonomyLevel, { label: string; description: string; recommended?: boolean }> = {
  conservative: {
    label: 'Conservative',
    description: 'Finds and proposes a task at each scheduled time, but always waits for you to approve it before any code is written.',
  },
  balanced: {
    label: 'Balanced',
    description: 'Automatically approves and runs one matching task per scheduled slot, then opens a draft PR for you to review.',
    recommended: true,
  },
  autopilot: {
    label: 'Autopilot',
    description: 'Same as Balanced, but actively ranks and selects the best matching task among candidates rather than just taking the first match.',
  },
}

export const SCHEDULE_TYPE_LABEL: Record<ScheduleType, string> = {
  daily: 'Every day',
  weekdays: 'Weekdays only',
  weekly: 'Once a week',
  custom: 'Custom days',
}

export const WEEKDAY_LABEL = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export const SCHEDULED_RUN_STATUS_LABEL: Record<ScheduledRunStatus, string> = {
  scheduled: 'Scheduled',
  waiting: 'Waiting',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  skipped: 'Skipped',
  cancelled: 'Cancelled',
}

export const SCHEDULED_RUN_STATUS_COLOR: Record<ScheduledRunStatus, string> = {
  scheduled: 'var(--color-muted-foreground)',
  waiting: 'var(--color-warn)',
  running: 'var(--color-accent)',
  completed: 'var(--color-accent)',
  failed: 'var(--color-destructive)',
  skipped: 'var(--color-muted-foreground)',
  cancelled: 'var(--color-muted-foreground)',
}
