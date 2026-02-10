import { useMemo } from 'react'
import { useAppearanceStore } from '../store/useAppearanceStore'

/**
 * Returns chart colors that adapt to the current theme (light/dark).
 * Uses CSS custom properties defined in index.css so colors stay in sync.
 */
export function useChartTheme() {
  const theme = useAppearanceStore((s) => s.theme)
  const isLight = theme === 'light'

  return useMemo(
    () => ({
      axis: isLight ? '#475569' : '#8b949e',
      tick: isLight ? '#334155' : '#c9d1d9',
      grid: isLight ? 'rgba(148, 163, 184, 0.3)' : 'rgba(72, 79, 88, 0.3)',
      tooltipStyle: {
        backgroundColor: isLight ? 'rgba(255, 255, 255, 0.95)' : 'rgba(22, 27, 34, 0.95)',
        border: `1px solid ${isLight ? 'rgba(203, 213, 225, 0.6)' : 'rgba(72, 79, 88, 0.3)'}`,
        borderRadius: '8px',
        backdropFilter: 'blur(12px)',
        color: isLight ? '#1e293b' : '#c9d1d9',
      } as React.CSSProperties,
      tooltipTextClass: isLight ? 'text-slate-800' : 'text-dark-50',
      tooltipMutedClass: isLight ? 'text-slate-500' : 'text-muted-foreground',
      mapBackground: isLight ? '#e2e8f0' : '#0d1117',
      mapTileUrl: isLight
        ? 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'
        : 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    }),
    [isLight],
  )
}
