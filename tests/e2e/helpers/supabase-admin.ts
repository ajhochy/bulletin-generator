import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { randomUUID } from 'node:crypto';
import { e2eEnv } from './env';

export interface EphemeralIdentity {
  userId: string;
  workspaceId: string;
  email: string;
  password: string;
}

function admin(): SupabaseClient {
  const env = e2eEnv(['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'] as const);
  return createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}

/** Create an isolated user + workspace + owner membership. RLS-bypassing (service_role). */
export async function createEphemeralIdentity(label: string): Promise<EphemeralIdentity> {
  const sb = admin();
  const tag = randomUUID().slice(0, 8);
  const email = `e2e-${label}-${tag}@e2e.bulletin.test`;
  const password = `E2e-${randomUUID()}`;

  const { data: created, error: userErr } = await sb.auth.admin.createUser({
    email, password, email_confirm: true,
  });
  if (userErr || !created.user) throw new Error(`createUser failed: ${userErr?.message}`);
  const userId = created.user.id;

  await sb.from('profiles').upsert({ id: userId, email }, { onConflict: 'id' });

  const { data: ws, error: wsErr } = await sb
    .from('workspaces')
    .insert({ name: `E2E ${tag}`, slug: `e2e-${tag}`, created_by_user_id: userId })
    .select('id')
    .single();
  if (wsErr || !ws) throw new Error(`workspace insert failed: ${wsErr?.message}`);
  const workspaceId = ws.id as string;

  const { error: memErr } = await sb
    .from('workspace_members')
    .insert({ workspace_id: workspaceId, user_id: userId, role: 'owner' });
  if (memErr) throw new Error(`membership insert failed: ${memErr.message}`);

  return { userId, workspaceId, email, password };
}

export async function destroyEphemeralIdentity(id: EphemeralIdentity): Promise<void> {
  const sb = admin();
  await sb.from('projects').delete().eq('workspace_id', id.workspaceId);
  await sb.from('workspace_members').delete().eq('workspace_id', id.workspaceId);
  await sb.from('workspaces').delete().eq('id', id.workspaceId);
  await sb.auth.admin.deleteUser(id.userId);
}

/**
 * Safety net for the single-live-project model: delete any `e2e-`-prefixed
 * leftovers a prior failed teardown left behind. ONLY touches `e2e-` rows.
 */
export async function sweepStaleEphemeralIdentities(): Promise<void> {
  const sb = admin();
  const { data: stale } = await sb.from('workspaces').select('id').like('slug', 'e2e-%');
  for (const ws of stale ?? []) {
    await sb.from('projects').delete().eq('workspace_id', ws.id);
    await sb.from('workspace_members').delete().eq('workspace_id', ws.id);
    await sb.from('workspaces').delete().eq('id', ws.id);
  }
  const { data: list } = await sb.auth.admin.listUsers({ perPage: 1000 });
  for (const u of list?.users ?? []) {
    if (u.email?.startsWith('e2e-')) await sb.auth.admin.deleteUser(u.id);
  }
}
