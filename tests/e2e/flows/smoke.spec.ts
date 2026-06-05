import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { AppShell } from '../pages/AppShell';
import { installClock, settlePersist } from '../helpers/clock';
import { assertValidPdf } from '../helpers/pdf';

test.describe('@core harness smoke', () => {
  test('boots, authenticates, navigates, persists a project, exports PDF', async ({ page }) => {
    await installClock(page);
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();

    for (const tab of ['files', 'songdb', 'format', 'templates', 'settings', 'editor'] as const) {
      await shell.switchTo(tab);
    }

    // Create + persist a project via the UI.
    await shell.switchTo('editor');
    await page.locator('#bulletin-title').fill('E2E Smoke Bulletin');
    await page.locator('#svc-title').fill('Smoke Service');
    await page.locator('#add-item-btn').click();
    await page.locator('[data-testid="item-row"][data-index="0"] .item-title-input').fill('Welcome');
    await settlePersist(page);

    // Confirm it persisted by reloading and finding it in Files.
    await page.reload();
    await shell.switchTo('files');
    await expect(page.locator('#files-list')).toContainText('E2E Smoke Bulletin');

    // Export a PDF through the real UI button (authenticated, via app JS) and
    // assert the downloaded bytes are a valid PDF.
    await shell.switchTo('editor');
    const printBtn = page.locator('#btn-print');
    await expect(printBtn).toBeEnabled();
    const downloadPromise = page.waitForEvent('download');
    await printBtn.click();
    const download = await downloadPromise;
    const filePath = await download.path();
    expect(filePath).toBeTruthy();
    assertValidPdf(readFileSync(filePath!));
  });
});

test.describe('@live real-integration smoke', () => {
  test('e2e-live member is authenticated and PCO is connected', async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    // PCO connected (inherited from worship@'s workspace) → the import view
    // (hidden until connected) is visible. Read-only: we never trigger an import.
    await page.locator('#editor-toolbar-sync').click();
    await expect(page.locator('#pco-import-view')).toBeVisible();
  });
});
