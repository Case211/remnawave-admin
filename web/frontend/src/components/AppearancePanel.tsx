import { Paintbrush, RotateCcw } from 'lucide-react'
import {
  useAppearanceStore,
  type UIDensity,
  type BorderRadius,
  type FontSize,
} from '../store/useAppearanceStore'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface OptionButtonProps<T extends string> {
  value: T
  current: T
  onChange: (v: T) => void
  label: string
}

function OptionButton<T extends string>({ value, current, onChange, label }: OptionButtonProps<T>) {
  const isActive = value === current
  return (
    <button
      onClick={() => onChange(value)}
      className={cn(
        "flex-1 px-2 py-1.5 text-xs font-medium rounded-md transition-all duration-150",
        isActive
          ? "bg-primary/20 text-primary-400 border border-primary/30"
          : "bg-dark-800 text-dark-200 border border-dark-400/20 hover:border-dark-400/40 hover:text-dark-50"
      )}
    >
      {label}
    </button>
  )
}

const densityOptions: { value: UIDensity; label: string }[] = [
  { value: 'compact', label: 'Compact' },
  { value: 'comfortable', label: 'Comfort' },
  { value: 'spacious', label: 'Spacious' },
]

const radiusOptions: { value: BorderRadius; label: string; preview: string }[] = [
  { value: 'sharp', label: 'Sharp', preview: 'rounded-none' },
  { value: 'default', label: 'Default', preview: 'rounded' },
  { value: 'rounded', label: 'Rounded', preview: 'rounded-xl' },
  { value: 'pill', label: 'Pill', preview: 'rounded-full' },
]

const fontSizeOptions: { value: FontSize; label: string }[] = [
  { value: 'small', label: 'S' },
  { value: 'default', label: 'M' },
  { value: 'large', label: 'L' },
]

export function AppearancePanel() {
  const {
    density,
    borderRadius,
    fontSize,
    animationsEnabled,
    setDensity,
    setBorderRadius,
    setFontSize,
    setAnimationsEnabled,
    resetToDefaults,
  } = useAppearanceStore()

  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon" className="relative">
              <Paintbrush className="w-5 h-5" />
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent>Appearance</TooltipContent>
      </Tooltip>

      <PopoverContent align="end" className="w-80 p-0">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-dark-400/20">
          <h4 className="text-sm font-semibold text-white">Appearance</h4>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-dark-300 hover:text-white"
                onClick={resetToDefaults}
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Reset to defaults</TooltipContent>
          </Tooltip>
        </div>

        <div className="p-4 space-y-4">
          {/* UI Density */}
          <div className="space-y-2">
            <Label className="text-xs text-dark-200 uppercase tracking-wider">Density</Label>
            <div className="flex gap-1.5">
              {densityOptions.map((opt) => (
                <OptionButton
                  key={opt.value}
                  value={opt.value}
                  current={density}
                  onChange={setDensity}
                  label={opt.label}
                />
              ))}
            </div>
          </div>

          <Separator className="bg-dark-400/20" />

          {/* Border Radius */}
          <div className="space-y-2">
            <Label className="text-xs text-dark-200 uppercase tracking-wider">Border Radius</Label>
            <div className="flex gap-1.5">
              {radiusOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setBorderRadius(opt.value)}
                  className={cn(
                    "flex-1 flex flex-col items-center gap-1.5 py-2 text-xs font-medium rounded-md transition-all duration-150",
                    opt.value === borderRadius
                      ? "bg-primary/20 text-primary-400 border border-primary/30"
                      : "bg-dark-800 text-dark-200 border border-dark-400/20 hover:border-dark-400/40 hover:text-dark-50"
                  )}
                >
                  <div className={cn("w-6 h-4 border-2 border-current", opt.preview)} />
                  <span>{opt.label}</span>
                </button>
              ))}
            </div>
          </div>

          <Separator className="bg-dark-400/20" />

          {/* Font Size */}
          <div className="space-y-2">
            <Label className="text-xs text-dark-200 uppercase tracking-wider">Font Size</Label>
            <div className="flex gap-1.5">
              {fontSizeOptions.map((opt) => (
                <OptionButton
                  key={opt.value}
                  value={opt.value}
                  current={fontSize}
                  onChange={setFontSize}
                  label={opt.label}
                />
              ))}
            </div>
          </div>

          <Separator className="bg-dark-400/20" />

          {/* Animations */}
          <div className="flex items-center justify-between">
            <Label htmlFor="animations-toggle" className="text-sm text-dark-100 cursor-pointer">
              Animations
            </Label>
            <Switch
              id="animations-toggle"
              checked={animationsEnabled}
              onCheckedChange={setAnimationsEnabled}
            />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
