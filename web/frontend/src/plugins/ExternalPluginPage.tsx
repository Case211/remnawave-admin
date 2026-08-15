/**
 * Generic host for pages of plugins that ship outside this repository.
 *
 * Built-in plugin pages live in ``src/plugins/<id>/`` and are wired through
 * ``PLUGIN_ROUTES``. A plugin distributed as a standalone wheel cannot add
 * itself there, so it declares its UI in the backend manifest
 * (``PluginUI(kind="module", path=...)``) and this component mounts it on the
 * generic ``/plugins/:pluginId`` route.
 *
 * The plugin's script is loaded from ``api_prefix + path`` and is expected to
 * register itself as
 *
 *     window.rwaPluginUI['<plugin id>'] = { mount(el), unmount?() }
 *
 * The script is same-origin, so it passes the panel CSP (``script-src
 * 'self'``). An iframe kind is not offered: the backend stamps
 * ``X-Frame-Options: DENY`` on every response, plugin routers included.
 */
import { useEffect, useRef, useState } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useActivePlugins, type PluginInfo } from '@/lib/plugins'
import NotFound from '@/pages/NotFound'

interface PluginUIHandle {
  mount: (el: HTMLElement) => void
  unmount?: () => void
}

declare global {
  interface Window {
    rwaPluginUI?: Record<string, PluginUIHandle | undefined>
  }
}

/** Nav paths use dashes (``/plugins/my-plugin``), plugin ids underscores. */
export function findPlugin(plugins: PluginInfo[], pluginId: string, pathname: string) {
  const byNav = plugins.find((p) => p.navigation.some((n) => n.path === pathname))
  if (byNav) return byNav
  return plugins.find((p) => p.id === pluginId || p.id.replace(/_/g, '-') === pluginId)
}

const SCRIPT_ATTR = 'data-plugin-ui'

/**
 * Load the plugin script once per page lifetime.
 *
 * A tag that failed to load is removed again, so the next visit starts from
 * scratch instead of waiting on ``load``/``error`` events that already fired.
 */
export function loadScript(src: string): Promise<void> {
  // Compare attribute values instead of building a selector from ``src``:
  // no escaping to get wrong, whatever characters the path contains.
  const existing = Array.from(
    document.head.querySelectorAll<HTMLScriptElement>(`script[${SCRIPT_ATTR}]`),
  ).find((s) => s.getAttribute(SCRIPT_ATTR) === src)
  if (existing) {
    if (existing.dataset.loaded === '1') return Promise.resolve()
    // Still loading: piggyback on the pending tag.
    return new Promise((resolve, reject) => {
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error(src)), { once: true })
    })
  }
  return new Promise((resolve, reject) => {
    const el = document.createElement('script')
    el.src = src
    el.defer = true
    el.setAttribute(SCRIPT_ATTR, src)
    el.addEventListener(
      'load',
      () => {
        el.dataset.loaded = '1'
        resolve()
      },
      { once: true },
    )
    el.addEventListener(
      'error',
      () => {
        el.remove()
        reject(new Error(src))
      },
      { once: true },
    )
    document.head.appendChild(el)
  })
}

export default function ExternalPluginPage() {
  const { pluginId = '' } = useParams()
  const { pathname } = useLocation()
  const { t } = useTranslation()
  const { data: plugins, isLoading } = useActivePlugins()
  const hostRef = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)

  const plugin = findPlugin(plugins ?? [], pluginId, pathname)
  const ui = plugin?.ui ?? null
  const src = plugin && ui ? plugin.api_prefix + ui.path : null

  useEffect(() => {
    if (!plugin || !src) return
    let cancelled = false
    setFailed(false)

    loadScript(src)
      .then(() => {
        if (cancelled) return
        const handle = window.rwaPluginUI?.[plugin.id]
        if (!handle || !hostRef.current) {
          setFailed(true)
          return
        }
        handle.mount(hostRef.current)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
      window.rwaPluginUI?.[plugin.id]?.unmount?.()
    }
  }, [plugin, src])

  if (isLoading) {
    return <div className="py-16 text-center text-muted-foreground">{t('plugins.external.loading')}</div>
  }
  if (!plugin) {
    // Unknown id behaves like any other unknown URL.
    return <NotFound />
  }
  if (!ui) {
    return <div className="py-16 text-center text-muted-foreground">{t('plugins.external.no_ui')}</div>
  }
  return (
    <>
      {failed && (
        <div role="alert" className="py-16 text-center text-muted-foreground">
          {t('plugins.external.failed')}
        </div>
      )}
      <div ref={hostRef} data-testid="plugin-host" />
    </>
  )
}
