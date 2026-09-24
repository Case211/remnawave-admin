import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { setDisplayTimeZone } from './timezone'

export const DISPLAY_TIME_ZONE_QUERY = ['display-timezone'] as const

/** Подтянуть часовой пояс панели и применить его ко всему времени в админке. */
export function useTimeZoneSync(): void {
  const { data } = useQuery({
    queryKey: DISPLAY_TIME_ZONE_QUERY,
    queryFn: async () => {
      const { data } = await client.get('/settings/timezone')
      return data as { timezone: string }
    },
    staleTime: 5 * 60_000,
    retry: 1,
  })

  useEffect(() => {
    if (data?.timezone) setDisplayTimeZone(data.timezone)
  }, [data?.timezone])
}
