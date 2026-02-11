/**
 * E2E test helpers — shared utilities for Playwright tests.
 */
import { Page, expect } from '@playwright/test';

/** Inject a mock JWT token into localStorage to bypass auth. */
export async function loginAsAdmin(page: Page) {
  // Set window.__ENV before page loads
  await page.addInitScript(() => {
    (window as any).__ENV = {
      VITE_API_URL: 'http://localhost:8081',
    };
  });

  // Set auth token in localStorage to simulate logged-in state
  await page.evaluate(() => {
    const mockToken = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.' +
      btoa(JSON.stringify({
        sub: 'pwd:admin',
        username: 'admin',
        type: 'access',
        auth_method: 'password',
        exp: Math.floor(Date.now() / 1000) + 3600,
        iat: Math.floor(Date.now() / 1000),
      })) + '.fake-signature';

    localStorage.setItem('access_token', mockToken);
    localStorage.setItem('refresh_token', 'mock-refresh-token');
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
