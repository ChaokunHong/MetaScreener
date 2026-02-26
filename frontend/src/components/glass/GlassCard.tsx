import type { ReactNode } from 'react'
import { clsx } from 'clsx'

interface GlassCardProps {
  children: ReactNode
  className?: string
  variant?: 'normal' | 'strong' | 'subtle'
}

export function GlassCard({ children, className, variant = 'normal' }: GlassCardProps) {
  return (
    <div
      className={clsx(
        'glass p-6 rounded-2xl',
        variant === 'strong' && 'glass-strong',
        variant === 'subtle' && 'glass-subtle',
        className,
      )}
    >
      {children}
    </div>
  )
}
