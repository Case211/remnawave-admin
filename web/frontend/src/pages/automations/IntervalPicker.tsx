import { useState } from 'react'
import { Timer } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { INTERVAL_PRESETS } from './helpers'

interface IntervalPickerProps {
  value: string
  onChange: (minutes: string) => void
}

export function IntervalPicker({ value, onChange }: IntervalPickerProps) {
  const [showCustom, setShowCustom] = useState(
    () => !!value && !INTERVAL_PRESETS.some((p) => p.value.toString() === value)
  )

  const numValue = parseInt(value) || 0

  const humanInterval = (mins: number): string => {
    if (!mins) return ''
    if (mins < 60) return `Каждые ${mins} мин.`
    if (mins === 60) return 'Каждый час'
    if (mins % 60 === 0) {
      const h = mins / 60
      if (h === 24) return 'Каждые 24 часа (раз в сутки)'
      return `Каждые ${h} ч.`
    }
    const h = Math.floor(mins / 60)
    const m = mins % 60
    return `Каждые ${h} ч. ${m} мин.`
  }

  return (
    <div className="space-y-3">
      <Label className="text-xs text-dark-400">Запускать с интервалом</Label>

      {/* Preset buttons */}
      <div className="flex flex-wrap gap-1.5">
        {INTERVAL_PRESETS.map((preset) => (
          <button
            key={preset.value}
            onClick={() => {
              onChange(preset.value.toString())
              setShowCustom(false)
            }}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              value === preset.value.toString() && !showCustom
                ? 'bg-accent-teal/20 text-accent-teal border border-accent-teal/30'
                : 'bg-dark-800 text-dark-300 border border-dark-700 hover:border-dark-600'
            }`}
          >
            {preset.label}
          </button>
        ))}
        <button
          onClick={() => setShowCustom(true)}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            showCustom
              ? 'bg-accent-teal/20 text-accent-teal border border-accent-teal/30'
              : 'bg-dark-800 text-dark-300 border border-dark-700 hover:border-dark-600'
          }`}
        >
          Другой
        </button>
      </div>

      {/* Custom input */}
      {showCustom && (
        <div>
          <Label className="text-xs text-dark-400">Интервал в минутах</Label>
          <Input
            type="number"
            min={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="mt-1 bg-dark-800 border-dark-700 w-32"
            placeholder="45"
          />
        </div>
      )}

      {/* Preview */}
      {numValue > 0 && (
        <div className="flex items-center gap-2 p-2.5 rounded-lg bg-dark-900/50 border border-dark-700/50">
          <Timer className="w-3.5 h-3.5 text-accent-teal flex-shrink-0" />
          <span className="text-xs text-dark-200">{humanInterval(numValue)}</span>
        </div>
      )}
    </div>
  )
}
