import { createClient, type SupabaseClient, type User } from '@supabase/supabase-js';
import { randomUUID } from 'node:crypto';
import { e2eEnv } from './env';

/** List ALL auth users (paginates past the 1000/page cap). */
async function listAllUsers(sb: SupabaseClient): Promise<User[]> {
  const all: User[] = [];
  let page = 1;
  for (;;) {
    const { data } = await sb.auth.admin.listUsers({ page, perPage: 1000 });
    const users = data?.users ?? [];
    if (!users.length) break;
    all.push(...users);
    const nextPage = (data as { nextPage?: number }).nextPage;
    if (!nextPage) break;
    page = nextPage;
  }
  return all;
}

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
  // `e2e-eph-` prefix marks DISPOSABLE identities the sweep may delete. The
  // persistent live user (`e2e-live@`) deliberately does NOT match this prefix.
  const email = `e2e-eph-${label}-${tag}@e2e.bulletin.test`;
  const password = `E2e-${randomUUID()}`;

  const { data: created, error: userErr } = await sb.auth.admin.createUser({
    email, password, email_confirm: true,
  });
  if (userErr || !created.user) throw new Error(`createUser failed: ${userErr?.message}`);
  const userId = created.user.id;

  await sb.from('profiles').upsert({ id: userId, email }, { onConflict: 'id' });

  const { data: ws, error: wsErr } = await sb
    .from('workspaces')
    .insert({ name: `E2E-EPH ${tag}`, slug: `e2e-eph-${tag}`, created_by_user_id: userId })
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
  // Defense in depth: never delete anything that isn't a disposable identity,
  // even if core-ids.json is stale/corrupted.
  if (!id.email?.startsWith('e2e-eph-') || !id.workspaceId || !id.userId) {
    throw new Error(`refusing to destroy non-ephemeral identity: ${JSON.stringify(id)}`);
  }
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
  // Only `e2e-eph-` (disposable) rows — never the persistent `e2e-live` member.
  const { data: stale } = await sb.from('workspaces').select('id').like('slug', 'e2e-eph-%');
  for (const ws of stale ?? []) {
    await sb.from('projects').delete().eq('workspace_id', ws.id);
    await sb.from('workspace_members').delete().eq('workspace_id', ws.id);
    await sb.from('workspaces').delete().eq('id', ws.id);
  }
  for (const u of await listAllUsers(sb)) {
    if (u.email?.startsWith('e2e-eph-')) await sb.auth.admin.deleteUser(u.id);
  }
}

/**
 * Create a disposable extra member in an EXISTING workspace (for multi-user
 * tests like read-only / conflict). Does NOT create a workspace. Clean up with
 * removeWorkspaceMember — NOT destroyEphemeralIdentity (which deletes the shared
 * workspace). Email is `e2e-eph-` prefixed so the sweep also catches it.
 */
export async function createWorkspaceMember(
  workspaceId: string,
  role: 'viewer' | 'editor' | 'owner',
): Promise<EphemeralIdentity> {
  const sb = admin();
  const tag = randomUUID().slice(0, 8);
  const email = `e2e-eph-member-${tag}@e2e.bulletin.test`;
  const password = `E2e-${randomUUID()}`;
  const { data: created, error } = await sb.auth.admin.createUser({ email, password, email_confirm: true });
  if (error || !created.user) throw new Error(`createUser failed: ${error?.message}`);
  const userId = created.user.id;
  await sb.from('profiles').upsert({ id: userId, email }, { onConflict: 'id' });
  const { error: memErr } = await sb
    .from('workspace_members')
    .upsert({ workspace_id: workspaceId, user_id: userId, role }, { onConflict: 'workspace_id,user_id' });
  if (memErr) throw new Error(`member upsert failed: ${memErr.message}`);
  return { userId, workspaceId, email, password };
}

/** Remove an extra member created by createWorkspaceMember (membership + auth user only). */
export async function removeWorkspaceMember(id: EphemeralIdentity): Promise<void> {
  if (!id.email?.startsWith('e2e-eph-')) {
    throw new Error(`refusing to remove non-ephemeral user: ${id.email}`);
  }
  const sb = admin();
  await sb.from('workspace_members').delete().eq('workspace_id', id.workspaceId).eq('user_id', id.userId);
  await sb.auth.admin.deleteUser(id.userId);
}

/**
 * Ensure a PERSISTENT `e2e-live` user exists and is a member of the owner's
 * (worship@'s) workspace, so the live lane inherits that workspace's already-
 * connected PCO/Google tokens (tokens are stored per-workspace). Idempotent.
 * Does NOT touch the owner account. Returns the resolved workspace id.
 */
export async function ensureLiveWorkspaceMember(opts: {
  liveEmail: string;
  livePassword: string;
  ownerEmail: string;
}): Promise<{ workspaceId: string; liveUserId: string }> {
  const sb = admin();

  // 1. Resolve the owner's workspace via profiles -> workspace_members.
  const { data: ownerProfile, error: pErr } = await sb
    .from('profiles').select('id').eq('email', opts.ownerEmail).single();
  if (pErr || !ownerProfile) {
    throw new Error(`owner profile not found for ${opts.ownerEmail}: ${pErr?.message}`);
  }
  const { data: mem, error: mErr } = await sb
    .from('workspace_members').select('workspace_id').eq('user_id', ownerProfile.id).limit(1).single();
  if (mErr || !mem) {
    throw new Error(`no workspace membership for ${opts.ownerEmail}: ${mErr?.message}`);
  }
  const workspaceId = mem.workspace_id as string;

  // 2. Ensure the persistent e2e-live user exists with the known password.
  let liveUser = (await listAllUsers(sb)).find((u) => u.email === opts.liveEmail) ?? null;
  if (!liveUser) {
    const { data: created, error: cErr } = await sb.auth.admin.createUser({
      email: opts.liveEmail, password: opts.livePassword, email_confirm: true,
    });
    if (cErr || !created.user) throw new Error(`create e2e-live user failed: ${cErr?.message}`);
    liveUser = created.user;
  } else {
    await sb.auth.admin.updateUserById(liveUser.id, { password: opts.livePassword });
  }
  await sb.from('profiles').upsert({ id: liveUser.id, email: opts.liveEmail }, { onConflict: 'id' });

  // 3. Ensure viewer membership in the owner's workspace (read-only).
  const { error: upErr } = await sb
    .from('workspace_members')
    .upsert({ workspace_id: workspaceId, user_id: liveUser.id, role: 'viewer' }, { onConflict: 'workspace_id,user_id' });
  if (upErr) throw new Error(`live membership upsert failed: ${upErr.message}`);

  return { workspaceId, liveUserId: liveUser.id };
}
