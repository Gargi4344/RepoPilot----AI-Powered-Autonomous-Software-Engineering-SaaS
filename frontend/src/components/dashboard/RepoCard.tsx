import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { buttonVariants } from '../../lib/buttonVariants'
import { GithubMark } from '../brand/Marks'
import { RepoGraph } from './RepoGraph'
import { Play, ArrowUpRight, Clock, Lock, GitFork } from 'lucide-react'
import type { GitHubRepo } from '../../types'

function relativeTime(iso: string): string {
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.floor(months / 12)}y ago`
}

// Purely decorative graph variety -- not a claim about the repo's real commit history.
function decorativeActiveIndex(name: string): number {
  const sum = [...name].reduce((acc, ch) => acc + ch.charCodeAt(0), 0)
  return 2 + (sum % 4)
}

interface RepoCardProps {
  repo: GitHubRepo
  onStart: (repo: GitHubRepo) => void
  starting: boolean
}

export function RepoCard({ repo, onStart, starting }: RepoCardProps) {
  const owner = repo.full_name.split('/')[0]

  return (
    <Card className="flex flex-col p-6 transition-colors duration-200 hover:border-border-strong">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border-strong text-foreground">
          <GithubMark className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-[15px] font-medium text-foreground">{repo.name}</p>
          <p className="text-sm text-muted-foreground">{owner}</p>
        </div>
      </div>

      {repo.description && <p className="mt-4 line-clamp-2 text-sm text-muted-foreground">{repo.description}</p>}

      {(repo.private || repo.fork) && (
        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {repo.private && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Lock className="h-3 w-3" /> Private
            </span>
          )}
          {repo.fork && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <GitFork className="h-3 w-3" /> Fork
            </span>
          )}
        </div>
      )}

      <div className="mt-5">
        <RepoGraph activeIndex={decorativeActiveIndex(repo.name)} branch={repo.default_branch} />
      </div>

      <div className="mt-4 flex items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" />
          Updated {relativeTime(repo.updated_at)}
        </span>
      </div>

      <div className="mt-5 flex items-center gap-2 border-t border-border pt-5">
        <Button variant="secondary" size="sm" className="flex-1" onClick={() => onStart(repo)} disabled={starting}>
          {starting ? 'Starting…' : 'Start working'}
          {!starting && <Play className="h-3.5 w-3.5" />}
        </Button>
        <a href={repo.html_url} target="_blank" rel="noreferrer" className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
          View on GitHub
          <ArrowUpRight className="h-3.5 w-3.5" />
        </a>
      </div>
    </Card>
  )
}
