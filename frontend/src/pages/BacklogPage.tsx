import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Container } from '../components/ui/Container'
import { DashboardNav } from '../components/dashboard/DashboardNav'
import { BacklogHeader } from '../components/backlog/BacklogHeader'
import { RepoTabs } from '../components/backlog/RepoTabs'
import { RepoAnalysisPanel } from '../components/backlog/RepoAnalysisPanel'
import { RepositoryInsight } from '../components/backlog/RepositoryInsight'
import { TaskList } from '../components/backlog/TaskList'
import { describeRepoPath } from '../lib/repoPath'
import { api, ApiError } from '../api'
import type { ProjectAnalysis, RepositorySummary, Run, Task } from '../types'

export function BacklogPage() {
  const { id } = useParams<{ id: string }>()
  const repositoryId = Number(id)
  const navigate = useNavigate()

  const [repository, setRepository] = useState<RepositorySummary | null>(null)
  const [analysis, setAnalysis] = useState<ProjectAnalysis | null>(null)
  const [tasks, setTasks] = useState<Task[] | null>(null)
  const [latestRuns, setLatestRuns] = useState<Record<string, Run>>({})
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const [repos, taskList, latestAnalysis] = await Promise.all([
      api.listRepositories(),
      api.listRepositoryTasks(repositoryId),
      api.getRepositoryAnalysis(repositoryId),
    ])
    setRepository(repos.find((r) => r.id === repositoryId) ?? null)
    setTasks(taskList)
    setAnalysis(latestAnalysis)

    const needingRun = taskList.filter((t) => t.status !== 'backlog' && t.status !== 'approved')
    const runEntries = await Promise.all(
      needingRun.map(async (task) => {
        const runs = await api.listTaskRuns(task.id)
        return [task.id, runs[0]] as const
      }),
    )
    setLatestRuns(Object.fromEntries(runEntries.filter(([, run]) => run)))
  }, [repositoryId])

  useEffect(() => {
    load().catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load this repository.'))
  }, [load])

  // Light polling while anything is actively running, so status/badges catch up without SSE.
  useEffect(() => {
    const anyRunning = tasks?.some((t) => t.status === 'running') ?? false
    if (!anyRunning) return
    const interval = setInterval(load, 4000)
    return () => clearInterval(interval)
  }, [tasks, load])

  async function approve(taskId: string) {
    setBusyTaskId(taskId)
    setError(null)
    try {
      await api.approveTask(taskId)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to approve task.')
    } finally {
      setBusyTaskId(null)
    }
  }

  async function startRun(taskId: string) {
    setBusyTaskId(taskId)
    setError(null)
    try {
      const run = await api.startRun(taskId)
      navigate(`/runs/${run.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to start run.')
      setBusyTaskId(null)
    }
  }

  async function generateMoreTasks() {
    setGenerating(true)
    setError(null)
    try {
      await api.generateTasks(repositoryId)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to generate tasks.')
    } finally {
      setGenerating(false)
    }
  }

  const repoName = repository ? describeRepoPath(repository.path).name : `Repository #${repositoryId}`

  return (
    <div className="landing-theme min-h-screen bg-background font-sans text-foreground">
      <DashboardNav />

      <main className="py-10">
        <Container>
          <BacklogHeader
            repoName={repoName}
            fileCount={analysis?.source_files ?? null}
            languages={analysis?.languages ?? {}}
            generating={generating}
            onBack={() => navigate('/repositories')}
            onGenerate={generateMoreTasks}
          />

          <RepoTabs repositoryId={repositoryId} />

          {error && (
            <div className="mt-6 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {tasks === null ? (
            <p className="mt-8 text-sm text-muted-foreground">Loading…</p>
          ) : (
            <>
              <div className="mt-8 grid gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                <RepoAnalysisPanel onGenerate={generateMoreTasks} generating={generating} />
                <RepositoryInsight tasks={tasks} />
              </div>

              <div className="mt-10">
                <TaskList
                  tasks={tasks}
                  latestRuns={latestRuns}
                  busyTaskId={busyTaskId}
                  onApprove={approve}
                  onStartRun={startRun}
                />
              </div>
            </>
          )}
        </Container>
      </main>
    </div>
  )
}
