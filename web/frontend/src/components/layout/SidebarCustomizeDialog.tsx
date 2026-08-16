import { useMemo } from 'react'
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

import { GripVertical, RotateCcw } from '@/components/brand/icons'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { entryKey } from '@/lib/sidebarOrder'
import {
  isNavGroup,
  isNavSection,
  type NavGroup,
  type NavItem,
  type NavigationEntry,
} from './navigation'

/** Префикс id подпункта группы: отделяет вложенный уровень от верхнего. */
const SUB = 'sub:'

interface SidebarCustomizeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Полное меню в текущем порядке, включая скрытое правами. */
  entries: NavigationEntry[]
  /** То, что этот админ реально видит, — его и показываем в списке. */
  visible: NavigationEntry[]
  onMoveTop: (keys: string[], activeKey: string, overKey: string) => void
  onMoveInGroup: (groupKey: string, hrefs: string[], activeHref: string, overHref: string) => void
  onReset: () => void
  isCustomized: boolean
}

/**
 * Диалог «в каком порядке идут пункты меню».
 *
 * Настройка живёт не в самом сайдбаре, а рядом: колонка узкая, со своим
 * скроллом и сворачиванием — перетаскивать в ней неудобно, а на телефоне она
 * вообще выезжает поверх экрана. Здесь же список показан целиком, той же
 * структурой, что и в меню: заголовок секции, пункты под ним, группа со
 * своими подпунктами.
 *
 * Изменения применяются сразу — сайдбар за диалогом перестраивается на
 * глазах, поэтому кнопки «сохранить» нет, а есть «сбросить».
 */
export function SidebarCustomizeDialog({
  open,
  onOpenChange,
  entries,
  visible,
  onMoveTop,
  onMoveInGroup,
  onReset,
  isCustomized,
}: SidebarCustomizeDialogProps) {
  const { t } = useTranslation()

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  /** Полный порядок верхнего уровня — он и сохраняется при перетаскивании. */
  const topKeys = useMemo(() => entries.map(entryKey), [entries])

  /** По id подпункта — ключ его группы и полный список маршрутов группы. */
  const subIndex = useMemo(() => {
    const index = new Map<string, { groupKey: string; hrefs: string[] }>()
    for (const entry of entries) {
      if (!isNavGroup(entry)) continue
      const groupKey = entryKey(entry)
      const hrefs = entry.items.map((item) => item.href)
      for (const href of hrefs) index.set(`${SUB}${href}`, { groupKey, hrefs })
    }
    return index
  }, [entries])

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const activeId = String(active.id)
    const overId = String(over.id)

    const from = subIndex.get(activeId)
    const to = subIndex.get(overId)
    if (from || to) {
      // Подпункт остаётся в своей группе: вытащить «Логи» из «Администрирования»
      // в корень меню нельзя — группа для того и заведена.
      if (!from || !to || from.groupKey !== to.groupKey) return
      onMoveInGroup(from.groupKey, from.hrefs, activeId.slice(SUB.length), overId.slice(SUB.length))
      return
    }

    onMoveTop(topKeys, activeId, overId)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('sidebar.customize.title')}</DialogTitle>
          <DialogDescription>{t('sidebar.customize.description')}</DialogDescription>
        </DialogHeader>

        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={visible.map(entryKey)} strategy={verticalListSortingStrategy}>
            <ul className="max-h-[55vh] space-y-0.5 overflow-y-auto pr-1">
              {visible.map((entry) => {
                const key = entryKey(entry)
                if (isNavSection(entry)) return <SortableSectionRow key={key} id={key} label={t(entry.name)} />
                if (isNavGroup(entry)) {
                  return (
                    <SortableGroupRow
                      key={key}
                      id={key}
                      group={entry}
                      label={t(entry.name)}
                    />
                  )
                }
                const item = entry as NavItem
                return (
                  <SortableItemRow key={key} id={key} item={item} label={t(item.name)} />
                )
              })}
            </ul>
          </SortableContext>
        </DndContext>

        <p className="text-[11px] text-dark-400">{t('sidebar.customize.hint')}</p>

        <DialogFooter className="gap-2">
          <Button variant="ghost" size="sm" onClick={onReset} disabled={!isCustomized}>
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            {t('sidebar.customize.reset')}
          </Button>
          <Button size="sm" onClick={() => onOpenChange(false)}>
            {t('sidebar.customize.done')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

type SortableHandle = Pick<ReturnType<typeof useSortable>, 'attributes' | 'listeners'>

/** Ручка перетаскивания — единственное, за что строка тянется. */
function DragHandle({ attributes, listeners }: SortableHandle) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      className="shrink-0 cursor-grab touch-none p-0.5 text-dark-400 hover:text-white active:cursor-grabbing"
      aria-label={t('sidebar.customize.drag')}
      title={t('sidebar.customize.drag')}
      {...attributes}
      {...listeners}
    >
      <GripVertical className="h-3.5 w-3.5" />
    </button>
  )
}

function useRow(id: string) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  return {
    ref: setNodeRef,
    style: { transform: CSS.Transform.toString(transform), transition },
    isDragging,
    handle: <DragHandle attributes={attributes} listeners={listeners} />,
  }
}

function SortableSectionRow({ id, label }: { id: string; label: string }) {
  const row = useRow(id)
  return (
    <li
      ref={row.ref}
      style={row.style}
      className={cn(
        'flex items-center gap-2 rounded px-1 py-1.5 mt-2 first:mt-0',
        'border-t border-[var(--glass-border)] pt-2.5',
        row.isDragging && 'bg-[var(--glass-bg)] ring-1 ring-primary-500/50',
      )}
    >
      {row.handle}
      <span className="text-[10px] font-bold uppercase tracking-widest text-dark-400">{label}</span>
    </li>
  )
}

function SortableItemRow({
  id,
  item,
  label,
  nested,
}: {
  id: string
  item: NavItem
  label: string
  nested?: boolean
}) {
  const row = useRow(id)
  return (
    <li
      ref={row.ref}
      style={row.style}
      className={cn(
        'flex items-center gap-2 rounded px-1 py-1.5 hover:bg-[var(--glass-bg)]',
        nested && 'ml-4 border-l border-[var(--glass-border)] pl-2',
        row.isDragging && 'bg-[var(--glass-bg)] ring-1 ring-primary-500/50',
      )}
    >
      {row.handle}
      <item.icon className={cn('shrink-0 text-dark-300', nested ? 'h-3.5 w-3.5' : 'h-4 w-4')} />
      <span className={cn('flex-1 truncate', nested ? 'text-xs text-dark-200' : 'text-sm text-dark-100')}>
        {label}
      </span>
    </li>
  )
}

function SortableGroupRow({ id, group, label }: { id: string; group: NavGroup; label: string }) {
  const { t } = useTranslation()
  const row = useRow(id)
  return (
    <>
      <li
        ref={row.ref}
        style={row.style}
        className={cn(
          'flex items-center gap-2 rounded px-1 py-1.5 hover:bg-[var(--glass-bg)]',
          row.isDragging && 'bg-[var(--glass-bg)] ring-1 ring-primary-500/50',
        )}
      >
        {row.handle}
        <group.icon className="h-4 w-4 shrink-0 text-dark-300" />
        <span className="flex-1 truncate text-sm text-dark-100">{label}</span>
      </li>
      <SortableContext
        items={group.items.map((item) => `${SUB}${item.href}`)}
        strategy={verticalListSortingStrategy}
      >
        {group.items.map((item) => (
          <SortableItemRow
            key={item.href}
            id={`${SUB}${item.href}`}
            item={item}
            label={t(item.name)}
            nested
          />
        ))}
      </SortableContext>
    </>
  )
}
