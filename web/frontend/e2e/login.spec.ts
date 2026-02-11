/**
 * E2E: Login flow — critical authentication scenarios.
 *
 * Tests the login page renders correctly and handles
 * various authentication states.
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
    // Default: 401 for auth-related, empty response for others
    return route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Not authenticated' }),
    });
  });
  await page.route('**/ws/**', (route) => route.abort());
}

test.describe('Login Page', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test('renders login form', async ({ page }) => {
    await page.goto('/login');

    // Should display login form elements
    await expect(page.locator('input[type="text"], input[name="username"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.getByRole('button', { name: /войти|вход|login|sign in/i })).toBeVisible();
  });

  test('shows validation on empty submit', async ({ page }) => {
    await page.goto('/login');

    // Click login button without filling fields
    const loginButton = page.getByRole('button', { name: /войти|вход|login|sign in/i });
    await loginButton.click();

    // Should stay on login page (no redirect)
    await expect(page).toHaveURL(/login/);
  });

  test('redirects to login when not authenticated', async ({ page }) => {
    // Try to access a protected page
    await page.goto('/');

    // Should redirect to login
    await expect(page).toHaveURL(/login/);
  });

  test('login page has correct title', async ({ page }) => {
    await page.goto('/login');

    // Page should have a title
    const title = await page.title();
    expect(title).toBeTruthy();
  });
});
