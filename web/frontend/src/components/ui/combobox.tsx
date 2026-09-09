import { useState } from 'react'
import { Check, ChevronDown } from '@/components/brand/icons'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { cn } from '@/lib/utils'

export interface ComboboxOption {
  value: string
  label: string
  /** Второстепенный текст справа (адрес, тег); тоже участвует в поиске. */
  hint?: string
}

interface ComboboxProps {
  value: string
  onChange: (value: string) => void
  options: ComboboxOption[]
  placeholder: string
  searchPlaceholder: string
  emptyText: string
  disabled?: boolean
  className?: string
}

/**
 * Выпадающий список с поиском (Popover + cmdk) для длинных списков, где
 * обычный Select не годится. Поиск — по подстроке в подписи, подсказке и
 * значении, без fuzzy: так «de1» не подтянет «Node-1».
 */
export function Combobox({
  value,
  onChange,
  options,
  placeholder,
  searchPlaceholder,
  emptyText,
  disabled,
  className,
}: ComboboxProps) {
  const [open, setOpen] = useState(false)
  const current = options.find((o) => o.value === value)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          role="combobox"
          aria-expanded={open}
          aria-label={placeholder}
          disabled={disabled}
          className={cn(
            // Тот же вид, что у SelectTrigger, чтобы в форме не выбивался
            'flex h-10 w-full items-center justify-between rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 disabled:cursor-not-allowed disabled:opacity-50',
            current ? 'text-dark-50' : 'text-dark-200',
            className,
          )}
        >
          <span className="truncate">{current ? current.label : placeholder}</span>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[var(--radix-popover-trigger-width)] p-0">
        <Command filter={(v, s) => (v.toLowerCase().includes(s.toLowerCase()) ? 1 : 0)}>
          <CommandInput placeholder={searchPlaceholder} />
          <CommandList>
            <CommandEmpty>{emptyText}</CommandEmpty>
            {options.map((o) => (
              <CommandItem
                key={o.value}
                value={`${o.label} ${o.hint ?? ''} ${o.value}`}
                onSelect={() => {
                  onChange(o.value)
                  setOpen(false)
                }}
              >
                <Check className={cn('mr-2 h-4 w-4 shrink-0', o.value === value ? 'opacity-100' : 'opacity-0')} />
                <span className="truncate">{o.label}</span>
                {o.hint && <span className="ml-auto pl-2 text-xs text-dark-400 truncate">{o.hint}</span>}
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
