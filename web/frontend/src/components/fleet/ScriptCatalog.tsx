/**
 * ScriptCatalog — Grid of scripts grouped by category.
 * Shows built-in and custom scripts with search and category filter.
 */
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Shield,
  Globe,
  Server,
  Activity,
  Search,
  Play,
  Lock,
} from 'lucide-react'
import client from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// ── Types ──────────────────────────────────────────────────────

export interface Script {
  id: number
  name: string
  display_name: string
  description: string | null
  category: string
  timeout_seconds: number
  requires_root: boolean
  is_builtin: boolean
}

interface ScriptCatalogProps {
  onRunScript: (script: Script) => void
}

// ── Constants ──────────────────────────────────────────────────

const CATEGORY_META: Record<string, { icon: typeof Shield; color: string; label: string }> = {
  security: { icon: Shield, color: 'text-red-400', label: 'fleet.scripts.categories.security' },
  network: { icon: Globe, color: 'text-blue-400', label: 'fleet.scripts.categories.network' },
  system: { icon: Server, color: 'text-orange-400', label: 'fleet.scripts.categories.system' },
  monitoring: { icon: Activity, color: 'text-green-400', label: 'fleet.scripts.categories.monitoring' },
  custom: { icon: Server, color: 'text-violet-400', label: 'fleet.scripts.categories.custom' },
}

// ── Component ──────────────────────────────────────────────────

export default function ScriptCatalog({ onRunScript }: ScriptCatalogProps) {
  const { t } = useTranslation()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  const { data: scripts = [], isLoading } = useQuery<Script[]>({
    queryKey: ['fleet-scripts'],
    queryFn: async () => {
      const { data } = await client.get('/fleet/scripts')
      return data
    },
  })

  const filteredScripts = useMemo(() => {
    let result = scripts
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (s) =>
          s.display_name.toLowerCase().includes(q) ||
          (s.description || '').toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q),
      )
    }
    if (selectedCategory) {
      result = result.filter((s) => s.category === selectedCategory)
    }
    return result
  }, [scripts, searchQuery, selectedCategory])

  const categories = useMemo(() => {
    const cats = new Set(scripts.map((s) => s.category))
    return Array.from(cats).sort()
  }, [scripts])

  const groupedScripts = useMemo(() => {
    const groups: Record<string, Script[]> = {}
    for (const script of filteredScripts) {
      if (!groups[script.category]) groups[script.category] = []
      groups[script.category].push(script)
    }
    return groups
  }, [filteredScripts])

  return (
    <div className="space-y-4">
      {/* Search + category filter */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-300" />
          <Input
            placeholder={t('fleet.scripts.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <Button
            variant={selectedCategory === null ? 'default' : 'secondary'}
            size="sm"
            className="h-8 text-xs"
            onClick={() => setSelectedCategory(null)}
          >
            {t('fleet.scripts.allCategories')}
          </Button>
          {categories.map((cat) => {
            const meta = CATEGORY_META[cat] || CATEGORY_META.custom
            const Icon = meta.icon
            return (
              <Button
                key={cat}
                variant={selectedCategory === cat ? 'default' : 'secondary'}
                size="sm"
                className="h-8 text-xs gap-1"
                onClick={() => setSelectedCategory(cat)}
              >
                <Icon className={cn('w-3 h-3', meta.color)} />
                {t(meta.label, { defaultValue: cat })}
              </Button>
            )
          })}
        </div>
      </div>

      {/* Script grid by category */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="h-[80px] bg-dark-700/30 rounded animate-pulse" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : Object.keys(groupedScripts).length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-dark-300 text-sm">{t('fleet.scripts.noScripts')}</p>
          </CardContent>
        </Card>
      ) : (
        Object.entries(groupedScripts).map(([category, categoryScripts]) => {
          const meta = CATEGORY_META[category] || CATEGORY_META.custom
          const Icon = meta.icon

          return (
            <div key={category}>
              <div className="flex items-center gap-2 mb-2">
                <Icon className={cn('w-4 h-4', meta.color)} />
                <h3 className="text-sm font-medium text-white">
                  {t(meta.label, { defaultValue: category })}
                </h3>
                <span className="text-dark-400 text-xs">({categoryScripts.length})</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
                {categoryScripts.map((script) => (
                  <Card
                    key={script.id}
                    className="hover:border-dark-200/40 transition-colors"
                  >
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="min-w-0">
                          <h4 className="text-sm font-medium text-white truncate">
                            {script.display_name}
                          </h4>
                          {script.description && (
                            <p className="text-xs text-dark-300 mt-0.5 line-clamp-2">
                              {script.description}
                            </p>
                          )}
                        </div>
                        <Button
                          variant="secondary"
                          size="sm"
                          className="h-7 w-7 p-0 shrink-0"
                          onClick={() => onRunScript(script)}
                        >
                          <Play className="w-3 h-3" />
                        </Button>
                      </div>
                      <div className="flex items-center gap-2 mt-2">
                        {script.requires_root && (
                          <Badge variant="secondary" className="text-[10px] gap-0.5 px-1.5 py-0">
                            <Lock className="w-2.5 h-2.5" />
                            root
                          </Badge>
                        )}
                        {script.is_builtin && (
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                            {t('fleet.scripts.builtin')}
                          </Badge>
                        )}
                        <span className="text-[10px] text-dark-400 ml-auto">
                          {script.timeout_seconds}s
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}
