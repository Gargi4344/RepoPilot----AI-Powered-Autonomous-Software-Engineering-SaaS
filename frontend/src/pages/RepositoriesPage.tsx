import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Container } from '../components/ui/Container'
import { DashboardNav } from '../components/dashboard/DashboardNav'
import { RepoCard } from '../components/dashboard/RepoCard'
import { PreviousAnalysisTable } from '../components/dashboard/PreviousAnalysisTable'
import { api, ApiError } from '../api'
import type { GitHubRepo, RepositorySummary } from '../types'
import { Search, Plus } from 'lucide-react'

export function RepositoriesPage() {
  const [repositories, setRepositories] = useState<RepositorySummary[] | null>(null)
  const [githubRepos, setGithubRepos] = useState<GitHubRepo[] | null>(null)
  const [githubError, setGithubError] = useState<string | null>(null)
  const [startingRepo, setStartingRepo] = useState<string | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api.listRepositories().then(setRepositories).catch(() => setRepositories([]))
    api
      .listGithubRepos()
      .then(setGithubRepos)
      .catch((err) =>
        setGithubError(err instanceof ApiError ? err.message : 'Could not load your GitHub repositories.'),
      )
  }, [])

  const startRepo = async (repo: GitHubRepo) => {
    setStartingRepo(repo.full_name)
    setStartError(null)
    try {
      const plan = await api.startGithubRepo(repo.full_name)
      navigate(`/repositories/${plan.repository_id}`)
    } catch (err) {
      setStartingRepo(null)
      setStartError(err instanceof ApiError ? err.message : `Could not start ${repo.full_name}.`)
    }
  }

  const filteredRepos = useMemo(() => {
    if (!githubRepos) return null
    const q = query.trim().toLowerCase()
    if (!q) return githubRepos
    return githubRepos.filter(
      (repo) => repo.name.toLowerCase().includes(q) || repo.description?.toLowerCase().includes(q),
    )
  }, [githubRepos, query])

  return (
    <div className="landing-theme min-h-screen bg-background font-sans text-foreground">
      <DashboardNav />

      <main className="py-10">
        <Container>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-foreground">Repositories</h1>
              <p className="mt-1.5 text-sm text-muted-foreground">Choose where PR Engineer should work.</p>
            </div>
            <button
              type="button"
              onClick={() => navigate('/analyze')}
              className="inline-flex h-11 items-center gap-2 rounded-md border border-dashed border-border-strong px-4 text-sm text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground"
            >
              <Plus className="h-4 w-4" />
              Analyze local path
            </button>
          </div>

          {(startError || githubError) && (
            <div className="mt-6 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {startError ?? githubError}
            </div>
          )}

          <div className="mt-8">
            <div className="relative">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="search"
                placeholder="Search your repositories..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="h-11 w-full rounded-md border border-border bg-surface/60 pl-11 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet"
              />
            </div>
          </div>

          <div className="mt-8">
            {githubError ? null : filteredRepos === null ? (
              <p className="text-sm text-muted-foreground">Loading your repositories…</p>
            ) : filteredRepos.length === 0 ? (
              <div className="rounded-md border border-dashed border-border px-6 py-10 text-center text-sm text-muted-foreground">
                {githubRepos && githubRepos.length === 0
                  ? 'No public repositories found on your GitHub account.'
                  : 'No repositories match your search.'}
              </div>
            ) : (
              <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
                {filteredRepos.map((repo) => (
                  <RepoCard
                    key={repo.full_name}
                    repo={repo}
                    onStart={startRepo}
                    starting={startingRepo === repo.full_name}
                  />
                ))}
              </div>
            )}
          </div>

          {repositories !== null && repositories.length > 0 && (
            <div className="mt-8">
              <PreviousAnalysisTable repositories={repositories} />
            </div>
          )}
        </Container>
      </main>
    </div>
  )
}
