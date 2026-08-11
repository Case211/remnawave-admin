/**
 * Generic host for pages of plugins that ship outside this repository.
 *
 * Built-in plugin pages live in ``src/plugins/<id>/`` and are wired through
 * ``PLUGIN_ROUTES``. A plugin distributed as a standalone wheel cannot add
 * itself there, so it declares its UI in the backend manifest
 * (``PluginUI(kind=..., path=...)``) and this component mounts it on the
 * generic ``/plugins/:pluginId`` route.
 *
 * ``kind="module"``: the plugin's script is loaded from
 * ``api_prefix + path`` and is expected to register itself as
 *
 *     window.rwaPluginUI['<plugin id>'] = { mount(el), unmount?() }
 *
 * The script is same-origin, so it passes the panel CSP (``script-src
 * 'self'``). ``kind="iframe"``: the same URL is embedded in an iframe and the
 * plugin serves it with ``frame-ancestors 'self'``.
 */
import { useEffect, useRef, useState } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useActivePlugins, type PluginInfo } from '@/lib/plugins'

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
function findPlugin(plugins: PluginInfo[], pluginId: string, pathname: string) {
  const byNav = plugins.find((p) => p.navigation.some((n) => n.path === pathname))
  if (byNav) return byNav
  return plugins.find((p) => p.id === pluginId || p.id.replace(/_/g, '-') === pluginId)
}

function loadScript(src: string): Promise<void> {
  const existing = document.querySelector<HTMLScriptElement>(`script[data-plugin-ui="${src}"]`)
  if (existing) {
    if (existing.dataset.loaded === '1') return Promise.resolve()
    return new Promise((resolve, reject) => {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error(src)))
    })
  }
  return new Promise((resolve, reject) => {
    const el = document.createElement('script')
    el.src = src
    el.defer = true
    el.dataset.pluginUi = src
    el.addEventListener('load', () => {
      el.dataset.loaded = '1'
      resolve()
    })
    el.addEventListener('error', () => reject(new Error(src)))
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
    if (!plugin || !ui || ui.kind !== 'module' || !src) return
    let cancelled = false
    setFailed(false)

    loadScript(src)
      .then(() => {
        const handle = window.rwaPluginUI?.[plugin.id]
        if (cancelled) return
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
  }, [plugin, ui, src])

  if (isLoading) {
    return <div className="py-16 text-center text-muted-foreground">{t('plugins.external.loading')}</div>
  }
  if (!plugin) {
    return <div className="py-16 text-center text-muted-foreground">{t('plugins.external.unknown')}</div>
  }
  if (!ui) {
    return <div className="py-16 text-center text-muted-foreground">{t('plugins.external.no_ui')}</div>
  }
  if (ui.kind === 'iframe') {
    return (
      <iframe
        src={src ?? ''}
        title={plugin.name}
        className="w-full h-[calc(100vh-10rem)] rounded-xl border border-border bg-card"
      />
    )
  }
  return (
    <>
      {failed && <div className="py-16 text-center text-muted-foreground">{t('plugins.external.failed')}</div>}
      <div ref={hostRef} />
    </>
  )
}
