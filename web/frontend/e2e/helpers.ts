/**
 * E2E test helpers — shared utilities for Playwright tests.
 */
import { Page, expect } from '@playwright/test';

/**
 * Inject persisted auth state under the real zustand persist key.
 *
 * Токены в localStorage не хранятся (живут в HttpOnly cookies) — приложению
 * достаточно isAuthenticated=true в persisted-стейте плюс замоканный
 * GET /auth/me (validateSession проверяет cookie-сессию именно им).
 */
export async function loginAsAdmin(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem(
      'remnawave-auth',
      JSON.stringify({
        state: {
          user: { username: 'admin', firstName: 'admin', authMethod: 'password' },
          isAuthenticated: true,
        },
        version: 0,
      })
    );
  });
}

/** Wait for the page to fully load (no network activity). */
export async function waitForPageLoad(page: Page) {
  await page.waitForLoadState('networkidle');
}

/** Assert that the page has no console errors. */
export async function assertNoConsoleErrors(page: Page) {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });
  // Give the page a moment to settle
  await page.waitForTimeout(500);
  expect(errors).toEqual([]);
}
