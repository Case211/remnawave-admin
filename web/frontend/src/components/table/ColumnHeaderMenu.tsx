import { useTranslation } from 'react-i18next'

import { ArrowDown, ArrowUp, Eye, EyeOff, Filter, MoreVertical, X } from '@/components/brand/icons'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export interface ColumnHeaderMenuProps {
  /** Подпись столбца — подставляется в пункты меню. */
  label: string
  /** Текущее направление сортировки по этому столбцу, если он активный. */
  sortDir?: 'asc' | 'desc' | null
  onSort?: (dir: 'asc' | 'desc') => void
  /** Вернуть сортировку по умолчанию. Не передан — пункт скрыт. */
  onClearSort?: () => void
  /** Фильтр по столбцу задан — тогда показываем «сбросить фильтр». */
  hasFilter?: boolean
  onClearFilter?: () => void
  /** Не передан — столбец скрыть нельзя (например, имя). */
  onHide?: () => void
  onShowAll?: () => void
}

/**
 * Меню столбца: сортировка, сброс фильтра, скрытие, «показать все».
 *
 * Живёт в общей табличной папке и не знает, чем таблица наполняется:
 * получает подпись и колбэки. Пункты, для которых колбэк не передан,
 * не отображаются — так одно меню подходит и столбцу без сортировки,
 * и столбцу, который нельзя спрятать.
 */
export function ColumnHeaderMenu({
  label,
  sortDir = null,
  onSort,
  onClearSort,
  hasFilter = false,
  onClearFilter,
  onHide,
  onShowAll,
}: ColumnHeaderMenuProps) {
  const { t } = useTranslation()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          aria-label={t('common.columns.menu', { column: label })}
          title={t('common.columns.menu', { column: label })}
          className="p-0.5 rounded text-dark-400 hover:text-white transition-colors"
        >
          <MoreVertical className="w-3.5 h-3.5" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60" onClick={(e) => e.stopPropagation()}>
        {onSort && (
          <>
            <DropdownMenuItem onClick={() => onSort('asc')} disabled={sortDir === 'asc'}>
              <ArrowUp className="w-4 h-4 mr-2" />
              {t('common.columns.sortAsc', { column: label })}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onSort('desc')} disabled={sortDir === 'desc'}>
              <ArrowDown className="w-4 h-4 mr-2" />
              {t('common.columns.sortDesc', { column: label })}
            </DropdownMenuItem>
            {onClearSort && (
              <DropdownMenuItem onClick={onClearSort} disabled={!sortDir}>
                <X className="w-4 h-4 mr-2" />
                {t('common.columns.clearSort')}
              </DropdownMenuItem>
            )}
          </>
        )}

        {onClearFilter && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onClearFilter} disabled={!hasFilter}>
              <Filter className="w-4 h-4 mr-2" />
              {t('common.columns.clearFilter')}
            </DropdownMenuItem>
          </>
        )}

        {(onHide || onShowAll) && <DropdownMenuSeparator />}
        {onHide && (
          <DropdownMenuItem onClick={onHide}>
            <EyeOff className="w-4 h-4 mr-2" />
            {t('common.columns.hide', { column: label })}
          </DropdownMenuItem>
        )}
        {onShowAll && (
          <DropdownMenuItem onClick={onShowAll}>
            <Eye className="w-4 h-4 mr-2" />
            {t('common.columns.showAll')}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
