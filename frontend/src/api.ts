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

// Login must complete through the exact same origin every other API call uses (Netlify's
// proxy rule in production, Vite's dev proxy locally) -- not the backend's own bare domain.
// The session cookie GitHub's callback response sets is scoped to whichever origin the
// browser's connection actually was when it received that Set-Cookie header. Hitting the
// backend directly sets the cookie on the backend's own domain; every other call (including
// the auth check that decides whether the app treats you as logged in) goes through the
// proxied same-origin path instead, which then never sends that cookie back -- observed in
// production as "GitHub sign-in completes but the app never recognizes it."
export const GITHUB_LOGIN_URL = import.meta.env.PROD
  ? `${BASE}/auth/github/login`
  : 'http://localhost:8000/api/v1/auth/github/login'

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
