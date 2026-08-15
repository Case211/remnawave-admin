import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { MemoryRouter, Route, Routes, RouterProvider, createMemoryRouter } from 'react-router-dom'
import i18n from '@/i18n'

import ExternalPluginPage, { loadScript } from '@/plugins/ExternalPluginPage'
import type { PluginInfo } from '@/lib/plugins'

const useActivePlugins = vi.fn()
vi.mock('@/lib/plugins', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/plugins')>()
  return { ...actual, useActivePlugins: () => useActivePlugins() }
})

vi.mock('@/pages/NotFound', () => ({
  default: () => <div data-testid="not-found" />,
}))

const PLUGIN: PluginInfo = {
  id: 'my_plugin',
  name: 'My plugin',
  version: '1.0.0',
  license_state: 'not_required',
  api_prefix: '/api/v2/plugins/my_plugin',
  navigation: [
    { path: '/plugins/my-plugin', label_i18n: 'My plugin', icon: 'Zap', permission: ['my_plugin', 'view'] },
  ],
  ui: { kind: 'module', path: '/app' },
}

const SRC = '/api/v2/plugins/my_plugin/app'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/plugins/:pluginId" element={<ExternalPluginPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

function pluginScript(): HTMLScriptElement | null {
  return document.head.querySelector<HTMLScriptElement>(`script[data-plugin-ui="${SRC}"]`)
}

async function fire(el: HTMLElement, type: 'load' | 'error') {
  await act(async () => {
    el.dispatchEvent(new Event(type))
  })
}

describe('ExternalPluginPage', () => {
  beforeEach(() => {
    useActivePlugins.mockReturnValue({ data: [PLUGIN], isLoading: false })
    delete window.rwaPluginUI
  })

  afterEach(() => {
    document.head.querySelectorAll('script[data-plugin-ui]').forEach((s) => s.remove())
  })

  it('renders NotFound for an unknown plugin id', () => {
    renderAt('/plugins/does-not-exist')
    expect(screen.getByTestId('not-found')).toBeInTheDocument()
    expect(pluginScript()).toBeNull()
  })

  it('tells when the plugin ships no page', () => {
    useActivePlugins.mockReturnValue({ data: [{ ...PLUGIN, ui: null }], isLoading: false })
    renderAt('/plugins/my-plugin')
    expect(screen.getByText(i18n.t('plugins.external.no_ui'))).toBeInTheDocument()
    expect(pluginScript()).toBeNull()
  })

  it('shows the loading state while plugins are being fetched', () => {
    useActivePlugins.mockReturnValue({ data: undefined, isLoading: true })
    renderAt('/plugins/my-plugin')
    expect(screen.getByText(i18n.t('plugins.external.loading'))).toBeInTheDocument()
  })

  it('mounts the plugin UI once its script has loaded', async () => {
    const mount = vi.fn()
    const unmount = vi.fn()
    const view = renderAt('/plugins/my-plugin')

    const tag = pluginScript()
    expect(tag).not.toBeNull()
    expect(tag!.src).toContain(SRC)

    window.rwaPluginUI = { my_plugin: { mount, unmount } }
    await fire(tag!, 'load')

    await waitFor(() => expect(mount).toHaveBeenCalledTimes(1))
    expect(mount.mock.calls[0][0]).toBe(screen.getByTestId('plugin-host'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    view.unmount()
    expect(unmount).toHaveBeenCalledTimes(1)
  })

  it('reports a failed script and does not get stuck on the next visit', async () => {
    const first = renderAt('/plugins/my-plugin')
    const tag = pluginScript()
    expect(tag).not.toBeNull()

    await fire(tag!, 'error')
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(i18n.t('plugins.external.failed')),
    )
    // The failed tag must not linger, otherwise the next attempt would wait
    // forever on load/error events that already fired.
    expect(pluginScript()).toBeNull()
    first.unmount()

    // Second visit: a fresh tag is inserted and can succeed this time.
    const mount = vi.fn()
    renderAt('/plugins/my-plugin')
    const retryTag = pluginScript()
    expect(retryTag).not.toBeNull()
    expect(retryTag).not.toBe(tag)
    window.rwaPluginUI = { my_plugin: { mount } }
    await fire(retryTag!, 'load')
    await waitFor(() => expect(mount).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('gives the next plugin a fresh container when switching between two external pages', async () => {
    const OTHER: PluginInfo = {
      ...PLUGIN,
      id: 'other_plugin',
      name: 'Other',
      api_prefix: '/api/v2/plugins/other_plugin',
      navigation: [
        { path: '/plugins/other-plugin', label_i18n: 'Other', icon: 'Zap', permission: ['other_plugin', 'view'] },
      ],
    }
    useActivePlugins.mockReturnValue({ data: [PLUGIN, OTHER], isLoading: false })
    const firstMount = vi.fn((el: HTMLElement) => {
      el.appendChild(Object.assign(document.createElement('div'), { id: 'leftover' }))
    })
    const firstUnmount = vi.fn() // deliberately leaves #leftover behind
    const secondMount = vi.fn()
    window.rwaPluginUI = {
      my_plugin: { mount: firstMount, unmount: firstUnmount },
      other_plugin: { mount: secondMount },
    }

    // Both routes render the same component; only :pluginId changes.
    const router = createMemoryRouter(
      [{ path: '/plugins/:pluginId', element: <ExternalPluginPage /> }],
      { initialEntries: ['/plugins/my-plugin'] },
    )
    render(<RouterProvider router={router} />)
    await fire(pluginScript()!, 'load')
    await waitFor(() => expect(firstMount).toHaveBeenCalledTimes(1))
    const firstHost = screen.getByTestId('plugin-host')
    expect(firstHost.querySelector('#leftover')).not.toBeNull()

    await act(async () => {
      await router.navigate('/plugins/other-plugin')
    })
    const otherTag = document.head.querySelector<HTMLScriptElement>(
      'script[data-plugin-ui="/api/v2/plugins/other_plugin/app"]',
    )
    expect(otherTag).not.toBeNull()
    await fire(otherTag!, 'load')
    await waitFor(() => expect(secondMount).toHaveBeenCalledTimes(1))

    expect(firstUnmount).toHaveBeenCalledTimes(1)
    const secondHost = screen.getByTestId('plugin-host')
    expect(secondHost).not.toBe(firstHost)
    expect(secondMount.mock.calls[0][0]).toBe(secondHost)
    // Whatever the previous plugin failed to clean up must not leak into the next page.
    expect(secondHost.querySelector('#leftover')).toBeNull()
  })

  it('reports when the script loads but never registers a handle', async () => {
    renderAt('/plugins/my-plugin')
    await fire(pluginScript()!, 'load')
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })
})

describe('loadScript', () => {
  afterEach(() => {
    document.head.querySelectorAll('script[data-plugin-ui]').forEach((s) => s.remove())
  })

  it('reuses a tag that already loaded', async () => {
    const p1 = loadScript('/x/app')
    const tag = document.head.querySelector<HTMLScriptElement>('script[data-plugin-ui="/x/app"]')!
    tag.dispatchEvent(new Event('load'))
    await p1
    await loadScript('/x/app')
    expect(document.head.querySelectorAll('script[data-plugin-ui="/x/app"]')).toHaveLength(1)
  })

  it('shares one pending tag between concurrent callers', async () => {
    const p1 = loadScript('/y/app')
    const p2 = loadScript('/y/app')
    const tags = document.head.querySelectorAll<HTMLScriptElement>('script[data-plugin-ui="/y/app"]')
    expect(tags).toHaveLength(1)
    tags[0].dispatchEvent(new Event('load'))
    await expect(Promise.all([p1, p2])).resolves.toBeDefined()
  })

  it('removes the tag when loading fails', async () => {
    const p = loadScript('/z/app')
    const tag = document.head.querySelector<HTMLScriptElement>('script[data-plugin-ui="/z/app"]')!
    tag.dispatchEvent(new Event('error'))
    await expect(p).rejects.toThrow()
    expect(document.head.querySelector('script[data-plugin-ui="/z/app"]')).toBeNull()
  })

  it('does not choke on quotes in the path', () => {
    const src = '/q/app?x="1"'
    void loadScript(src).catch(() => {})
    void loadScript(src).catch(() => {})
    const tags = Array.from(document.head.querySelectorAll<HTMLScriptElement>('script[data-plugin-ui]')).filter(
      (s) => s.getAttribute('data-plugin-ui') === src,
    )
    expect(tags).toHaveLength(1)
  })
})
