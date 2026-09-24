import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { ToServers } from '@/components/ToServers'

function Where() {
  const { pathname, search } = useLocation()
  return <span data-testid="where">{pathname + search}</span>
}

function go(from: string, tab?: string) {
  const r = render(
    <MemoryRouter initialEntries={[from]}>
      <Routes>
        <Route path="/nodes" element={<ToServers tab="nodes" />} />
        <Route path="/fleet" element={<ToServers tab={tab} />} />
        <Route path="/servers" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
  return r.container.querySelector('[data-testid="where"]')?.textContent
}

describe('старые адреса ведут на «Сервера»', () => {
  it('/nodes → вкладка нод, параметры сохраняются', () => {
    expect(go('/nodes?node=abc')).toBe('/servers?node=abc&tab=nodes')
  })
  it('/fleet → Флот по умолчанию', () => {
    expect(go('/fleet')).toBe('/servers')
    expect(go('/fleet?tab=monitoring&node=x')).toBe('/servers?node=x')
  })
  it('вкладки Флота сохраняются', () => {
    expect(go('/fleet?tab=scripts')).toBe('/servers?tab=scripts')
  })
})
