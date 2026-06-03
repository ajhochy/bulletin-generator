# Current Plan

_Last updated: 2026-06-03_

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
