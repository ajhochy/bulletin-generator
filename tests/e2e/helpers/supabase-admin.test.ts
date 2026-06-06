import { e2eEnv } from './env';
try { e2eEnv(['SUPABASE_SERVICE_ROLE_KEY']); } catch {}

import { describe, it, expect, afterAll } from 'vitest';
import { createEphemeralIdentity, destroyEphemeralIdentity, type EphemeralIdentity } from './supabase-admin';

// This is a LIVE integration test: it provisions and destroys a real ephemeral
// identity in the Supabase project. It is NOT part of the default `npm test`
// (which must stay hermetic). Opt in explicitly once the service_role DML grant
// migration is applied:
//   E2E_DB_INTEGRATION=1 npx vitest run tests/e2e/helpers/supabase-admin.test.ts
const RUN = process.env.E2E_DB_INTEGRATION ? describe : describe.skip;
let id: EphemeralIdentity;

RUN('ephemeral identity lifecycle', () => {
  it('creates a user + workspace + membership', async () => {
    id = await createEphemeralIdentity('lifecycle');
    expect(id.userId).toMatch(/^[0-9a-f-]{36}$/);
    expect(id.workspaceId).toMatch(/^[0-9a-f-]{36}$/);
    expect(id.email).toContain('@');
    expect(id.password.length).toBeGreaterThan(12);
  });
  afterAll(async () => { if (id) await destroyEphemeralIdentity(id); });
});
