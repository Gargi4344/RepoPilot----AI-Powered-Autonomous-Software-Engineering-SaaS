import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { Container } from '../ui/Container'
import { PREngineerMark } from '../brand/Marks'
import { Bot, ChevronDown, Menu, X } from 'lucide-react'
import { cn } from '../../lib/cn'
import { api } from '../../api'
import { useAuth } from '../../hooks/useAuth'
import type { StatusSummary } from '../../types'

const TABS: { label: string; to: string }[] = [
  { label: 'Repositories', to: '/repositories' },
  { label: 'Analyze', to: '/analyze' },
  { label: 'Activity', to: '/activity' },
]

export function DashboardNav() {
  const [open, setOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [status, setStatus] = useState<StatusSummary | null>(null)
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    let cancelled = false
    const poll = () => {
      api
        .getStatus()
        .then((value) => {
          if (!cancelled) setStatus(value)
        })
        .catch(() => {
          if (!cancelled) setStatus(null)
        })
    }
    poll()
    const interval = setInterval(poll, 5000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  const handleLogout = async () => {
    setMenuOpen(false)
    await logout()
    navigate('/')
  }

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/90 backdrop-blur-md">
      <Container className="flex h-16 items-center justify-between">
        <div className="flex items-center gap-10">
          <NavLink to="/repositories" className="flex items-center gap-2.5 text-foreground">
            <PREngineerMark className="h-6 w-6" />
            <span className="text-[15px] font-semibold tracking-tight">PR Engineer</span>
          </NavLink>

          <nav className="hidden items-center gap-7 md:flex" aria-label="Primary">
            {TABS.map((tab) => (
              <NavLink
                key={tab.label}
                to={tab.to}
                className={({ isActive }) =>
                  cn(
                    'relative py-1 text-sm transition-colors',
                    isActive
                      ? 'text-foreground after:absolute after:-bottom-[21px] after:left-0 after:h-[2px] after:w-full after:bg-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )
                }
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="hidden items-center gap-6 md:flex">
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              {status?.running ?? 0} running
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-warn" />
              {status?.queued ?? 0} queued
            </span>
          </div>

          {user && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2.5 rounded-full py-1 pl-1 pr-2 transition-colors hover:bg-white/[0.04]"
              >
                {user.avatar_url ? (
                  <img src={user.avatar_url} alt="" className="h-7 w-7 rounded-full" />
                ) : (
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-violet to-accent text-[11px] font-semibold text-black">
                    {user.login[0]?.toUpperCase()}
                  </span>
                )}
                <span className="text-sm text-foreground">{user.name || user.login}</span>
                <ChevronDown className={cn('h-3.5 w-3.5 text-muted-foreground transition-transform', menuOpen && 'rotate-180')} />
              </button>

              {menuOpen && (
                <div className="absolute right-0 top-full mt-2 w-44 rounded-md border border-border bg-card py-1 shadow-[0_18px_40px_-24px_oklch(0_0_0/70%)]">
                  <NavLink
                    to="/settings"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 px-3.5 py-2 text-left text-sm text-muted-foreground hover:bg-white/[0.04] hover:text-foreground"
                  >
                    <Bot className="h-3.5 w-3.5" />
                    AI Model
                  </NavLink>
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="w-full px-3.5 py-2 text-left text-sm text-muted-foreground hover:bg-white/[0.04] hover:text-foreground"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <button
          className="-mr-2 p-2 text-foreground md:hidden"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </Container>

      {open && (
        <div className="border-t border-border bg-background/95 backdrop-blur-md md:hidden">
          <Container className="flex flex-col gap-1 py-4">
            {TABS.map((tab) => (
              <NavLink
                key={tab.label}
                to={tab.to}
                onClick={() => setOpen(false)}
                className={({ isActive }) => cn('py-2.5 text-sm', isActive ? 'text-foreground' : 'text-muted-foreground')}
              >
                {tab.label}
              </NavLink>
            ))}
            {user && (
              <div className="mt-3 border-t border-border pt-4">
                <div className="flex items-center justify-between gap-2.5">
                  <div className="flex items-center gap-2.5">
                    {user.avatar_url ? (
                      <img src={user.avatar_url} alt="" className="h-7 w-7 rounded-full" />
                    ) : (
                      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-violet to-accent text-[11px] font-semibold text-black">
                        {user.login[0]?.toUpperCase()}
                      </span>
                    )}
                    <span className="text-sm text-foreground">{user.name || user.login}</span>
                  </div>
                  <button type="button" onClick={handleLogout} className="text-sm text-muted-foreground hover:text-foreground">
                    Sign out
                  </button>
                </div>
                <NavLink
                  to="/settings"
                  onClick={() => setOpen(false)}
                  className="mt-3 flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
                >
                  <Bot className="h-3.5 w-3.5" />
                  AI Model
                </NavLink>
              </div>
            )}
          </Container>
        </div>
      )}
    </header>
  )
}
