# 022: Add presence heartbeat table + API endpoints

**Milestone:** M5  ·  **Plan ref:** Issue 022 (D6)
**Depends on:** 020

## Context

With conflict detection removed (issues 021, 023), the app needs a lightweight replacement that answers "is someone already editing this project right now?" without WebSockets or Supabase Realtime. The answer is a `workspace_presences` table: the owner's browser sends a heartbeat every 30 s while a project is open; the project list polls `GET /api/presence?project_id=X` on the same interval and shows an informational badge.

This is intentionally dumb: presence is best-effort and informational only. There are no hard locks; a non-owner who views a workspace-visible project does not send heartbeats. Stale rows expire naturally — rows older than 90 s are excluded at read time; no background cron is required for v1.

The DB migration and the two API endpoints are bundled in this issue because neither is useful without the other.

## Acceptance criteria

- [ ] **AC-022-1:** `POST /api/presence/heartbeat { "project_id": "<id>" }` by an authenticated user upserts a row in `workspace_presences` with `last_seen = now()`. Returns `{ "ok": true }` with HTTP 200.
- [ ] **AC-022-2:** `GET /api/presence?project_id=X` returns a JSON array of `{ "user_id": "...", "display_name": "..." }` for all users in the same workspace who have `last_seen > now() - 90s` for that `project_id`.
- [ ] **AC-022-3:** A presence row with `last_seen` older than 90 s does NOT appear in the `GET /api/presence` response.
- [ ] **AC-022-4:** A workspace member cannot read presence rows from a different workspace — RLS `SELECT` policy requires `is_workspace_member(workspace_id)`.
- [ ] **AC-022-5:** Both endpoints return HTTP 401 when called without a valid JWT (unauthenticated).
- [ ] **AC-022-6:** Both endpoints are no-ops / return 404 or 501 in desktop mode (`IS_DESKTOP=True`) — they must not be reachable from the `JsonStorageBackend` path.
- [ ] **AC-022-7:** The migration file creates the `workspace_presences` table if it does not exist (idempotent `CREATE TABLE IF NOT EXISTS`).
- [ ] **AC-022-8:** `python3 -c "import server"` passes after the new endpoints are added.
- [ ] **AC-022-9:** `pytest tests/test_presence.py -v` passes — covers: heartbeat upsert, TTL filter excludes stale rows, cross-workspace isolation.

## Likely files

- `supabase/migrations/20260604000002_presence.sql` (new — create `workspace_presences` table + RLS policies)
- `storage.py` — add `upsert_presence(user_id, workspace_id, project_id, display_name)` and `get_presence(workspace_id, project_id, ttl_seconds=90)` to `PostgresStorageBackend`; stubs on `JsonStorageBackend`
- `server.py` — add `_handle_post_presence_heartbeat` and `_handle_get_presence`; add route dispatch in `do_GET` / `do_POST`
- `tests/test_presence.py` (new) — unit/integration tests for heartbeat upsert, TTL filter, RLS isolation
- `docs/ai/decisions.md` (append — confirm D6: presence table chosen over Realtime)
- `docs/ai/project-state.md` (update — reflect 022 landed)

## Tests / validation

```bash
# Syntax check
python3 -c "import server"

# Run presence tests
pytest tests/test_presence.py -v
# → all pass

# Full test suite must not regress
pytest -v
```

Manual smoke (staging, two tabs):
1. User A opens a project — browser starts sending `POST /api/presence/heartbeat` every 30 s (verify in DevTools Network tab).
2. In User B's project list, the project card shows "User A is editing" badge.
3. User A closes the project tab. Within 90 s (≤ 2 poll cycles) the badge disappears from User B's view.
4. Open DevTools for User B's tab — confirm `GET /api/presence?project_id=X` returns an empty array after the TTL expires.

TTL quick-test (SQL Editor on staging):
```sql
-- Insert a stale presence row (last_seen 2 minutes ago)
INSERT INTO public.workspace_presences (user_id, workspace_id, project_id, display_name, last_seen)
VALUES ('<uid>', '<wid>', '<pid>', 'Stale User', now() - interval '2 minutes')
ON CONFLICT (user_id) DO UPDATE SET last_seen = EXCLUDED.last_seen;

-- Query should NOT return this row
SELECT * FROM public.workspace_presences
WHERE project_id = '<pid>'
  AND last_seen > now() - interval '90 seconds';
-- → 0 rows
```

## Data-safety / out of scope

- `workspace_presences` rows are ephemeral metadata — they contain no user-generated content. There is no backup requirement; they expire naturally.
- The migration uses `CREATE TABLE IF NOT EXISTS` — safe to re-run; no data loss if applied more than once.
- `display_name` is a denormalized copy of the user's display name at heartbeat time. It is not a source of truth for auth; it is display-only.
- Out of scope: Supabase Realtime / WebSocket push — explicitly excluded per the plan non-goals.
- Out of scope: a background cron to hard-delete stale rows — TTL-at-read is sufficient for v1. A cron cleanup can be added later if the table grows large.
- Out of scope: presence for non-owner viewers (read-only visitors do not send heartbeats; the badge is "owner is editing", not "anyone is viewing").
- Out of scope: frontend presence badge rendering — that is issue 023.
