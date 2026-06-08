/**
 * @file multitenant-isolation.spec.ts
 * @core
 *
 * Issue #272 M5 multi-tenant QA matrix — automated e2e coverage.
 *
 * Covers:
 *   1. Cross-tenant isolation  — a user in workspace B cannot see workspace A's
 *      projects in the Files list or read them via the API.
 *   2. Ownership + hand-off    — owner A1 creates a workspace-visible project;
 *      member A2 sees it read-only and can duplicate; non-owner save → 403;
 *      transfer makes A2 the owner and A1 read-only.
 *   3. Revision history        — A1 saves 3 edits; GET /api/projects/{id}/history
 *      returns ≥ 3 revisions; restore to revision 1 returns 200 with project state.
 *
 * Presence (badge) coverage lives in server-mode-behaviors.spec.ts and is
 * confirmed there.  This file does not re-test it.
 *
 * Design notes:
 * - All helper calls that touch Supabase admin API use the existing
 *   createEphemeralIdentity / createWorkspaceMember / removeWorkspaceMember /
 *   destroyEphemeralIdentity utilities from supabase-admin.ts.
 * - The "membership-visibility race" (issue #288) is handled via expect.poll
 *   with reload — identical to the pattern in server-mode-behaviors.spec.ts.
 * - Auth for direct API calls is obtained by calling window.apiFetch inside
 *   page.evaluate() so that the Supabase session token is automatically
 *   attached (same as every other API call the app makes).
 * - All test data (projects, users) is destroyed in afterEach / finally blocks.
 */

import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { AppShell } from '../pages/AppShell';
import { ProjectsPage } from '../pages/ProjectsPage';
import { createAndSaveProject, waitForAppReady } from '../pages/common';
import { signInAs } from '../helpers/session';
import {
  createEphemeralIdentity,
  createWorkspaceMember,
  removeWorkspaceMember,
  destroyEphemeralIdentity,
  type EphemeralIdentity,
} from '../helpers/supabase-admin';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Read the core ephemeral identity written by auth.setup.ts */
function readCoreIds(): EphemeralIdentity {
  return JSON.parse(readFileSync('tests/e2e/.auth/core-ids.json', 'utf8')) as EphemeralIdentity;
}

/**
 * Make an authenticated API call via Playwright's Node-side request context.
 * The Bearer token is extracted from localStorage (where supabase-js stores the
 * session) and attached as an Authorization header.  baseURL is taken from the
 * page's URL so the call lands on the same server the test is driving.
 *
 * This avoids page.evaluate for the HTTP calls, eliminating any risk of the
 * fetch hanging inside the browser JS context.
 */
async function pageApiFetch(
  page: import('@playwright/test').Page,
  path: string,
  method: string = 'GET',
  body: unknown = null,
): Promise<{ status: number; body: unknown }> {
  // Extract the access_token from supabase-js's localStorage key.
  const session = await page.evaluate(() => {
    // supabase-js v2 stores the session under sb-<ref>-auth-token.
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith('sb-') && key.endsWith('-auth-token')) {
        try {
          const parsed = JSON.parse(localStorage.getItem(key) ?? '{}');
          return parsed as { access_token?: string };
        } catch { /* ignore */ }
      }
    }
    return null;
  });

  const origin = new URL(page.url()).origin;
  const headers: Record<string, string> = {};
  if (session?.access_token) {
    headers['Authorization'] = `Bearer ${session.access_token}`;
  }
  if (body !== null) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await page.request.fetch(`${origin}${path}`, {
    method,
    headers,
    data: body !== null ? JSON.stringify(body) : undefined,
    timeout: 15_000,
    failOnStatusCode: false,
  });

  let json: unknown = null;
  try { json = await res.json(); } catch { /* no body or non-JSON */ }
  return { status: res.status(), body: json };
}

// ---------------------------------------------------------------------------
// 1. Cross-tenant isolation
// ---------------------------------------------------------------------------

test.describe('@core Cross-tenant isolation (e2e)', () => {
  /**
   * A user in workspace B must NOT see workspace A's projects in the Files list.
   * The security guarantee is enforced at the DB/RLS layer (pytest suite); this
   * test confirms the server-mode API + UI surface respects the isolation too.
   */
  test('workspace-B user cannot see workspace-A projects in Files list', async ({
    page,
    browser,
  }) => {
    test.setTimeout(90_000);

    const uniqueTag = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    const projectName = `E2E CrossTenant A ${uniqueTag}`;

    // ── Workspace A: create a project as the core ephemeral owner ──
    const shellA = new AppShell(page);
    await shellA.goto();
    await shellA.expectAuthenticated();
    await shellA.switchTo('editor');
    await createAndSaveProject(page, projectName);

    // ── Workspace B: create a completely separate tenant ──
    let identityB: EphemeralIdentity | null = null;
    try {
      identityB = await createEphemeralIdentity('cross-b');

      // Sign in as B in a fresh browser context.
      const ctxB = await browser.newContext();
      const pageB = await ctxB.newPage();
      await signInAs(pageB, identityB.email, identityB.password);

      const shellB = new AppShell(pageB);
      await shellB.switchTo('files');

      // B should have NO projects (fresh tenant) and must NOT see A's project.
      const projectsB = new ProjectsPage(pageB);
      await expect(projectsB.cards()).toHaveCount(0, { timeout: 10_000 });
      await expect(pageB.locator('#files-list')).not.toContainText(projectName);

      // Also confirm the API returns an empty list for B, not A's projects.
      const apiResult = await pageApiFetch(pageB, '/api/projects');
      expect(apiResult.status).toBe(200);
      const projects = (apiResult.body as { projects?: { name?: string }[] }).projects ?? [];
      const leakedName = projects.find((p) => p.name === projectName);
      expect(leakedName, `workspace B API must not return workspace A project "${projectName}"`).toBeUndefined();

      await ctxB.close();
    } finally {
      if (identityB) await destroyEphemeralIdentity(identityB);
      // Clean up A's project.
      try {
        await shellA.switchTo('files');
        await new ProjectsPage(page).deleteByName(projectName);
      } catch { /* non-fatal */ }
    }
  });
});

// ---------------------------------------------------------------------------
// 2. Ownership + hand-off
// ---------------------------------------------------------------------------

test.describe('@core Ownership model and transfer (e2e)', () => {
  test('non-owner A2 sees read-only banner; duplicate makes own copy; transfer makes A2 owner', async ({
    page,
    browser,
  }) => {
    test.setTimeout(120_000);

    const uniqueTag = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    const projectName = `E2E Ownership ${uniqueTag}`;

    // ── A1: create a workspace-visible project ──
    const a = readCoreIds();
    const shellA1 = new AppShell(page);
    await shellA1.goto();
    await shellA1.expectAuthenticated();
    await shellA1.switchTo('editor');
    await createAndSaveProject(page, projectName);

    // Capture the project id A1 is editing.
    const projectId = await page.evaluate(() => localStorage.getItem('worshipActiveProjectId'));
    expect(projectId, 'A1 should have an active project after save').toBeTruthy();

    // ── Add A2 as a second workspace member ──
    let a2: EphemeralIdentity | null = null;
    let duplicateProjectName: string | null = null;
    let a2ProjectId: string | null = null;
    try {
      a2 = await createWorkspaceMember(a.workspaceId, 'editor');

      // ── A2 signs in ──
      const ctxA2 = await browser.newContext();
      const pageA2 = await ctxA2.newPage();
      await signInAs(pageA2, a2.email, a2.password);
      const shellA2 = new AppShell(pageA2);

      // Wait out the membership-visibility race (issue #288).
      const loadBtn = pageA2.locator(`#files-list .file-card [data-fm="load"][data-id="${projectId}"]`);
      await expect.poll(async () => {
        await shellA2.switchTo('files');
        if (await loadBtn.count() === 1) return true;
        await pageA2.reload();
        await waitForAppReady(pageA2);
        return false;
      }, {
        message: "A2's workspace never resolved A1's project (membership race?)",
        timeout: 45_000,
        intervals: [1000, 2000, 3000, 5000],
      }).toBe(true);

      // Load the project as A2.
      await loadBtn.click();
      await shellA2.switchTo('editor');

      // READ-ONLY: A2 sees the read-only banner (non-owner).
      await expect(pageA2.locator('#readonly-banner')).toBeVisible({ timeout: 15_000 });
      await expect(pageA2.locator('#readonly-banner')).toContainText("changes won't save");

      // NON-OWNER SAVE → 403: A2 tries to save via the API; must get 403.
      // We call the API directly (not via the UI) since the UI suppresses saves
      // in read-only mode — the API-level enforcement is what the test validates.
      const saveAttempt = await pageApiFetch(pageA2, '/api/projects', 'POST', {
        id: projectId,
        name: projectName,
        state: {},
      });
      expect(saveAttempt.status, 'non-owner POST /api/projects must return 403').toBe(403);

      // DUPLICATE: A2 clicks the Duplicate button to make their own copy.
      const dupBtn = pageA2.locator('#readonly-duplicate-btn');
      await expect(dupBtn).toBeVisible({ timeout: 10_000 });

      // Intercept the POST so we can grab the duplicate's project id.
      const dupResponse = pageA2.waitForResponse(
        (r) => r.url().includes('/api/projects') && r.request().method() === 'POST' && r.ok(),
        { timeout: 15_000 },
      );
      await dupBtn.click();
      await dupResponse;

      // After duplicate, A2 should no longer see the read-only banner.
      await expect(pageA2.locator('#readonly-banner')).toBeHidden({ timeout: 10_000 });

      // Capture A2's new duplicate project id.
      a2ProjectId = await pageA2.evaluate(() => localStorage.getItem('worshipActiveProjectId'));
      duplicateProjectName = await pageA2.evaluate(
        () => (document.querySelector('#bulletin-title') as HTMLInputElement | null)?.value ?? null,
      );
      expect(a2ProjectId).not.toBe(projectId); // must be a new project

      // ── TRANSFER: A1 transfers ownership to A2 ──
      // Call transfer API as A1 (page = A1's context).
      const transferResult = await pageApiFetch(
        page,
        `/api/projects/${projectId}/transfer`,
        'POST',
        { to_user_id: a2.userId },
      );
      expect(transferResult.status, 'transfer must return 200').toBe(200);
      expect((transferResult.body as { ok?: boolean }).ok).toBe(true);
      expect((transferResult.body as { new_owner?: string }).new_owner).toBe(a2.userId);

      // POST-TRANSFER: A1 (original owner) should now get 403 on save.
      const a1SaveAfterTransfer = await pageApiFetch(page, '/api/projects', 'POST', {
        id: projectId,
        name: projectName,
        state: {},
      });
      expect(
        a1SaveAfterTransfer.status,
        'original owner should get 403 after transfer',
      ).toBe(403);

      // POST-TRANSFER: A2 (new owner) can now save successfully.
      const a2SaveAfterTransfer = await pageApiFetch(pageA2, '/api/projects', 'POST', {
        id: projectId,
        name: projectName,
        state: {},
      });
      expect(
        a2SaveAfterTransfer.status,
        'new owner (A2) should be able to save after transfer',
      ).toBe(200);

      await ctxA2.close();
    } finally {
      if (a2) await removeWorkspaceMember(a2);
      // Clean up projects.
      try {
        await shellA1.switchTo('files');
        const pp = new ProjectsPage(page);
        await pp.deleteByName(projectName);
        if (duplicateProjectName) {
          try { await pp.deleteByName(duplicateProjectName); } catch { /* non-fatal */ }
        }
      } catch { /* non-fatal */ }
    }
  });
});

// ---------------------------------------------------------------------------
// 3. Revision history
// ---------------------------------------------------------------------------

test.describe('@core Revision history (e2e)', () => {
  /**
   * After N saves, GET /api/projects/{id}/history returns N revisions.
   * POST /api/projects/{id}/restore with revision=1 returns 200 + project body.
   *
   * Note: save_project snapshots on every save (#216), so each POST to
   * /api/projects creates a new project_revisions row in the live DB.
   *
   * We make the extra saves via pageApiFetch (direct API calls from page context)
   * rather than through the editor UI to avoid toolbar-open-state races between
   * sequential opens of the same <details> element.
   */
  test('3 saves produce ≥3 history entries; restore to revision 1 returns 200', async ({
    page,
  }) => {
    test.setTimeout(90_000);

    const uniqueTag = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    const projectName = `E2E Revisions ${uniqueTag}`;

    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    await shell.switchTo('editor');

    // Save #1 — creates the project and its first revision via the standard UI path.
    await createAndSaveProject(page, projectName);
    const projectId = await page.evaluate(() => localStorage.getItem('worshipActiveProjectId'));
    expect(projectId, 'project must have been persisted').toBeTruthy();

    // Save #2 and #3 — direct API calls so we bypass toolbar-state races.
    // We POST the same project id with updated names; the server snapshots each save.
    for (const suffix of [' v2', ' v3']) {
      const saveResult = await pageApiFetch(page, '/api/projects', 'POST', {
        id: projectId,
        name: `${projectName}${suffix}`,
        state: {},
      });
      expect(saveResult.status, `save ${suffix} must return 200`).toBe(200);
    }

    try {
      // ── GET /api/projects/{id}/history ──
      const historyResult = await pageApiFetch(page, `/api/projects/${projectId}/history`);
      expect(historyResult.status, 'history endpoint must return 200').toBe(200);

      const revisions = (historyResult.body as { revisions?: { revision: number }[] }).revisions ?? [];
      expect(
        revisions.length,
        `expected ≥3 revisions after 3 saves, got ${revisions.length}`,
      ).toBeGreaterThanOrEqual(3);

      // ── POST /api/projects/{id}/restore with earliest revision ──
      const earliestRevision = revisions.reduce(
        (min, r) => (r.revision < min ? r.revision : min),
        revisions[0].revision,
      );

      const currentRevision = revisions.reduce(
        (max, r) => (r.revision > max ? r.revision : max),
        revisions[0].revision,
      );

      const restoreResult = await pageApiFetch(
        page,
        `/api/projects/${projectId}/restore`,
        'POST',
        { revision: earliestRevision, _clientRevision: currentRevision },
      );
      expect(restoreResult.status, 'restore must return 200').toBe(200);
      expect((restoreResult.body as { ok?: boolean }).ok).toBe(true);
      // The restored project is the new head — verify a project object came back.
      expect(
        typeof (restoreResult.body as { project?: object }).project,
        'restore response must include a project object',
      ).toBe('object');
    } finally {
      // Clean up via the API (no UI navigation needed — avoids deleteByName
      // hanging on non-existent card locators in Playwright's default timeout).
      if (projectId) {
        try {
          await pageApiFetch(page, `/api/projects/${projectId}`, 'DELETE');
        } catch { /* non-fatal */ }
      }
    }
  });
});
