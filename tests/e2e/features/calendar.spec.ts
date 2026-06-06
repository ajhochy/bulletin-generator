import { test, expect } from '@playwright/test';
import { AppShell } from '../pages/AppShell';
import { waitForAppReady } from '../pages/common';

test.describe('@core Calendar settings', () => {
  test('iCal feed URLs persist across reload', async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    await shell.switchTo('settings');

    const urls = page.locator('#cal-urls-input');
    await expect(urls).toBeVisible();

    // "Save & Refresh" persists the iCal feed list via POST /api/settings.
    const saved = page.waitForResponse(
      (r) => r.url().includes('/api/settings') && r.request().method() === 'POST' && r.ok(),
      { timeout: 15_000 },
    );
    await urls.fill('https://example.com/feed.ics');
    await page.locator('#cal-settings-save-btn').click();
    await saved;

    // Reload and confirm the saved feed URL is restored.
    await page.reload();
    await waitForAppReady(page);
    await shell.switchTo('settings');
    await expect(page.locator('#cal-urls-input')).toHaveValue('https://example.com/feed.ics');
  });

  // NOTE: a manual-event add test (#cal-add-event-btn) is deferred to Phase 5.
  // The "Add Event" button only appears once a calendar fetch succeeds and
  // initializes calEvents to an array; a fresh workspace has no calendar source
  // (/cal -> "Calendar unavailable"), so calEvents stays null. Deterministic
  // coverage needs the record/replay helper to mock /cal returning an array.
});
