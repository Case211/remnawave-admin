import { Navigate, useLocation } from 'react-router-dom'

/**
 * «Хосты» и «Сквады» переехали вкладками на страницу «Ресурсы». Старая
 * ссылка /squads?tab=external ведёт туда же, на внешние сквады.
 */
export function ToResources({ tab }: { tab: 'hosts' | 'squads' }) {
  const { search } = useLocation()
  const params = new URLSearchParams(search)
  const kind = params.get('tab')
  params.set('tab', tab)
  if (tab === 'squads' && kind === 'external') params.set('squads', 'external')
  return <Navigate to={`/resources?${params.toString()}`} replace />
}
