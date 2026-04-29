import { useCallback, type MouseEvent as ReactMouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'

type MouseLikeEvent = { button: number; metaKey: boolean; ctrlKey: boolean; preventDefault: () => void }

/**
 * Click handlers for non-anchor row containers (`<tr>`, `<div>` cards). Applies SPA navigation,
 * supports cmd/ctrl/middle-click for new tab. Does NOT set role="link" — that mismatches the
 * underlying tag's a11y semantics. For real anchor markup use `useUserLinkProps`.
 */
export function useOpenUser() {
  const navigate = useNavigate()
  return useCallback(
    (uuid: string | null | undefined, suffix = '') => {
      if (!uuid) return {}
      const path = `/users/${uuid}${suffix}`
      return {
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

/**
 * Props for an `<a>` element pointing at a user. Native browser handles middle-click /
 * ctrl-click / right-click → "open in new tab"; we intercept plain left-click for SPA nav.
 */
export function useUserLinkProps() {
  const navigate = useNavigate()
  return useCallback(
    (uuid: string | null | undefined, suffix = '') => {
      if (!uuid) return {}
      const path = `/users/${uuid}${suffix}`
      return {
        href: path,
        onClick: (e: ReactMouseEvent<HTMLAnchorElement>) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return
          e.preventDefault()
          navigate(path)
        },
      }
    },
    [navigate],
  )
}
