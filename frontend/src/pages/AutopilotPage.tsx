import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Container } from '../components/ui/Container'
import { Button } from '../components/ui/Button'
import { DashboardNav } from '../components/dashboard/DashboardNav'
import { RepoTabs } from '../components/backlog/RepoTabs'
import { ScheduleCard } from '../components/autopilot/ScheduleCard'
import { FocusAreasCard } from '../components/autopilot/FocusAreasCard'
import { AutonomyLevelCard } from '../components/autopilot/AutonomyLevelCard'
import { StatusPanel } from '../components/autopilot/StatusPanel'
import { GithubMark } from '../components/brand/Marks'
import { describeRepoPath } from '../lib/repoPath'
import { DEFAULT_FOCUS_AREAS } from '../lib/autopilotLabels'
import { ArrowLeft, Rocket } from 'lucide-react'
import { api, ApiError } from '../api'
import type { AutopilotPlanRequest, AutopilotState, RepositorySummary } from '../types'

function defaultDraft(): AutopilotPlanRequest {
  return {
    schedule_type: 'daily',
    run_time: '09:00',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    weekly_day: 0,
    custom_days: [],
    max_runs_per_day: 1,
    focus_areas: DEFAULT_FOCUS_AREAS,
    autonomy_level: 'balanced',
  }
}

function draftFromPlan(plan: NonNullable<AutopilotState['plan']>): AutopilotPlanRequest {
  return {
    schedule_type: plan.schedule_type,
    run_time: plan.run_time,
    timezone: plan.timezone,
    weekly_day: plan.weekly_day,
    custom_days: plan.custom_days,
    max_runs_per_day: plan.max_runs_per_day,
    focus_areas: plan.focus_areas,
    autonomy_level: plan.autonomy_level,
  }
}

export function AutopilotPage() {
  const { id } = useParams<{ id: string }>()
  const repositoryId = Number(id)
  const navigate = useNavigate()

  const [repository, setRepository] = useState<RepositorySummary | null>(null)
  const [state, setState] = useState<AutopilotState | null>(null)
  const [draft, setDraft] = useState<AutopilotPlanRequest>(defaultDraft())
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [justSaved, setJustSaved] = useState(false)

  const load = useCallback(async () => {
    const [repos, autopilot] = await Promise.all([api.listRepositories(), api.getAutopilot(repositoryId)])
    setRepository(repos.find((r) => r.id === repositoryId) ?? null)
    setState(autopilot)
    setDraft(autopilot.plan ? draftFromPlan(autopilot.plan) : defaultDraft())
  }, [repositoryId])

  useEffect(() => {
    load().catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load Autopilot settings.'))
  }, [load])

  // Light polling so upcoming/recent runs and status catch up while the scheduler works
  // unattended in the background -- there's no SSE feed for scheduled-run state.
  useEffect(() => {
    if (!state?.plan || state.plan.status !== 'active') return
    const interval = setInterval(() => {
      api.getAutopilot(repositoryId).then(setState).catch(() => {})
    }, 8000)
    return () => clearInterval(interval)
  }, [state?.plan, repositoryId])

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const next = await api.saveAutopilot(repositoryId, draft)
      setState(next)
      setJustSaved(true)
      setTimeout(() => setJustSaved(false), 3000)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save Autopilot settings.')
    } finally {
      setSaving(false)
    }
  }

  async function withBusy(fn: () => Promise<AutopilotState>) {
    setBusy(true)
    setError(null)
    try {
      setState(await fn())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  const repoName = repository ? describeRepoPath(repository.path).name : `Repository #${repositoryId}`
  const isPaused = state?.plan?.status === 'paused'

  return (
    <div className="landing-theme min-h-screen bg-background font-sans text-foreground">
      <DashboardNav />

      <main className="py-10">
        <Container>
          <button
            type="button"
            onClick={() => navigate(`/repositories/${repositoryId}`)}
            className="flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to backlog
          </button>

          <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-foreground">Autopilot</h1>
              <span className="mt-3 flex items-center gap-1.5 text-sm text-muted-foreground">
                <GithubMark className="h-3.5 w-3.5 shrink-0" />
                {repoName}
              </span>
            </div>
          </div>

          <RepoTabs repositoryId={repositoryId} />

          {error && (
            <div className="mt-6 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {state === null ? (
            <p className="mt-8 text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="mt-8 grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
              <div className="flex flex-col gap-5">
                {isPaused && (
                  <div className="rounded-md border border-warn/30 bg-warn/5 px-4 py-3 text-sm text-warn">
                    Autopilot is paused. Saved settings are kept, but no new runs will start until you resume.
                  </div>
                )}

                <ScheduleCard draft={draft} disabled={saving} onChange={setDraft} />
                <FocusAreasCard
                  selected={draft.focus_areas}
                  disabled={saving}
                  onChange={(focus_areas) => setDraft({ ...draft, focus_areas })}
                />
                <AutonomyLevelCard
                  value={draft.autonomy_level}
                  disabled={saving}
                  onChange={(autonomy_level) => setDraft({ ...draft, autonomy_level })}
                />

                <div className="flex items-center gap-3">
                  <Button variant="accent" onClick={save} disabled={saving}>
                    {saving ? 'Saving…' : state.plan ? 'Save & regenerate schedule' : 'Save & activate Autopilot'}
                    {!saving && <Rocket className="h-4 w-4" />}
                  </Button>
                  {justSaved && <span className="text-sm text-accent">Saved — schedule updated.</span>}
                </div>
              </div>

              <StatusPanel
                plan={state.plan}
                upcoming={state.upcoming}
                recent={state.recent}
                busy={busy}
                onPause={() => withBusy(() => api.pauseAutopilot(repositoryId))}
                onResume={() => withBusy(() => api.resumeAutopilot(repositoryId))}
                onCancelPlan={() => withBusy(() => api.cancelAutopilot(repositoryId))}
                onCancelRun={(scheduledRunId) =>
                  withBusy(async () => {
                    await api.cancelScheduledRun(scheduledRunId)
                    return api.getAutopilot(repositoryId)
                  })
                }
              />
            </div>
          )}
        </Container>
      </main>
    </div>
  )
}
