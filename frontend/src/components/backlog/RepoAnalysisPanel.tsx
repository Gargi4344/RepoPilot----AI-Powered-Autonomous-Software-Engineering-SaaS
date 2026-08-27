import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { PREngineerMark } from '../brand/Marks'
import { Code2, Settings, CheckCircle2, Sparkles } from 'lucide-react'

export function RepoAnalysisPanel({ onGenerate, generating }: { onGenerate?: () => void; generating?: boolean }) {
  return (
    <Card className="relative flex flex-col gap-8 overflow-hidden p-8 lg:flex-row lg:items-center">
      <div className="max-w-sm">
        <p className="text-xs font-medium tracking-[0.15em] text-muted-foreground">PR ENGINEER ANALYSIS</p>
        <h2 className="mt-4 text-balance text-2xl font-semibold tracking-tight text-foreground">
          Ready to find more useful work
        </h2>
        <p className="mt-3 text-sm text-muted-foreground">
          Ask the local model to read through this repository and propose additional candidate
          tasks, on top of the deterministic backlog below.
        </p>
        <Button variant="secondary" className="mt-6" onClick={onGenerate} disabled={generating}>
          {generating ? 'Asking the model…' : 'Generate tasks with AI'}
          {!generating && <Sparkles className="h-4 w-4" />}
        </Button>
      </div>

      <div className="relative mx-auto aspect-square w-full max-w-[280px] shrink-0">
        <svg viewBox="0 0 280 280" className="absolute inset-0 h-full w-full" aria-hidden="true">
          {[120, 80].map((r) => (
            <circle key={r} cx="140" cy="140" r={r} fill="none" stroke="var(--color-border)" strokeWidth="1" />
          ))}
          <line x1="140" y1="60" x2="140" y2="100" stroke="var(--color-border-strong)" strokeWidth="1" />
          <line x1="140" y1="180" x2="80" y2="215" stroke="var(--color-border-strong)" strokeWidth="1" />
          <line x1="140" y1="180" x2="200" y2="215" stroke="var(--color-border-strong)" strokeWidth="1" />
          <circle cx="65" cy="120" r="3" fill="var(--color-accent)" />
          <circle cx="215" cy="140" r="3" fill="var(--color-accent)" />
          <line x1="120" y1="150" x2="65" y2="120" stroke="var(--color-border)" strokeWidth="1" strokeDasharray="2 4" />
          <line x1="160" y1="150" x2="215" y2="140" stroke="var(--color-border)" strokeWidth="1" strokeDasharray="2 4" />
        </svg>

        <div className="absolute left-1/2 top-1/2 flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-border-strong bg-surface shadow-[0_0_50px_rgba(255,255,255,0.08)]">
          <PREngineerMark className="h-6 w-6 text-foreground" />
        </div>

        <div className="absolute left-1/2 top-[21%] flex -translate-x-1/2 flex-col items-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border-strong bg-surface text-muted-foreground">
            <Code2 className="h-4 w-4" />
          </div>
          <span className="text-[10px] font-medium tracking-wide text-muted-foreground">CODEBASE</span>
        </div>

        <div className="absolute bottom-[6%] left-[27%] flex -translate-x-1/2 flex-col items-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-accent/40 bg-surface text-accent">
            <CheckCircle2 className="h-4 w-4" />
          </div>
          <span className="text-[10px] font-medium tracking-wide text-muted-foreground">TESTS</span>
        </div>

        <div className="absolute bottom-[6%] right-[1%] flex flex-col items-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border-strong bg-surface text-muted-foreground">
            <Settings className="h-4 w-4" />
          </div>
          <span className="text-[10px] font-medium tracking-wide text-muted-foreground">CONFIG</span>
        </div>
      </div>
    </Card>
  )
}
