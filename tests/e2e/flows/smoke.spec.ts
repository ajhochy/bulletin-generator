import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { AppShell } from '../pages/AppShell';
import { createAndSaveProject, openToolbarMenu } from '../pages/common';
import { assertValidPdf } from '../helpers/pdf';

test.describe('@core harness smoke', () => {
  test('boots, authenticates, navigates, persists a project, exports PDF', async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();

    for (const tab of ['files', 'songdb', 'format', 'templates', 'settings', 'editor'] as const) {
      await shell.switchTo(tab);
    }

    // Create + persist a project, proving the full frontend -> server.py ->
    // Supabase write path. (createAndSaveProject opens the File menu, names the
    // bulletin, Saves, and awaits the POST — the canonical persistable-project
    // flow, since autosave only fires once a project is active.)
    await shell.switchTo('editor');
    await createAndSaveProject(page, 'E2E Smoke Bulletin');

    // Confirm it persisted: the saved project appears in the Projects list.
    await shell.switchTo('files');
    await expect(page.locator('#files-list')).toContainText('E2E Smoke Bulletin', { timeout: 10_000 });

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
    await openToolbarMenu(page, 'sync');
    await expect(page.locator('#pco-import-view')).toBeVisible();
  });
});
