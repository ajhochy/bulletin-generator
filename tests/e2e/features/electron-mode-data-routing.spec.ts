/**
 * Issue #277-D — Electron mode data routing smoke
 *
 * Verifies that when the renderer is in "Electron mode" (window.electronAuth
 * present), data calls (projects, announcements, songs, settings, templates)
 * go directly to Supabase REST endpoints — NOT through the Python sidecar's
 * /api/* data routes.
 *
 * Mechanism
 * ---------
 * isElectronMode() in auth-ui.js returns true iff
 *   typeof window.electronAuth?.onCallback === 'function'
 *
 * We inject that shim via page.addInitScript() BEFORE any app JS runs.
 * loadAllFromServer() (api.js) then takes the Electron branch and fans out
 * calls to sdGetProjects / sdGetAnnouncements / sdGetSongs / sdGetSettings /
 * sdGetTemplates (supabase-data.js → Supabase REST) instead of
 * apiFetch('/api/projects') etc.
 *
 * auth-ui.js only REGISTERS a deep-link listener in the Electron branch;
 * client.auth.getSession() still restores the injected storageState session,
 * so the ephemeral core identity (provisioned by core-setup) works unchanged.
 *
 * Assertions
 * ----------
 * 1. At least one request to SUPABASE_URL/rest/v1/projects occurred →
 *    data came from Supabase REST.
 * 2. Zero data requests to the Python sidecar's /api/projects,
 *    /api/announcements, /api/songs, /api/settings, /api/templates.
 *    (Bootstrap and volunteer-roles are still expected on apiFetch even in
 *    Electron mode — they are excluded from the "forbidden" list.)
 *
 * Save round-trip
 * ---------------
 * Left as a manual smoke item — see comment at bottom of file. The read-path
 * assertion covers the core 277-D claim. A write assertion would require
 * inserting a real project row via supabase-js in Electron mode, which needs
 * the workspace_id from the ephemeral identity's session context; it is
 * achievable but adds retry complexity (RLS upsert requires workspace_id on
 * the row). Not shipped to avoid flakiness.
 */

import { test, expect } from '@playwright/test';
import { config as loadDotenv } from 'dotenv';
import { AppShell } from '../pages/AppShell';

loadDotenv({ path: '.env.e2e' });

const SUPABASE_URL = process.env.SUPABASE_URL ?? '';

// The sidecar data routes we must NOT see called in Electron mode.
// Bootstrap (/api/bootstrap) and volunteer-roles (/api/volunteer-roles) are
// intentionally omitted — they are still fetched via apiFetch in Electron mode.
const FORBIDDEN_API_PATHS = [
  '/api/projects',
  '/api/announcements',
  '/api/songs',
  '/api/settings',
  '/api/templates',
] as const;

test.describe('@core Electron mode data routing (issue #277-D)', () => {
  test(
    'renderer fetches data from Supabase REST, not /api/* data endpoints, when electronAuth is present',
    async ({ page }) => {
      if (!SUPABASE_URL) {
        test.fail(true, 'UNVERIFIED: SUPABASE_URL is not set — requires .env.e2e with a live Supabase project');
        return;
      }

      // ── Collect network requests ─────────────────────────────────────────
      const supabaseDataRequests: string[] = [];
      const forbiddenApiRequests: string[] = [];

      page.on('request', (req) => {
        const url = req.url();

        // Supabase REST data requests (any table under /rest/v1/)
        if (url.startsWith(SUPABASE_URL) && url.includes('/rest/v1/')) {
          supabaseDataRequests.push(url);
        }

        // Sidecar /api/* data routes we should NOT see
        for (const forbidden of FORBIDDEN_API_PATHS) {
          // Match as a path component: url ends with /api/X or /api/X?...
          // Use a simple includes check on the path portion.
          const urlObj = (() => { try { return new URL(url); } catch { return null; } })();
          if (urlObj && (urlObj.pathname === forbidden || urlObj.pathname.startsWith(forbidden + '/'))) {
            forbiddenApiRequests.push(url);
          }
        }
      });

      // ── Inject electronAuth shim BEFORE any app JS runs ──────────────────
      // This makes isElectronMode() return true in auth-ui.js, which routes
      // loadAllFromServer() to the supabase-data.js path in api.js.
      await page.addInitScript(() => {
        // Minimal stub: just needs onCallback to be a function.
        (window as unknown as { electronAuth: { onCallback: (fn: unknown) => void } }).electronAuth = {
          onCallback: (_fn: unknown) => { /* no-op: no real IPC in test */ },
        };
      });

      // ── Navigate and wait for app ready ──────────────────────────────────
      // storageState (core.json) injects the ephemeral session into localStorage;
      // the app picks it up via client.auth.getSession() in auth-ui.js.
      const shell = new AppShell(page);
      await shell.goto();
      await shell.expectAuthenticated();

      // Navigate to the Files tab so renderFilesList() + loadAllFromServer()
      // have had a chance to resolve. __BG_READY__ is set after startup
      // completes (AppShell.goto() already awaits it), but we switch tabs to
      // ensure the files list render has fired.
      await shell.switchTo('files');

      // Give any in-flight requests a moment to land.
      // (No sleep — we wait for the files list to render instead.)
      await expect(page.locator('#files-list')).toBeVisible({ timeout: 10_000 });

      // ── Assertions ───────────────────────────────────────────────────────

      // 1. At least one Supabase REST /rest/v1/projects call occurred.
      const projectsRequests = supabaseDataRequests.filter(u => u.includes('/rest/v1/projects'));
      expect(
        projectsRequests.length,
        `Expected at least 1 Supabase REST request to /rest/v1/projects, got 0.\n` +
        `All Supabase REST calls seen: ${JSON.stringify(supabaseDataRequests, null, 2)}`,
      ).toBeGreaterThan(0);

      // 2. Zero calls to the Python sidecar's /api/* data endpoints.
      expect(
        forbiddenApiRequests,
        `Expected ZERO calls to sidecar data endpoints ${FORBIDDEN_API_PATHS.join(', ')} in Electron mode.\n` +
        `Forbidden calls seen: ${JSON.stringify(forbiddenApiRequests, null, 2)}`,
      ).toHaveLength(0);
    },
  );
});

/*
 * ── Manual smoke item (save round-trip) ──────────────────────────────────────
 *
 * UNVERIFIED: POST/PATCH to SUPABASE_URL/rest/v1/projects round-trip in Electron mode.
 * Not automated here because sdSaveProject requires workspace_id in the row payload,
 * and resolving that from the ephemeral session context in-browser adds retry
 * complexity (RLS upsert failure without workspace_id). The read-path assertion
 * above already proves the core 277-D claim (Electron path is taken).
 *
 * To make this deterministic: expose workspace_id on the session object in
 * auth-ui.js (or via /api/me), then drive a Save through the UI and assert
 * a POST to SUPABASE_URL/rest/v1/projects with method POST appeared in the
 * captured request list. Clean up via supabase-admin.ts deleteProject helper.
 */
