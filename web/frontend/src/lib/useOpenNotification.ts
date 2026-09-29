import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { notificationsApi, type Notification } from '@/api/notifications'

/**
 * Клик по уведомлению: отметить прочитанным и открыть, куда оно ведёт.
 * Без ссылки — туда, куда скажет вызывающий (из колокольчика — в полный
 * список): раньше такой клик не делал ничего, даже не гасил «непрочитанное».
 */
export function useOpenNotification() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  return useCallback((n: Notification, fallback?: string) => {
    if (!n.is_read) {
      notificationsApi.markRead([n.id])
        .then(() => {
          for (const key of ['notifications-unread', 'notifications-recent', 'notifications']) {
            queryClient.invalidateQueries({ queryKey: [key] })
          }
        })
        .catch(() => {})  // не отметилось — не беда, переход важнее
    }
    const to = n.link || fallback
    if (to) navigate(to)
  }, [navigate, queryClient])
}
