import { test, expect } from '@playwright/test';
import { AppShell } from '../pages/AppShell';
import { openToolbarMenu } from '../pages/common';

// Live lane only: exercises the REAL Planning Center proxy using the connected
// token inherited from worship@'s workspace. Read-only — never imports a plan.
// (Requires the workspace-scoped settings fix: the proxy must read the
// authenticated member's workspace, not an arbitrary `workspace_settings LIMIT 1`.)
test.describe('@live Planning Center (read-only)', () => {
  test('service types load from PCO and selecting one loads its plans', async ({ page }) => {
    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();

    await openToolbarMenu(page, 'sync');
    await expect(page.locator('#pco-import-view')).toBeVisible();

    // Service types are fetched from the real PCO org (more than the placeholder).
    const serviceType = page.locator('#pco-service-type-sel');
    await expect
      .poll(async () => serviceType.locator('option').count(), { timeout: 30_000 })
      .toBeGreaterThan(1);

    // Selecting a service type fetches its plans via the PCO proxy.
    const plansFetched = page.waitForResponse(
      (r) => /pco-proxy\/.*plans/.test(r.url()) && r.ok(),
      { timeout: 30_000 },
    );
    await serviceType.selectOption({ index: 1 });
    await plansFetched;

    // Plans dropdown becomes populated (read-only: we never click Import).
    await expect
      .poll(async () => page.locator('#pco-plan-sel option').count(), { timeout: 30_000 })
      .toBeGreaterThan(0);
  });
});
