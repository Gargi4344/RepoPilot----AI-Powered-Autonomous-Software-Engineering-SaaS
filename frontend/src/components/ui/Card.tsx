import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/cn'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  glow?: 'none' | 'accent' | 'violet'
}

export function Card({ glow = 'none', className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'relative rounded-lg border border-border bg-card/80 backdrop-blur-[2px]',
        glow === 'accent' && 'border-accent/25 shadow-[0_0_80px_-40px_var(--color-accent)]',
        glow === 'violet' && 'border-violet/30 shadow-[0_0_90px_-40px_var(--color-violet)]',
        className,
      )}
      {...props}
    />
  )
}

export function CardLabel({
  children,
  tone = 'accent',
  className,
}: {
  children: ReactNode
  tone?: 'accent' | 'violet' | 'muted'
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 font-mono text-[0.7rem] tracking-[0.18em] uppercase',
        tone === 'accent' && 'text-accent',
        tone === 'violet' && 'text-violet',
        tone === 'muted' && 'text-muted-foreground',
        className,
      )}
    >
      {children}
    </div>
  )
}
