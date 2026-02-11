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
    await page.waitForLoadState('domcontentloaded');

    // Wait for the password form to appear (auto-shown when no Telegram bot configured)
    await expect(page.locator('#username')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('#password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible();
  });

  test('shows validation on empty submit', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded');

    // Wait for the form to appear
    const loginButton = page.getByRole('button', { name: 'Войти', exact: true });
    await expect(loginButton).toBeVisible({ timeout: 10_000 });

    // Button should be disabled when fields are empty
    await expect(loginButton).toBeDisabled();

    // Should stay on login page
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
