import { test, expect } from '@playwright/test';
import { AppShell } from '../pages/AppShell';
import { waitForAppReady } from '../pages/common';

test.describe('@core Format', () => {
  test('document page size changes and persists across reload', async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    await shell.switchTo('format');

    const sel = page.locator('#doc-page-size-sel');
    await expect(sel).toBeVisible();

    // Changing page size POSTs /api/settings { docTemplate } immediately.
    const saved = page.waitForResponse(
      (r) => r.url().includes('/api/settings') && r.request().method() === 'POST' && r.ok(),
      { timeout: 15_000 },
    );
    await sel.selectOption('8.5x11');
    await saved;
    await expect(sel).toHaveValue('8.5x11');

    // Persisted: survives a reload.
    await page.reload();
    await waitForAppReady(page);
    await shell.switchTo('format');
    await expect(page.locator('#doc-page-size-sel')).toHaveValue('8.5x11');
  });
});
