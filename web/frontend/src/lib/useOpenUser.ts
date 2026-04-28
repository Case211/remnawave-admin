import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

type MouseLikeEvent = { button: number; metaKey: boolean; ctrlKey: boolean; preventDefault: () => void }

export function useOpenUser() {
  const navigate = useNavigate()
  return useCallback(
    (uuid: string | null | undefined, suffix = '') => {
      if (!uuid) return {}
      const path = `/users/${uuid}${suffix}`
      return {
        role: 'link' as const,
        onClick: (e: MouseLikeEvent) => {
          if (e.metaKey || e.ctrlKey || e.button === 1) {
            window.open(path, '_blank', 'noopener,noreferrer')
            return
          }
          navigate(path)
        },
        onAuxClick: (e: MouseLikeEvent) => {
          if (e.button === 1) {
            e.preventDefault()
            window.open(path, '_blank', 'noopener,noreferrer')
          }
        },
      }
    },
    [navigate],
  )
}
