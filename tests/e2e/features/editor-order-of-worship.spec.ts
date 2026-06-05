import { test, expect } from '@playwright/test';
import { AppShell } from '../pages/AppShell';
import { EditorPage } from '../pages/EditorPage';
import { createAndSaveProject } from '../pages/common';

test.describe('@core Order of Worship editing', () => {
  test('add items, set type/title, reorder, page break, delete — reflected in preview', async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    await createAndSaveProject(page, 'E2E OOW');

    const editor = new EditorPage(page);
    await editor.openOrderOfWorship();

    // Add a section heading. Editor state is the stable signal; the section
    // also renders in the live preview (the preview re-renders constantly as the
    // calendar loads, so we only assert the always-rendered section heading there).
    await editor.addItem();
    await editor.setType(0, 'section');
    await editor.setTitle(0, 'GATHERING');
    await expect(editor.item(0).locator('.item-title-input')).toHaveValue('GATHERING');
    await expect(editor.preview()).toContainText('GATHERING', { timeout: 10_000 });

    // Add a song (title-only songs don't render in the preview; assert state).
    await editor.addItem();
    await editor.setType(1, 'song');
    await editor.setTitle(1, 'Amazing Grace');
    await expect(editor.item(1).locator('.item-title-input')).toHaveValue('Amazing Grace');
    await expect(editor.items()).toHaveCount(2);

    // Reorder: move the song above the section heading.
    await editor.moveUp(1);
    await expect(editor.item(0).locator('.item-title-input')).toHaveValue('Amazing Grace');
    await expect(editor.item(1).locator('.item-title-input')).toHaveValue('GATHERING');

    // Insert a page break, then delete it.
    await editor.addPageBreak();
    await expect(editor.items()).toHaveCount(3);
    await editor.deleteItem(2);
    await expect(editor.items()).toHaveCount(2);

    // Delete the song; the section heading remains.
    await editor.deleteItem(0);
    await expect(editor.items()).toHaveCount(1);
    await expect(editor.item(0).locator('.item-title-input')).toHaveValue('GATHERING');
  });
});
