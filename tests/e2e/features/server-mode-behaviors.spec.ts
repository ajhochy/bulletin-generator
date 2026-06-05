import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { AppShell } from '../pages/AppShell';
import { ProjectsPage } from '../pages/ProjectsPage';
import { createAndSaveProject, waitForAppReady } from '../pages/common';
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
});
