import { ArrowRight } from 'lucide-react'
import { GITHUB_LOGIN_URL } from '../../api'
import { GithubMark, PREngineerMark } from '../brand/Marks'
import { Button } from '../ui/Button'
import { Container } from '../ui/Container'

export function FinalCTA() {
  return (
    <section className="section-seam relative overflow-hidden py-24 md:py-36" id="cta">
      <div className="pointer-events-none absolute inset-0 grid-faint opacity-30" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-72 bg-[radial-gradient(ellipse_at_bottom,oklch(0.78_0.17_152/10%),transparent_70%)]" />

      <Container className="relative">
        <div className="mx-auto flex max-w-md items-center justify-center gap-4 sm:gap-6">
          <span className="grid h-14 w-14 shrink-0 place-items-center rounded-xl border border-border bg-surface">
            <GithubMark className="h-6 w-6" />
          </span>
          <svg viewBox="0 0 160 24" className="h-6 min-w-0 flex-1" aria-hidden="true">
            <line x1="0" y1="12" x2="160" y2="12" stroke="var(--color-border-strong)" strokeDasharray="3 5" />
            <circle r="3" fill="var(--color-accent)">
              <animateMotion dur="2.6s" repeatCount="indefinite" path="M0 12 H160" />
            </circle>
          </svg>
          <span className="grid h-14 w-14 shrink-0 place-items-center rounded-xl border border-accent/40 bg-accent/8 shadow-[0_0_60px_-20px_var(--color-accent)]">
            <PREngineerMark className="h-6 w-6 text-accent" />
          </span>
        </div>

        <div className="mx-auto mt-12 max-w-2xl text-center">
          <h2 className="text-[clamp(2.1rem,5.6vw,3.6rem)] leading-[1] font-semibold tracking-[-0.03em] text-glow">
            Ship while you sleep
          </h2>
          <p className="mx-auto mt-5 max-w-lg text-muted-foreground">
            Sign in, pick a repo, approve a task -- PR Engineer opens its first draft pull request while you do something else.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a href={GITHUB_LOGIN_URL}>
              <Button size="lg">
                <GithubMark className="h-4.5 w-4.5" />
                Sign in with GitHub
              </Button>
            </a>
            <a href="#how-it-works">
              <Button size="lg" variant="ghost">
                See how it works
                <ArrowRight className="h-4 w-4" />
              </Button>
            </a>
          </div>
          <p className="mt-6 font-mono text-[0.68rem] tracking-[0.16em] text-muted-foreground/70 uppercase">
            public_repo scope only &middot; revoke anytime on GitHub
          </p>
        </div>
      </Container>
    </section>
  )
}

export function Footer() {
  return (
    <footer className="section-seam py-10">
      <Container size="wide">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <PREngineerMark className="h-5 w-5 shrink-0 text-muted-foreground" />
            <span className="truncate text-sm text-muted-foreground">PR Engineer &copy; {new Date().getFullYear()}</span>
          </div>
          <div className="flex shrink-0 items-center gap-5 text-xs text-muted-foreground">
            <a href="#how-it-works" className="transition-colors hover:text-foreground">
              How it works
            </a>
            <a href="#safety" className="transition-colors hover:text-foreground">
              Safety
            </a>
          </div>
        </div>
      </Container>
    </footer>
  )
}
