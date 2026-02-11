import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  ShieldAlert,
  Server,
  Trash2,
  Bell,
  RotateCcw,
  FileText,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { automationsApi, type AutomationTemplate } from '../../api/automations'
import { categoryColor, categoryLabel, describeTrigger, describeAction } from './helpers'

const TEMPLATE_ICONS: Record<string, React.ElementType> = {
  auto_block_sharing: ShieldAlert,
  node_monitoring: Server,
  cleanup_expired: Trash2,
  traffic_notification: Bell,
  auto_restart_node: RotateCcw,
  daily_report: FileText,
}

interface TemplatesGalleryProps {
  canCreate: boolean
}

export function TemplatesGallery({ canCreate }: TemplatesGalleryProps) {
  const queryClient = useQueryClient()
  const [activatingId, setActivatingId] = useState<string | null>(null)

  const activateMutation = useMutation({
    mutationFn: automationsApi.activateTemplate,
    onSuccess: (rule) => {
      toast.success(`Шаблон "${rule.name}" активирован`)
      queryClient.invalidateQueries({ queryKey: ['automations'] })
      setActivatingId(null)
    },
    onError: () => {
      toast.error('Не удалось активировать шаблон')
      setActivatingId(null)
    },
  })

  const { data: templates, isLoading } = useQuery({
    queryKey: ['automation-templates'],
    queryFn: automationsApi.templates,
  })

  const handleActivate = (templateId: string) => {
    setActivatingId(templateId)
    activateMutation.mutate(templateId)
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-48 bg-dark-800" />
        ))}
      </div>
    )
  }

  if (!templates?.length) {
    return (
      <div className="text-center py-12 text-dark-400">
        Нет доступных шаблонов
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {templates.map((template) => (
        <TemplateCard
          key={template.id}
          template={template}
          canCreate={canCreate}
          onActivate={() => handleActivate(template.id)}
          isActivating={activatingId === template.id}
        />
      ))}
    </div>
  )
}

function TemplateCard({
  template,
  canCreate,
  onActivate,
  isActivating,
}: {
  template: AutomationTemplate
  canCreate: boolean
  onActivate: () => void
  isActivating: boolean
}) {
  const Icon = TEMPLATE_ICONS[template.id] || FileText

  return (
    <Card className="bg-dark-800/50 border-dark-700 hover:border-dark-600 transition-colors">
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-start gap-3 mb-3">
          <div className="p-2 rounded-lg bg-dark-700/50">
            <Icon className="w-5 h-5 text-primary-400" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-medium text-white">{template.name}</h3>
            <p className="text-xs text-dark-400 mt-1">{template.description}</p>
          </div>
        </div>

        {/* Badges */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          <Badge
            variant="outline"
            className={`text-[10px] ${categoryColor(template.category)}`}
          >
            {categoryLabel(template.category)}
          </Badge>
        </div>

        {/* Trigger -> Action summary */}
        <div className="text-xs text-dark-300 mb-4 space-y-2">
          <div className="flex items-start gap-2">
            <span className="text-dark-500 flex-shrink-0 mt-px">Когда:</span>
            <span>{describeTrigger(template)}</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-dark-500 flex-shrink-0 mt-px">Тогда:</span>
            <span className="text-primary-400">{describeAction(template)}</span>
          </div>
        </div>

        {/* Activate button */}
        {canCreate && (
          <Button
            size="sm"
            className="w-full bg-accent-teal/20 text-accent-teal hover:bg-accent-teal/30 border border-accent-teal/30"
            onClick={onActivate}
            disabled={isActivating}
          >
            {isActivating ? 'Активация...' : 'Включить'}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
