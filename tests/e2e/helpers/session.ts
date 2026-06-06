import { type Page, expect } from '@playwright/test';
import { createClient } from '@supabase/supabase-js';
import { e2eEnv } from './env';
import { waitForAppReady } from '../pages/common';

function projectRef(url: string): string {
  return new URL(url).hostname.split('.')[0];
}

/**
 * Sign a page's browser context in as the given Supabase user by injecting the
 * session into localStorage (the app login UI has no password field). Reusable
 * across contexts — used by multi-user tests to drive a second member. Leaves
 * the page on '/' authenticated and ready.
 */
export async function signInAs(page: Page, email: string, password: string): Promise<void> {
  const env = e2eEnv(['SUPABASE_URL', 'SUPABASE_ANON_KEY'] as const);
  const node = createClient(env.SUPABASE_URL, env.SUPABASE_ANON_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await node.auth.signInWithPassword({ email, password });
  if (error || !data.session) throw new Error(`signInWithPassword failed for ${email}: ${error?.message}`);
  const key = `sb-${projectRef(env.SUPABASE_URL)}-auth-token`;
  const value = JSON.stringify(data.session);

  await page.goto('/');
  await page.evaluate((a: { key: string; value: string }) => window.localStorage.setItem(a.key, a.value), { key, value });
  await page.reload();
  await expect(page.locator('#user-info')).toBeVisible({ timeout: 15_000 });
  await waitForAppReady(page);
}
