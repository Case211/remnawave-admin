import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity, Server, FileCode, History, Clock, Zap, Loader2 } from '@/components/brand/icons'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useTabParam } from '@/lib/useTabParam'
import { usePermissionStore } from '@/store/permissionStore'
import type { FleetTab } from './Fleet'

const Fleet = lazy(() => import('./Fleet'))
const Nodes = lazy(() => import('./Nodes'))

type ServersTab = 'fleet' | 'nodes' | 'scripts' | 'history' | 'scheduled' | 'bulk'

/** Вкладка страницы → вкладка «Флота» (у ноды панели своя страница). */
const FLEET_TAB: Record<Exclude<ServersTab, 'nodes'>, FleetTab> = {
  fleet: 'monitoring',
  scripts: 'scripts',
  history: 'history',
  scheduled: 'scheduled',
  bulk: 'bulk',
}

/**
 * «Сервера»: флот машин и ноды панели под одной крышей. Вкладки не смешивают
 * логику: «Флот» — про машины (в том числе серверы вне панели), «Ноды панели» —
 * про то, что панель отдаёт клиентам. Права у вкладок прежние.
 */
export default function Servers() {
  const { t } = useTranslation()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const canFleet = hasPermission('fleet', 'view')
  const canNodes = hasPermission('nodes', 'view')
  const canScripts = canFleet && hasPermission('fleet', 'scripts')

  const tabs: { key: ServersTab; label: string; icon: typeof Server; visible: boolean }[] = [
    { key: 'fleet', label: t('nav.fleet'), icon: Activity, visible: canFleet },
    { key: 'nodes', label: t('servers.tabs.nodes'), icon: Server, visible: canNodes },
    { key: 'scripts', label: t('fleet.tabs.scripts'), icon: FileCode, visible: canScripts },
    { key: 'history', label: t('fleet.tabs.history'), icon: History, visible: canFleet },
    { key: 'scheduled', label: t('fleet.tabs.scheduled'), icon: Clock, visible: canScripts },
    { key: 'bulk', label: t('fleet.tabs.bulk'), icon: Zap, visible: canFleet },
  ]
  const visible = tabs.filter((x) => x.visible)
  // По умолчанию «Флот»; кому он закрыт — первая доступная вкладка
  const [tab, setTab] = useTabParam<ServersTab>(visible[0]?.key ?? 'fleet', visible.map((x) => x.key))

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('servers.title')}</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">{t('servers.subtitle')}</p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-9 flex-wrap">
          {visible.map(({ key, label, icon: Icon }) => (
            <TabsTrigger key={key} value={key} className="text-xs gap-1.5">
              <Icon className="w-3.5 h-3.5" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Смонтирована только выбранная вкладка: каждая опрашивает свой API */}
      <Suspense fallback={<Loader2 className="w-6 h-6 animate-spin mx-auto text-dark-300" />}>
        {tab === 'nodes' ? <Nodes embedded /> : <Fleet embedded tab={FLEET_TAB[tab]} />}
      </Suspense>
    </div>
  )
}
