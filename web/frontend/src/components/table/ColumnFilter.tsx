import { useTranslation } from 'react-i18next'
import { Filter } from '@/components/brand/icons'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { FilterValue, RangeValue } from '@/lib/useTableControls'

export interface ColumnFilterProps {
  /**
   * `select` — несколько значений, `range` — числовой диапазон (оба про
   * списки, загруженные целиком). `single` и `text` добавлены для таблиц,
   * которые фильтруются на сервере: там у параметра одно значение.
   */
  type: 'select' | 'range' | 'single' | 'text'
  /** Options for `select` and `single` types. */
  options?: { value: string; label: string }[]
  value?: FilterValue
  onChange: (v: FilterValue | null) => void
  /** Show range inputs in friendly units, e.g. { label: 'ГБ', factor: 1e9 } for bytes. */
  rangeUnit?: { label: string; factor: number }
  /** Подсказка для `text`. */
  placeholder?: string
}

function isActive(value?: FilterValue) {
  if (value == null) return false
  return Array.isArray(value) ? value.length > 0 : value.min != null || value.max != null
}

export function ColumnFilter({ type, options = [], value, onChange, rangeUnit, placeholder }: ColumnFilterProps) {
  const { t } = useTranslation()
  const active = isActive(value)

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          aria-label={t('common.filter', 'Фильтр')}
          className={cn(
            'relative p-1 rounded transition-colors',
            active ? 'text-primary-400' : 'text-dark-400 hover:text-white',
          )}
        >
          <Filter className="w-3.5 h-3.5" />
          {active && <span className="absolute top-0 right-0 w-1.5 h-1.5 rounded-full bg-primary-400" />}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56 p-2" onClick={(e) => e.stopPropagation()}>
        {type === 'select' || type === 'single' ? (
          <SelectFilter
            options={options}
            value={Array.isArray(value) ? value : []}
            onChange={onChange}
            single={type === 'single'}
          />
        ) : type === 'text' ? (
          <TextFilter
            value={Array.isArray(value) ? value[0] || '' : ''}
            onChange={onChange}
            placeholder={placeholder}
          />
        ) : (
          <RangeFilter
            value={!Array.isArray(value) ? (value as RangeValue | undefined) : undefined}
            onChange={onChange}
            unit={rangeUnit}
          />
        )}
      </PopoverContent>
    </Popover>
  )
}

function SelectFilter({
  options,
  value,
  onChange,
  single = false,
}: {
  options: { value: string; label: string }[]
  value: string[]
  onChange: (v: FilterValue | null) => void
  /** Одно значение: выбор заменяет предыдущее, повторный клик снимает фильтр. */
  single?: boolean
}) {
  const { t } = useTranslation()
  const toggle = (v: string) => {
    if (single) {
      onChange(value.includes(v) ? null : [v])
      return
    }
    const set = new Set(value)
    if (set.has(v)) set.delete(v)
    else set.add(v)
    onChange(Array.from(set))
  }
  return (
    <div className="space-y-0.5 max-h-64 overflow-auto">
      {options.length === 0 && (
        <div className="px-2 py-1.5 text-xs text-dark-400">{t('common.noOptions', 'Нет значений')}</div>
      )}
      {options.map((o) => (
        <label
          key={o.value}
          className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[var(--glass-bg)] cursor-pointer text-sm"
        >
          <Checkbox checked={value.includes(o.value)} onCheckedChange={() => toggle(o.value)} />
          <span className="truncate text-dark-100">{o.label}</span>
        </label>
      ))}
      {value.length > 0 && (
        <button
          type="button"
          onClick={() => onChange(null)}
          className="w-full text-left px-2 py-1.5 text-xs text-dark-300 hover:text-white border-t border-[var(--glass-border)] mt-1 pt-2"
        >
          {t('common.reset', 'Сбросить')}
        </button>
      )}
    </div>
  )
}

function RangeFilter({
  value,
  onChange,
  unit,
}: {
  value?: RangeValue
  onChange: (v: FilterValue | null) => void
  unit?: { label: string; factor: number }
}) {
  const { t } = useTranslation()
  const factor = unit?.factor ?? 1
  const min = value?.min ?? null
  const max = value?.max ?? null
  const toDisplay = (n: number | null) => (n == null ? '' : String(+(n / factor).toFixed(4)))
  const parse = (s: string) => (s.trim() === '' ? null : Number(s) * factor)

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        <Input
          type="number"
          value={toDisplay(min)}
          aria-label={t('common.min', 'Мин')}
          placeholder={t('common.min', 'Мин')}
          onChange={(e) => onChange({ min: parse(e.target.value), max })}
          className="h-8 text-sm"
        />
        <span className="text-dark-400">—</span>
        <Input
          type="number"
          value={toDisplay(max)}
          aria-label={t('common.max', 'Макс')}
          placeholder={t('common.max', 'Макс')}
          onChange={(e) => onChange({ min, max: parse(e.target.value) })}
          className="h-8 text-sm"
        />
      </div>
      {unit && <div className="text-[10px] text-dark-400 px-0.5">{unit.label}</div>}
      {(min != null || max != null) && (
        <button
          type="button"
          onClick={() => onChange(null)}
          className="w-full text-left text-xs text-dark-300 hover:text-white"
        >
          {t('common.reset', 'Сбросить')}
        </button>
      )}
    </div>
  )
}

function TextFilter({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (v: FilterValue | null) => void
  placeholder?: string
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-2">
      <Input
        autoFocus
        value={value}
        placeholder={placeholder || t('common.search', 'Поиск')}
        aria-label={placeholder || t('common.search', 'Поиск')}
        onChange={(e) => onChange(e.target.value ? [e.target.value] : null)}
        className="h-8 text-sm"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange(null)}
          className="w-full text-left text-xs text-dark-300 hover:text-white"
        >
          {t('common.reset', 'Сбросить')}
        </button>
      )}
    </div>
  )
}
