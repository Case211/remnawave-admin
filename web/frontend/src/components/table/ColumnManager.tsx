import { useTranslation } from 'react-i18next'
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

import { GripVertical, LayoutGrid, RotateCcw } from '@/components/brand/icons'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import type { TableColumn } from '@/lib/useTableColumns'

export interface ColumnManagerProps {
  /** Все колонки в текущем порядке — из useTableColumns().ordered. */
  columns: TableColumn[]
  isVisible: (key: string) => boolean
  onToggle: (key: string) => void
  /** Поставить колонку на место другой — useTableColumns().reorder. */
  onReorder: (activeKey: string, overKey: string) => void
  onReset: () => void
  isCustomized?: boolean
  className?: string
}

/**
 * Меню «какие колонки показывать и в каком порядке».
 *
 * Ничего не знает о конкретной таблице: получает описания колонок и
 * колбэки из useTableColumns, поэтому подключается к любой таблице —
 * витрине юзеров, списку нод, хостам.
 *
 * Порядок меняется перетаскиванием за ручку. Сенсоры те же, что у
 * виджетов дашборда: мышь, палец (с задержкой, чтобы не мешать скроллу
 * списка) и клавиатура — последняя важна, потому что кнопок-стрелок
 * здесь нет и без неё порядок был бы недоступен без мыши.
 */
export function ColumnManager({
  columns,
  isVisible,
  onToggle,
  onReorder,
  onReset,
  isCustomized = false,
  className,
}: ColumnManagerProps) {
  const { t } = useTranslation()

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    onReorder(String(active.id), String(over.id))
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(isCustomized && 'border-primary-500/40 text-primary-300', className)}
          title={t('common.columns.title')}
        >
          <LayoutGrid className="w-4 h-4 mr-2" />
          {t('common.columns.button')}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-2">
        <div className="flex items-center justify-between px-2 py-1.5">
          <span className="text-xs font-medium text-dark-200">{t('common.columns.title')}</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={onReset}
            disabled={!isCustomized}
          >
            <RotateCcw className="w-3.5 h-3.5 mr-1" />
            {t('common.columns.reset')}
          </Button>
        </div>

        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={columns.map((c) => c.key)} strategy={verticalListSortingStrategy}>
            <ul className="max-h-[320px] overflow-y-auto">
              {columns.map((column) => (
                <SortableColumnRow
                  key={column.key}
                  column={column}
                  visible={isVisible(column.key)}
                  onToggle={() => onToggle(column.key)}
                />
              ))}
            </ul>
          </SortableContext>
        </DndContext>

        <p className="px-2 pt-1.5 text-[11px] text-dark-400">{t('common.columns.hint')}</p>
      </PopoverContent>
    </Popover>
  )
}

function SortableColumnRow({
  column,
  visible,
  onToggle,
}: {
  column: TableColumn
  visible: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: column.key,
  })

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        'flex items-center gap-2 rounded px-1 py-1.5 hover:bg-[var(--glass-bg)]',
        isDragging && 'bg-[var(--glass-bg)] ring-1 ring-primary-500/50',
      )}
    >
      <button
        type="button"
        className="shrink-0 p-0.5 text-dark-400 hover:text-white cursor-grab active:cursor-grabbing touch-none"
        aria-label={t('common.columns.drag')}
        title={t('common.columns.drag')}
        {...attributes}
        {...listeners}
      >
        <GripVertical className="w-3.5 h-3.5" />
      </button>
      <Checkbox
        id={`col-${column.key}`}
        checked={visible}
        disabled={column.locked}
        onCheckedChange={onToggle}
      />
      <label
        htmlFor={`col-${column.key}`}
        className={cn(
          'flex-1 text-sm cursor-pointer truncate',
          column.locked ? 'text-dark-300' : 'text-dark-100',
        )}
      >
        {t(column.labelKey)}
      </label>
    </li>
  )
}
