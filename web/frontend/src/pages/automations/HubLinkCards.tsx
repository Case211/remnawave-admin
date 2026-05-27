import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Terminal,
  CalendarClock,
  Activity,
  Bot,
  ArrowRight,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface HubLinkCardProps {
  icon: ReactNode
  title: string
  description: string
  to: string
  badge?: string
  accent?: 'cyan' | 'amber' | 'violet' | 'red' | 'green'
}

function HubLinkCard({ icon, title, description, to, badge, accent = 'cyan' }: HubLinkCardProps) {
  const { t } = useTranslation()
  const accentClass = {
    cyan: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
    amber: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    violet: 'text-violet-400 bg-violet-500/10 border-violet-500/20',
    red: 'text-red-400 bg-red-500/10 border-red-500/20',
    green: 'text-green-400 bg-green-500/10 border-green-500/20',
  }[accent]

  return (
    <Link to={to} className="group block">
      <Card className="h-full transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_0_24px_-8px_rgba(99,102,241,0.4)]">
        <CardContent className="p-4 flex items-start gap-3">
          <div className={cn('p-2.5 rounded-lg border shrink-0', accentClass)}>
            {icon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-semibold text-white truncate">{title}</h3>
              {badge && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-dark-200 uppercase tracking-wide">
                  {badge}
                </span>
              )}
            </div>
            <p className="text-xs text-dark-200 mt-1 line-clamp-2">{description}</p>
            <div className="mt-3 flex items-center gap-1 text-xs text-primary-400 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
              {t('automations.hub.open', { defaultValue: 'Открыть' })}
              <ArrowRight className="w-3 h-3" />
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

export function NodeScriptsPanel() {
  const { t } = useTranslation()
  return (
    <div className="space-y-4">
      <p className="text-sm text-dark-200">
        {t('automations.hub.nodeScriptsHint', {
          defaultValue: 'Каталог shell-скриптов для нод, история запусков и плановые задачи живут на странице Fleet. Откройте нужный раздел напрямую.',
        })}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <HubLinkCard
          accent="cyan"
          icon={<Terminal className="w-5 h-5" />}
          title={t('automations.hub.scripts.catalog', { defaultValue: 'Каталог скриптов' })}
          description={t('automations.hub.scripts.catalogDesc', {
            defaultValue: 'Готовые и кастомные shell-скрипты. Запуск ручной или через расписание.',
          })}
          to="/fleet?tab=scripts"
        />
        <HubLinkCard
          accent="violet"
          icon={<Activity className="w-5 h-5" />}
          title={t('automations.hub.scripts.history', { defaultValue: 'История запусков' })}
          description={t('automations.hub.scripts.historyDesc', {
            defaultValue: 'Логи выполненных скриптов, exit-коды, вывод и поиск по нодам.',
          })}
          to="/fleet?tab=history"
        />
        <HubLinkCard
          accent="amber"
          icon={<Bot className="w-5 h-5" />}
          title={t('automations.hub.scripts.terminal', { defaultValue: 'Терминал нод' })}
          description={t('automations.hub.scripts.terminalDesc', {
            defaultValue: 'Прямой SSH-терминал к ноде через панель.',
          })}
          to="/fleet?tab=monitoring"
        />
      </div>
    </div>
  )
}

export function SchedulesPanel() {
  const { t } = useTranslation()
  return (
    <div className="space-y-4">
      <p className="text-sm text-dark-200">
        {t('automations.hub.schedulesHint', {
          defaultValue: 'Плановые задачи запускают скрипты на нодах по cron-расписанию. Создавайте и редактируйте на вкладке Fleet → Плановые.',
        })}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <HubLinkCard
          accent="green"
          icon={<CalendarClock className="w-5 h-5" />}
          title={t('automations.hub.schedules.fleet', { defaultValue: 'Плановые задачи (Fleet)' })}
          description={t('automations.hub.schedules.fleetDesc', {
            defaultValue: 'CRON-расписание для скриптов на нодах. История, активация/отключение.',
          })}
          to="/fleet?tab=scheduled"
        />
        <HubLinkCard
          accent="cyan"
          icon={<Activity className="w-5 h-5" />}
          title={t('automations.hub.schedules.rules', { defaultValue: 'Правила по расписанию' })}
          description={t('automations.hub.schedules.rulesDesc', {
            defaultValue: 'Правила с триггером schedule (cron/интервал) — создаются в табе «Правила».',
          })}
          to="/automations?tab=rules"
        />
      </div>
    </div>
  )
}

