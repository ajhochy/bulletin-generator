import { test as teardown } from '@playwright/test';
import { readFileSync, existsSync, rmSync } from 'node:fs';
import { destroyEphemeralIdentity, type EphemeralIdentity } from './supabase-admin';

const CORE_IDS = 'tests/e2e/.auth/core-ids.json';

teardown('destroy ephemeral identity', async () => {
  if (!existsSync(CORE_IDS)) return;
  const id = JSON.parse(readFileSync(CORE_IDS, 'utf8')) as EphemeralIdentity;
  await destroyEphemeralIdentity(id);
  rmSync(CORE_IDS, { force: true });
});
