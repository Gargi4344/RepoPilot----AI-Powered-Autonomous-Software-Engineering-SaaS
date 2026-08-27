import { Bot, GitBranch, GitCommitHorizontal, GitPullRequest, Calendar } from 'lucide-react'

export interface RunInfoStripProps {
  branch: string | null
  baseBranch: string | null
  started: string | null
  commit: string | null
  pullRequest: string | null
  aiProvider?: string | null
  aiModel?: string | null
}

const PROVIDER_LABEL: Record<string, string> = { ollama: 'Ollama', anthropic: 'Anthropic', gemini: 'Gemini' }

export function RunInfoStrip({ branch, baseBranch, started, commit, pullRequest, aiProvider, aiModel }: RunInfoStripProps) {
  const items = [
    { icon: GitBranch, label: 'BRANCH', value: branch ?? '—', mono: true },
    { icon: GitBranch, label: 'BASE BRANCH', value: baseBranch ?? '—', mono: true },
    { icon: Calendar, label: 'STARTED', value: started ? new Date(started).toLocaleString() : '—', mono: false },
    { icon: GitCommitHorizontal, label: 'COMMIT', value: commit ? commit.slice(0, 12) : '—', mono: true },
    {
      icon: Bot,
      label: 'AI MODEL',
      value: aiModel ? `${aiProvider ? `${PROVIDER_LABEL[aiProvider] ?? aiProvider} · ` : ''}${aiModel}` : '—',
      mono: false,
    },
  ]

  return (
    <div className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-3">
      {items.map((item) => (
        <div key={item.label} className="bg-surface p-4">
          <div className="flex items-center gap-1.5 text-[10px] font-medium tracking-wide text-muted-foreground">
            <item.icon className="h-3 w-3" />
            {item.label}
          </div>
          <p className={`mt-1.5 truncate text-sm text-foreground ${item.mono ? 'font-mono' : ''}`}>{item.value}</p>
        </div>
      ))}
      <div className="bg-surface p-4">
        <div className="flex items-center gap-1.5 text-[10px] font-medium tracking-wide text-muted-foreground">
          <GitPullRequest className="h-3 w-3" />
          PULL REQUEST
        </div>
        {pullRequest ? (
          <a
            href={pullRequest}
            target="_blank"
            rel="noreferrer"
            className="mt-1.5 block truncate text-sm text-accent hover:underline"
          >
            {pullRequest}
          </a>
        ) : (
          <p className="mt-1.5 truncate text-sm text-foreground">—</p>
        )}
      </div>
    </div>
  )
}
