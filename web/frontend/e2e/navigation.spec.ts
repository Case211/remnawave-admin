/**
 * E2E: Navigation — sidebar and routing smoke tests.
 *
 * Verifies that all major pages are reachable from the sidebar
 * and render without errors. Uses API mocking to avoid backend dependency.
 */
import { test, expect, Page } from '@playwright/test';

/**
 * Set up route intercepts for all API calls so pages
 * can render without a running backend.
 */
async function mockAllApiCalls(page: Page) {
  // Generic API mock — return empty success for any GET
  await page.route('**/api/v2/**', (route) => {
    const url = route.request().url();

    // Auth endpoints
    if (url.includes('/auth/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          telegram_id: 100000,
          username: 'admin',
          role: 'superadmin',
          role_id: 1,
          auth_method: 'password',
          password_is_generated: false,
          permissions: [
            { resource: 'users', action: 'view' },
            { resource: 'nodes', action: 'view' },
            { resource: 'hosts', action: 'view' },
            { resource: 'analytics', action: 'view' },
            { resource: 'admins', action: 'view' },
            { resource: 'audit', action: 'view' },
            { resource: 'settings', action: 'view' },
            { resource: 'automations', action: 'view' },
            { resource: 'fleet', action: 'view' },
            { resource: 'logs', action: 'view' },
            { resource: 'violations', action: 'view' },
          ],
        }),
      });
    }

    if (url.includes('/auth/setup-status')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ needs_setup: false }),
      });
    }

    if (url.includes('/health')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', service: 'remnawave-admin-web', version: '2.6.0' }),
      });
    }

    // Default: return empty paginated list
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, page: 1, per_page: 50, pages: 0 }),
    });
  });

  // Mock WebSocket connections
  await page.route('**/ws/**', (route) => route.abort());
}

/** Inject auth state so the app thinks we're logged in. */
async function setAuth(page: Page) {
  await page.addInitScript(() => {
    const fakeToken = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwd2Q6YWRtaW4iLCJ1c2VybmFtZSI6ImFkbWluIiwidHlwZSI6ImFjY2VzcyIsImF1dGhfbWV0aG9kIjoicGFzc3dvcmQiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTcwMDAwMDAwMH0.fake';
    localStorage.setItem('access_token', fakeToken);
    localStorage.setItem('refresh_token', 'mock-refresh');
  });
}

test.describe('Navigation Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApiCalls(page);
    await setAuth(page);
  });

  const pages = [
    { path: '/', name: 'Dashboard' },
    { path: '/users', name: 'Users' },
    { path: '/nodes', name: 'Nodes' },
    { path: '/hosts', name: 'Hosts' },
    { path: '/violations', name: 'Violations' },
    { path: '/analytics', name: 'Analytics' },
    { path: '/admins', name: 'Admins' },
    { path: '/settings', name: 'Settings' },
    { path: '/audit', name: 'Audit Log' },
    { path: '/automations', name: 'Automations' },
  ];

  for (const { path, name } of pages) {
    test(`${name} page (${path}) renders without error`, async ({ page }) => {
      const consoleErrors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !msg.text().includes('Failed to fetch')) {
          consoleErrors.push(msg.text());
        }
      });

      await page.goto(path);
      await page.waitForLoadState('domcontentloaded');

      // Should not show a hard crash / white screen
      const bodyText = await page.textContent('body');
      expect(bodyText).toBeTruthy();

      // Should not have JS errors (excluding expected network errors)
      expect(consoleErrors).toEqual([]);
    });
  }
});
