import { describe, it, expect, beforeEach } from 'vitest'
import { useFiltersStore } from '@/store/useFiltersStore'

describe('useFiltersStore', () => {
  beforeEach(() => {
    useFiltersStore.setState({ savedFilters: [] })
  })

  describe('saveFilter', () => {
    it('saves a filter with auto-generated id and timestamp', () => {
      useFiltersStore.getState().saveFilter({
        name: 'Active users',
        page: 'users',
        filters: { status: 'active' },
      })

      const filters = useFiltersStore.getState().savedFilters
      expect(filters).toHaveLength(1)
      expect(filters[0].name).toBe('Active users')
      expect(filters[0].page).toBe('users')
      expect(filters[0].filters).toEqual({ status: 'active' })
      expect(filters[0].id).toBeTruthy()
      expect(filters[0].createdAt).toBeGreaterThan(0)
    })

    it('saves multiple filters', () => {
      const store = useFiltersStore.getState()
      store.saveFilter({ name: 'Filter 1', page: 'users', filters: {} })
      store.saveFilter({ name: 'Filter 2', page: 'violations', filters: {} })

      expect(useFiltersStore.getState().savedFilters).toHaveLength(2)
    })
  })

  describe('deleteFilter', () => {
    it('deletes a filter by id', () => {
      useFiltersStore.getState().saveFilter({
        name: 'To delete',
        page: 'users',
        filters: {},
      })

      const id = useFiltersStore.getState().savedFilters[0].id
      useFiltersStore.getState().deleteFilter(id)

      expect(useFiltersStore.getState().savedFilters).toHaveLength(0)
    })

    it('does nothing for non-existent id', () => {
      useFiltersStore.getState().saveFilter({
        name: 'Keep me',
        page: 'users',
        filters: {},
      })

      useFiltersStore.getState().deleteFilter('non-existent')

      expect(useFiltersStore.getState().savedFilters).toHaveLength(1)
    })
  })

  describe('getFiltersForPage', () => {
    it('returns filters for a specific page', () => {
      const store = useFiltersStore.getState()
      store.saveFilter({ name: 'Users filter', page: 'users', filters: { status: 'active' } })
      store.saveFilter({ name: 'Violations filter', page: 'violations', filters: { type: 'sharing' } })
      store.saveFilter({ name: 'Another users filter', page: 'users', filters: { status: 'disabled' } })

      const usersFilters = useFiltersStore.getState().getFiltersForPage('users')
      expect(usersFilters).toHaveLength(2)
      expect(usersFilters.every((f) => f.page === 'users')).toBe(true)

      const violationsFilters = useFiltersStore.getState().getFiltersForPage('violations')
      expect(violationsFilters).toHaveLength(1)
      expect(violationsFilters[0].name).toBe('Violations filter')
    })

    it('returns empty array if no filters for page', () => {
      expect(useFiltersStore.getState().getFiltersForPage('users')).toEqual([])
    })
  })
})
