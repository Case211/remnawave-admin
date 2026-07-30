import { useTranslation } from 'react-i18next'

import { ArrowDown, ArrowUp, LayoutGrid, RotateCcw } from '@/components/brand/icons'
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
  onMove: (key: string, direction: -1 | 1) => void
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
 */
export function ColumnManager({
  columns,
  isVisible,
  onToggle,
  onMove,
  onReset,
  isCustomized = false,
  className,
}: ColumnManagerProps) {
  const { t } = useTranslation()

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

        <ul className="max-h-[320px] overflow-y-auto">
          {columns.map((column, index) => (
            <li
              key={column.key}
              className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-[var(--glass-bg)]"
            >
              <Checkbox
                id={`col-${column.key}`}
                checked={isVisible(column.key)}
                disabled={column.locked}
                onCheckedChange={() => onToggle(column.key)}
              />
              <label
                htmlFor={`col-${column.key}`}
                className={cn(
                  'flex-1 text-sm cursor-pointer',
                  column.locked ? 'text-dark-300' : 'text-dark-100',
                )}
              >
                {t(column.labelKey)}
              </label>
              <div className="flex items-center">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  disabled={index === 0}
                  onClick={() => onMove(column.key, -1)}
                  aria-label={t('common.columns.moveUp')}
                >
                  <ArrowUp className="w-3.5 h-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  disabled={index === columns.length - 1}
                  onClick={() => onMove(column.key, 1)}
                  aria-label={t('common.columns.moveDown')}
                >
                  <ArrowDown className="w-3.5 h-3.5" />
                </Button>
              </div>
            </li>
          ))}
        </ul>

        <p className="px-2 pt-1.5 text-[11px] text-dark-400">{t('common.columns.hint')}</p>
      </PopoverContent>
    </Popover>
  )
}
