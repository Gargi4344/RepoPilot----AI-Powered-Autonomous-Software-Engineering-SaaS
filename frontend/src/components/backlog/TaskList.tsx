import { TaskRow } from './TaskRow'
import { Sparkles } from 'lucide-react'
import type { Run, Task } from '../../types'

export function TaskList({
  tasks,
  latestRuns,
  busyTaskId,
  onApprove,
  onStartRun,
}: {
  tasks: Task[]
  latestRuns: Record<string, Run>
  busyTaskId: string | null
  onApprove: (id: string) => void
  onStartRun: (id: string) => void
}) {
  return (
    <div>
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <Sparkles className="h-4 w-4 text-violet" />
        Tasks ({tasks.length})
      </div>

      {tasks.length === 0 ? (
        <div className="mt-5 rounded-md border border-dashed border-border px-6 py-10 text-center text-sm text-muted-foreground">
          No candidate tasks were found for this repository yet.
        </div>
      ) : (
        <div className="mt-5 flex flex-col gap-3">
          {tasks.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              runId={latestRuns[task.id]?.id}
              runTriggeredBy={latestRuns[task.id]?.triggered_by}
              busy={busyTaskId === task.id}
              onApprove={onApprove}
              onStartRun={onStartRun}
            />
          ))}
        </div>
      )}
    </div>
  )
}
