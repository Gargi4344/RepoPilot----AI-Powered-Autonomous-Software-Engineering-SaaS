interface RepoGraphProps {
  nodes?: number
  activeIndex?: number
  branch?: string
}

export function RepoGraph({ nodes = 6, activeIndex = 4, branch = 'main' }: RepoGraphProps) {
  const width = 300
  const height = 36
  const padRight = 46
  const usableWidth = width - padRight
  const step = usableWidth / (nodes - 1)
  const y = height / 2

  const points = Array.from({ length: nodes }, (_, i) => {
    const x = i * step
    const dip = i === activeIndex ? y + 10 : i === activeIndex - 1 ? y + 4 : y
    return { x, y: i >= activeIndex - 1 && i < nodes - 1 ? dip : y }
  })

  const path = points.map((p, i) => (i === 0 ? `M${p.x},${p.y}` : `L${p.x},${p.y}`)).join(' ')

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-9 w-full" aria-hidden="true">
      <path d={path} fill="none" stroke="var(--color-border-strong)" strokeWidth="1.5" />
      {points.map((p, i) =>
        i === activeIndex ? (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r="8" fill="var(--color-accent)" opacity="0.18" />
            <circle cx={p.x} cy={p.y} r="4" fill="var(--color-accent)" />
          </g>
        ) : (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill="var(--color-background)" stroke="var(--color-border-strong)" strokeWidth="1.4" />
        ),
      )}
      <text x={width - padRight + 14} y={y + 4} fontSize="11" fontFamily="var(--font-sans)" fill="var(--color-muted-foreground)">
        {branch}
      </text>
    </svg>
  )
}
