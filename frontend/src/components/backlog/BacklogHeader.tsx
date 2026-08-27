import { Button } from '../ui/Button'
import { GithubMark } from '../brand/Marks'
import { ArrowLeft, File, Sparkles } from 'lucide-react'

const TAG_COLORS = ['var(--color-info)', 'var(--color-violet)', 'var(--color-warn)', 'var(--color-accent)']

export interface BacklogHeaderProps {
  repoName: string
  fileCount: number | null
  languages: Record<string, number>
  generating?: boolean
  onBack?: () => void
  onGenerate?: () => void
}

export function BacklogHeader({ repoName, fileCount, languages, generating, onBack, onGenerate }: BacklogHeaderProps) {
  const tags = Object.keys(languages)

  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to repositories
      </button>

      <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">Backlog</h1>

          <div className="mt-3 flex flex-wrap items-center gap-2.5">
            <span className="flex items-center gap-1.5 truncate text-sm text-muted-foreground">
              <GithubMark className="h-3.5 w-3.5 shrink-0" />
              {repoName}
            </span>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-muted-foreground">
            {fileCount !== null && (
              <span className="flex items-center gap-1.5">
                <File className="h-3.5 w-3.5" />
                {fileCount} source files
              </span>
            )}
            {tags.map((label, i) => (
              <span key={label} className="flex items-center gap-1.5">
                {(fileCount !== null || i > 0) && <span className="text-muted-foreground/50">·</span>}
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: TAG_COLORS[i % TAG_COLORS.length] }} />
                {label}
              </span>
            ))}
          </div>
        </div>

        <Button variant="secondary" onClick={onGenerate} disabled={generating} className="shrink-0">
          {generating ? 'Asking the model…' : 'Generate tasks with AI'}
          {!generating && <Sparkles className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  )
}
