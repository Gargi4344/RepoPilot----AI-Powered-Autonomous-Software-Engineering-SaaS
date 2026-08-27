import type {
  AIConfigRequest,
  AIConfigResponse,
  AuthUser,
  AutopilotPlanRequest,
  AutopilotState,
  ConnectionTestResponse,
  GitHubRepo,
  ProjectAnalysis,
  Run,
  RunEvent,
  RepositorySummary,
  ScheduledRun,
  StatusSummary,
  Task,
  TaskPlan,
} from './types'

const BASE = '/api/v1'

// The OAuth login must hit the backend directly at the host registered as its GitHub OAuth
// App callback -- going through a same-origin proxy (Vite's dev proxy, or Netlify's redirect
// rule in production) would rewrite the Host header and break GitHub's exact-match check on
// the redirect URI. VITE_API_ORIGIN is set at build time (see netlify.toml / .env) for
// production; it defaults to the local dev backend when unset.
const API_ORIGIN = import.meta.env.VITE_API_ORIGIN || 'http://localhost:8000'
export const GITHUB_LOGIN_URL = `${API_ORIGIN}/api/v1/auth/github/login`

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...options,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // response wasn't JSON -- keep statusText
    }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  analyzeRepository: (path: string) =>
    request<TaskPlan>('/repositories/analyze', { method: 'POST', body: JSON.stringify({ path }) }),
  listRepositories: () => request<RepositorySummary[]>('/repositories'),
  listGithubRepos: () => request<GitHubRepo[]>('/github/repos'),
  startGithubRepo: (fullName: string) => request<TaskPlan>(`/github/repos/${fullName}/start`, { method: 'POST' }),
  listRepositoryTasks: (repositoryId: number) => request<Task[]>(`/repositories/${repositoryId}/tasks`),
  getRepositoryAnalysis: (repositoryId: number) =>
    request<ProjectAnalysis | null>(`/repositories/${repositoryId}/analysis`),
  generateTasks: (repositoryId: number) =>
    request<Task[]>(`/repositories/${repositoryId}/generate-tasks`, { method: 'POST' }),
  getTask: (taskId: string) => request<Task>(`/tasks/${taskId}`),
  approveTask: (taskId: string) => request<Task>(`/tasks/${taskId}/approve`, { method: 'POST' }),
  startRun: (taskId: string) => request<Run>(`/tasks/${taskId}/runs`, { method: 'POST' }),
  listTaskRuns: (taskId: string) => request<Run[]>(`/tasks/${taskId}/runs`),
  getRun: (runId: string) => request<Run>(`/runs/${runId}`),
  cancelRun: (runId: string) => request<Run>(`/runs/${runId}/cancel`, { method: 'POST' }),
  listRunEvents: (runId: string) => request<RunEvent[]>(`/runs/${runId}/events`),
  getStatus: () => request<StatusSummary>('/status'),
  me: () => request<AuthUser>('/auth/me'),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),

  getAutopilot: (repositoryId: number) => request<AutopilotState>(`/repositories/${repositoryId}/autopilot`),
  saveAutopilot: (repositoryId: number, plan: AutopilotPlanRequest) =>
    request<AutopilotState>(`/repositories/${repositoryId}/autopilot`, { method: 'POST', body: JSON.stringify(plan) }),
  pauseAutopilot: (repositoryId: number) =>
    request<AutopilotState>(`/repositories/${repositoryId}/autopilot/pause`, { method: 'POST' }),
  resumeAutopilot: (repositoryId: number) =>
    request<AutopilotState>(`/repositories/${repositoryId}/autopilot/resume`, { method: 'POST' }),
  cancelAutopilot: (repositoryId: number) =>
    request<AutopilotState>(`/repositories/${repositoryId}/autopilot/cancel`, { method: 'POST' }),
  cancelScheduledRun: (scheduledRunId: string) =>
    request<ScheduledRun>(`/autopilot/scheduled-runs/${scheduledRunId}/cancel`, { method: 'POST' }),
  rescheduleScheduledRun: (scheduledRunId: string, scheduledAt: string) =>
    request<ScheduledRun>(`/autopilot/scheduled-runs/${scheduledRunId}`, {
      method: 'PUT',
      body: JSON.stringify({ scheduled_at: scheduledAt }),
    }),

  getAiSettings: () => request<AIConfigResponse | null>('/ai-settings'),
  saveAiSettings: (config: AIConfigRequest) =>
    request<AIConfigResponse>('/ai-settings', { method: 'PUT', body: JSON.stringify(config) }),
  testAiConnection: (config: AIConfigRequest) =>
    request<ConnectionTestResponse>('/ai-settings/test-connection', { method: 'POST', body: JSON.stringify(config) }),
  listOllamaModels: (endpoint?: string) =>
    request<string[]>(`/ai-settings/ollama-models${endpoint ? `?endpoint=${encodeURIComponent(endpoint)}` : ''}`),
}
