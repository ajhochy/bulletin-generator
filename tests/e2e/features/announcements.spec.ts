import { test, expect } from '@playwright/test';
import { AppShell } from '../pages/AppShell';
import { expandSection, row } from '../pages/common';

test.describe('@core Announcements', () => {
  test('add, edit, and remove announcements', async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    await shell.switchTo('editor');
    await expandSection(page, 'Announcements');

    const rows = page.locator('[data-testid="ann-row"]');
    const addBtn = page.locator('#ann-add-btn');

    // Add the first announcement; it persists via POST /api/announcements.
    const saved = page.waitForResponse(
      (r) => r.url().includes('/api/announcements') && r.request().method() === 'POST' && r.ok(),
      { timeout: 15_000 },
    );
    await addBtn.click();
    await saved;
    await expect(rows).toHaveCount(1);

    // Edit its title.
    await row(page, 'ann', 0).locator('.ann-title-input').fill('E2E Announcement');
    await expect(row(page, 'ann', 0).locator('.ann-title-input')).toHaveValue('E2E Announcement');

    // Add a second, then remove the first (no confirm on announcement delete).
    await addBtn.click();
    await expect(rows).toHaveCount(2);
    await row(page, 'ann', 0).getByTitle('Remove').click();
    await expect(rows).toHaveCount(1);
  });
});
