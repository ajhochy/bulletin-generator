/**
 * supabase-data.js — Renderer-side Supabase data-access module (issue #277-C)
 *
 * Performs all project/data CRUD directly via the Supabase JS client
 * (supabase.from(...) / supabase.rpc(...)) using the signed-in user's JWT
 * so that RLS is enforced end-to-end.
 *
 * This module is a DROP-IN replacement for the apiFetch('/api/...') → Python
 * sidecar path. Call-site wiring (projects.js, announcements.js, etc.) is
 * handled in issue #277-D.
 *
 * ── Client resolution ────────────────────────────────────────────────────────
 * Each exported function accepts an optional `opts` / `client` argument for
 * testability (dependency injection). In production the client is resolved via
 * _getSupabaseClient() from auth-ui.js (available on globalThis after that
 * module loads), which creates the @supabase/supabase-js client from
 * BULLETIN_SUPABASE_CONFIG (url + anonKey).
 *
 * ── Error handling ───────────────────────────────────────────────────────────
 * Supabase returns { data, error }. Every function throws when error is truthy
 * so callers can catch uniformly.
 *
 * ── Table/column assumptions (verified against storage.py) ──────────────────
 *
 * projects:
 *   id TEXT, workspace_id uuid, owner_user_id uuid, name text,
 *   visibility text ('workspace'|'private'), state jsonb,
 *   revision int, created_at timestamptz, updated_at timestamptz,
 *   created_by_user_id uuid, updated_by_user_id uuid
 *
 * project_revisions:
 *   id uuid, project_id text, revision_number int, state jsonb,
 *   created_at timestamptz, created_by_user_id uuid, summary text,
 *   workspace_id uuid
 *
 * announcements:
 *   id uuid, workspace_id uuid, title text, body text, state jsonb,
 *   created_at timestamptz, updated_at timestamptz, created_by_user_id uuid
 *
 * songs:
 *   id uuid, workspace_id uuid, title text, data jsonb,
 *   created_at timestamptz, updated_at timestamptz
 *
 * workspace_settings:
 *   workspace_id uuid, settings jsonb
 *
 * workspace_members:
 *   workspace_id uuid, user_id uuid, role text ('owner'|'editor'|'viewer')
 *
 * workspace_presences:
 *   workspace_id uuid, user_id uuid (PK composite: workspace_id,user_id,project_id),
 *   project_id text, display_name text, last_seen_at timestamptz
 *
 * templates:
 *   id uuid, workspace_id uuid, name text, template_data jsonb, is_default bool
 *
 * ── Limitations (noted for 277-D) ────────────────────────────────────────────
 * sdRestoreProject: the Python handler uses save_project_transactional (a
 *   multi-step UPDATE+INSERT that checks client_revision for CAS semantics).
 *   The supabase-js client has no native multi-statement transaction; this
 *   implementation fetches the revision state and upserts it via sdSaveProject,
 *   which increments the revision (safe) but does NOT enforce a CAS check on
 *   the current revision. In 277-D, if conflict-free restore is required, wire
 *   through a Postgres function / Edge Function.
 *
 * sdSaveAnnouncements: the Python handler does DELETE+INSERT (full replacement).
 *   The supabase-js implementation uses upsert (additive) without a preceding
 *   delete. A full-replace via supabase-js requires two round-trips
 *   (delete then insert) or an RPC. Marked as a 277-D concern.
 */

// ---------------------------------------------------------------------------
// Internal: client resolution
// ---------------------------------------------------------------------------

/**
 * Resolve the Supabase client. Used internally when no client is injected.
 *
 * Resolution order (mirrors how auth-ui.js creates the client):
 * 1. Call _getSupabaseClient() if it is available on globalThis (auth-ui.js
 *    exports it there after it first initialises).
 * 2. Otherwise fall back to calling globalThis.supabase?.createClient with
 *    BULLETIN_SUPABASE_CONFIG — enabling pre-auth usage if needed.
 *
 * Returns null in desktop mode (BULLETIN_SUPABASE_CONFIG absent) so callers
 * can detect the no-op desktop path.
 */
function _resolveClient() {
  // Prefer the already-initialised singleton from auth-ui.js (carries the
  // user's session so all requests include the JWT).
  if (typeof globalThis._getSupabaseClient === 'function') {
    return globalThis._getSupabaseClient();
  }
  // Fallback: construct from config (e.g. early-init callers).
  const config = globalThis.BULLETIN_SUPABASE_CONFIG || {};
  const createClient =
    typeof createSupabaseClient === 'function'  // vitest shim
      ? createSupabaseClient
      : globalThis.supabase?.createClient;
  if (!config.url || !config.anonKey || typeof createClient !== 'function') {
    return null;
  }
  return createClient(config.url, config.anonKey, {
    auth: { persistSession: true, autoRefreshToken: true },
  });
}

/**
 * Throw a normalised error for a Supabase { data, error } response.
 * @param {{ data: any, error: object|null }} result
 * @param {string} [context]  - extra context for the error message
 */
function _throwIfError(result, context = '') {
  if (result && result.error) {
    const msg = result.error.message || result.error.code || 'Supabase error';
    const err = new Error(context ? `${context}: ${msg}` : msg);
    err.code = result.error.code || null;
    err.details = result.error.details || null;
    throw err;
  }
}

/**
 * Resolve the current session's workspace_id + user_id for stamping onto writes.
 *
 * Every workspace table's RLS WITH CHECK requires the row's workspace_id to pass
 * is_workspace_member() (projects additionally need owner_user_id = auth.uid();
 * workspace_presences needs user_id = auth.uid()). The renderer must therefore
 * stamp these onto every INSERT/UPSERT. workspace_id is NOT in the JWT — it is
 * surfaced onto getCurrentUser() from /api/me by auth-ui.js. Callers may also
 * pass explicit { workspaceId, userId } (those win).
 */
function _sessionContext() {
  const u = (typeof globalThis !== 'undefined' && typeof globalThis.getCurrentUser === 'function')
    ? globalThis.getCurrentUser()
    : null;
  return {
    workspaceId: (u && u.workspace_id) || null,
    userId: (u && (u.id || u.user_id)) || null,
  };
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

/**
 * List all projects visible to the current user (RLS scopes the result).
 *
 * Mirrors: GET /api/projects → storage.list_projects_for_user()
 *
 * Columns returned: id, name, owner_user_id, visibility, state, revision,
 *   created_at, updated_at, updated_by_user_id + profiles join for attribution.
 * Note: the full `state` JSONB is included (unlike the Python list path which
 * omits it for performance). In 277-D, consider a lighter select for the
 * file-picker list.
 *
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}
 */
export async function sdGetProjects({ client } = {}) {
  const sb = client || _resolveClient();
  // METADATA ONLY — the `state` JSONB embeds base64 cover/logo images (tens of
  // MB per project). The file list + the 30s hand-off poll only need metadata;
  // pulling `state` here meant re-downloading every project's images on every
  // poll (~27 MB). The full state is fetched on demand by sdGetProject(id) when
  // a project is actually opened/exported (loadProjectById / restoreOnStartup /
  // buildProjectPdfBlob already guard on `!project.state`).
  const result = await sb
    .from('projects')
    .select(
      'id, name, owner_user_id, visibility, revision, ' +
      'created_at, updated_at, created_by_user_id, updated_by_user_id',
    )
    .order('updated_at', { ascending: false });
  _throwIfError(result, 'sdGetProjects');
  return result.data;
}

/**
 * Fetch a single project by its TEXT id.
 *
 * Mirrors: GET /api/projects → storage.get_project(id)
 *
 * @param {string} id - TEXT project id (proj_<ts>_<rand>)
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object>}
 */
export async function sdGetProject(id, { client } = {}) {
  const sb = client || _resolveClient();
  const result = await sb
    .from('projects')
    .select(
      'id, name, owner_user_id, visibility, state, revision, ' +
      'created_at, updated_at, created_by_user_id, updated_by_user_id',
    )
    .eq('id', id)
    .single();
  _throwIfError(result, `sdGetProject(${id})`);
  return result.data;
}

/**
 * Upsert (insert or update) a project.
 *
 * Mirrors: POST /api/projects → storage.save_project()
 *
 * The `state` field must be the full project payload (same shape stored in
 * the JSONB column). On INSERT revision defaults to 1 via the DB default;
 * on UPDATE supabase-js does not auto-increment — pass onConflict so the
 * DB default triggers. For true revision-increment on update, use an RPC
 * (flagged for 277-D).
 *
 * Required fields: id (TEXT), name (text), state (object), workspace_id (uuid).
 * Optional: owner_user_id (uuid), visibility ('workspace'|'private').
 *
 * @param {object} project
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object>}  the saved project row
 */
export async function sdSaveProject(project, { client } = {}) {
  const sb = client || _resolveClient();
  const ctx = _sessionContext();  // RLS: is_workspace_member(workspace_id) AND owner_user_id = auth.uid()
  const payload = {
    id: project.id,
    name: project.name || '',
    state: project.state ?? project,  // full project is the state
    owner_user_id: project.owner_user_id || ctx.userId || null,
    workspace_id: project.workspace_id || ctx.workspaceId || null,
    visibility: project.visibility || 'workspace',
    updated_at: new Date().toISOString(),
  };
  const result = await sb
    .from('projects')
    .upsert(payload, { onConflict: 'id' });
  _throwIfError(result, 'sdSaveProject');
  // Return the first row of the result data (or the payload if no RETURNING)
  return (result.data && result.data[0]) || payload;
}

/**
 * Delete a project by id.
 *
 * Mirrors: DELETE /api/projects → storage.delete_project()
 *
 * @param {string} id
 * @param {{ client?: object }} [opts]
 * @returns {Promise<void>}
 */
export async function sdDeleteProject(id, { client } = {}) {
  const sb = client || _resolveClient();
  const result = await sb
    .from('projects')
    .delete()
    .eq('id', id);
  _throwIfError(result, `sdDeleteProject(${id})`);
}

/**
 * Transfer project ownership to another workspace member.
 *
 * Calls the `transfer_project_owner` RPC added in 277-B.
 * Param names: p_project_id, p_to_user_id (confirmed from the RPC spec).
 *
 * Mirrors: POST /api/projects/{id}/transfer
 *
 * @param {string} projectId
 * @param {string} toUserId
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object>}  updated project
 */
export async function sdTransferProject(projectId, toUserId, { client } = {}) {
  const sb = client || _resolveClient();
  const result = await sb.rpc('transfer_project_owner', {
    p_project_id: projectId,
    p_to_user_id: toUserId,
  });
  _throwIfError(result, `sdTransferProject(${projectId} → ${toUserId})`);
  return result.data;
}

// ---------------------------------------------------------------------------
// Project revisions
// ---------------------------------------------------------------------------

/**
 * Return revision metadata for a project, newest first.
 *
 * Mirrors: GET /api/projects/{id}/revisions → storage.get_project_revisions()
 *
 * Columns: id, project_id, revision_number, summary, created_at,
 *   created_by_user_id (+ profiles join for display_name/email handled by RLS view
 *   or manually in 277-D).
 *
 * @param {string} projectId
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}
 */
export async function sdGetProjectHistory(projectId, { client } = {}) {
  const sb = client || _resolveClient();
  const result = await sb
    .from('project_revisions')
    .select('id, project_id, revision_number, summary, created_at, created_by_user_id, state')
    .eq('project_id', projectId)
    .order('revision_number', { ascending: false });
  _throwIfError(result, `sdGetProjectHistory(${projectId})`);
  return result.data;
}

/**
 * Restore a project to a prior revision by fetching the snapshot state and
 * saving it as the new head.
 *
 * LIMITATION: The Python handler uses save_project_transactional (CAS check
 * on client_revision). This implementation does NOT enforce a CAS check —
 * it is a simple fetch-then-upsert. For transactional restore with conflict
 * detection, wire through a Postgres function in 277-D.
 *
 * Mirrors: POST /api/projects/{id}/restore
 *
 * @param {string} projectId
 * @param {number} revisionNumber
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object>}  updated project
 */
export async function sdRestoreProject(projectId, revisionNumber, { client } = {}) {
  const sb = client || _resolveClient();
  // 1. Fetch the target revision snapshot
  const revResult = await sb
    .from('project_revisions')
    .select('id, project_id, revision_number, state')
    .eq('project_id', projectId)
    .eq('revision_number', revisionNumber)
    .single();
  _throwIfError(revResult, `sdRestoreProject fetch revision(${revisionNumber})`);

  const snapshot = revResult.data;
  const state = snapshot && snapshot.state;
  if (!state || typeof state !== 'object') {
    throw new Error(`sdRestoreProject: revision ${revisionNumber} has invalid state`);
  }

  // 2. Save the snapshot state as the new head (no CAS — see limitation above)
  return sdSaveProject({ ...state, id: projectId }, { client: sb });
}

// ---------------------------------------------------------------------------
// Announcements
// ---------------------------------------------------------------------------

/**
 * List all announcements for the current workspace, ordered by created_at ASC.
 *
 * Mirrors: GET /api/announcements → storage.list_announcements()
 *
 * Columns: id, workspace_id, title, body, state, created_at, updated_at,
 *   created_by_user_id
 *
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}
 */
export async function sdGetAnnouncements({ client } = {}) {
  const sb = client || _resolveClient();
  const result = await sb
    .from('announcements')
    .select('id, workspace_id, title, body, state, created_at, updated_at, created_by_user_id')
    .order('created_at', { ascending: true });
  _throwIfError(result, 'sdGetAnnouncements');
  return result.data;
}

/**
 * Save (upsert) the announcements list.
 *
 * LIMITATION: The Python handler does DELETE + INSERT (full replacement).
 * This implementation upserts without deleting — items removed from the list
 * on the client will persist in the DB until a delete is issued explicitly.
 * For full-replace behaviour, use an RPC or two round-trips in 277-D.
 *
 * Mirrors: POST /api/announcements → storage.save_announcements()
 *
 * @param {object[]} data
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}  the upserted rows
 */
export async function sdSaveAnnouncements(data, { client, workspaceId } = {}) {
  const sb = client || _resolveClient();
  const ws = workspaceId || _sessionContext().workspaceId;  // RLS: is_workspace_member(workspace_id)
  const rows = (Array.isArray(data) ? data : []).map(item => ({
    id: item.id || undefined,
    workspace_id: item.workspace_id || ws,
    title: item.title || '',
    body: item.body || '',
    state: item,       // full item dict stored in state JSONB (mirrors Python)
  }));
  const result = await sb
    .from('announcements')
    .upsert(rows, { onConflict: 'id' });
  _throwIfError(result, 'sdSaveAnnouncements');
  return result.data || rows;
}

// ---------------------------------------------------------------------------
// Songs
// ---------------------------------------------------------------------------

/**
 * List all songs for the current workspace, ordered by title ASC.
 *
 * Mirrors: GET /api/songs (bootstrap) → storage.list_songs()
 *
 * Columns: id, workspace_id, title, data, created_at, updated_at
 *
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}
 */
export async function sdGetSongs({ client } = {}) {
  const sb = client || _resolveClient();
  const result = await sb
    .from('songs')
    .select('id, workspace_id, title, data, created_at, updated_at')
    .order('title', { ascending: true });
  _throwIfError(result, 'sdGetSongs');
  return result.data;
}

/**
 * Upsert songs (additive — never deletes existing rows).
 *
 * Mirrors: POST /api/songs → storage.save_songs()
 * (save_songs is additive: it upserts each song individually, never deletes.)
 *
 * @param {object[]} data
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}
 */
export async function sdSaveSongs(data, { client, workspaceId } = {}) {
  const sb = client || _resolveClient();
  const ws = workspaceId || _sessionContext().workspaceId;  // RLS: is_workspace_member(workspace_id)
  const rows = (Array.isArray(data) ? data : []).map(item => ({
    id: item.id || undefined,
    workspace_id: item.workspace_id || ws,
    title: item.title || '',
    data: item,  // full song dict stored in data JSONB (mirrors Python)
  }));
  const result = await sb
    .from('songs')
    .upsert(rows, { onConflict: 'id' });
  _throwIfError(result, 'sdSaveSongs');
  return result.data || rows;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

/**
 * Fetch workspace settings blob.
 *
 * Mirrors: GET /api/settings → storage.get_settings()
 *
 * Returns the raw row(s) — callers should read result[0].settings for the blob.
 * RLS scopes to the current user's workspace.
 *
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}
 */
export async function sdGetSettings({ client } = {}) {
  const sb = client || _resolveClient();
  const result = await sb
    .from('workspace_settings')
    .select('workspace_id, settings');
  _throwIfError(result, 'sdGetSettings');
  return result.data;
}

/**
 * Save the workspace settings blob.
 *
 * Mirrors: POST /api/settings → storage.save_settings()
 *
 * RLS requires the row's workspace_id matches auth.uid()'s workspace.
 * workspace_id is omitted from the payload — the DB constraint / RLS resolves it.
 * In 277-D, the workspace_id must be supplied from the session context.
 *
 * @param {object} settings  - the full settings dict
 * @param {{ client?: object, workspaceId?: string }} [opts]
 * @returns {Promise<object[]>}
 */
export async function sdSaveSettings(settings, { client, workspaceId } = {}) {
  const sb = client || _resolveClient();
  const ws = workspaceId || _sessionContext().workspaceId;  // RLS: is_workspace_member(workspace_id)
  const payload = { settings };
  if (ws) payload.workspace_id = ws;
  const result = await sb
    .from('workspace_settings')
    .upsert(payload, { onConflict: 'workspace_id' });
  _throwIfError(result, 'sdSaveSettings');
  return result.data || [payload];
}

// ---------------------------------------------------------------------------
// Workspace members
// ---------------------------------------------------------------------------

/**
 * List workspace members with profile info.
 *
 * Mirrors: GET /api/workspace/members → server._handle_get_workspace_members()
 * (uses admin_transaction in Python — RLS may limit this; confirm RLS policy
 * for workspace_members SELECT in 277-D.)
 *
 * Columns: user_id, role + profiles(display_name, email)
 *
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}
 */
export async function sdGetMembers({ client } = {}) {
  const sb = client || _resolveClient();
  const result = await sb
    .from('workspace_members')
    .select('user_id, role, profiles(display_name, email)');
  _throwIfError(result, 'sdGetMembers');
  return result.data;
}

// ---------------------------------------------------------------------------
// Presence
// ---------------------------------------------------------------------------

/**
 * Get active presence records for a project (last_seen_at within 90 seconds).
 *
 * Mirrors: GET /api/presence?project_id=X → server._handle_get_presence()
 *
 * The 90-second TTL filter is enforced server-side in the Python handler via
 * SQL (last_seen_at > now() - interval '90 seconds'). With supabase-js the
 * filter must be applied via an RPC or a computed column, or post-filtered
 * client-side. This implementation returns all presence rows for the project
 * and lets the caller filter by last_seen_at if needed. A proper TTL filter
 * via supabase-js requires .gt('last_seen_at', <iso>) or an RPC — flagged for
 * 277-D.
 *
 * @param {string} projectId
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}  [{ user_id, display_name, last_seen_at }, ...]
 */
export async function sdGetPresence(projectId, { client } = {}) {
  const sb = client || _resolveClient();
  // NOTE: workspace_presences has no display_name column (the server got it via
  // a profiles JOIN); selecting it returns 400. Select only real columns and
  // apply the 90-second TTL filter server-side (mirrors the Python handler).
  // Callers can resolve user_id → display name from the members list if needed.
  const cutoff = new Date(Date.now() - 90000).toISOString();
  const result = await sb
    .from('workspace_presences')
    .select('user_id, last_seen_at')
    .eq('project_id', projectId)
    .gt('last_seen_at', cutoff)
    .order('last_seen_at', { ascending: false });
  _throwIfError(result, `sdGetPresence(${projectId})`);
  return result.data;
}

/**
 * Upsert a presence heartbeat row for the current user + project.
 *
 * Mirrors: POST /api/presence/heartbeat
 *
 * workspace_id and user_id are omitted here — they must be supplied from
 * session context in 277-D (or included via a DB trigger / RLS default).
 *
 * @param {string} projectId
 * @param {{ client?: object, userId?: string, workspaceId?: string }} [opts]
 * @returns {Promise<void>}
 */
export async function sdPostPresenceHeartbeat(projectId, { client, userId, workspaceId } = {}) {
  const sb = client || _resolveClient();
  const ctx = _sessionContext();  // RLS: user_id = auth.uid() AND is_workspace_member(workspace_id)
  const uid = userId || ctx.userId;
  const ws = workspaceId || ctx.workspaceId;
  const payload = {
    project_id: projectId,
    last_seen_at: new Date().toISOString(),
  };
  if (uid) payload.user_id = uid;
  if (ws) payload.workspace_id = ws;
  const result = await sb
    .from('workspace_presences')
    .upsert(payload, { onConflict: 'workspace_id,user_id,project_id' });
  _throwIfError(result, `sdPostPresenceHeartbeat(${projectId})`);
}

/**
 * Delete the current user's presence rows (called on project close / sign-out).
 *
 * Mirrors: DELETE /api/presence → server._handle_delete_presence()
 *
 * @param {{ client?: object, userId?: string }} [opts]
 * @returns {Promise<void>}
 */
export async function sdDeletePresence({ client, userId } = {}) {
  const sb = client || _resolveClient();
  const uid = userId || _sessionContext().userId;
  const q = sb.from('workspace_presences').delete();
  if (uid) {
    q.eq('user_id', uid);
  }
  const result = await q;
  _throwIfError(result, 'sdDeletePresence');
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

/**
 * List all templates, ordered by is_default DESC, name ASC.
 *
 * Mirrors: GET /api/templates → storage.list_templates()
 *
 * Columns: id, name, template_data, is_default
 *
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}
 */
export async function sdGetTemplates({ client } = {}) {
  const sb = client || _resolveClient();
  const result = await sb
    .from('templates')
    .select('id, name, template_data, is_default')
    .order('is_default', { ascending: false })
    .order('name', { ascending: true });
  _throwIfError(result, 'sdGetTemplates');
  return result.data;
}

/**
 * Upsert custom templates; default/built-in templates are never modified.
 *
 * Mirrors: POST /api/templates → storage.save_templates()
 *
 * @param {object[]} data
 * @param {{ client?: object }} [opts]
 * @returns {Promise<object[]>}
 */
export async function sdSaveTemplates(data, { client, workspaceId } = {}) {
  const sb = client || _resolveClient();
  const ws = workspaceId || _sessionContext().workspaceId;  // RLS: is_workspace_member(workspace_id)
  // Filter out built-in/default templates — never overwrite them (mirrors Python)
  const custom = (Array.isArray(data) ? data : []).filter(
    t => !t.is_default && !t.built_in && !t.builtIn,
  );
  if (custom.length === 0) {
    return [];
  }
  const rows = custom.map(item => ({
    id: item.id || undefined,
    workspace_id: item.workspace_id || ws,
    name: item.name || '',
    template_data: item,
    is_default: false,
  }));
  const result = await sb
    .from('templates')
    .upsert(rows, { onConflict: 'id' });
  _throwIfError(result, 'sdSaveTemplates');
  return result.data || rows;
}

// ---------------------------------------------------------------------------
// Module export (dual pattern: ESM named exports + CommonJS for vitest)
// ---------------------------------------------------------------------------

// Named ESM exports are declared above (export function ...).
// The CommonJS path below allows vitest (which uses Node's require() path for
// non-bundled CJS interop) to import the module without a bundler.
if (typeof module !== 'undefined' && module.exports) {
  Object.assign(module.exports, {
    sdGetProjects,
    sdGetProject,
    sdSaveProject,
    sdDeleteProject,
    sdTransferProject,
    sdGetProjectHistory,
    sdRestoreProject,
    sdGetAnnouncements,
    sdSaveAnnouncements,
    sdGetSongs,
    sdSaveSongs,
    sdGetSettings,
    sdSaveSettings,
    sdGetMembers,
    sdGetPresence,
    sdPostPresenceHeartbeat,
    sdDeletePresence,
    sdGetTemplates,
    sdSaveTemplates,
  });
}
