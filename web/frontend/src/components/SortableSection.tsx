import type { CSSProperties, ReactNode } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical } from '@/components/brand/icons'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

interface SortableSectionProps {
  id: string
  children: ReactNode
  /** Hide drag handle (e.g. when DnD is disabled for the section). */
  disabled?: boolean
  /** Position of the floating drag handle. Default: top-right. */
  handlePosition?: 'top-left' | 'top-right'
  /** Extra className on the wrapper div. */
  className?: string
}

/**
 * Wraps arbitrary section content with a drag handle for use inside
 * <DndContext> + <SortableContext>. Handle is hover-revealed and uses
 * absolute positioning so it doesn't push layout around.
 */
export function SortableSection({
  id,
  children,
  disabled,
  handlePosition = 'top-right',
  className,
}: SortableSectionProps) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
    disabled,
  })

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 50 : undefined,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        'relative group/sortable',
        isDragging && 'ring-2 ring-primary-500/60 rounded-xl shadow-[0_0_24px_-4px_rgba(99,102,241,0.45)]',
        className,
      )}
    >
      {!disabled && (
        <button
          type="button"
          className={cn(
            'absolute z-20 inline-flex items-center justify-center h-7 w-6 rounded-md',
            'bg-[var(--glass-bg)] backdrop-blur-sm border border-[var(--glass-border)]',
            'text-dark-300 hover:text-white hover:bg-white/10',
            'cursor-grab active:cursor-grabbing touch-none',
            'opacity-0 group-hover/sortable:opacity-100 focus-visible:opacity-100 transition-opacity',
            handlePosition === 'top-left' ? '-top-2 -left-2' : '-top-2 -right-2',
          )}
          aria-label={t('common.dragToReorder', { defaultValue: 'Перетащите для изменения порядка' })}
          title={t('common.dragToReorder', { defaultValue: 'Перетащите для изменения порядка' })}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="w-3.5 h-3.5" />
        </button>
      )}
      {children}
    </div>
  )
}
