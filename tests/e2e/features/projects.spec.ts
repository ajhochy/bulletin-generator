import { test, expect } from '@playwright/test';
import { AppShell } from '../pages/AppShell';
import { ProjectsPage } from '../pages/ProjectsPage';
import { createAndSaveProject, openToolbarMenu } from '../pages/common';

test.describe('@core Projects (Files)', () => {
  test('create, list, open, select, and delete projects', async ({ page }) => {
    page.on('dialog', (d) => d.accept()); // New / Delete use native confirm()

    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    const projects = new ProjectsPage(page);

    // Create project Alpha.
    await shell.switchTo('editor');
    await createAndSaveProject(page, 'E2E Project Alpha');

    // Start a New project, then save it as Beta (saving the active project would
    // rename it, so New resets the active project first).
    await openToolbarMenu(page, 'file');
    await page.locator('#project-new-btn').click();
    await createAndSaveProject(page, 'E2E Project Beta');

    // Both appear in the Projects list.
    await shell.switchTo('files');
    await expect(projects.cardByName('E2E Project Alpha')).toBeVisible();
    await expect(projects.cardByName('E2E Project Beta')).toBeVisible();

    // Open Alpha → the editor loads it (bulletin title reflects the name).
    await projects.loadByName('E2E Project Alpha');
    await shell.switchTo('editor');
    await openToolbarMenu(page, 'file');
    await expect(page.locator('#bulletin-title')).toHaveValue('E2E Project Alpha');

    // Selecting a card surfaces the bulk-actions bar.
    await shell.switchTo('files');
    await projects.toggleSelect('E2E Project Alpha');
    await expect(projects.bulkBar()).toHaveClass(/visible/);

    // Delete Beta; Alpha remains.
    await projects.deleteByName('E2E Project Beta');
    await expect(projects.cardByName('E2E Project Alpha')).toBeVisible();
  });
});
