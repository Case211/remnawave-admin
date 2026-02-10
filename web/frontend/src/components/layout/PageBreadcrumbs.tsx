import { Link, useLocation, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import client from '@/api/client'

const ROUTE_LABELS: Record<string, string> = {
  '': 'Дашборд',
  users: 'Пользователи',
  nodes: 'Ноды',
  fleet: 'Флот',
  hosts: 'Хосты',
  violations: 'Нарушения',
  admins: 'Администраторы',
  settings: 'Настройки',
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
  const dynamicLabel = useDynamicLabel(segment, parentSegment)
  const label = dynamicLabel || ROUTE_LABELS[segment] || segment

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
            <Link to="/">Дашборд</Link>
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
