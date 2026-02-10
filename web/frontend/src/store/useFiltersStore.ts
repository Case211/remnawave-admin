import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface SavedFilter {
  id: string
  name: string
  page: 'users' | 'violations'
  filters: Record<string, unknown>
  createdAt: number
}

interface FiltersState {
  savedFilters: SavedFilter[]
  saveFilter: (filter: Omit<SavedFilter, 'id' | 'createdAt'>) => void
  deleteFilter: (id: string) => void
  getFiltersForPage: (page: 'users' | 'violations') => SavedFilter[]
}

export const useFiltersStore = create<FiltersState>()(
  persist(
    (set, get) => ({
      savedFilters: [],

      saveFilter: (filter) => {
        const newFilter: SavedFilter = {
          ...filter,
          id: crypto.randomUUID(),
          createdAt: Date.now(),
        }
        set((state) => ({
          savedFilters: [...state.savedFilters, newFilter],
        }))
      },

      deleteFilter: (id) => {
        set((state) => ({
          savedFilters: state.savedFilters.filter((f) => f.id !== id),
        }))
      },

      getFiltersForPage: (page) => {
        return get().savedFilters.filter((f) => f.page === page)
      },
    }),
    {
      name: 'remnawave-saved-filters',
    },
  ),
)
