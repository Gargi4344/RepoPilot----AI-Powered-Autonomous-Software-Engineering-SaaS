export function SegmentedProgressBar({ progress, segments = 20 }: { progress: number; segments?: number }) {
  const litCount = Math.round((progress / 100) * segments)

  return (
    <div className="flex items-center gap-6">
      <div className="flex flex-1 items-center gap-[3px]">
        {Array.from({ length: segments }).map((_, i) => {
          const lit = i < litCount
          const isEdge = i === litCount - 1
          return (
            <span
              key={i}
              className="h-2 flex-1 rounded-[1px] transition-colors duration-300"
              style={{
                backgroundColor: lit ? 'var(--color-accent)' : 'rgba(255,255,255,0.07)',
                boxShadow: isEdge ? '0 0 8px var(--color-accent)' : 'none',
              }}
            />
          )
        })}
      </div>
      <span className="w-10 shrink-0 text-right font-mono text-sm text-foreground">{Math.round(progress)}%</span>
    </div>
  )
}
