import { test, expect } from '@playwright/test';
import { AppShell } from '../pages/AppShell';
import { waitForAppReady } from '../pages/common';

test.describe('@core Settings — branding', () => {
  test('church name and give-online URL persist across reload', async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    await shell.switchTo('settings');

    // Each field POSTs to /api/settings on input.
    const churchSaved = page.waitForResponse(
      (r) => r.url().includes('/api/settings') && r.request().method() === 'POST' && r.ok(),
      { timeout: 15_000 },
    );
    await page.locator('#svc-church').fill('E2E Test Church');
    await churchSaved;

    const giveSaved = page.waitForResponse(
      (r) => r.url().includes('/api/settings') && r.request().method() === 'POST' && r.ok(),
      { timeout: 15_000 },
    );
    await page.locator('#give-online-url-input').fill('https://example.org/give');
    await giveSaved;

    // Reload and confirm the server-persisted values are restored.
    await page.reload();
    await waitForAppReady(page);
    await shell.switchTo('settings');
    await expect(page.locator('#svc-church')).toHaveValue('E2E Test Church');
    await expect(page.locator('#give-online-url-input')).toHaveValue('https://example.org/give');
  });
});
