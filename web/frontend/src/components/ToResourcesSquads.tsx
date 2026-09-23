import { Navigate, useLocation } from 'react-router-dom'

/**
 * «Сквады» переехали вкладкой на страницу «Ресурсы». Старая ссылка
 * /squads?tab=external ведёт туда же, на внешние сквады.
 */
export function ToResourcesSquads() {
  const { search } = useLocation()
  const params = new URLSearchParams(search)
  const kind = params.get('tab')
  params.set('tab', 'squads')
  if (kind === 'external') params.set('squads', 'external')
  return <Navigate to={`/resources?${params.toString()}`} replace />
}
