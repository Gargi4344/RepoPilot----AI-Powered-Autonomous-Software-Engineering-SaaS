import { cn } from './cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'outline' | 'accent' | 'violet'
type Size = 'sm' | 'md' | 'lg'

const sizeClasses: Record<Size, string> = {
  sm: 'h-9 px-3.5 text-sm',
  md: 'h-11 px-5 text-sm',
  lg: 'h-12 px-6 text-[0.95rem]',
}

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-primary text-primary-foreground hover:bg-primary/90 shadow-[0_0_0_1px_var(--color-border-strong),0_18px_40px_-24px_oklch(1_0_0/40%)]',
  secondary: 'bg-surface-2 text-foreground border border-border hover:border-border-strong',
  ghost: 'text-muted-foreground hover:text-foreground hover:bg-surface',
  outline: 'border border-border-strong text-foreground hover:bg-surface hover:border-foreground/40',
  accent: 'border border-accent/50 text-accent bg-accent/8 hover:bg-accent/14 hover:border-accent/80',
  violet: 'bg-violet text-foreground hover:brightness-110 shadow-[0_18px_44px_-22px_var(--color-violet)]',
}

export function buttonVariants(
  opts: { variant?: Variant; size?: Size; className?: string } = {},
): string {
  const { variant = 'primary', size = 'md', className } = opts
  return cn(
    'inline-flex items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap',
    'transition-[transform,background-color,border-color,box-shadow,color] duration-200',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
    'disabled:pointer-events-none disabled:opacity-50 active:translate-y-px',
    sizeClasses[size],
    variantClasses[variant],
    className,
  )
}
