import { test, expect } from '@playwright/test';
import { AppShell } from '../pages/AppShell';
import { expandSection, row } from '../pages/common';

/** Add a row, edit a field, remove it — asserting relative to the current count
 *  (these sections may be pre-seeded with workspace defaults). */
async function addEditRemove(opts: {
  page: import('@playwright/test').Page;
  sectionLabel: string;
  addBtn: string;
  area: string;
  fieldSelector: string;
  value: string;
}): Promise<void> {
  const { page, sectionLabel, addBtn, area, fieldSelector, value } = opts;
  await expandSection(page, sectionLabel);
  const rows = page.locator(`[data-testid="${area}-row"]`);
  const before = await rows.count();

  await page.locator(addBtn).click();
  await expect(rows).toHaveCount(before + 1);

  await row(page, area, before).locator(fieldSelector).first().fill(value);
  await expect(row(page, area, before).locator(fieldSelector).first()).toHaveValue(value);

  await row(page, area, before).getByTitle('Remove').click();
  await expect(rows).toHaveCount(before);
}

test.describe('@core Editor sidebar sections', () => {
  test.beforeEach(async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    await shell.switchTo('editor');
  });

  test('Welcome: add, edit, remove', async ({ page }) => {
    await addEditRemove({
      page, sectionLabel: 'Welcome', addBtn: '#welcome-add-btn',
      area: 'welcome', fieldSelector: '.ann-title-input', value: 'E2E Welcome Item',
    });
  });

  test('Volunteer Roles: add, edit, remove', async ({ page }) => {
    await addEditRemove({
      page, sectionLabel: 'Volunteer Roles', addBtn: '#vr-add-btn',
      area: 'vr', fieldSelector: '.vr-title-input', value: 'E2E Role',
    });
  });

  test('Staff: add, edit, remove', async ({ page }) => {
    await addEditRemove({
      page, sectionLabel: 'Church Staff', addBtn: '#staff-add-btn',
      area: 'staff', fieldSelector: '.staff-ed-input', value: 'E2E Person',
    });
  });
});
