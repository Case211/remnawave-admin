import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type UIDensity = 'compact' | 'comfortable' | 'spacious'
export type BorderRadius = 'sharp' | 'default' | 'rounded' | 'pill'
export type FontSize = 'small' | 'default' | 'large'

interface AppearanceState {
  // Settings
  density: UIDensity
  borderRadius: BorderRadius
  fontSize: FontSize
  animationsEnabled: boolean
  sidebarCollapsed: boolean

  // Actions
  setDensity: (density: UIDensity) => void
  setBorderRadius: (radius: BorderRadius) => void
  setFontSize: (size: FontSize) => void
  setAnimationsEnabled: (enabled: boolean) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
  resetToDefaults: () => void
}

const defaults = {
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
        density: state.density,
        borderRadius: state.borderRadius,
        fontSize: state.fontSize,
        animationsEnabled: state.animationsEnabled,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    }
  )
)
