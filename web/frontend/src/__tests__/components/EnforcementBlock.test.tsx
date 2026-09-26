import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import EnforcementBlock from '@/components/settings/EnforcementBlock'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('@/components/PermissionGate', () => ({ useHasPermission: () => true }))
vi.mock('@/api/client', () => ({ default: { get: vi.fn(async (url: string) => ({ data: url.endsWith('/status') ? {
  enabled: false, mode: 'dry_run', scope: 'trial_only', grace_hours: 12, min_score: 0,
  final_action: 'manual_review', notice_suffix: 'Wait {hours}', pause_for_support: true, delivery_failure: 'manual_review',
  delivery_attempts: 3, throttle_kbit: 1024, throttle_hours: 0, pilot_user_uuids: [], pilot_users: [], case_counts: {},
} : { items: [] } })), put: vi.fn(), post: vi.fn() } }))

test('shows a safe disabled dry-run configuration and support endpoint', async () => {
  render(<QueryClientProvider client={new QueryClient()}><EnforcementBlock canEdit /></QueryClientProvider>)
  expect(await screen.findByText('settings.enforcement.title')).toBeInTheDocument()
  expect(screen.getByText('POST /api/v3/enforcement/support-events')).toBeInTheDocument()
  expect(screen.getByText('settings.enforcement.emptyPilot')).toBeInTheDocument()
})
