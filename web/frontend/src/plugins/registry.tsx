/**
 * Plugin UI page registry.
 *
 * UI pages for paid/optional plugins live in the open-source repo under
 * ``src/plugins/<id>/`` so they can be lazy-loaded with the rest of the
 * frontend. This registry maps a plugin id to the React routes that should
 * be mounted whenever the backend reports that plugin as installed.
 *
 * A plugin without a backend pip-package will not appear in
 * ``useActivePlugins()`` — its routes are never rendered. When the plugin
 * is installed but its license is expired or missing, the routes still
 * render: their own pages call the plugin API and react to the resulting
 * HTTP 402 to show a "buy/renew license" banner.
 *
 * Adding a plugin: import a lazy page below and add an entry to
 * ``PLUGIN_ROUTES`` keyed by the plugin id.
 */
import { lazy, type ComponentType } from 'react'

interface PluginRoute {
  path: string
  Component: ComponentType
}

// Plugin id (key) must match the ``id`` returned by the backend manifest.
export const PLUGIN_ROUTES: Record<string, PluginRoute[]> = {
  smart_support: [
    { path: '/plugins/smart-support', Component: lazy(() => import('./smart-support/SearchPage')) },
    { path: '/plugins/smart-support/report/:uuid', Component: lazy(() => import('./smart-support/ReportPage')) },
    { path: '/plugins/smart-support/settings', Component: lazy(() => import('./smart-support/SettingsPage')) },
    { path: '/plugins/smart-support/audit', Component: lazy(() => import('./smart-support/AuditPage')) },
  ],
}

export type { PluginRoute }
