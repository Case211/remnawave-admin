import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type UIDensity = 'compact' | 'comfortable' | 'spacious'
export type BorderRadius = 'sharp' | 'default' | 'rounded' | 'pill'
export type FontSize = 'small' | 'default' | 'large'
export type ThemePreset = 'cyan' | 'emerald' | 'violet' | 'rose' | 'amber' | 'blue' | 'light'

interface AppearanceState {
  // Settings
  theme: ThemePreset
  density: UIDensity
  borderRadius: BorderRadius
  fontSize: FontSize
  animationsEnabled: boolean
  sidebarCollapsed: boolean

  // Actions
  setTheme: (theme: ThemePreset) => void
  setDensity: (density: UIDensity) => void
  setBorderRadius: (radius: BorderRadius) => void
  setFontSize: (size: FontSize) => void
  setAnimationsEnabled: (enabled: boolean) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
  resetToDefaults: () => void
}

const defaults = {
  theme: 'cyan' as ThemePreset,
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
      setDensity: (density) => set({ density }),
      setBorderRadius: (borderRadius) => set({ borderRadius }),
      setFontSize: (fontSize) => set({ fontSize }),
      setAnimationsEnabled: (animationsEnabled) => set({ animationsEnabled }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      resetToDefaults: () => set(defaults),
    }),
    {
      name: 'remnawave-appearance',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        theme: state.theme,
        density: state.density,
        borderRadius: state.borderRadius,
        fontSize: state.fontSize,
        animationsEnabled: state.animationsEnabled,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    }
  )
)
