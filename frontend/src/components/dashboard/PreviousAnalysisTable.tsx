import { Link } from 'react-router-dom'
import { Card } from '../ui/Card'
import { Clock, ChevronRight } from 'lucide-react'
import { describeRepoPath } from '../../lib/repoPath'
import type { RepositorySummary } from '../../types'

export function PreviousAnalysisTable({ repositories }: { repositories: RepositorySummary[] }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-2.5 border-b border-border px-6 py-4">
        <Clock className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">Previously analyzed</span>
      </div>

      <div>
        {repositories.map((repo) => {
          const { name, source } = describeRepoPath(repo.path)
          return (
            <Link
              key={repo.id}
              to={`/repositories/${repo.id}`}
              className="flex w-full items-center gap-4 border-b border-border px-6 py-4 text-left transition-colors last:border-b-0 hover:bg-white/[0.02] focus-visible:bg-white/[0.03] focus-visible:outline-none"
            >
              <span className="min-w-0 flex-[1.6] truncate font-mono text-[13px] text-foreground">{name}</span>
              <span className="hidden flex-1 text-sm text-muted-foreground sm:block">{source}</span>
              <span className="hidden flex-1 text-sm text-muted-foreground md:block">
                Analyzed {new Date(repo.created_at).toLocaleString()}
              </span>
              <span className="ml-auto flex shrink-0 items-center gap-1 text-sm text-muted-foreground">
                View details
                <ChevronRight className="h-3.5 w-3.5" />
              </span>
            </Link>
          )
        })}
      </div>
    </Card>
  )
}
