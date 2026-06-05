import { type Page, type Locator, expect } from '@playwright/test';

const TOOLBAR_MENU_IDS = {
  file: 'editor-toolbar-file',
  sync: 'editor-toolbar-sync',
  document: 'editor-toolbar-document',
} as const;
export type ToolbarMenu = keyof typeof TOOLBAR_MENU_IDS;

/** Open one of the editor toolbar <details> dropdowns (idempotent). */
export async function openToolbarMenu(page: Page, menu: ToolbarMenu): Promise<void> {
  const id = TOOLBAR_MENU_IDS[menu];
  const details = page.locator(`#${id}`);
  const isOpen = await details.evaluate((el) => (el as HTMLDetailsElement).open);
  if (!isOpen) await page.locator(`#${id} summary`).click();
  await expect(details).toHaveJSProperty('open', true);
}

/**
 * The canonical "make a persistable project" flow. Autosave only fires once a
 * project is active (projects.js:345), so most specs must call this first.
 * Opens the File menu, names the bulletin, clicks Save, and awaits the POST.
 */
export async function createAndSaveProject(page: Page, name: string): Promise<void> {
  await openToolbarMenu(page, 'file');
  await page.locator('#bulletin-title').fill(name);
  const saved = page.waitForResponse(
    (r) => r.url().includes('/api/projects') && r.request().method() === 'POST' && r.ok(),
    { timeout: 15_000 },
  );
  await page.locator('#project-save-btn').click();
  await saved;
}

/** Locator for a dynamic row by its data-testid area + numeric index. */
export function row(page: Page, area: string, index: number): Locator {
  return page.locator(`[data-testid="${area}-row"][data-index="${index}"]`);
}

/**
 * Expand an editor sidebar section card (they start collapsed; editor.js:595).
 * Clicking the `.section-label` toggles `.collapsed`. Idempotent.
 */
export async function expandSection(page: Page, labelText: string): Promise<Locator> {
  const section = page
    .locator('aside .panel-section')
    .filter({ has: page.locator('.section-label', { hasText: labelText }) })
    .first();
  const collapsed = await section.evaluate((el) => el.classList.contains('collapsed'));
  if (collapsed) await section.locator('.section-label').first().click();
  await expect(section).not.toHaveClass(/(^|\s)collapsed(\s|$)/);
  return section;
}
