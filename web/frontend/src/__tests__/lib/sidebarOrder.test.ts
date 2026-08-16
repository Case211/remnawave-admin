import { describe, it, expect, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'

import { Users } from '@/components/brand/icons'
import {
  SIDEBAR_ORDER_KEY,
  applySidebarOrder,
  entryKey,
  mergeOrder,
  moveTopLevel,
  splitBlocks,
  useSidebarOrder,
  type SidebarOrder,
} from '@/lib/sidebarOrder'
import type { NavGroup, NavItem, NavSection, NavigationEntry } from '@/components/layout/navigation'

const section = (name: string): NavSection => ({ type: 'section', name })
const item = (href: string): NavItem => ({ name: href, href, icon: Users, permission: null })
const group = (name: string, hrefs: string[]): NavGroup => ({
  type: 'group',
  name,
  icon: Users,
  items: hrefs.map(item),
})

/** Учебное меню: две секции по два пункта и группа с тремя подпунктами. */
const MENU: NavigationEntry[] = [
  section('overview'),
  item('/'),
  item('/analytics'),
  section('infra'),
  item('/nodes'),
  item('/hosts'),
  section('admin'),
  group('administration', ['/admins', '/audit', '/logs']),
]

const keys = (entries: NavigationEntry[]) => entries.map(entryKey)
const EMPTY: SidebarOrder = { top: [], groups: {} }

describe('sidebarOrder — расстановка', () => {
  it('без сохранённого порядка меню остаётся исходным', () => {
    expect(keys(applySidebarOrder(MENU, EMPTY))).toEqual(keys(MENU))
  })

  it('пункт меняется местами с соседом', () => {
    const next = moveTopLevel(keys(MENU), 'item:/nodes', 'item:/hosts')
    expect(next).toEqual([
      'section:overview', 'item:/', 'item:/analytics',
      'section:infra', 'item:/hosts', 'item:/nodes',
      'section:admin', 'group:administration',
    ])
  })

  it('пункт можно утащить в другую секцию', () => {
    const next = moveTopLevel(keys(MENU), 'item:/nodes', 'item:/')
    // «Ноды» встали в первую секцию, а «Инфраструктура» осталась со своим хостом
    expect(next.slice(0, 4)).toEqual(['section:overview', 'item:/nodes', 'item:/', 'item:/analytics'])
    expect(next.slice(4)).toEqual(['section:infra', 'item:/hosts', 'section:admin', 'group:administration'])
  })

  it('пункт можно поднять выше первой секции — над всеми заголовками', () => {
    const next = moveTopLevel(keys(MENU), 'item:/nodes', 'section:overview')
    expect(next[0]).toBe('item:/nodes')
    expect(splitBlocks(next)[0]).toEqual(['item:/nodes'])
  })

  it('секция переезжает вместе со своими пунктами', () => {
    const next = moveTopLevel(keys(MENU), 'section:infra', 'section:overview')
    expect(next).toEqual([
      'section:infra', 'item:/nodes', 'item:/hosts',
      'section:overview', 'item:/', 'item:/analytics',
      'section:admin', 'group:administration',
    ])
  })

  it('секцию можно бросить на пункт чужой секции — переедет весь блок', () => {
    const next = moveTopLevel(keys(MENU), 'section:admin', 'item:/analytics')
    expect(next).toEqual([
      'section:admin', 'group:administration',
      'section:overview', 'item:/', 'item:/analytics',
      'section:infra', 'item:/nodes', 'item:/hosts',
    ])
  })

  it('перетаскивание на самого себя ничего не меняет', () => {
    expect(moveTopLevel(keys(MENU), 'item:/nodes', 'item:/nodes')).toEqual(keys(MENU))
  })
})

describe('sidebarOrder — жизнь после изменений меню', () => {
  it('новый пункт встаёт в свою секцию, а не в самый низ', () => {
    const saved = keys(MENU).filter((key) => key !== 'item:/hosts')
    const merged = mergeOrder(keys(MENU), saved)
    expect(merged.indexOf('item:/hosts')).toBe(merged.indexOf('item:/nodes') + 1)
  })

  it('цепочка новых пунктов не рассыпается', () => {
    const current = ['section:a', 'item:/1', 'item:/2', 'item:/3', 'section:b', 'item:/4']
    const merged = mergeOrder(current, ['section:b', 'item:/4', 'section:a', 'item:/1'])
    expect(merged).toEqual(['section:b', 'item:/4', 'section:a', 'item:/1', 'item:/2', 'item:/3'])
  })

  it('новый пункт в самом начале списка остаётся первым', () => {
    const merged = mergeOrder(['item:/new', 'section:a', 'item:/1'], ['section:a', 'item:/1'])
    expect(merged[0]).toBe('item:/new')
  })

  it('исчезнувший пункт выпадает, остальные держат порядок', () => {
    const saved = ['section:infra', 'item:/hosts', 'item:/gone', 'item:/nodes']
    const merged = mergeOrder(['section:infra', 'item:/nodes', 'item:/hosts'], saved)
    expect(merged).toEqual(['section:infra', 'item:/hosts', 'item:/nodes'])
  })

  it('дубли в сохранённом порядке не размножают пункты', () => {
    const merged = mergeOrder(['item:/1', 'item:/2'], ['item:/2', 'item:/2', 'item:/1'])
    expect(merged).toEqual(['item:/2', 'item:/1'])
  })
})

describe('sidebarOrder — группы', () => {
  it('подпункты группы переставляются отдельно от верхнего уровня', () => {
    const ordered = applySidebarOrder(MENU, {
      top: [],
      groups: { 'group:administration': ['/logs', '/admins', '/audit'] },
    })
    const administration = ordered.find((entry) => entryKey(entry) === 'group:administration') as NavGroup
    expect(administration.items.map((i) => i.href)).toEqual(['/logs', '/admins', '/audit'])
    // Верхний уровень при этом не тронут
    expect(keys(ordered)).toEqual(keys(MENU))
  })

  it('исходное меню не мутируется — правится копия', () => {
    applySidebarOrder(MENU, { top: [], groups: { 'group:administration': ['/logs', '/admins', '/audit'] } })
    const administration = MENU.find((entry) => entryKey(entry) === 'group:administration') as NavGroup
    expect(administration.items.map((i) => i.href)).toEqual(['/admins', '/audit', '/logs'])
  })
})

describe('useSidebarOrder', () => {
  beforeEach(() => localStorage.clear())

  it('свежая панель считается ненастроенной', () => {
    const { result } = renderHook(() => useSidebarOrder())
    expect(result.current.isCustomized).toBe(false)
    expect(result.current.order).toEqual(EMPTY)
  })

  it('перестановка переживает перезагрузку', () => {
    const first = renderHook(() => useSidebarOrder())
    act(() => first.result.current.moveTop(keys(MENU), 'section:infra', 'section:overview'))
    first.unmount()

    const second = renderHook(() => useSidebarOrder())
    expect(second.result.current.isCustomized).toBe(true)
    expect(keys(applySidebarOrder(MENU, second.result.current.order))[0]).toBe('section:infra')
  })

  it('порядок внутри группы сохраняется отдельно', () => {
    const { result } = renderHook(() => useSidebarOrder())
    act(() =>
      result.current.moveInGroup('group:administration', ['/admins', '/audit', '/logs'], '/logs', '/admins'),
    )
    expect(result.current.order.groups['group:administration']).toEqual(['/logs', '/admins', '/audit'])
  })

  it('сброс возвращает меню к исходному виду и чистит хранилище', () => {
    const { result } = renderHook(() => useSidebarOrder())
    act(() => result.current.moveTop(keys(MENU), 'item:/nodes', 'item:/'))
    act(() => result.current.reset())

    expect(result.current.isCustomized).toBe(false)
    expect(localStorage.getItem(SIDEBAR_ORDER_KEY)).toBeNull()
    expect(keys(applySidebarOrder(MENU, result.current.order))).toEqual(keys(MENU))
  })

  it('испорченное хранилище не роняет меню', () => {
    localStorage.setItem(SIDEBAR_ORDER_KEY, '{ не json')
    const { result } = renderHook(() => useSidebarOrder())
    expect(result.current.order).toEqual(EMPTY)
  })

  it('чужие типы в хранилище отсеиваются', () => {
    localStorage.setItem(SIDEBAR_ORDER_KEY, JSON.stringify({ top: ['item:/', 42, null], groups: { g: 'нет' } }))
    const { result } = renderHook(() => useSidebarOrder())
    expect(result.current.order.top).toEqual(['item:/'])
    expect(result.current.order.groups).toEqual({})
  })
})
