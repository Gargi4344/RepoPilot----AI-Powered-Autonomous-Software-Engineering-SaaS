import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Container } from '../components/ui/Container'
import { DashboardNav } from '../components/dashboard/DashboardNav'
import { TaskRunHeader } from '../components/task-run/TaskRunHeader'
import { RunInfoStrip } from '../components/task-run/RunInfoStrip'
import { AgentPanel } from '../components/task-run/AgentPanel'
import { TestsPanel } from '../components/task-run/TestsPanel'
import { LiveActivityLog } from '../components/task-run/LiveActivityLog'
import { StageStepper } from '../components/task-run/StageStepper'
import { useRunProgress } from '../lib/useRunProgress'
import { describeRepoPath } from '../lib/repoPath'
import { useEventStream } from '../hooks/useEventStream'
import { api, ApiError } from '../api'
import type { RepositorySummary, Run, RunEvent, Task } from '../types'

const TERMINAL_STATUSES = new Set(['needs_human_review', 'pr_open', 'failed', 'cancelled'])

export function RunDetailPage() {
  const { id } = useParams<{ id: string }>()
  const runId = id!
  const navigate = useNavigate()

  const [run, setRun] = useState<Run | null>(null)
  const [task, setTask] = useState<Task | null>(null)
  const [repository, setRepository] = useState<RepositorySummary | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const seenEventIds = useRef(new Set<number>())

  useEffect(() => {
    api.getRun(runId).then(setRun).catch(() => setRun(null))
    api.listRunEvents(runId).then((history) => {
      seenEventIds.current = new Set(history.map((e) => e.id))
      setEvents(history)
    })
  }, [runId])

  useEffect(() => {
    if (run?.task_id) {
      api.getTask(run.task_id).then(setTask).catch(() => setTask(null))
    }
  }, [run?.task_id])

  useEffect(() => {
    if (task?.repository_id == null) return
    api
      .listRepositories()
      .then((repos) => setRepository(repos.find((r) => r.id === task.repository_id) ?? null))
      .catch(() => setRepository(null))
  }, [task?.repository_id])

  // Poll the run object while it's active -- SSE carries the log, but not the row mutations
  // (status, test_results, pr_url, ...) that land alongside each phase.
  useEffect(() => {
    if (!run || TERMINAL_STATUSES.has(run.status)) return
    const interval = setInterval(() => {
      api.getRun(runId).then(setRun).catch(() => {})
    }, 3000)
    return () => clearInterval(interval)
  }, [run, runId])

  // Fallback for SSE: a long quiet gap between events (a slow baseline `npm install` ran
  // silent for 5+ minutes in production) can leave the connection looking alive to the
  // browser while it's actually gone dark at the network layer, with nothing to trigger a
  // reconnect. Polling the same history endpoint SSE replays from means the feed self-heals
  // within a few seconds regardless of what happened to the stream.
  useEffect(() => {
    if (!run || TERMINAL_STATUSES.has(run.status)) return
    const interval = setInterval(() => {
      api
        .listRunEvents(runId)
        .then((history) => {
          const fresh = history.filter((e) => !seenEventIds.current.has(e.id))
          if (fresh.length === 0) return
          fresh.forEach((e) => seenEventIds.current.add(e.id))
          setEvents((prev) => [...prev, ...fresh].sort((a, b) => a.id - b.id))
        })
        .catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [run, runId])

  const isLive = run !== null && !TERMINAL_STATUSES.has(run.status)
  const streamUrl = useMemo(() => (isLive ? `/api/v1/runs/${runId}/events/stream` : null), [runId, isLive])
  const handleEvent = useCallback((event: RunEvent) => {
    if (seenEventIds.current.has(event.id)) return
    seenEventIds.current.add(event.id)
    setEvents((prev) => [...prev, event])
  }, [])
  useEventStream(streamUrl, handleEvent)

  const { stepStatuses, progress, stageIndex, currentStepIndex, lastEvent } = useRunProgress(run, events)

  async function cancelRun() {
    setCancelling(true)
    setError(null)
    try {
      const updated = await api.cancelRun(runId)
      setRun(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to cancel run.')
    } finally {
      setCancelling(false)
    }
  }

  if (!run) return <div className="landing-theme min-h-screen bg-background font-sans text-foreground"><DashboardNav /></div>

  const repoName = repository ? describeRepoPath(repository.path).name : task?.repository_id != null ? `Repository #${task.repository_id}` : '—'

  return (
    <div className="landing-theme min-h-screen bg-background font-sans text-foreground">
      <DashboardNav />

      <main className="py-10">
        <Container>
          <TaskRunHeader
            title={task?.title ?? 'Run'}
            status={run.status}
            repoName={repoName}
            branch={run.branch_name}
            baseBranch={run.base_branch}
            triggeredBy={run.triggered_by}
            cancelling={cancelling}
            onBack={() => navigate(task?.repository_id != null ? `/repositories/${task.repository_id}` : '/repositories')}
            onCancel={cancelRun}
          />

          {error && (
            <div className="mt-6 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}
          {run.error_message && (
            <div className="mt-6 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {run.error_message}
            </div>
          )}

          <RunInfoStrip
            branch={run.branch_name}
            baseBranch={run.base_branch}
            started={run.started_at}
            commit={run.commit_sha}
            pullRequest={run.pr_url}
            aiProvider={run.ai_provider}
            aiModel={run.ai_model}
          />

          <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
            <div className="min-w-0">
              <AgentPanel
                progress={progress}
                stepStatuses={stepStatuses}
                currentStepIndex={currentStepIndex}
                activeMessage={lastEvent?.message}
              />
              {/* run.test_results is overwritten by whichever _run_tests call happened most
                  recently on the backend, including the pre-task baseline check -- showing
                  it before the real "test" phase has actually run would present baseline
                  noise as if it were the task's own test outcome. */}
              <TestsPanel testResults={events.some((e) => e.phase === 'test') ? run.test_results : []} />
              {run.review_result && (
                <div className="mt-5 rounded-xl border border-border bg-surface p-6">
                  <p className="text-xs font-medium tracking-[0.15em] text-muted-foreground">AUTOMATED REVIEW (ADVISORY)</p>
                  <p className="mt-3 text-sm text-foreground">
                    {run.review_result.approved ? 'Approved' : 'Flagged'} · {run.review_result.risk} risk
                  </p>
                  <p className="mt-2 text-sm text-muted-foreground">{run.review_result.summary}</p>
                  {run.review_result.concerns.length > 0 && (
                    <ul className="mt-2 list-inside list-disc text-sm text-muted-foreground">
                      {run.review_result.concerns.map((concern, i) => (
                        <li key={i}>{concern}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>

            <LiveActivityLog events={events} isLive={isLive} />
          </div>

          <StageStepper stageIndex={stageIndex} status={run.status} />
        </Container>
      </main>
    </div>
  )
}
