import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { AppShell } from '../pages/AppShell';
import { EditorPage } from '../pages/EditorPage';
import { createAndSaveProject, expandSection, row } from '../pages/common';
import { assertValidPdf } from '../helpers/pdf';

test.describe('@core Golden flow — build a bulletin from scratch', () => {
  test('create → add order of worship + announcement → set page size → export PDF', async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();

    // 1. Create + persist a named project.
    await shell.switchTo('editor');
    await createAndSaveProject(page, 'E2E Golden Bulletin');

    // 2. Build the order of worship (section heading + song).
    const editor = new EditorPage(page);
    await editor.openOrderOfWorship();
    await editor.addItem();
    await editor.setType(0, 'section');
    await editor.setTitle(0, 'GATHERING');
    await editor.addItem();
    await editor.setType(1, 'song');
    await editor.setTitle(1, 'How Great Thou Art');
    await expect(editor.items()).toHaveCount(2);

    // 3. Add an announcement.
    await expandSection(page, 'Announcements');
    await page.locator('#ann-add-btn').click();
    await row(page, 'ann', 0).locator('.ann-title-input').fill('Potluck Sunday');
    await expect(row(page, 'ann', 0).locator('.ann-title-input')).toHaveValue('Potluck Sunday');

    // 4. Choose a page size in the Format tab.
    await shell.switchTo('format');
    await page.locator('#doc-page-size-sel').selectOption('8.5x11');
    await expect(page.locator('#doc-page-size-sel')).toHaveValue('8.5x11');

    // 5. Export a print-ready PDF and assert the bytes are a valid PDF.
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
