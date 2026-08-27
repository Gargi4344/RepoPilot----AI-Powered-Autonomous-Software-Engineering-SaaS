import { Card } from '../ui/Card'
import { Sparkles } from 'lucide-react'
import type { Task } from '../../types'

const CATEGORY_LABEL: Record<string, string> = {
  'repository-todo': 'Tracked TODOs',
  'repository-analysis': 'Repository checks',
  'llm-backlog': 'AI proposed',
}

const CATEGORY_ORDER = ['repository-todo', 'repository-analysis', 'llm-backlog']

function SegmentBar({ count, max }: { count: number; max: number }) {
  const segments = Math.max(max, 1)
  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: segments }).map((_, i) => (
        <span key={i} className={`h-2 w-3.5 rounded-[2px] ${i < count ? 'bg-foreground' : 'bg-white/[0.07]'}`} />
      ))}
    </div>
  )
}

export function RepositoryInsight({ tasks }: { tasks: Task[] }) {
  const counts = new Map<string, number>()
  for (const task of tasks) counts.set(task.source, (counts.get(task.source) ?? 0) + 1)
  const categories = CATEGORY_ORDER.filter((source) => counts.has(source)).map((source) => ({
    label: CATEGORY_LABEL[source] ?? source,
    count: counts.get(source) ?? 0,
  }))
  const max = Math.max(1, ...categories.map((c) => c.count))

  return (
    <Card className="flex h-full flex-col p-8">
      <p className="text-xs font-medium tracking-[0.15em] text-muted-foreground">REPOSITORY INSIGHT</p>

      <div className="mt-4 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-violet" />
        <p className="text-sm text-foreground">{tasks.length} candidate task{tasks.length === 1 ? '' : 's'} found</p>
      </div>

      <div className="mt-8 flex flex-1 flex-col justify-center gap-6">
        {categories.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tasks yet.</p>
        ) : (
          categories.map((c) => (
            <div key={c.label} className="flex items-center justify-between gap-4">
              <span className="w-32 shrink-0 text-sm text-muted-foreground">{c.label}</span>
              <SegmentBar count={c.count} max={max} />
              <span className="w-4 shrink-0 text-right text-sm text-foreground">{c.count}</span>
            </div>
          ))
        )}
      </div>
    </Card>
  )
}
