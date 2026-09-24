import { Navigate, useLocation } from 'react-router-dom'

/**
 * /nodes и /fleet переехали во вкладки страницы «Сервера». Параметры
 * сохраняются (?node=<uuid> ведёт к нужной карточке), вкладка «Флота»
 * monitoring теперь называется fleet и стоит по умолчанию.
 */
export function ToServers({ tab }: { tab?: string }) {
  const { search } = useLocation()
  const params = new URLSearchParams(search)
  const current = tab ?? params.get('tab')
  if (!current || current === 'monitoring' || current === 'fleet') params.delete('tab')
  else params.set('tab', current)
  const query = params.toString()
  return <Navigate to={`/servers${query ? `?${query}` : ''}`} replace />
}
