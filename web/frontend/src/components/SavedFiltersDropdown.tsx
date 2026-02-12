import { useState } from 'react'
import { Bookmark, X, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useFiltersStore, type SavedFilter } from '@/store/useFiltersStore'

interface SavedFiltersDropdownProps {
  page: 'users' | 'violations'
  currentFilters: Record<string, unknown>
  onLoadFilter: (filters: Record<string, unknown>) => void
  hasActiveFilters: boolean
}

export function SavedFiltersDropdown({
  page,
  currentFilters,
  onLoadFilter,
  hasActiveFilters,
}: SavedFiltersDropdownProps) {
  const { t } = useTranslation()
  const { savedFilters, saveFilter, deleteFilter } = useFiltersStore()
  const pageFilters = savedFilters.filter((f) => f.page === page)
  const [showNameInput, setShowNameInput] = useState(false)
  const [filterName, setFilterName] = useState('')

  const handleSave = () => {
    if (!filterName.trim()) return
    saveFilter({ name: filterName.trim(), page, filters: currentFilters })
    toast.success(t('common.savedFilters.filterSaved', { name: filterName }))
    setFilterName('')
    setShowNameInput(false)
  }

  const handleLoad = (filter: SavedFilter) => {
    onLoadFilter(filter.filters)
    toast.info(t('common.savedFilters.filterApplied', { name: filter.name }))
  }

  const handleDelete = (e: React.MouseEvent, filter: SavedFilter) => {
    e.stopPropagation()
    deleteFilter(filter.id)
    toast.success(t('common.savedFilters.filterDeleted', { name: filter.name }))
  }

  return (
    <DropdownMenu onOpenChange={(open) => { if (!open) setShowNameInput(false) }}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <Bookmark className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">{t('common.savedFilters.title')}</span>
          {pageFilters.length > 0 && (
            <span className="ml-1 text-xs text-dark-300">{pageFilters.length}</span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {/* Saved filters list */}
        {pageFilters.map((filter) => (
          <DropdownMenuItem
            key={filter.id}
            onSelect={() => handleLoad(filter)}
            className="flex items-center justify-between group"
          >
            <span className="truncate">{filter.name}</span>
            <button
              onClick={(e) => handleDelete(e, filter)}
              className="opacity-0 group-hover:opacity-100 ml-2 p-0.5 rounded hover:bg-dark-600 transition-opacity"
            >
              <X className="w-3 h-3 text-dark-300" />
            </button>
          </DropdownMenuItem>
        ))}

        {pageFilters.length > 0 && hasActiveFilters && <DropdownMenuSeparator />}

        {/* Save current filter */}
        {hasActiveFilters && !showNameInput && (
          <DropdownMenuItem onSelect={(e) => { e.preventDefault(); setShowNameInput(true) }}>
            <Plus className="w-4 h-4 mr-2" />
            {t('common.savedFilters.save')}
          </DropdownMenuItem>
        )}

        {showNameInput && (
          <div className="px-2 py-1.5 flex gap-1.5" onClick={(e) => e.stopPropagation()}>
            <Input
              type="text"
              placeholder={t('common.savedFilters.enterName')}
              value={filterName}
              onChange={(e) => setFilterName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSave()}
              className="h-7 text-xs"
              autoFocus
            />
            <Button size="sm" onClick={handleSave} disabled={!filterName.trim()} className="h-7 px-2 text-xs">
              OK
            </Button>
          </div>
        )}

        {pageFilters.length === 0 && !hasActiveFilters && (
          <div className="px-2 py-3 text-center text-xs text-dark-300">
            {t('common.savedFilters.noSaved')}
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
