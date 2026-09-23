import { useTranslation } from 'react-i18next'
import { Gauge } from '@/components/brand/icons'
import { cn } from '@/lib/utils'

export type ShaperState = 'active' | 'rough' | 'error' | 'waiting'

const TONE: Record<ShaperState, string> = {
  active: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  rough: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  error: 'border-red-500/30 bg-red-500/10 text-red-300',
  waiting: 'border-primary-500/30 bg-primary-500/10 text-primary-300',
}

/** Бейдж «Шейпер» на карточке ноды. Шейпер выключен — бейджа нет. */
export function ShaperBadge({ state, className }: { state?: string | null; className?: string }) {
  const { t } = useTranslation()
  if (!state || !(state in TONE)) return null
  const tone = state as ShaperState
  return (
    <span
      title={t(`nodes.shaper.badge.${tone}`)}
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap',
        TONE[tone],
        className,
      )}
    >
      <Gauge className="w-3 h-3" />
      {t('nodes.shaper.badge.label')}
    </span>
  )
}
