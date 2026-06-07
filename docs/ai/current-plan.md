# Current Plan

_Last updated: 2026-06-06_

---

## Issue #277 — Desktop security: stop bundling DATABASE_URL — route data through anon key + RLS

_Plan written 2026-06-06. Supersedes the "ownership model" plan below for active work._

### Clarification interview

Skipped formal interview. The issue provides explicit acceptance criteria, names the preferred approach (S2 over S1), specifies which variables must be absent (DATABASE_URL, service-role/JWT secrets), and states the done-definition (packaged build contains only SUPABASE_URL + publishable key). The only substantive ambiguity — whether server (Docker) mode is also in scope or desktop-only — is answered by the issue text ("route data through anon key + RLS" implies the sidecar's data path, not the browser path which already uses supabase-js via anon key). Resolved in the intent pass below.

---

### Intent + Constraints Pass

**Goal (one sentence):** Remove DATABASE_URL from the Electron desktop build by migrating the data operations currently served by the Python sidecar (psycopg + DATABASE_URL) to the browser renderer using supabase-js + the anon/publishable key + RLS.

**In scope:**
- Migrating all Postgres data reads/writes currently going through server.py/storage.py/psycopg to supabase-js calls in the browser renderer (for the Electron path only, or uniformly if the architecture permits).
- Writing RLS policies for any operation that does not yet have a safe anon-key path.
- Removing DATABASE_URL from `release-electron.yml`'s `.env` step.
- Adding a new migration for any `workspace_settings` anon-key write path (the OAuth callback write is the known gap).
- Negative-path RLS tests: a user cannot read or write another workspace's rows.

**Not in scope:**
- Changing the Docker/server-mode data path (Docker mode can keep psycopg + DATABASE_URL; issue is desktop-only).
- Rewriting the PCO proxy, Google Calendar fetch, or PDF generation — those stay in the sidecar.
- Removing `psycopg` from `requirements.txt` — server mode still needs it.
- Any UI change beyond the minimum needed for the new call sites.
- Supabase Realtime / WebSockets.

**Hard constraints:**
- AGENTS.md: atomic writes; migrations idempotent + additive; never delete user data.
- The packaged DMG must launch without DATABASE_URL or any owner-role credential.
- Desktop (Electron) and server (Docker) must continue to work side-by-side — server mode keeps psycopg.
- No service-role key in the distributed binary (already stated in release-electron.yml comments).
- RLS must be the real security boundary; sidecar Python guards are defence-in-depth only.
- Tests must keep passing: pytest, vitest, vite build.

**Design tensions:**
- **Full renderer-side S2 vs. hybrid S2:** A pure S2 moves all CRUD to the renderer. A hybrid keeps a few sidecar-mediated ops (e.g. transfer_project_owner, which uses admin_transaction because the WITH CHECK on the new owner_user_id fails under the caller's JWT). The hybrid is safer as a first pass.
- **Desktop-only vs. both modes:** Migrating all modes at once reduces code duplication but risks regressing Docker. Migrating desktop-only requires a `IS_ELECTRON` branch in JS, adding complexity. Recommendation: implement the supabase-js data layer uniformly (it works for both modes) but keep the sidecar routing as a fallback; only remove DATABASE_URL from the Electron build.
- **Anon key for workspace_settings writes:** The OAuth callback currently writes tokens via admin_transaction/owner-role (no user JWT). Moving this to RLS requires the callback to pass a Supabase access token (already being done for the CONNECT path as of the 2026-06-05 decision). The RLS for workspace_settings (any workspace member can insert/update) already permits this — no new policy needed, only wiring.

**Cheapest path that proves the idea:**
1. Write a `supabase-data.js` module that implements `getProjects()`, `saveProject()`, `getAnnouncements()`, `saveAnnouncements()`, `getSongs()`, `saveSongs()`, `getSettings()`, `saveSettings()` using `supabase.from(...)`.
2. In `IS_ELECTRON` mode (detectable at the JS level since `window.electronAPI` is present), use `supabase-data.js` for all data ops instead of `apiFetch`.
3. Verify: packaged build starts, projects load, save round-trips, PDF exports.
4. If that works, remove DATABASE_URL from the `.env` step in `release-electron.yml`.

---

### Evidence-Based S1 vs S2 Analysis

#### What every server.py data endpoint does and where the psycopg call lives

| Endpoint | Handler | psycopg path | Client call site | RLS path exists? |
|---|---|---|---|---|
| GET /api/projects | `_handle_get_projects` | `store.list_projects_for_user()` → `_transaction(claims)` | `api.js:loadAllFromServer`, `projects.js:694` | YES — `projects_select` policy; scoped to workspace + visibility |
| GET /api/projects/{id} | `_handle_get_single_project` | `store.get_project()` → `_transaction(claims)` | `projects.js:498, 626` | YES — same select policy |
| POST /api/projects | `_handle_post_projects` | `store.save_project()` → `_transaction(claims)` | `projects.js:251` | YES — `projects_insert` + `projects_update` policies; owner-only update |
| DELETE /api/projects/{id} | `_handle_delete_project` | `store.delete_project()` → `_transaction(claims)` | `projects.js:271` | YES — `projects_delete` policy; owner-only |
| POST /api/projects/{id}/transfer | `_handle_post_transfer_project` | `store.transfer_project_owner()` → **`admin_transaction()`** | `projects.js:1210` | **PARTIAL GAP** — `admin_transaction` bypasses RLS; see risk below |
| GET /api/projects/{id}/history | `_handle_project_history` | `store.get_project_revisions()` → `_transaction(claims)` | (revision history UI) | YES — `project_revisions_select` policy |
| GET /api/projects/{id}/revision | `_handle_project_revision` | `store.get_project_revision()` → `_transaction(claims)` | (not actively called by frontend in current code) | YES |
| POST /api/projects/{id}/restore | `_handle_project_restore` | `store.save_project_transactional()` → `_transaction(claims)` | (revision restore UI) | YES — update policy + insert policy for revision |
| GET /api/announcements | `_handle_get_announcements` | `store.list_announcements()` → `_transaction(claims)` | `api.js:45` | YES — `announcements_select` |
| POST /api/announcements | `_handle_post_announcements` | `store.save_announcements()` → `_transaction(claims)` | `announcements.js:140` | YES — `announcements_insert`+`update` |
| GET /api/songs (via bootstrap) | `_handle_bootstrap` | `store.list_songs()` → `_transaction(claims)` | `api.js:44` | YES — `songs_select` |
| POST /api/songs | `_handle_post_songs` | `store.save_songs()` → `_transaction(claims)` | `songs.js:6` | YES — `songs_insert`+`update` |
| GET /api/settings (via bootstrap) | `_handle_bootstrap` | `store.get_settings()` → `_transaction(claims)` | `api.js:44` | YES — `workspace_settings_select` (any workspace member) |
| POST /api/settings | `_handle_post_settings` | `store.save_settings()` → `_transaction(claims)` | `songs.js:1029`, `staff.js:29`, `calendar.js:1029` | YES — `workspace_settings_update` (any workspace member) |
| GET /api/workspace/members | `_handle_get_workspace_members` | `admin_transaction()` → plain SQL on `workspace_members` | `projects.js:1166` | **GAP** — uses admin_transaction; anon-key path needs `workspace_members_select` policy, which exists, but the handler hardcodes `admin_transaction` |
| POST /api/presence/heartbeat | `_handle_post_presence_heartbeat` | `_db.transaction(user.claims)` | `projects.js:61` | YES — `presences_insert`+`update` user_id = auth.uid() |
| GET /api/presence | `_handle_get_presence` | `_db.transaction(user.claims)` | `projects.js:69` | YES — `presences_select` workspace member |
| DELETE /api/presence | `_handle_delete_presence` | `_db.transaction(user.claims)` | `projects.js:94` | YES — `presences_delete` user_id = auth.uid() |
| GET /api/templates | `_handle_get_templates` | `store.list_templates()` | `api.js:46` | YES — `templates_select` |
| POST /api/templates | `_handle_post_templates` | `store.save_templates()` | (template designer) | YES — `templates_insert`+`update` |
| DELETE /api/templates/{id} | `_handle_delete_template` | `store.delete_template()` | (template designer) | YES — `templates_delete` |
| GET/POST/DELETE /api/fonts | font handlers | `store.*_font()` | (font uploader) | YES — `fonts_*` policies |

**Operations that cannot cleanly move to the renderer today:**

1. **`POST /api/projects/{id}/transfer` — `storage.transfer_project_owner()`**: Uses `admin_transaction()` because the `projects_update` WITH CHECK requires `owner_user_id = auth.uid()` on the NEW row — after the transfer, owner_user_id is the target user, not the caller, so the caller's JWT fails the WITH CHECK. This is a genuine RLS constraint mismatch. **Risk: HIGH.** Proposed handling: keep in sidecar via a new RLS-friendly pattern: a DB function (`SECURITY DEFINER`) that validates caller = current owner, target = workspace member, then updates. The renderer calls this via `supabase.rpc('transfer_project_owner', {...})`.

2. **`GET /api/workspace/members` — `admin_transaction()`**: Hardcodes admin connection to read `workspace_members + profiles`. The `workspace_members_select` policy (`user_id = auth.uid() OR is_workspace_member(workspace_id)`) means authenticated users CAN read workspace_members under their own JWT. The `profiles_select` policy (`id = auth.uid() OR shares_workspace_with(id)`) permits reading co-workspace profiles. Both are anon-key safe. **Risk: LOW.** This can move directly to `supabase.from('workspace_members').select('*, profiles(display_name,email)')`.

3. **OAuth callback `save_settings` (workspace_settings write)**: The PCO/Google OAuth callbacks are unauthenticated browser redirects. The 2026-06-05 decision already threads the workspace id through the signed state, and the callback writes via `get_storage(workspace_id=..., user_claims=None)` — that is, owner-role DATABASE_URL bypasses RLS. **Risk: MEDIUM.** This write cannot use the anon key because there's no user JWT in the callback context. Two options: (a) keep this in the sidecar (acceptable since PCO/Google OAuth happens in the browser via redirect, not Electron IPC), or (b) after the OAuth callback, the SPA makes a second `POST /api/settings` call with the token — but this duplicates the write. Recommended: keep the OAuth callback write in the sidecar; it only runs when the user explicitly connects PCO/Google and the sidecar is still running.

4. **`save_project_transactional` (restore path)**: Uses `_transaction(claims)`, so already RLS-safe. No issue.

5. **Fonts upload to Supabase Storage** (`storage_assets.py`): Handled by `_handle_post_fonts` which calls `store.save_font()`. The font binary upload goes to Supabase Storage via the service-role key (`SUPABASE_SERVICE_ROLE_KEY`). This is already NOT bundled in the Electron build (release-electron.yml explicitly omits it). The metadata insert (`fonts` table) runs under `_transaction(claims)` — RLS-safe. The storage upload in a renderer-only path would use the supabase-js Storage client with the anon key — storage RLS policies govern access. **This needs investigation** — if storage buckets have RLS policies, anon-key upload may work; if not, this is a gap. However, font upload is a relatively rare operation and keeping it sidecar-mediated is acceptable.

#### S1 recommendation: Not preferred

S1 (sidecar calls PostgREST via publishable key) means rewriting all psycopg queries to HTTP REST calls in Python, losing multi-statement transactions (revision inserts), losing type-safe RETURNING clauses, and gaining no UX improvement. The sidecar still needs to run and the DATABASE_URL is removed but replaced by a different credential path that doesn't meaningfully improve isolation. S1 is strictly worse than S2 with no compensating benefit.

#### S2 recommendation: Preferred, with hybrid for transfer

**S2 (renderer does data via supabase-js directly)** is the right approach. The evidence:

- RLS is already correctly configured for all main data tables (projects, announcements, songs, workspace_settings, project_revisions, workspace_presences, templates, fonts).
- The live DB confirms: `anon` role has no grants on any data table (confirmed above — only `authenticated` and `service_role`). The anon/publishable key authenticates as `authenticated` after Supabase Auth issues the JWT; the JWT is already flowing through `apiFetch` as the Bearer token.
- The renderer already has `supabase-js` (the `@supabase/supabase-js` UMD is bundled in the PyInstaller binary for auth). Adding data calls to the same client adds zero new dependencies.
- The only true blocker is `transfer_project_owner`, which needs a SECURITY DEFINER RPC to work under an anon-key session. That is a one-migration fix.

**LOC estimate for S2:**
- New `src/js/supabase-data.js`: ~300 LOC (one function per table operation, with proper error handling).
- Modifications to `projects.js`, `announcements.js`, `songs.js`, `calendar.js`, `staff.js`: ~50–80 LOC total (redirect calls through the new module when `window.electronAPI` is present or `IS_ELECTRON` is true; in server mode keep apiFetch as-is).
- New migration for `transfer_project_owner` RPC: ~30 LOC.
- `release-electron.yml` change: remove 3 lines (DATABASE_URL secret reference and `.env` key).
- `server.py` `_validate_server_config()`: add a guard so DATABASE_URL is not required in `APP_MODE=electron`.

**What breaks without DATABASE_URL in the desktop sidecar:**
- `_validate_server_config()` currently calls `sys.exit(1)` when DATABASE_URL is missing and not IS_DESKTOP. Since APP_MODE for Electron is `server` (confirmed in project-state.md: "APP_MODE=server is correct (Supabase-connected)"), this will immediately kill the sidecar on launch. Fix: treat `APP_MODE=electron` as desktop-equivalent in the validator. This is a one-line change.
- `db.py`'s `transaction()` raises RuntimeError when DATABASE_URL is empty. Any code path that reaches `db.transaction()` in electron mode will crash. Fix: each endpoint that calls psycopg already guards on `IS_DESKTOP`; those guards need to also apply to `IS_ELECTRON`. The sidecar can return 501 for endpoints it no longer handles (projects, announcements, songs, settings, presence) once the renderer handles them.

**Hybrid recommended for v1:**
The pragmatic path for issue #277 is:
1. Implement `supabase-data.js` (renderer data layer via anon key).
2. Wire it into the existing JS call sites with an `IS_ELECTRON` guard.
3. Add `transfer_project_owner` RPC migration.
4. Update `server.py` to gracefully handle `APP_MODE=electron` with no DATABASE_URL.
5. Remove DATABASE_URL from the build.

The sidecar in electron mode keeps: static serving, PCO proxy, Google Calendar fetch, PDF (via Electron IPC or Chrome fallback), OAuth callbacks.

---

### RLS Gap Analysis (live DB confirmed 2026-06-06)

| Table | Operations | Current RLS | Anon-key safe for renderer? | Gap? |
|---|---|---|---|---|
| `projects` | SELECT/INSERT/UPDATE/DELETE | workspace_member + owner-only update/delete | YES — all four policies present and correct | None |
| `announcements` | SELECT/INSERT/UPDATE/DELETE | workspace_member for all ops | YES | None |
| `songs` | SELECT/INSERT/UPDATE/DELETE | workspace_member for all ops | YES | None |
| `workspace_settings` | SELECT/INSERT/UPDATE/DELETE | workspace_member for all ops | YES | None — the anon-key can read/write workspace_settings after auth |
| `project_revisions` | SELECT/INSERT only (append-only) | workspace_member + own user insert | YES | None |
| `workspace_presences` | SELECT/INSERT/UPDATE/DELETE | workspace_member read; own-user write | YES — project_id is TEXT (confirmed live) | None |
| `templates` | SELECT/INSERT/UPDATE/DELETE | workspace_member for all ops | YES | None |
| `workspace_members` | SELECT only (authenticated) | user_id = auth.uid() OR is_workspace_member | YES | None (no INSERT/UPDATE/DELETE policy needed — managed by service_role/seed only) |
| `profiles` | SELECT | id = auth.uid() OR shares_workspace_with(id) | YES | None |
| `fonts` | SELECT/INSERT/UPDATE/DELETE | workspace_member for all ops | YES | None |
| MISSING: `transfer_project_owner` | UPDATE (cross-user ownership change) | current projects_update requires owner_user_id = auth.uid() on WITH CHECK — fails when new owner != caller | **NO** | **GAP** — needs SECURITY DEFINER RPC |

**Security advisor output (2026-06-06):** Only finding is "Leaked Password Protection Disabled" (auth setting, unrelated to this issue). No RLS gaps flagged by the advisor.

**Net assessment:** The only structural RLS gap is the transfer endpoint. All other data operations can move to anon-key paths without any new migrations beyond the `transfer_project_owner` RPC. The `anon` role has zero table grants (confirmed) — the published key only gets `authenticated` grants after JWT auth, which is correct.

---

### Desktop vs Server mode impact

- **Server (Docker) mode**: No change. `APP_MODE=server` keeps psycopg + DATABASE_URL. All existing server-mode code paths are unaffected.
- **Desktop (Electron) mode** (`APP_MODE=electron`, `APP_MODE=desktop`): The Python sidecar must start without DATABASE_URL. The renderer's data calls go through supabase-js directly. The sidecar keeps serving: static files, PCO proxy, Google Calendar, PDF, OAuth callbacks.
- The JS change (`IS_ELECTRON` guard) can be implemented as a clean abstraction — `supabase-data.js` exposes the same interface as the `apiFetch('/api/...')` call sites. In server mode the existing `apiFetch` path is unchanged.

---

### Decomposed Sub-Issues

| Order | Title | Goal | Likely files | Tests / evaluation | Dependencies |
|---|---|---|---|---|---|
| **#277-A** | Fix `_validate_server_config` and `IS_ELECTRON` guards so sidecar starts without DATABASE_URL | Make `APP_MODE=electron` bypass the DATABASE_URL validation; add `IS_ELECTRON` guards so sidecar endpoints that need psycopg return 501/no-op gracefully instead of crashing | `server.py` (lines ~270–288, IS_DESKTOP guards in presence handlers) | `python -c "APP_MODE=electron python server.py"` exits without error (no DATABASE_URL set); pytest all pass | None |
| **#277-B** | Add `transfer_project_owner` SECURITY DEFINER RPC migration | New Supabase migration adding a PL/pgSQL function callable via `supabase.rpc('transfer_project_owner')` that validates caller=current owner, target=workspace member, then UPDATEs; accessible to `authenticated` role | `supabase/migrations/20260606000001_transfer_owner_rpc.sql` | pytest: call the RPC as owner → 200; as non-owner → error; as non-member target → error (can be run against live Supabase via test_rls_isolation.py) | None — migration only |
| **#277-C** | Implement `supabase-data.js` — renderer data layer via anon key | New module exposing `sdGetProjects()`, `sdSaveProject()`, `sdDeleteProject()`, `sdGetAnnouncements()`, `sdSaveAnnouncements()`, `sdGetSongs()`, `sdSaveSongs()`, `sdGetSettings()`, `sdSaveSettings()`, `sdGetMembers()`, `sdTransferProject()`, `sdGetPresence()`, `sdPostPresenceHeartbeat()`, `sdDeletePresence()`, `sdGetTemplates()`, `sdSaveTemplates()`, `sdGetProjectHistory()`, `sdRestoreProject()` — all using `supabase.from(...)` or `supabase.rpc(...)` | `src/js/supabase-data.js` (new) | vitest unit tests; `node --check` passes | #277-B (for sdTransferProject) |
| **#277-D** | Wire `supabase-data.js` into existing call sites with `IS_ELECTRON` guard | In each JS file that calls `apiFetch('/api/...')`, add an electron-mode branch that calls the corresponding `supabase-data.js` function. Keep `apiFetch` path for server mode unchanged. | `src/js/projects.js`, `src/js/announcements.js`, `src/js/songs.js`, `src/js/calendar.js`, `src/js/staff.js`, `src/js/api.js` (loadAllFromServer) | vitest: existing tests pass (server-mode paths unchanged); manual Electron smoke: open project, save, reload; annotations in console | #277-A, #277-C |
| **#277-E** | RLS negative-path integration tests | Add pytest tests (using authenticated + a second workspace's session) proving cross-workspace isolation: user from workspace A cannot SELECT/INSERT/UPDATE/DELETE rows in workspace B's projects, announcements, songs, workspace_settings | `tests/test_rls_isolation.py` (extend existing) | All negative tests produce `rowcount=0` or empty results; positive tests for own workspace return data; run against live Supabase | #277-B |
| **#277-F** | Remove DATABASE_URL from Electron build + update server.py bootstrap path | Delete DATABASE_URL from `release-electron.yml` `.env` step (both arm64 + x64 matrix); update `_validate_server_config` to skip DATABASE_URL check in electron mode; update the NOTE comment; remove DATABASE_URL from the `keys` list in the .env writer | `.github/workflows/release-electron.yml`, `server.py` | CI run on a tag-triggered release build passes; `grep -r DATABASE_URL release-electron.yml` returns only comments, not the secret reference | #277-A, #277-D |
| **#277-G** (optional) | Move workspace/members endpoint to anon-key path | Replace `admin_transaction()` in `_handle_get_workspace_members` with `_transaction(user.claims)` — the existing `workspace_members_select` RLS policy already permits this | `server.py` (handler ~L2759) | pytest: workspace members returned correctly under user JWT; negative: wrong workspace member gets empty list | #277-A |

**Execution order:** #277-A and #277-B can be done in parallel. #277-C depends on #277-B (RPC). #277-D depends on #277-A and #277-C. #277-E depends on #277-B. #277-F depends on #277-A and #277-D. #277-G is independent cleanup.

**Stop-bundling gate:** DATABASE_URL can ONLY be removed from the build (#277-F) after #277-A (sidecar boots without it), #277-C (renderer has data layer), and #277-D (call sites wired) are all merged and manually smoked in the Electron app.

---

### Acceptance Criteria

**AC-277-A:**
- `APP_MODE=electron python server.py` (with no DATABASE_URL in env) starts without calling `sys.exit(1)`.
- All existing pytest tests continue to pass.

**AC-277-B:**
- `supabase.rpc('transfer_project_owner', {project_id, to_user_id})` called by the current project owner returns success and the project's `owner_user_id` changes.
- Same call by a non-owner returns an error.
- Same call targeting a user who is not a workspace member returns an error.
- Migration is idempotent (safe to re-apply).

**AC-277-C:**
- `supabase-data.js` exports all named functions.
- Each function uses `supabase.from(...)` or `supabase.rpc(...)`, never `psycopg`.
- `node --check src/js/supabase-data.js` passes.
- vitest unit tests covering the happy path of each function (mock supabase client).

**AC-277-D:**
- In Electron mode (`window.electronAPI !== undefined` or `isElectronMode()` flag), `apiFetch('/api/projects')` is NOT called; `sdGetProjects()` is called instead. Confirmed via DevTools Network tab: no `/api/projects` network request on startup in the packaged Electron app.
- All project operations (open, save, delete, transfer) work end-to-end in the packaged Electron app.
- Announcement, song, settings, presence operations all work.
- Server-mode (Docker) behavior is unchanged: existing tests pass.

**AC-277-E:**
- New test `test_rls_cross_workspace_isolation` passes: workspace-A user cannot read workspace-B projects/announcements/songs/settings.
- New test `test_rls_cross_workspace_write_rejected` passes: workspace-A user cannot INSERT/UPDATE/DELETE workspace-B data.
- Tests run against the live Supabase project (`APP_MODE=server pytest tests/test_rls_isolation.py`).

**AC-277-F:**
- `grep DATABASE_URL .github/workflows/release-electron.yml` returns only comment lines (no `${{ secrets.DATABASE_URL }}`).
- A release build triggered by a new tag produces a DMG that launches without DATABASE_URL in the bundled `.env`.
- `strings dist/server | grep DATABASE_URL` returns no connection string.

**AC-277-G (optional):**
- `GET /api/workspace/members` works under user JWT (no admin_transaction).
- Negative: a user from workspace B cannot retrieve workspace A's members.

---

### Data Safety Notes

- No user data is deleted by this change. The migration is purely additive (new RPC function).
- The Postgres DATABASE_URL password rotation note in project-state.md applies: if any existing DMG is circulating with DATABASE_URL bundled, rotate the DB password after the new anon-key build is confirmed working.
- Old draft prereleases (v0.0.1/2/3) contain the extractable DATABASE_URL — delete them after the new build lands.

---

### Validation Strategy

- **Per sub-issue:** `python3 -c "import server"`; `node --check src/js/supabase-data.js`; full `pytest` + `vitest` + `vite build`.
- **RLS tests:** `APP_MODE=server pytest tests/test_rls_isolation.py -v` against the live Supabase project.
- **Electron smoke (manual):** Package the app from the updated branch; confirm launch without DATABASE_URL; open a project, save, load, export PDF; check DevTools Network tab shows supabase REST calls (not `/api/projects`) for data operations.
- **Release build smoke:** Tag a prerelease build from the updated `release-electron.yml`; confirm the .env in the bundle does not contain DATABASE_URL (use `strings` on the binary).

---

### Known Ambiguities

1. **Fonts upload path**: `POST /api/fonts` in Electron mode relies on `storage_assets.py` which needs the Supabase storage URL. The anon-key can write to storage if bucket policies permit authenticated inserts. This is not investigated in this plan — font upload can remain sidecar-mediated for v1 (the sidecar is still running; only its DATA_URL usage is removed).
2. **`save_project_transactional` (restore path)**: Currently uses `_transaction(claims)` — already RLS-safe. In electron mode, the renderer can call the Supabase PostgREST API directly for project restore, or a second SECURITY DEFINER RPC can be added later. Deferred to follow-up.
3. **Session presence of Supabase JWT in electron mode at sidecar boot**: The sidecar validates Supabase JWTs in `_require_auth()`. In electron mode, the renderer must pass the access token to all remaining sidecar calls (PCO proxy, PDF, calendar) via `Authorization: Bearer`. This already works (apiFetch always attaches the token).

---

_Last updated: 2026-06-03 (original ownership plan, partially superseded — see above)_

> **⚠️ SUPERSEDED in part (2026-06-04):** the shipped model is **A — workspace-visible by default + hand-off** (see `decisions.md` 2026-06-04). "Private-by-default" and "share to workspace" below were **abandoned**: `save_project` keeps `visibility='workspace'`, there is no Share UI/endpoint, and ownership transfer (hand-off) is the only reassignment path. Read the rest of this file as historical planning context, not current behavior.

> **Active effort:** Project ownership and sharing model — private-by-default,
> workspace sharing, ownership transfer, lightweight presence badge, and removal
> of 409 conflict detection.
> Branch: `feat/supabase-multitenant-electron` (continuing on this branch).

---

## Clarification interview

Skipped full interview — the request provides explicit, concrete acceptance criteria for all five features, named non-goals (no hard locks, no WebSockets, desktop unaffected), boundary conditions (owner-only write, informational-only presence), and done-definitions (private default, migration for existing rows). Two residual ambiguities documented under Known Ambiguities rather than blocking on a clarification round.

---

## Goal (one sentence)

Make each project privately owned by default in server mode, allow the owner to optionally share it to the workspace (read-only for others), transfer ownership to a teammate, show a lightweight "User X is editing" badge when the owner has the project open, and remove the now-unnecessary 409 conflict/stale-poll system entirely.

---

## In scope

- Change the `visibility` column default from `'workspace'` to `'private'` for new projects.
- Enforce owner-only writes for `visibility='workspace'` projects: non-owners see the project but `POST /api/projects` returns 403 (server-side) and the UI shows read-only state (frontend-side).
- Add `POST /api/projects/{id}/transfer` — owner transfers ownership to another workspace member; new owner becomes sole editor.
- Add a presence subsystem: a lightweight DB table (`workspace_presences`) with heartbeat upserts; `GET /api/projects` (or a new `GET /api/projects/presence`) returns current editor names; frontend shows badge.
- Remove `save_project_transactional` call path, `ConflictError`, `_clientRevision` from project saves, `startStaleCheck` / 30s poll, conflict banner, conflict dialog from the frontend.
- `can_write_project` helper in `storage.py` updated: workspace-visible projects are now read-only for non-owners (not writable by all members as today).
- Existing `'workspace'`-visibility projects: migrated at runtime (no schema change needed — they keep their visibility but the write policy tightens). Legacy ownerless projects (`owner_user_id IS NULL`) retain the existing "accessible to all" read-only behavior, write-disabled until an owner is assigned.
- RLS policies updated to match new write semantics: `projects_update` should require `owner_user_id = auth.uid()`.

## Non-goals (explicit)

- No real-time collaborative editing (no WebSockets, no OT/CRDT).
- No hard locks — presence badge is informational only; non-owner can still view the project while the owner edits.
- Desktop mode (`APP_MODE=desktop`) is entirely unaffected — `JsonStorageBackend` and all desktop JS paths remain unchanged.
- No UI for workspace membership management or invite flows (out of scope for this plan).
- No changes to announcements, songs, templates, settings write semantics — ownership is a project-level concept only.
- No removal of `project_revisions` table or revision history feature — revision snapshots are still useful for the restore feature; we only remove the *conflict detection* use of revisions.

---

## Hard constraints

- **Data-safety (`AGENTS.md`):** atomic writes only; migrations idempotent + additive; never delete user data.
- **Visibility default change is a DB migration** — must be applied via `supabase/migrations/` (idempotent SQL), not a one-time hotfix. All existing `'workspace'` rows keep their current value; only new INSERTs get `'private'`.
- **RLS must remain the real boundary** — the update to `projects_update` policy must be applied as a migration, not just a Python-side `can_write_project` check.
- **Desktop mode (`IS_DESKTOP=True`, `APP_MODE=desktop`, `APP_MODE=electron`) must not be affected** — any new server-mode route must be gated behind `_require_auth()` and checked only when `not IS_DESKTOP`.
- Conventional Commits; feature branch only; draft PRs; manual merge.
- Test suite must continue to pass: 100 pytest, 71 vitest, vite build.

---

## Design tensions

- **Minimal surface area vs full enforcement.** The simplest implementation is a Python-side `can_write_project` check in `_handle_post_projects`. But the user request says RLS is the real boundary. We resolve this by doing *both*: Python-side check for clean 403 UX, and a DB migration that tightens `projects_update` RLS to `owner_user_id = auth.uid()`.
- **Presence heartbeat storage: Supabase Realtime vs simple DB table.** Realtime (Broadcast + Presence channels) is the canonical Supabase approach but requires `@supabase/supabase-js` in the browser and WebSocket infrastructure — explicitly out of scope. A simple `workspace_presences` table with TTL-based heartbeat is dumber, polling-based, and fully within the existing stack.
- **Removing conflict detection before the QA matrix is run.** The existing QA matrix item C1 ("conflict detection") will become moot. The plan removes conflict machinery; the QA matrix document should be updated to remove C1–C3 and add presence + write-protection checks in their place.

---

## Cheapest version that proves the idea

1. Apply DB migration: change default to `'private'`, tighten RLS update policy.
2. Update `can_write_project` in `storage.py`.
3. Add a single `403` guard in `_handle_post_projects`.
4. Remove `_clientRevision` / `save_project_transactional` from the save path, remove `startStaleCheck` from `projects.js`.
5. Smoke: create a project → it's private → share it → other user sees it read-only → owner can still edit.

That five-step slice proves the core thesis before adding presence or transfer.

---

## Prior Art

No prior-art swarm run (patterns are all well-established within the existing repo):

- **Owner-only write pattern** is already partially implemented in `can_delete_project` (storage.py L1849–1860): "owner is None → False; else str(owner)==str(user_id)". The same logic is extended to `can_write_project`.
- **Presence via DB heartbeat** is a classic low-overhead approach used widely where WebSockets are unavailable. TTL + periodic upsert (every 30s) + read on project load. Supabase Realtime is the "right" answer but was explicitly excluded.
- **Transfer ownership** is a single `UPDATE projects SET owner_user_id = %(new_owner)s WHERE id=... AND owner_user_id=%(current)s` — atomically safe, no two-phase commit needed.
- **Removing a stale-poll** (the `startStaleCheck` 30s timer in `projects.js`) is the same code added in the `lightweight-projects-poll` commit (`2026-05-28`). That timer is entirely eliminated, as is the `/api/projects/revisions` endpoint it called.

---

## Key design decisions

### D6 — Presence storage: `workspace_presences` table with 60s TTL

A new `workspace_presences` table:

```sql
create table if not exists public.workspace_presences (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  project_id   text,
  display_name text,
  last_seen    timestamptz not null default now()
);
```

- The owner's browser calls `POST /api/presence/heartbeat` every 30s when a project is open, upserting `last_seen`.
- `GET /api/projects` (or a dedicated `GET /api/presence?project_id=X`) returns presences where `last_seen > now() - 90s` (1.5× the heartbeat interval — survives one missed beat).
- The frontend polls `GET /api/presence?project_id=X` on a 30s interval when the project list or project editor is visible (replacing the removed `startStaleCheck` call).
- No RLS bypass needed — the presence row belongs to the authenticated user; other workspace members can read it via a `SELECT` policy gated on `is_workspace_member(workspace_id)`.
- Cleanup: `last_seen` is checked at read time (no cron needed for v1).

**Why not Supabase Realtime:** explicitly out of scope (no WebSockets).
**Why TTL-read not hard delete:** avoids a background job dependency; presence rows are self-expiring from the query's perspective.

### D7 — Conflict detection removal strategy

The 409 path is threaded through multiple layers. Removal order:
1. Remove `_clientRevision` from the `POST /api/projects` payload (frontend).
2. Remove `startStaleCheck` 30s timer and all conflict-banner/dialog DOM interaction (frontend).
3. Swap `save_project_transactional` for `save_project` in `_handle_post_projects` (server.py).
4. `ConflictError` class and `save_project_transactional` in `storage.py` are left in place for now (they have test coverage; removing them is a separate cleanup). The Postgres implementation is simply no longer called from the normal save path.
5. Remove the `/api/projects/revisions` GET endpoint (added purely for the stale poll — no other callers).
6. Update `testing-guide.md`: remove the "409 conflict" manual smoke item; add write-protection + presence smoke items.

**What is kept:** `project_revisions` table + `get_project_revisions` / `get_project_revision` (used by the revision history / restore feature, issue 019). Only the *save-side* transactional revision check is removed.

### D8 — Default visibility change requires a DB migration + Python change

The `projects` table has `visibility text not null default 'workspace'`. Changing it to `'private'` requires:
1. A new Supabase migration file (`supabase/migrations/20260604000001_private_default.sql`).
2. Updating `save_project` in `PostgresStorageBackend` — the INSERT hardcodes `'workspace'` as the visibility value (storage.py L643). Change to `'private'`.
3. Updating the RLS `projects_update` policy to require `owner_user_id = (select auth.uid())` (dropping the current `visibility = 'workspace' OR owner_user_id = auth.uid()` condition).

**Existing rows:** All existing `'workspace'`-visibility projects keep their value (no backfill needed). The tighter update RLS means non-owners can no longer save them — which is the desired behavior.

### D9 — Transfer uses a server-guarded endpoint, not direct RLS

`POST /api/projects/{id}/transfer { "new_owner_user_id": "<uuid>" }`:
- Python verifies: caller = current owner; new owner is a member of the same workspace.
- Single `UPDATE projects SET owner_user_id = %(new)s, updated_at = now() WHERE id=... AND owner_user_id=%(caller)s`.
- Returns 200 with updated project dict, or 403/404 as appropriate.
- RLS update policy (`owner_user_id = auth.uid()`) still covers this because the UPDATE runs under the caller's claims.

---

## Decomposed issues

| Order | Title | Goal | Likely files | Tests / evaluation | Dependencies |
|---|---|---|---|---|---|
| **Issue 020** | DB migration: private-by-default + RLS write policy | Change `visibility` default to `'private'`; tighten `projects_update` RLS to `owner_user_id = auth.uid()` only | `supabase/migrations/20260604000001_private_default.sql` | pytest: new project row has `visibility='private'`; non-owner UPDATE rejected by RLS; `tests/test_rls_isolation.py` | — |
| **Issue 021** | Server + storage: enforce owner-only writes + add transfer endpoint | Update `can_write_project`; replace `save_project_transactional` with `save_project` in normal save path; add `POST /api/projects/{id}/transfer`; gate all writes with 403 on non-owner | `storage.py`, `server.py` | pytest: non-owner POST → 403; owner POST → 200; transfer changes owner; tests in `tests/test_server_utils.py` or new `tests/test_ownership.py` | 020 |
| **Issue 022** | Add presence heartbeat table + API endpoints | Create `workspace_presences` table migration; add `POST /api/presence/heartbeat` and `GET /api/presence` (filtered by `project_id`); 90s TTL at read | `supabase/migrations/20260604000002_presence.sql`, `server.py` | pytest: heartbeat upsert → row visible; TTL filter excludes stale rows; RLS: only workspace members see presence | 020 |
| **Issue 023** | Frontend: remove conflict detection, add presence badge | Remove `_clientRevision`, `startStaleCheck`, conflict-banner/dialog; replace stale-poll timer with 30s presence poll; render "User X is editing" badge on project cards when owner is present; make workspace-visible projects non-editable by non-owners (disable save button + show read-only hint) | `src/js/projects.js`, `index.html` (conflict DOM removal) | vitest: `can_write_project` UI logic; manual smoke: private project list, share, non-owner read-only, presence badge appears/disappears | 021, 022 |
| **Issue 024** | Migration for existing projects + QA matrix update | Backfill `owner_user_id` on any ownerless `'workspace'`-visibility projects to the workspace's founding member (service_role script); update `docs/ai/qa-matrix-m5.md` removing C1–C3 conflict checks, adding write-protection + presence checks | `scripts/migrate_to_supabase.py` (add backfill step), `docs/ai/qa-matrix-m5.md` | Dry-run: ownerless count before/after; idempotent; QA matrix reviewable | 021, 022 |

---

## Acceptance criteria (per issue)

### Issue 020 — DB migration

- **AC-020-1:** After applying the migration, `INSERT INTO projects (...) VALUES (...)` without an explicit `visibility` value produces a row with `visibility='private'`.
- **AC-020-2:** A user who is not `owner_user_id` cannot `UPDATE` a project row under `authenticated` role (RLS rejects, `rowcount=0`); the project owner can update.
- **AC-020-3:** Existing rows with `visibility='workspace'` are unchanged by the migration.
- **AC-020-4:** Migration is idempotent: applying it twice is a no-op.

### Issue 021 — Server + storage

- **AC-021-1:** `POST /api/projects` by a non-owner of a workspace-visible project returns HTTP 403 (not 200 or 409).
- **AC-021-2:** `POST /api/projects` by the project owner returns HTTP 200 and the saved project is returned.
- **AC-021-3:** `POST /api/projects` without `_clientRevision` in the payload saves successfully (no conflict check needed).
- **AC-021-4:** `POST /api/projects/{id}/transfer { "new_owner_user_id": "<uuid>" }` by the current owner returns 200 with `owner_user_id` equal to the new owner.
- **AC-021-5:** The same transfer call by a non-owner returns 403.
- **AC-021-6:** Transferring to a user who is not a workspace member returns 403.
- **AC-021-7:** Desktop mode (`APP_MODE=desktop`) is unaffected — `JsonStorageBackend.save_project` is called without ownership checks.

### Issue 022 — Presence

- **AC-022-1:** `POST /api/presence/heartbeat { "project_id": "..." }` by an authenticated user upserts a row in `workspace_presences` with `last_seen` = now. Returns 200.
- **AC-022-2:** `GET /api/presence?project_id=X` returns an array of `{ user_id, display_name }` for all users in the same workspace who have `last_seen > now() - 90s` for that project.
- **AC-022-3:** A presence row older than 90s does NOT appear in the response.
- **AC-022-4:** A workspace member cannot read presence rows from a different workspace (RLS enforced — `is_workspace_member(workspace_id)`).
- **AC-022-5:** Both endpoints are no-ops / 401 in desktop mode.

### Issue 023 — Frontend

- **AC-023-1:** The project list no longer calls `/api/projects/revisions` (the stale-poll endpoint). DevTools Network tab shows no 30s polling to that endpoint.
- **AC-023-2:** Conflict-banner (`#conflict-banner`) and conflict-dialog (`#conflict-dialog`) DOM elements are removed from `index.html` and no JS references them.
- **AC-023-3:** When the current user is NOT the project owner and the project is `visibility='workspace'`, the save button is disabled (or absent) and a "Read only" or "View only" hint is visible on the project card or editor.
- **AC-023-4:** A project card for a workspace-visible project shows a "User X is editing" badge when `GET /api/presence?project_id=X` returns at least one entry and that user is not the current user.
- **AC-023-5:** The presence badge disappears within 2 poll cycles (~60s) after the editing user closes the project (no more heartbeats).
- **AC-023-6:** Browser console is clean (no errors) after exercising the project list, project load, and save in all ownership states.

### Issue 024 — Migration + QA matrix

- **AC-024-1:** The backfill script, run with `--dry-run`, prints a count of ownerless workspace-visible projects and exits 0.
- **AC-024-2:** After running without `--dry-run`, no `projects` row has `visibility='workspace' AND owner_user_id IS NULL` (except intentionally unowned rows that the script explicitly skips).
- **AC-024-3:** `docs/ai/qa-matrix-m5.md` no longer contains C1–C3 (conflict detection checks); contains new checks for owner-write enforcement and presence badge behavior.

---

## Validation strategy

- **Per issue:** `python3 -c "import server"`; `node --check src/js/projects.js`; full `pytest` + `vitest` + `vite build`.
- **DB/RLS:** integration tests prove `projects_update` rejects non-owner; `workspace_presences` scoped correctly. Run against the Supabase staging project (`APP_MODE=server pytest tests/test_rls_isolation.py`).
- **Manual-only:** open two browser sessions (owner + non-owner); verify: private project invisible to non-owner, workspace project visible-but-save-disabled, presence badge appears, transfer changes editor.
- **Conflict removal regression:** after issue 023, no new console errors; existing project save/load flow works without `_clientRevision`.

---

## Data-safety notes

- The visibility default change is purely additive for new rows. No backfill of existing rows is needed — they keep `'workspace'`.
- The ownerless-project backfill (issue 024) has a `--dry-run` gate and is idempotent.
- `workspace_presences` is ephemeral metadata — no backup needed; rows expire naturally.
- `ConflictError` and `save_project_transactional` are left in `storage.py` (dead code for the save path) to preserve test coverage; a separate cleanup issue can remove them after the cutover QA passes.

---

## Known ambiguities / open questions

1. **Non-owner save UX (issue 023):** Three options: (a) disable the save button entirely (no network call), (b) allow the user to copy the project and work on the copy, (c) show a banner "You're viewing a read-only project." Option (b) has precedent in `projects.js` (the existing "copy" path sets `visibility='private'`). **Recommended:** (a) disable save + (c) show banner. Implement as (a)+(c); the copy shortcut is already present.
2. **Presence heartbeat TTL (issue 022):** 60s heartbeat interval / 90s TTL at read is the recommended default. If the tab is backgrounded or the user leaves the project editor without closing the tab, the heartbeat stops and the badge disappears in ≤ 90s. Acceptable for informational-only presence.
3. **QA matrix conflict items (C1–C3):** These become moot after issue 023. The plan removes them from the QA matrix in issue 024. Confirm this is the desired outcome (vs. keeping them as "REMOVED / N/A" for audit history).

---

## Next in chain

Hand off to **`issue-writer`** to convert issues 020–024 into GitHub-ready issues under `docs/ai/generated-issues/`, in dependency order, with per-issue acceptance criteria, likely files, and tests. Issues 020, 021 warrant `acceptance-contract` before `coding-agent` (RLS and auth-boundary changes). Issue 023 (frontend) can go straight to `coding-agent` after 021 is merged.
