import { test as setup, expect, type Page } from '@playwright/test';
import { createClient } from '@supabase/supabase-js';
import { writeFileSync, mkdirSync } from 'node:fs';
import { e2eEnv } from './env';
import {
  createEphemeralIdentity,
  sweepStaleEphemeralIdentities,
  ensureLiveWorkspaceMember,
} from './supabase-admin';

const AUTH_DIR = 'tests/e2e/.auth';
const CORE_STATE = `${AUTH_DIR}/core.json`;
const LIVE_STATE = `${AUTH_DIR}/live.json`;
const CORE_IDS = `${AUTH_DIR}/core-ids.json`;

/** The Supabase project ref is the first hostname label of SUPABASE_URL. */
function projectRef(url: string): string {
  return new URL(url).hostname.split('.')[0];
}

/**
 * The app's login UI offers no password field (Google / magic-link only), so we
 * sign in programmatically with the password we control, then inject the
 * resulting session into the page's localStorage under the supabase-js v2 key
 * (`sb-<ref>-auth-token`). On reload the app's supabase client picks it up. The
 * `#user-info` assertion is a self-check: if the injected session shape is ever
 * wrong, setup fails loudly here instead of producing a silently-unauthed state.
 */
async function signInAndSave(page: Page, email: string, password: string, statePath: string): Promise<void> {
  const env = e2eEnv(['SUPABASE_URL', 'SUPABASE_ANON_KEY'] as const);
  const node = createClient(env.SUPABASE_URL, env.SUPABASE_ANON_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await node.auth.signInWithPassword({ email, password });
  if (error || !data.session) {
    throw new Error(`signInWithPassword failed for ${email}: ${error?.message}`);
  }
  const storageKey = `sb-${projectRef(env.SUPABASE_URL)}-auth-token`;
  const sessionJson = JSON.stringify(data.session);

  await page.goto('/');
  await page.evaluate(
    (args: { key: string; value: string }) => window.localStorage.setItem(args.key, args.value),
    { key: storageKey, value: sessionJson },
  );
  await page.reload();
  await expect(page.locator('#user-info')).toBeVisible({ timeout: 15_000 });

  mkdirSync(AUTH_DIR, { recursive: true });
  await page.context().storageState({ path: statePath });
}

setup('@core-setup provision ephemeral identity', async ({ page }) => {
  await sweepStaleEphemeralIdentities(); // remove any leftovers from a prior failed run
  const id = await createEphemeralIdentity('core');
  mkdirSync(AUTH_DIR, { recursive: true });
  writeFileSync(CORE_IDS, JSON.stringify(id));
  await signInAndSave(page, id.email, id.password, CORE_STATE);
});

setup('@live-setup ensure e2e-live member + sign in', async ({ page }) => {
  const env = e2eEnv(['E2E_LIVE_EMAIL', 'E2E_LIVE_PASSWORD'] as const);
  // worship@'s workspace holds the already-connected PCO/Google tokens.
  await ensureLiveWorkspaceMember({
    liveEmail: env.E2E_LIVE_EMAIL,
    livePassword: env.E2E_LIVE_PASSWORD,
    ownerEmail: 'worship@visaliacrc.com',
  });
  await signInAndSave(page, env.E2E_LIVE_EMAIL, env.E2E_LIVE_PASSWORD, LIVE_STATE);
});
