import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { clsx } from 'clsx'

interface GlassButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode
  variant?: 'primary' | 'outline' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
}

export function GlassButton({
  children,
  variant = 'primary',
  size = 'md',
  className,
  ...props
}: GlassButtonProps) {
  return (
    <button
      className={clsx(
        'rounded-xl font-medium transition-all cursor-pointer',
        variant === 'primary' && 'glass-button',
        variant === 'outline' && 'glass-button-outline',
        variant === 'ghost' && 'text-white/70 hover:text-white hover:bg-white/5',
        size === 'sm' && 'px-3 py-1.5 text-sm',
        size === 'md' && 'px-5 py-2.5 text-sm',
        size === 'lg' && 'px-6 py-3 text-base',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}
