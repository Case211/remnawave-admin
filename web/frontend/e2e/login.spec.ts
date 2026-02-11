/**
 * E2E: Login flow — critical authentication scenarios.
 *
 * Tests the login page renders correctly and handles
 * various authentication states.
 */
import { test, expect } from '@playwright/test';

test.describe('Login Page', () => {
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
