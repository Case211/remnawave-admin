import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import client from '@/api/client'

export const ROUTE_LABEL_KEYS: Record<string, string> = {
  '': 'nav.dashboard',
  users: 'nav.users',
  nodes: 'nav.nodes',
  fleet: 'nav.fleet',
  hosts: 'nav.hosts',
  violations: 'nav.violations',
  automations: 'nav.automations',
  notifications: 'nav.notifications',
  mailserver: 'nav.mailServer',
  analytics: 'nav.analytics',
  backups: 'nav.backups',
  'api-keys': 'nav.apiKeys',
  reports: 'nav.reports',
  resources: 'nav.resources',
  blocking: 'nav.blocking',
  squads: 'nav.squads',
  admins: 'nav.admins',
  audit: 'nav.audit',
  logs: 'nav.logs',
  settings: 'nav.settings',
  dns: 'nav.dns',
  bscheck: 'nav.bscheck',
  finance: 'nav.finance',
  bedolaga: 'nav.bedolagaGroup',
  customers: 'nav.bedolaga.customers',
  promo: 'nav.bedolaga.promo',
  marketing: 'nav.bedolaga.marketing',
  referrals: 'nav.bedolaga.referrals',
  admin: 'nav.administration',
  // Разделы плагинов: сегмент пути → подпись их собственной страницы.
  plugins: 'nav.sections.plugins',
  report: 'plugins.smart_support.report.crumb',
  'smart-support': 'plugins.smart_support.nav',
  'block-radar': 'plugins.block_radar.nav',
  clients: 'plugins.smart_support.clients.title',
}

/**
 * Сегменты, у которых нет своей страницы: они лишь группируют вложенные
 * пути (``/plugins/smart-support``, ``/admin/plugins``). Ссылка на такой
 * сегмент вела бы в 404, поэтому в крошках он остаётся просто текстом.
 */
export const VIRTUAL_SEGMENTS = new Set(['plugins', 'admin'])

/**
 * Resolves dynamic route segments like UUIDs to readable names.
 */
function useDynamicLabel(segment: string, parentSegment: string): string | null {
  // Only fetch user names for /users/:uuid
  // Отчёт плагина адресуется тем же uuid, что и карточка юзера, — резолвим
  // его так же, иначе в крошке висит 36 символов вместо имени.
  const isUserUuid = (parentSegment === 'users' || parentSegment === 'report') && segment.length > 8
  const { data } = useQuery({
    queryKey: ['breadcrumb-user', segment],
    queryFn: async () => {
      const { data } = await client.get(`/users/${segment}`)
      return data?.username || data?.email || segment.slice(0, 8)
    },
    enabled: isUserUuid,
    staleTime: 60_000,
    retry: false,
  })
  if (isUserUuid) return data ?? segment.slice(0, 8) + '...'
  return null
}

interface CrumbProps {
  segment: string
  parentSegment: string
  path: string
  isLast: boolean
}

function BreadcrumbEntry({ segment, parentSegment, path, isLast }: CrumbProps) {
  const { t } = useTranslation()
  const dynamicLabel = useDynamicLabel(segment, parentSegment)
  const labelKey = ROUTE_LABEL_KEYS[segment]
  const label = dynamicLabel || (labelKey ? t(labelKey) : segment)

  if (isLast || VIRTUAL_SEGMENTS.has(segment)) {
    return (
      <BreadcrumbItem className="min-w-0">
        <BreadcrumbPage className="truncate max-w-[140px] sm:max-w-[240px] md:max-w-none">{label}</BreadcrumbPage>
      </BreadcrumbItem>
    )
  }

  return (
    <BreadcrumbItem className="min-w-0">
      <BreadcrumbLink asChild>
        <Link to={path} className="truncate max-w-[100px] sm:max-w-[180px] md:max-w-none inline-block align-bottom">
          {label}
        </Link>
      </BreadcrumbLink>
    </BreadcrumbItem>
  )
}

export default function PageBreadcrumbs() {
  const { t } = useTranslation()
  const location = useLocation()

  // Don't show breadcrumbs on the dashboard (root)
  if (location.pathname === '/') return null

  const segments = location.pathname.split('/').filter(Boolean)
  if (segments.length === 0) return null

  // Override breadcrumb trail for cross-section navigation (e.g. violations → user profile)
  const fromParam = new URLSearchParams(location.search).get('from')
  if (fromParam && ROUTE_LABEL_KEYS[fromParam] && segments[0] === 'users' && segments.length === 2) {
    return (
      <Breadcrumb className="px-4 md:px-6 pt-4 pb-0">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to="/">{t('nav.dashboard')}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link to={`/${fromParam}`}>{t(ROUTE_LABEL_KEYS[fromParam])}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbEntry
            segment={segments[1]}
            parentSegment="users"
            path={location.pathname}
            isLast={true}
          />
        </BreadcrumbList>
      </Breadcrumb>
    )
  }

  return (
    <Breadcrumb className="px-4 md:px-6 pt-4 pb-0">
      <BreadcrumbList>
        {/* Home */}
        <BreadcrumbItem>
          <BreadcrumbLink asChild>
            <Link to="/">{t('nav.dashboard')}</Link>
          </BreadcrumbLink>
        </BreadcrumbItem>

        {segments.map((segment, index) => {
          const path = '/' + segments.slice(0, index + 1).join('/')
          const parentSegment = index > 0 ? segments[index - 1] : ''
          const isLast = index === segments.length - 1

          return (
            <span key={path} className="contents">
              <BreadcrumbSeparator />
              <BreadcrumbEntry
                segment={segment}
                parentSegment={parentSegment}
                path={path}
                isLast={isLast}
              />
            </span>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}
