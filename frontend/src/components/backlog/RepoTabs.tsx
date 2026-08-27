import { NavLink } from 'react-router-dom'
import { cn } from '../../lib/cn'

export function RepoTabs({ repositoryId }: { repositoryId: number }) {
  const tabs = [
    { label: 'Backlog', to: `/repositories/${repositoryId}` },
    { label: 'Autopilot', to: `/repositories/${repositoryId}/autopilot` },
  ]

  return (
    <nav className="mt-6 flex items-center gap-6 border-b border-border" aria-label="Repository sections">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end
          className={({ isActive }) =>
            cn(
              'relative pb-3 text-sm transition-colors',
              isActive
                ? 'text-foreground after:absolute after:-bottom-px after:left-0 after:h-[2px] after:w-full after:bg-accent'
                : 'text-muted-foreground hover:text-foreground',
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
