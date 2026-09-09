import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ChevronDown, X } from '@/components/brand/icons'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { SelectFilter, type ColumnFilterProps } from './ColumnFilter'

/** Значение, которое «показать всё»: пустая строка в Select запрещена Radix. */
const ANY = '_any'

/**
 * Фильтр столбца прямо в шапке таблицы — строка полей под заголовками,
 * как в панели Remnawave. В отличие от ColumnFilter (иконка + попап)
 * значение всегда на виду, поэтому не нужно открывать меню, чтобы понять,
 * что список уже отфильтрован.
 *
 * Поддерживает режимы серверных таблиц: `text` (ввод с задержкой, чтобы не
 * дёргать API на каждую букву), `single` (выбор из списка) и `select`
 * (несколько значений: та же строка-триггер, под ней попап с чекбоксами).
 * `range` в шапке не рисуем — его место в попапе клиентских таблиц.
 */
export function ColumnFilterCell({ filter, label }: { filter: ColumnFilterProps; label: string }) {
  const { t } = useTranslation()

  if (filter.type === 'text') {
    return <TextFilterCell filter={filter} label={label} />
  }

  if (filter.type === 'single') {
    const current = Array.isArray(filter.value) && filter.value.length > 0 ? filter.value[0] : ''
    return (
      <Select
        // Пусто, а не ANY: тогда Select показывает подсказку «Фильтр по …»
        // и по шапке сразу видно, какой столбец ещё не сужен.
        value={current || undefined}
        onValueChange={(v) => filter.onChange(v === ANY ? null : [v])}
      >
        <SelectTrigger
          className="h-7 text-xs border-0 border-b border-[var(--glass-border)] rounded-none bg-transparent px-1 focus:ring-0"
          aria-label={t('common.columns.filterBy', { column: label })}
        >
          <SelectValue placeholder={t('common.columns.filterBy', { column: label })} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>{t('common.columns.filterAny')}</SelectItem>
          {(filter.options || []).map((o) => (
            <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }

  if (filter.type === 'select') {
    return <MultiFilterCell filter={filter} label={label} />
  }

  return null
}

/** Несколько значений: выбранные подписи в строке-триггере, попап с чекбоксами. */
function MultiFilterCell({ filter, label }: { filter: ColumnFilterProps; label: string }) {
  const { t } = useTranslation()
  const value = Array.isArray(filter.value) ? filter.value : []
  const options = filter.options || []
  const chosen = value.map((v) => options.find((o) => o.value === v)?.label || v)

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={t('common.columns.filterBy', { column: label })}
          title={chosen.join(', ') || undefined}
          className={cn(
            'flex h-7 w-full items-center justify-between gap-1 rounded-none border-b border-[var(--glass-border)] bg-transparent px-1 text-xs focus:outline-none',
            chosen.length ? 'text-dark-100' : 'text-dark-400',
          )}
        >
          <span className="truncate">
            {chosen.length ? chosen.join(', ') : t('common.columns.filterBy', { column: label })}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56 p-2">
        <SelectFilter options={options} value={value} onChange={filter.onChange} />
      </PopoverContent>
    </Popover>
  )
}

function TextFilterCell({ filter, label }: { filter: ColumnFilterProps; label: string }) {
  const { t } = useTranslation()
  const external = Array.isArray(filter.value) && filter.value.length > 0 ? filter.value[0] : ''
  const [draft, setDraft] = useState(external)

  // Значение могли поменять снаружи — из панели фильтров, по ссылке с
  // параметрами или сбросом из меню столбца.
  useEffect(() => setDraft(external), [external])

  useEffect(() => {
    if (draft === external) return
    const timer = setTimeout(() => filter.onChange(draft ? [draft] : null), 350)
    return () => clearTimeout(timer)
    // filter.onChange пересоздаётся на каждый рендер страницы — в зависимости
    // его не берём, иначе таймер сбрасывался бы и запрос не уходил никогда.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, external])

  return (
    <div className="relative">
      <Input
        value={draft}
        placeholder={filter.placeholder || t('common.columns.filterBy', { column: label })}
        aria-label={t('common.columns.filterBy', { column: label })}
        onChange={(e) => setDraft(e.target.value)}
        className="h-7 text-xs border-0 border-b border-[var(--glass-border)] rounded-none bg-transparent px-1 pr-5 focus-visible:ring-0"
      />
      {draft && (
        <button
          type="button"
          onClick={() => setDraft('')}
          aria-label={t('common.reset')}
          className="absolute right-0 top-1/2 -translate-y-1/2 p-0.5 text-dark-400 hover:text-white"
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </div>
  )
}
