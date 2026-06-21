import { useState, useEffect } from 'react'
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type UIDensity = 'compact' | 'comfortable' | 'spacious'
export type BorderRadius = 'sharp' | 'default' | 'rounded'
export type FontSize = 'small' | 'default' | 'large'
export type ThemePreset = 'halo' | 'obsidian' | 'arctic' | 'sakura' | 'twilight' | 'ember'
export type ColorMode = 'dark' | 'light' | 'auto'

interface AppearanceState {
  // Settings
  theme: ThemePreset
  colorMode: ColorMode
  density: UIDensity
  borderRadius: BorderRadius
  fontSize: FontSize
  animationsEnabled: boolean
  sidebarCollapsed: boolean

  // Actions
  setTheme: (theme: ThemePreset) => void
  setColorMode: (mode: ColorMode) => void
  setDensity: (density: UIDensity) => void
  setBorderRadius: (radius: BorderRadius) => void
  setFontSize: (size: FontSize) => void
  setAnimationsEnabled: (enabled: boolean) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
  toggleColorMode: () => void
  resetToDefaults: () => void
}

const defaults = {
  theme: 'halo' as ThemePreset,
  colorMode: 'dark' as ColorMode,
  density: 'comfortable' as UIDensity,
  borderRadius: 'default' as BorderRadius,
  fontSize: 'default' as FontSize,
  animationsEnabled: true,
  sidebarCollapsed: false,
}

export const useAppearanceStore = create<AppearanceState>()(
  persist(
    (set) => ({
      ...defaults,

      setTheme: (theme) => set({ theme }),
      setColorMode: (colorMode) => set({ colorMode }),
      setDensity: (density) => set({ density }),
      setBorderRadius: (borderRadius) => set({ borderRadius }),
      setFontSize: (fontSize) => set({ fontSize }),
      setAnimationsEnabled: (animationsEnabled) => set({ animationsEnabled }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      toggleColorMode: () => set((s) => ({
        colorMode: s.colorMode === 'dark' ? 'light' : s.colorMode === 'light' ? 'auto' : 'dark',
      })),
      resetToDefaults: () => set(defaults),
    }),
    {
      name: 'remnawave-appearance',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        theme: state.theme,
        colorMode: state.colorMode,
        density: state.density,
        borderRadius: state.borderRadius,
        fontSize: state.fontSize,
        animationsEnabled: state.animationsEnabled,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    }
  )
)

function getSystemPreference(): 'dark' | 'light' {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useResolvedColorMode(): 'dark' | 'light' {
  const colorMode = useAppearanceStore((s) => s.colorMode)
  const [resolved, setResolved] = useState<'dark' | 'light'>(
    colorMode === 'auto' ? getSystemPreference() : colorMode
  )

  useEffect(() => {
    if (colorMode !== 'auto') {
      setResolved(colorMode)
      return
    }
    setResolved(getSystemPreference())
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setResolved(e.matches ? 'dark' : 'light')
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [colorMode])

  return resolved
}
