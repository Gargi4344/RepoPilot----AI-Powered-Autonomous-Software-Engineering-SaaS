export interface AuthUser {
  login: string
  name: string | null
  avatar_url: string | null
}

export interface GitHubRepo {
  name: string
  full_name: string
  description: string | null
  html_url: string
  clone_url: string
  default_branch: string
  private: boolean
  fork: boolean
  updated_at: string
}

export type RiskLevel = 'low' | 'medium' | 'high'

export type TaskStatus =
  | 'backlog'
  | 'approved'
  | 'running'
  | 'needs_human_review'
  | 'pr_open'
  | 'failed'
  | 'cancelled'

export type RunStatus =
  | 'queued'
  | 'running'
  | 'needs_human_review'
  | 'pr_open'
  | 'failed'
  | 'cancelled'

export interface ProjectAnalysis {
  root: string
  languages: Record<string, number>
  manifests: string[]
  readme_present: boolean
  test_directories: string[]
  todo_items: string[]
  source_files: number
  ignored_files: number
  detected_tools: string[]
  summary: string
}

export interface Task {
  id: string
  repository_id: number | null
  title: string
  description: string
  priority: number
  risk: RiskLevel
  affected_files: string[]
  required_checks: string[]
  source: string
  requires_human_approval: boolean
  status: TaskStatus
  approved_at: string | null
}

export interface TaskPlan {
  analysis: ProjectAnalysis
  tasks: Task[]
  repository_id: number | null
}

export interface RepositorySummary {
  id: number
  path: string
  created_at: string
}

export interface TestOutcome {
  tool: string
  exit_code: number
  stdout: string
  stderr: string
  duration_seconds: number
}

export interface ReviewResult {
  approved: boolean
  summary: string
  concerns: string[]
  risk: RiskLevel
}

export interface Run {
  id: string
  task_id: string
  status: RunStatus
  triggered_by: string | null
  branch_name: string | null
  worktree_path: string | null
  base_branch: string | null
  started_at: string | null
  finished_at: string | null
  pr_url: string | null
  error_message: string | null
  commit_sha: string | null
  review_result: ReviewResult | null
  test_results: TestOutcome[]
  ai_provider: string | null
  ai_model: string | null
}

export interface RunEvent {
  id: number
  run_id: string
  ts: string
  phase: string
  level: string
  message: string
  data: Record<string, unknown> | null
}

export interface StatusSummary {
  max_concurrent_runs: number
  queued?: number
  running?: number
}

export type AutonomyLevel = 'conservative' | 'balanced' | 'autopilot'

export type FocusArea =
  | 'bug_fixes'
  | 'tests'
  | 'documentation'
  | 'code_cleanup'
  | 'dependencies'
  | 'security'
  | 'performance'
  | 'major_features'

export type ScheduleType = 'daily' | 'weekdays' | 'weekly' | 'custom'

export type AutopilotPlanStatus = 'active' | 'paused' | 'cancelled'

export type ScheduledRunStatus = 'scheduled' | 'waiting' | 'running' | 'completed' | 'failed' | 'skipped' | 'cancelled'

export interface AutopilotPlanRequest {
  schedule_type: ScheduleType
  run_time: string
  timezone: string
  weekly_day?: number | null
  custom_days?: number[]
  max_runs_per_day?: number
  focus_areas: FocusArea[]
  autonomy_level: AutonomyLevel
}

export interface AutopilotPlan {
  id: string
  repository_id: number
  status: AutopilotPlanStatus
  schedule_type: ScheduleType
  run_time: string
  timezone: string
  weekly_day: number | null
  custom_days: number[]
  max_runs_per_day: number
  focus_areas: FocusArea[]
  autonomy_level: AutonomyLevel
  created_at: string
  updated_at: string
}

export interface ScheduledRun {
  id: string
  plan_id: string
  repository_id: number
  scheduled_at: string
  status: ScheduledRunStatus
  task_id: string | null
  run_id: string | null
  result_message: string | null
  started_at: string | null
  finished_at: string | null
}

export interface AutopilotState {
  plan: AutopilotPlan | null
  upcoming: ScheduledRun[]
  recent: ScheduledRun[]
}

export type AIProviderKind = 'ollama' | 'anthropic' | 'gemini'

export interface AIConfigRequest {
  provider: AIProviderKind
  model: string
  api_key?: string | null
  endpoint?: string | null
}

export interface AIConfigResponse {
  provider: AIProviderKind
  model: string
  endpoint: string | null
  configured: boolean
  enabled: boolean
  updated_at: string | null
}

export interface ConnectionTestResponse {
  ok: boolean
  message: string
}
