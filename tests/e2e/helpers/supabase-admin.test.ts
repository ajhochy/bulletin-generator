import { e2eEnv } from './env';
try { e2eEnv(['SUPABASE_SERVICE_ROLE_KEY']); } catch {}

import { describe, it, expect, afterAll } from 'vitest';
import { createEphemeralIdentity, destroyEphemeralIdentity, type EphemeralIdentity } from './supabase-admin';

const RUN = process.env.SUPABASE_SERVICE_ROLE_KEY ? describe : describe.skip;
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
