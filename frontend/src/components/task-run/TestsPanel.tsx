import { useState } from 'react'
import { Card } from '../ui/Card'
import { CheckCircle2, XCircle, ChevronDown, ChevronRight } from 'lucide-react'
import type { TestOutcome } from '../../types'

export function TestsPanel({ testResults }: { testResults: TestOutcome[] }) {
  const [expanded, setExpanded] = useState<string | null>(null)

  if (testResults.length === 0) return null

  return (
    <Card className="mt-5 p-6">
      <p className="text-xs font-medium tracking-[0.15em] text-muted-foreground">TESTS</p>

      <div className="mt-4 space-y-2">
        {testResults.map((result) => {
          const passed = result.exit_code === 0
          const output = (result.stdout + result.stderr).trim()
          const isOpen = expanded === result.tool
          return (
            <div key={result.tool}>
              <div className="flex items-center gap-4">
                <span className="w-20 shrink-0 truncate text-sm text-foreground">{result.tool}</span>
                <span className="flex w-20 shrink-0 items-center gap-1.5 text-sm">
                  {passed ? (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5 text-accent" />
                      <span className="text-accent">passed</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="h-3.5 w-3.5 text-destructive" />
                      <span className="text-destructive">failed</span>
                    </>
                  )}
                </span>
                <span className="flex-1" />
                <span className="w-14 shrink-0 text-right font-mono text-xs text-muted-foreground">
                  {result.duration_seconds.toFixed(2)}s
                </span>
                {output && (
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : result.tool)}
                    className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                    aria-label={isOpen ? 'Hide output' : 'Show output'}
                  >
                    {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  </button>
                )}
              </div>
              {isOpen && output && (
                <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-border bg-surface p-3 font-mono text-xs text-muted-foreground">
                  {output}
                </pre>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}
