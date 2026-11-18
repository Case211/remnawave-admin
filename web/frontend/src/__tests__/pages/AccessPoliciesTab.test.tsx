import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from '@/i18n'
import type { PolicyDetail } from '@/api/accessPolicies'

const get = vi.fn()
const listPolicies = vi.fn()
const getPolicy = vi.fn()
const createPolicy = vi.fn()
const updatePolicy = vi.fn()
const listAdmins = vi.fn()

vi.mock('@/api/client', () => ({
  default: { get: (...args: unknown[]) => get(...args) },
}))
vi.mock('@/api/accessPolicies', () => ({
  accessPoliciesApi: {
    list: (...args: unknown[]) => listPolicies(...args),
    get: (...args: unknown[]) => getPolicy(...args),
    create: (...args: unknown[]) => createPolicy(...args),
    update: (...args: unknown[]) => updatePolicy(...args),
    remove: vi.fn(),
    attachToRole: vi.fn(),
    attachToAdmin: vi.fn(),
  },
}))
vi.mock('@/api/admins', () => ({
  adminsApi: { list: (...args: unknown[]) => listAdmins(...args) },
}))
vi.mock('@/api/squads', () => ({
  squadsApi: {
    listInternal: vi.fn().mockResolvedValue([]),
    listExternal: vi.fn().mockResolvedValue([]),
  },
}))

import AccessPoliciesTab from '@/pages/AccessPoliciesTab'

const SAVED_UUID = '11111111-1111-4111-8111-111111111111'
const LATE_UUID = '22222222-2222-4222-8222-222222222222'

function policy(overrides: Partial<PolicyDetail> = {}): PolicyDetail {
  return {
    id: 7,
    name: 'User scope',
    description: null,
    rules: [{
      id: 11,
      resource_type: 'user',
      scope_type: 'uuid',
      scope_value: SAVED_UUID,
      actions: ['view'],
    }],
    role_ids: [],
    admin_ids: [],
    ...overrides,
  }
}

function policyListItem() {
  return {
    id: 7,
    name: 'User scope',
    description: null,
    rules_count: 1,
    roles_count: 0,
    admins_count: 0,
  }
}

function mockOptions(users: Array<{ uuid: string; username?: string }> = []) {
  get.mockImplementation((url: string) => {
    if (url === '/users') return Promise.resolve({ data: { items: users, total: users.length, pages: 1 } })
    if (url === '/nodes' || url === '/hosts') return Promise.resolve({ data: { items: [] } })
    return Promise.reject(new Error(`Unexpected GET ${url}`))
  })
}

async function renderEditor(detail: PolicyDetail = policy()) {
  listPolicies.mockResolvedValue([policyListItem()])
  getPolicy.mockResolvedValue(detail)
  listAdmins.mockResolvedValue({ items: [] })
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <AccessPoliciesTab roles={[]} />
    </QueryClientProvider>,
  )
  fireEvent.click(await screen.findByText('User scope'))
  await screen.findByRole('button', { name: 'Save' })
  return rendered
}

describe('AccessPoliciesTab user rules', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage('en')
    mockOptions()
    updatePolicy.mockResolvedValue(policy())
  })

  afterAll(async () => {
    await i18n.changeLanguage('ru')
  })

  it('requests a valid bounded page of user options', async () => {
    await renderEditor()
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith('/users', {
        params: { page: 1, per_page: 100, search: undefined },
      })
    })
  })

  it('keeps a saved UUID visible when it is absent from the loaded options', async () => {
    await renderEditor()
    expect(await screen.findByLabelText('User UUID')).toHaveValue(SAVED_UUID)
  })

  it('shows a manual UUID path when user options fail to load', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/users') return Promise.reject({ response: { status: 403 } })
      if (url === '/nodes' || url === '/hosts') return Promise.resolve({ data: { items: [] } })
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    await renderEditor()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load users. Enter a UUID manually or check users:view permission.',
    )
    expect(screen.getByLabelText('User UUID')).toHaveValue(SAVED_UUID)
  })

  it('offers only view for user rules', async () => {
    await renderEditor()
    expect(screen.getByRole('checkbox', { name: 'View' })).toBeChecked()
    expect(screen.queryByRole('checkbox', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('finds and saves a user outside the first options page', async () => {
    get.mockImplementation((url: string, config?: { params?: { search?: string } }) => {
      if (url === '/users') {
        const lateUser = { uuid: LATE_UUID, username: 'user-101-beyond-first-page' }
        return Promise.resolve({
          data: {
            items: config?.params?.search === lateUser.username ? [lateUser] : [],
            total: config?.params?.search ? 1 : 101,
          },
        })
      }
      if (url === '/nodes' || url === '/hosts') return Promise.resolve({ data: { items: [] } })
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    await renderEditor()

    fireEvent.change(screen.getByLabelText('Search users'), {
      target: { value: 'user-101-beyond-first-page' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    fireEvent.click((await screen.findAllByRole('combobox'))[2])
    fireEvent.click(await screen.findByRole('option', { name: 'user-101-beyond-first-page' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(updatePolicy).toHaveBeenCalled())
    const [, body] = updatePolicy.mock.calls[0]
    expect(body.rules[0]).toMatchObject({
      resource_type: 'user',
      scope_value: LATE_UUID,
      actions: ['view'],
    })
  })
})
