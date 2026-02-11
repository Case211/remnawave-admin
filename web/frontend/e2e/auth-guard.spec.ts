/**
 * E2E: Auth guard — tests that protected routes redirect to login.
 */
import { test, expect } from '@playwright/test';

/** Mock API calls so the app doesn't hit a real backend. */
async function mockApi(page: import('@playwright/test').Page) {
  await page.route('**/api/v2/**', (route) => {
    const url = route.request().url();
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
        body: JSON.stringify({ status: 'ok' }),
      });
    }
    return route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Not authenticated' }),
    });
  });
  await page.route('**/ws/**', (route) => route.abort());
}

test.describe('Auth Guard', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    // Clear all stored auth state
    await page.addInitScript(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  });

  const protectedPaths = [
    '/',
    '/users',
    '/nodes',
    '/hosts',
    '/analytics',
    '/admins',
    '/settings',
    '/violations',
    '/audit',
    '/automations',
  ];

  for (const path of protectedPaths) {
    test(`${path} redirects to login without auth`, async ({ page }) => {
      await page.goto(path);
      // Should end up on the login page
      await expect(page).toHaveURL(/login/);
    });
  }
});
