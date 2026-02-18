import { describe, it, expect, beforeEach } from 'vitest'
import { useAppearanceStore } from '@/store/useAppearanceStore'

describe('useAppearanceStore', () => {
  beforeEach(() => {
    // Reset to defaults
    useAppearanceStore.getState().resetToDefaults()
  })

  describe('default values', () => {
    it('has correct default theme', () => {
      expect(useAppearanceStore.getState().theme).toBe('cyan')
    })

    it('has correct default density', () => {
      expect(useAppearanceStore.getState().density).toBe('comfortable')
    })

    it('has correct default border radius', () => {
      expect(useAppearanceStore.getState().borderRadius).toBe('default')
    })

    it('has correct default font size', () => {
      expect(useAppearanceStore.getState().fontSize).toBe('default')
    })

    it('has animations enabled by default', () => {
      expect(useAppearanceStore.getState().animationsEnabled).toBe(true)
    })

    it('has sidebar expanded by default', () => {
      expect(useAppearanceStore.getState().sidebarCollapsed).toBe(false)
    })
  })

  describe('setTheme', () => {
    it('updates theme', () => {
      useAppearanceStore.getState().setTheme('violet')
      expect(useAppearanceStore.getState().theme).toBe('violet')
    })

    it('can set all theme presets', () => {
      const presets = ['cyan', 'emerald', 'violet', 'rose', 'amber', 'blue', 'light'] as const
      presets.forEach((preset) => {
        useAppearanceStore.getState().setTheme(preset)
        expect(useAppearanceStore.getState().theme).toBe(preset)
      })
    })
  })

  describe('setDensity', () => {
    it('updates density', () => {
      useAppearanceStore.getState().setDensity('compact')
      expect(useAppearanceStore.getState().density).toBe('compact')
    })
  })

  describe('setBorderRadius', () => {
    it('updates border radius', () => {
      useAppearanceStore.getState().setBorderRadius('pill')
      expect(useAppearanceStore.getState().borderRadius).toBe('pill')
    })
  })

  describe('setFontSize', () => {
    it('updates font size', () => {
      useAppearanceStore.getState().setFontSize('large')
      expect(useAppearanceStore.getState().fontSize).toBe('large')
    })
  })

  describe('setAnimationsEnabled', () => {
    it('disables animations', () => {
      useAppearanceStore.getState().setAnimationsEnabled(false)
      expect(useAppearanceStore.getState().animationsEnabled).toBe(false)
    })

    it('enables animations', () => {
      useAppearanceStore.getState().setAnimationsEnabled(false)
      useAppearanceStore.getState().setAnimationsEnabled(true)
      expect(useAppearanceStore.getState().animationsEnabled).toBe(true)
    })
  })

  describe('sidebar', () => {
    it('setSidebarCollapsed updates state', () => {
      useAppearanceStore.getState().setSidebarCollapsed(true)
      expect(useAppearanceStore.getState().sidebarCollapsed).toBe(true)
    })

    it('toggleSidebar toggles collapsed state', () => {
      expect(useAppearanceStore.getState().sidebarCollapsed).toBe(false)

      useAppearanceStore.getState().toggleSidebar()
      expect(useAppearanceStore.getState().sidebarCollapsed).toBe(true)

      useAppearanceStore.getState().toggleSidebar()
      expect(useAppearanceStore.getState().sidebarCollapsed).toBe(false)
    })
  })

  describe('resetToDefaults', () => {
    it('resets all settings to defaults', () => {
      useAppearanceStore.getState().setTheme('rose')
      useAppearanceStore.getState().setDensity('spacious')
      useAppearanceStore.getState().setBorderRadius('pill')
      useAppearanceStore.getState().setFontSize('large')
      useAppearanceStore.getState().setAnimationsEnabled(false)
      useAppearanceStore.getState().setSidebarCollapsed(true)

      useAppearanceStore.getState().resetToDefaults()

      const state = useAppearanceStore.getState()
      expect(state.theme).toBe('cyan')
      expect(state.density).toBe('comfortable')
      expect(state.borderRadius).toBe('default')
      expect(state.fontSize).toBe('default')
      expect(state.animationsEnabled).toBe(true)
      expect(state.sidebarCollapsed).toBe(false)
    })
  })
})
