/**
 * E2E: Auth guard — tests that protected routes redirect to login.
 */
import { test, expect } from '@playwright/test';

test.describe('Auth Guard', () => {
  test.beforeEach(async ({ page }) => {
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
