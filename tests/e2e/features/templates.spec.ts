import { test, expect } from '@playwright/test';
import { AppShell } from '../pages/AppShell';

test.describe('@core Templates', () => {
  test('gallery renders and the designer overlay opens and closes', async ({ page }) => {
    page.on('dialog', (d) => d.accept()); // Back on an unsaved designer prompts discard

    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    await shell.switchTo('templates');

    // The gallery shows at least the built-in templates.
    await expect(page.locator('#tpl-grid .tpl-template-card').first()).toBeVisible();

    // "New Template" first opens a base-template picker modal; Create proceeds
    // into the full-screen designer overlay.
    const overlay = page.locator('#tpl-designer-overlay');
    await page.locator('#tpl-new-btn').click();
    await page.getByRole('button', { name: 'Create', exact: true }).click();
    await expect(overlay).toBeVisible();

    // Back closes it.
    await page.locator('#tpl-designer-back').click();
    await expect(overlay).toBeHidden();
  });
});
