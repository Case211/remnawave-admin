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

const ROUTE_LABEL_KEYS: Record<string, string> = {
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
  billing: 'nav.billing',
  backups: 'nav.backups',
  'api-keys': 'nav.apiKeys',
  admins: 'nav.admins',
  audit: 'nav.audit',
  logs: 'nav.logs',
  settings: 'nav.settings',
}

/**
 * Resolves dynamic route segments like UUIDs to readable names.
 */
function useDynamicLabel(segment: string, parentSegment: string): string | null {
  // Only fetch user names for /users/:uuid
  const isUserUuid = parentSegment === 'users' && segment.length > 8
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

  if (isLast) {
    return (
      <BreadcrumbItem>
        <BreadcrumbPage>{label}</BreadcrumbPage>
      </BreadcrumbItem>
    )
  }

  return (
    <BreadcrumbItem>
      <BreadcrumbLink asChild>
        <Link to={path}>{label}</Link>
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
