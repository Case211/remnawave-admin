import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: ReactNode
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  size = 'md',
}: EmptyStateProps) {
  const padding = size === 'sm' ? 'py-6' : size === 'lg' ? 'py-16' : 'py-10'
  const iconSize = size === 'sm' ? 'w-8 h-8' : size === 'lg' ? 'w-14 h-14' : 'w-12 h-12'
  const titleSize = size === 'sm' ? 'text-sm' : 'text-base'

  return (
    <div className={cn('flex flex-col items-center justify-center text-center px-4', padding, className)}>
      {Icon && <Icon className={cn(iconSize, 'mb-3 text-dark-400')} aria-hidden="true" />}
      <p className={cn(titleSize, 'text-dark-100 font-medium')}>{title}</p>
      {description && <p className="text-sm text-dark-300 mt-1 max-w-md">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
