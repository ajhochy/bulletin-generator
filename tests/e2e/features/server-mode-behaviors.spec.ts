import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { AppShell } from '../pages/AppShell';
import { ProjectsPage } from '../pages/ProjectsPage';
import { createAndSaveProject, waitForAppReady, openToolbarMenu } from '../pages/common';
import { signInAs } from '../helpers/session';
import {
  createWorkspaceMember,
  removeWorkspaceMember,
  type EphemeralIdentity,
} from '../helpers/supabase-admin';

test.describe('@core Server-mode multitenant behaviors', () => {
  test('a non-owner member sees another member\'s workspace project as read-only', async ({ page, browser }) => {
    // User A = the core ephemeral owner (default storageState). Create a project
    // (new projects default to visibility='workspace', so other members see it).
    const shellA = new AppShell(page);
    await shellA.goto();
    await shellA.expectAuthenticated();
    await shellA.switchTo('editor');
    await createAndSaveProject(page, 'E2E Shared Bulletin');

    // Add a disposable second member (User B) to A's workspace.
    const a = JSON.parse(readFileSync('tests/e2e/.auth/core-ids.json', 'utf8')) as EphemeralIdentity;
    let b: EphemeralIdentity | null = null;
    try {
      b = await createWorkspaceMember(a.workspaceId, 'editor');

      // Drive User B in a separate browser context.
      const ctxB = await browser.newContext();
      const pageB = await ctxB.newPage();
      await signInAs(pageB, b.email, b.password);

      const shellB = new AppShell(pageB);
      await shellB.switchTo('files');
      await new ProjectsPage(pageB).loadByName('E2E Shared Bulletin');
      await shellB.switchTo('editor');

      // B is not the owner → read-only banner appears.
      await expect(pageB.locator('#readonly-banner')).toBeVisible({ timeout: 15_000 });

      await ctxB.close();
    } finally {
      if (b) await removeWorkspaceMember(b);
    }
  });

  // NOTE: There is intentionally no 409 revision-conflict test. The multitenant
  // model (server.py _handle_post_projects, "issue 021") deliberately REPLACED
  // revision-based conflict detection with owner-only write enforcement: the
  // server ignores _clientRevision and only the project owner may save (others
  // get 403). The legacy #conflict-dialog element is therefore inert. Ownership
  // safety is covered by the read-only test above (non-owners can't edit).

  test('presence: a second member opening the same project shows a presence badge', async ({ page, browser }) => {
    // Reloading to wait out the membership-visibility race (below) can take a few
    // round-trips; give this test headroom beyond the 30s default.
    test.setTimeout(75_000);

    // Unique per-run name so leftover same-named projects from earlier runs can
    // never make the Files list ambiguous.
    const projectName = `E2E Presence Bulletin ${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

    // User A creates + saves a workspace project, then reloads so restoreOnStartup
    // reopens it and registers A's presence heartbeat.
    const shellA = new AppShell(page);
    await shellA.goto();
    await shellA.expectAuthenticated();
    await shellA.switchTo('editor');
    await createAndSaveProject(page, projectName);
    await page.reload();
    await waitForAppReady(page);

    // Capture the EXACT project id A is now editing (persisted to localStorage by
    // restoreOnStartup). B must open this id, not match by name: a stray same-name
    // duplicate would be ambiguous and could miss A's heartbeat (the cause of the
    // historical flake — see ProjectsPage.loadById).
    const projectId = await page.evaluate(() => localStorage.getItem('worshipActiveProjectId'));
    expect(projectId, 'A should have an active project after restore').toBeTruthy();

    const a = JSON.parse(readFileSync('tests/e2e/.auth/core-ids.json', 'utf8')) as EphemeralIdentity;
    let b: EphemeralIdentity | null = null;
    try {
      b = await createWorkspaceMember(a.workspaceId, 'editor');

      // User B opens the same project in a second context; B polls presence on
      // open and sees A actively editing → the presence badge appears.
      const ctxB = await browser.newContext();
      const pageB = await ctxB.newPage();
      await signInAs(pageB, b.email, b.password);
      const shellB = new AppShell(pageB);

      // Membership-visibility race: B was added to A's workspace moments ago, and
      // B's server-side membership resolution can lag B's first authenticated
      // request (server returns 403 → empty project list, which the app does NOT
      // auto-retry). In real use a member is invited long before they log in, so
      // this is a test-setup race, not a product bug. Reload B until A's project
      // actually resolves into B's Files list before driving the UI.
      const loadBtn = pageB.locator(`#files-list .file-card [data-fm="load"][data-id="${projectId}"]`);
      await expect.poll(async () => {
        await shellB.switchTo('files');
        if (await loadBtn.count() === 1) return true;
        await pageB.reload();
        await waitForAppReady(pageB);
        return false;
      }, {
        message: "member B's workspace never resolved A's project (membership race?)",
        timeout: 45_000,
        intervals: [1000, 2000, 3000, 5000],
      }).toBe(true);

      await loadBtn.click();
      await shellB.switchTo('editor');

      // The presence badge lives inside the File toolbar dropdown — open it.
      await openToolbarMenu(pageB, 'file');
      await expect(pageB.locator('#presence-badge')).toBeVisible({ timeout: 15_000 });

      await ctxB.close();
    } finally {
      if (b) await removeWorkspaceMember(b);
      // Best-effort cleanup: remove A's project so the staging workspace doesn't
      // accumulate rows across runs. Failure here must not fail the test.
      try {
        await shellA.switchTo('files');
        await new ProjectsPage(page).deleteByName(projectName);
      } catch { /* non-fatal */ }
    }
  });
});
