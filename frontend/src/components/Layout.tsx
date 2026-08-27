import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../hooks/useAuth'
import type { StatusSummary } from '../types'

export function Layout() {
  const [status, setStatus] = useState<StatusSummary | null>(null)
  const { user, logout } = useAuth()

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

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink to="/repositories" className="brand">
          PR Engineer
        </NavLink>
        <nav className="nav">
          <NavLink to="/repositories" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Repositories
          </NavLink>
          <NavLink to="/analyze" className={({ isActive }) => (isActive ? 'active' : '')}>
            Analyze
          </NavLink>
          <NavLink to="/activity" className={({ isActive }) => (isActive ? 'active' : '')}>
            Activity
          </NavLink>
        </nav>
        <div className="topbar-status">
          {status ? (
            <>
              <span>{status.running ?? 0} running</span>
              <span>&middot;</span>
              <span>{status.queued ?? 0} queued</span>
              <span>&middot;</span>
              <span>max {status.max_concurrent_runs}</span>
            </>
          ) : (
            <span>backend unreachable</span>
          )}
        </div>
        {user && (
          <div className="user-menu">
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="" className="user-avatar" />
            ) : (
              <span className="user-avatar user-avatar-fallback">{user.login[0]?.toUpperCase()}</span>
            )}
            <span>{user.name || user.login}</span>
            <button type="button" className="secondary" onClick={logout}>
              Sign out
            </button>
          </div>
        )}
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
