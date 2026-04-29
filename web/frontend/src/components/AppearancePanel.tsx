import { Paintbrush, RotateCcw, Sun, Moon, Monitor } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  useAppearanceStore,
  type UIDensity,
  type BorderRadius,
  type FontSize,
  type ThemePreset,
} from '../store/useAppearanceStore'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
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
          : "bg-[var(--glass-bg)] text-dark-200 border border-[var(--glass-border)] hover:border-[var(--glass-border)]/40 hover:text-dark-50"
      )}
    >
      {label}
    </button>
  )
}

// Theme presets with their display colors and labels
const themePresets: { value: ThemePreset; label: string; colors: [string, string] }[] = [
  { value: 'obsidian', label: 'Obsidian', colors: ['#6366f1', '#818cf8'] },
  { value: 'arctic', label: 'Arctic', colors: ['#0ea5e9', '#38bdf8'] },
  { value: 'sakura', label: 'Sakura', colors: ['#ec4899', '#f472b6'] },
  { value: 'twilight', label: 'Twilight', colors: ['#8b5cf6', '#a78bfa'] },
  { value: 'ember', label: 'Ember', colors: ['#f59e0b', '#fbbf24'] },
]

const densityOptions: { value: UIDensity; label: string }[] = [
  { value: 'compact', label: 'Compact' },
  { value: 'comfortable', label: 'Comfort' },
  { value: 'spacious', label: 'Spacious' },
]

const radiusOptions: { value: BorderRadius; label: string; preview: string }[] = [
  { value: 'sharp', label: 'Sharp', preview: 'rounded-none' },
  { value: 'default', label: 'Default', preview: 'rounded' },
  { value: 'rounded', label: 'Rounded', preview: 'rounded-xl' },
]

const fontSizeOptions: { value: FontSize; label: string }[] = [
  { value: 'small', label: 'S' },
  { value: 'default', label: 'M' },
  { value: 'large', label: 'L' },
]

export function AppearancePanel() {
  const { t } = useTranslation()
  const {
    theme,
    colorMode,
    density,
    borderRadius,
    fontSize,
    animationsEnabled,
    setTheme,
    setColorMode,
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
            <Button variant="ghost" size="icon" className="relative" aria-label={t('appearance.title', 'Appearance')}>
              <Paintbrush className="w-5 h-5" />
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent>{t('appearance.title')}</TooltipContent>
      </Tooltip>

      <PopoverContent align="end" className="w-80 p-0">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--glass-border)]">
          <h4 className="text-sm font-semibold text-white">{t('appearance.title')}</h4>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-dark-300 hover:text-white"
                onClick={resetToDefaults}
                aria-label={t('common.reset')}
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('appearance.resetToDefaults')}</TooltipContent>
          </Tooltip>
        </div>

        <ScrollArea className="max-h-[70vh]">
          <div className="p-4 space-y-4">
            {/* Theme */}
            <div className="space-y-2">
              <Label className="text-xs text-dark-200 uppercase tracking-wider">{t('appearance.theme')}</Label>
              <div className="grid grid-cols-5 gap-1.5">
                {themePresets.map((preset) => {
                  const isActive = preset.value === theme
                  return (
                    <Tooltip key={preset.value} delayDuration={0}>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => setTheme(preset.value)}
                          className={cn(
                            "flex flex-col items-center gap-1.5 py-2 px-1 text-[10px] font-medium rounded-md transition-all duration-150",
                            isActive
                              ? "ring-2 ring-primary/50 bg-primary/10"
                              : "hover:bg-[var(--glass-bg)]"
                          )}
                        >
                          {/* Color swatch */}
                          <div
                            className="w-7 h-7 rounded-full border-2 border-[var(--glass-border)]"
                            style={{
                              background: `linear-gradient(135deg, ${preset.colors[0]} 0%, ${preset.colors[1]} 100%)`,
                            }}
                          />
                          <span className={cn(
                            "truncate w-full text-center",
                            isActive ? "text-primary-400" : "text-dark-200"
                          )}>
                            {preset.label}
                          </span>
                        </button>
                      </TooltipTrigger>
                      <TooltipContent>{preset.label}</TooltipContent>
                    </Tooltip>
                  )
                })}
              </div>
            </div>

            <Separator className="bg-[var(--glass-border)]" />

            {/* Color Mode */}
            <div className="space-y-2">
              <Label className="text-xs text-dark-200 uppercase tracking-wider">{t('appearance.colorMode')}</Label>
              <div className="flex gap-1.5">
                {([
                  { value: 'dark' as const, icon: Moon, label: 'Dark' },
                  { value: 'light' as const, icon: Sun, label: 'Light' },
                  { value: 'auto' as const, icon: Monitor, label: 'Auto' },
                ]).map(({ value, icon: Icon, label }) => {
                  const isActive = colorMode === value
                  return (
                    <button
                      key={value}
                      onClick={() => setColorMode(value)}
                      className={cn(
                        "flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 text-xs font-medium rounded-md transition-all duration-150",
                        isActive
                          ? "bg-primary/20 text-primary-400 border border-primary/30"
                          : "bg-[var(--glass-bg)] text-dark-200 border border-[var(--glass-border)] hover:border-[var(--glass-border)]/40 hover:text-dark-50"
                      )}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {label}
                    </button>
                  )
                })}
              </div>
            </div>

            <Separator className="bg-[var(--glass-border)]" />

            {/* UI Density */}
            <div className="space-y-2">
              <Label className="text-xs text-dark-200 uppercase tracking-wider">{t('appearance.density')}</Label>
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

            <Separator className="bg-[var(--glass-border)]" />

            {/* Border Radius */}
            <div className="space-y-2">
              <Label className="text-xs text-dark-200 uppercase tracking-wider">{t('appearance.borderRadius')}</Label>
              <div className="flex gap-1.5">
                {radiusOptions.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setBorderRadius(opt.value)}
                    className={cn(
                      "flex-1 flex flex-col items-center gap-1.5 py-2 text-xs font-medium rounded-md transition-all duration-150",
                      opt.value === borderRadius
                        ? "bg-primary/20 text-primary-400 border border-primary/30"
                        : "bg-[var(--glass-bg)] text-dark-200 border border-[var(--glass-border)] hover:border-[var(--glass-border)]/40 hover:text-dark-50"
                    )}
                  >
                    <div className={cn("w-6 h-4 border-2 border-current", opt.preview)} />
                    <span>{opt.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <Separator className="bg-[var(--glass-border)]" />

            {/* Font Size */}
            <div className="space-y-2">
              <Label className="text-xs text-dark-200 uppercase tracking-wider">{t('appearance.fontSize')}</Label>
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

            <Separator className="bg-[var(--glass-border)]" />

            {/* Animations */}
            <div className="flex items-center justify-between">
              <Label htmlFor="animations-toggle" className="text-sm text-dark-100 cursor-pointer">
                {t('appearance.animations')}
              </Label>
              <Switch
                id="animations-toggle"
                checked={animationsEnabled}
                onCheckedChange={setAnimationsEnabled}
              />
            </div>
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
