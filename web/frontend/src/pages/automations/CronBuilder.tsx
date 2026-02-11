import { useState, useEffect, useMemo } from 'react'
import { Clock, HelpCircle } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { CRON_PRESETS, cronToHuman } from './helpers'

type ScheduleMode = 'preset' | 'custom' | 'visual'

interface CronBuilderProps {
  value: string
  onChange: (cron: string) => void
}

const HOURS = Array.from({ length: 24 }, (_, i) => i)
const MINUTES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
const DAYS_OF_WEEK = [
  { value: '1', label: 'Понедельник', short: 'Пн' },
  { value: '2', label: 'Вторник', short: 'Вт' },
  { value: '3', label: 'Среда', short: 'Ср' },
  { value: '4', label: 'Четверг', short: 'Чт' },
  { value: '5', label: 'Пятница', short: 'Пт' },
  { value: '6', label: 'Суббота', short: 'Сб' },
  { value: '0', label: 'Воскресенье', short: 'Вс' },
]
const DAYS_OF_MONTH = Array.from({ length: 31 }, (_, i) => i + 1)

type VisualFrequency = 'every_n_minutes' | 'hourly' | 'daily' | 'weekly' | 'monthly'

const FREQUENCY_OPTIONS: { value: VisualFrequency; label: string; description: string }[] = [
  { value: 'every_n_minutes', label: 'Каждые N минут', description: 'Повторяется через равные промежутки' },
  { value: 'hourly', label: 'Каждый час', description: 'В определённую минуту каждого часа' },
  { value: 'daily', label: 'Каждый день', description: 'В определённое время каждый день' },
  { value: 'weekly', label: 'Каждую неделю', description: 'В определённый день и время' },
  { value: 'monthly', label: 'Каждый месяц', description: 'В определённую дату и время' },
]

function pad2(n: number): string {
  return n.toString().padStart(2, '0')
}

export function CronBuilder({ value, onChange }: CronBuilderProps) {
  const [mode, setMode] = useState<ScheduleMode>(() => {
    if (!value) return 'preset'
    if (CRON_PRESETS.some((p) => p.cron === value)) return 'preset'
    return 'visual'
  })

  // Visual builder state
  const [frequency, setFrequency] = useState<VisualFrequency>('daily')
  const [minute, setMinute] = useState(0)
  const [hour, setHour] = useState(0)
  const [dayOfWeek, setDayOfWeek] = useState('1')
  const [dayOfMonth, setDayOfMonth] = useState(1)
  const [everyNMinutes, setEveryNMinutes] = useState(15)

  // Custom cron text
  const [customCron, setCustomCron] = useState(value || '')

  // Parse existing cron value into visual state on mount
  useEffect(() => {
    if (!value) return
    const parts = value.trim().split(/\s+/)
    if (parts.length !== 5) return

    const [min, hr, dom, , dow] = parts

    if (min.startsWith('*/') && hr === '*') {
      setFrequency('every_n_minutes')
      setEveryNMinutes(parseInt(min.slice(2)) || 15)
    } else if (/^\d+$/.test(min) && hr === '*') {
      setFrequency('hourly')
      setMinute(parseInt(min))
    } else if (/^\d+$/.test(min) && /^\d+$/.test(hr) && dom === '*' && dow === '*') {
      setFrequency('daily')
      setMinute(parseInt(min))
      setHour(parseInt(hr))
    } else if (/^\d+$/.test(min) && /^\d+$/.test(hr) && dom === '*' && /^\d+$/.test(dow)) {
      setFrequency('weekly')
      setMinute(parseInt(min))
      setHour(parseInt(hr))
      setDayOfWeek(dow)
    } else if (/^\d+$/.test(min) && /^\d+$/.test(hr) && /^\d+$/.test(dom)) {
      setFrequency('monthly')
      setMinute(parseInt(min))
      setHour(parseInt(hr))
      setDayOfMonth(parseInt(dom))
    }

    setCustomCron(value)
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // Build cron from visual state
  const visualCron = useMemo(() => {
    switch (frequency) {
      case 'every_n_minutes':
        return `*/${everyNMinutes} * * * *`
      case 'hourly':
        return `${minute} * * * *`
      case 'daily':
        return `${minute} ${hour} * * *`
      case 'weekly':
        return `${minute} ${hour} * * ${dayOfWeek}`
      case 'monthly':
        return `${minute} ${hour} ${dayOfMonth} * *`
      default:
        return '0 0 * * *'
    }
  }, [frequency, minute, hour, dayOfWeek, dayOfMonth, everyNMinutes])

  // Preview text for any cron expression
  const preview = cronToHuman(
    mode === 'preset' ? value : mode === 'visual' ? visualCron : customCron
  )

  // Emit change when visual params update (only in visual mode)
  useEffect(() => {
    if (mode === 'visual') {
      onChange(visualCron)
    }
  }, [visualCron, mode])  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-3">
      {/* Mode tabs */}
      <div className="flex gap-1 p-1 rounded-lg bg-dark-800 border-2 border-dark-600">
        {[
          { key: 'preset' as const, label: 'Готовые' },
          { key: 'visual' as const, label: 'Настроить' },
          { key: 'custom' as const, label: 'CRON' },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setMode(tab.key)}
            className={`flex-1 py-1.5 px-3 rounded-md text-xs font-medium transition-all ${
              mode === tab.key
                ? 'bg-accent-teal/20 text-accent-teal border border-accent-teal/30 shadow-sm'
                : 'text-dark-300 hover:text-dark-200 border border-transparent'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Preset mode */}
      {mode === 'preset' && (
        <div className="grid grid-cols-2 gap-1.5 max-h-52 overflow-y-auto pr-1">
          {CRON_PRESETS.map((preset) => (
            <button
              key={preset.id}
              onClick={() => onChange(preset.cron)}
              className={`p-2.5 rounded-lg border-2 text-left transition-all ${
                value === preset.cron
                  ? 'border-accent-teal bg-accent-teal/10'
                  : 'border-dark-600 bg-dark-800 hover:border-dark-500'
              }`}
            >
              <p className="text-xs font-medium text-white">{preset.label}</p>
              <p className="text-[10px] text-dark-400 font-mono mt-0.5">{preset.cron}</p>
            </button>
          ))}
        </div>
      )}

      {/* Visual mode */}
      {mode === 'visual' && (
        <div className="space-y-3">
          <div>
            <Label className="text-xs font-medium text-dark-300">Частота</Label>
            <Select value={frequency} onValueChange={(v) => setFrequency(v as VisualFrequency)}>
              <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FREQUENCY_OPTIONS.map((f) => (
                  <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-dark-500 mt-1">
              {FREQUENCY_OPTIONS.find((f) => f.value === frequency)?.description}
            </p>
          </div>

          {/* Every N minutes */}
          {frequency === 'every_n_minutes' && (
            <div>
              <Label className="text-xs font-medium text-dark-300">Интервал (минуты)</Label>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {[1, 5, 10, 15, 20, 30, 45].map((n) => (
                  <button
                    key={n}
                    onClick={() => setEveryNMinutes(n)}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      everyNMinutes === n
                        ? 'bg-accent-teal/20 text-accent-teal border-2 border-accent-teal/30'
                        : 'bg-dark-900 text-dark-300 border-2 border-dark-500 hover:border-dark-400'
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Hourly: pick minute */}
          {frequency === 'hourly' && (
            <div>
              <Label className="text-xs font-medium text-dark-300">В минуту</Label>
              <Select
                value={minute.toString()}
                onValueChange={(v) => setMinute(parseInt(v))}
              >
                <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white w-28">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MINUTES.map((m) => (
                    <SelectItem key={m} value={m.toString()}>:{pad2(m)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Daily: pick hour + minute */}
          {frequency === 'daily' && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs font-medium text-dark-300">Час</Label>
                <Select
                  value={hour.toString()}
                  onValueChange={(v) => setHour(parseInt(v))}
                >
                  <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {HOURS.map((h) => (
                      <SelectItem key={h} value={h.toString()}>{pad2(h)}:00</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs font-medium text-dark-300">Минута</Label>
                <Select
                  value={minute.toString()}
                  onValueChange={(v) => setMinute(parseInt(v))}
                >
                  <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MINUTES.map((m) => (
                      <SelectItem key={m} value={m.toString()}>:{pad2(m)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {/* Weekly: pick day of week + time */}
          {frequency === 'weekly' && (
            <div className="space-y-3">
              <div>
                <Label className="text-xs font-medium text-dark-300">День недели</Label>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {DAYS_OF_WEEK.map((d) => (
                    <button
                      key={d.value}
                      onClick={() => setDayOfWeek(d.value)}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                        dayOfWeek === d.value
                          ? 'bg-accent-teal/20 text-accent-teal border-2 border-accent-teal/30'
                          : 'bg-dark-900 text-dark-300 border-2 border-dark-500 hover:border-dark-400'
                      }`}
                    >
                      {d.short}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs font-medium text-dark-300">Час</Label>
                  <Select
                    value={hour.toString()}
                    onValueChange={(v) => setHour(parseInt(v))}
                  >
                    <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HOURS.map((h) => (
                        <SelectItem key={h} value={h.toString()}>{pad2(h)}:00</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs font-medium text-dark-300">Минута</Label>
                  <Select
                    value={minute.toString()}
                    onValueChange={(v) => setMinute(parseInt(v))}
                  >
                    <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MINUTES.map((m) => (
                        <SelectItem key={m} value={m.toString()}>:{pad2(m)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          )}

          {/* Monthly: pick day of month + time */}
          {frequency === 'monthly' && (
            <div className="space-y-3">
              <div>
                <Label className="text-xs font-medium text-dark-300">День месяца</Label>
                <Select
                  value={dayOfMonth.toString()}
                  onValueChange={(v) => setDayOfMonth(parseInt(v))}
                >
                  <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white w-28">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DAYS_OF_MONTH.map((d) => (
                      <SelectItem key={d} value={d.toString()}>{d}-е число</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs font-medium text-dark-300">Час</Label>
                  <Select
                    value={hour.toString()}
                    onValueChange={(v) => setHour(parseInt(v))}
                  >
                    <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HOURS.map((h) => (
                        <SelectItem key={h} value={h.toString()}>{pad2(h)}:00</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs font-medium text-dark-300">Минута</Label>
                  <Select
                    value={minute.toString()}
                    onValueChange={(v) => setMinute(parseInt(v))}
                  >
                    <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MINUTES.map((m) => (
                        <SelectItem key={m} value={m.toString()}>:{pad2(m)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Custom CRON mode */}
      {mode === 'custom' && (
        <div className="space-y-2">
          <div>
            <Label className="text-xs font-medium text-dark-300">CRON-выражение (5 полей)</Label>
            <Input
              value={customCron}
              onChange={(e) => {
                setCustomCron(e.target.value)
                onChange(e.target.value)
              }}
              className="mt-1 bg-dark-900 border-dark-500 text-white font-mono"
              placeholder="* * * * *"
            />
          </div>
          <div className="flex items-center gap-4 text-[11px] text-dark-400 font-mono px-1">
            <span>мин</span>
            <span>час</span>
            <span>день</span>
            <span>мес</span>
            <span>день_нед</span>
          </div>
          <div className="p-2 rounded-md bg-dark-800 border border-dark-600">
            <div className="flex items-start gap-1.5">
              <HelpCircle className="w-3 h-3 text-dark-400 flex-shrink-0 mt-0.5" />
              <p className="text-[11px] text-dark-400">
                <code className="text-dark-300">*</code> = любое, <code className="text-dark-300">*/N</code> = каждые N, <code className="text-dark-300">1-5</code> = диапазон, <code className="text-dark-300">1,3,5</code> = список
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Human-readable preview */}
      {(value || (mode === 'visual' && visualCron) || (mode === 'custom' && customCron)) && (
        <div className="flex items-center gap-2 p-2.5 rounded-lg bg-dark-900 border-2 border-dark-600">
          <Clock className="w-3.5 h-3.5 text-accent-teal flex-shrink-0" />
          <span className="text-xs text-dark-200 font-medium">{preview || 'Расписание не задано'}</span>
          {mode !== 'custom' && (
            <Badge variant="outline" className="text-[9px] ml-auto text-dark-400 border-dark-500 font-mono">
              {mode === 'visual' ? visualCron : value}
            </Badge>
          )}
        </div>
      )}
    </div>
  )
}
