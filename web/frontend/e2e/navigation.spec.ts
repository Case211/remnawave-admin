/**
 * E2E: Navigation — sidebar and routing smoke tests.
 *
 * Verifies that all major pages are reachable from the sidebar
 * and render without errors. Uses API mocking to avoid backend dependency.
 */
import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from './helpers';

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

test.describe('Navigation Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApiCalls(page);
    await loginAsAdmin(page);
  });

  const pages = [
    { path: '/', name: 'Dashboard' },
    { path: '/users', name: 'Users' },
    { path: '/nodes', name: 'Nodes' },
    { path: '/fleet', name: 'Fleet' },
    { path: '/hosts', name: 'Hosts' },
    { path: '/violations', name: 'Violations' },
    { path: '/blocking', name: 'Blocking' },
    { path: '/analytics', name: 'Analytics' },
    { path: '/admins', name: 'Admins' },
    { path: '/settings', name: 'Settings' },
    { path: '/audit', name: 'Audit Log' },
    { path: '/automations', name: 'Automations' },
    { path: '/notifications', name: 'Notifications' },
    { path: '/logs', name: 'System Logs' },
    { path: '/billing', name: 'Billing' },
    { path: '/backups', name: 'Backups' },
    { path: '/api-keys', name: 'API Keys' },
    { path: '/reports', name: 'Reports' },
    { path: '/resources', name: 'Resources' },
    { path: '/squads', name: 'Squads' },
  ];

  for (const { path, name } of pages) {
    test(`${name} page (${path}) renders without error`, async ({ page }) => {
      const consoleErrors: string[] = [];
      page.on('console', (msg) => {
        if (
          msg.type() === 'error' &&
          !msg.text().includes('Failed to fetch') &&
          !msg.text().includes('Failed to load resource')
        ) {
          consoleErrors.push(msg.text());
        }
      });

      await page.goto(path);
      await page.waitForLoadState('domcontentloaded');

      // КРИТИЧНО: страница не должна редиректить на /login — иначе тест
      // молча проверяет страницу логина вместо целевой (так и было,
      // пока setAuth писал токены в несуществующий ключ localStorage)
      await expect(page).not.toHaveURL(/login/);

      // Should not show a hard crash / white screen.
      // Auto-retrying: domcontentloaded ≠ React отрендерился — vite в dev
      // транспилирует lazy-чанки на лету, тяжёлым страницам нужно время
      await expect(page.locator('#root')).not.toBeEmpty({ timeout: 15_000 });

      // Should not have JS errors (excluding expected network errors)
      expect(consoleErrors).toEqual([]);
    });
  }
});
