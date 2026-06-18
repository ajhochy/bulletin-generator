---
date: 2026-06-03
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# Project ownership model: private-by-default, presence via DB heartbeat, conflict detection removed

> **SUPERSEDED 2026-06-04 (see entry above):** the "private-by-default" half was abandoned in favor of model A (workspace-visible by default + hand-off). The presence/heartbeat and conflict-detection-removal decisions below still stand.

**Context.** New planning effort (issues 020–024) introduces a formal ownership and sharing model to replace the concurrent-edit assumption that underpinned 409 conflict detection.

**D6 — Presence via `workspace_presences` table with 60s heartbeat / 90s TTL read filter.**
Supabase Realtime (WebSocket Broadcast/Presence channels) was explicitly excluded from scope ("no WebSockets"). A simple `workspace_presences` table with per-user upsert and a `last_seen > now() - 90s` read filter is the entire implementation. No background cleanup job required for v1 — rows expire from the query's perspective. The heartbeat interval matches the removed stale-check poll interval (30s) so the network budget is identical.

**D7 — Conflict detection removed; `save_project_transactional` / `ConflictError` left as dead code temporarily.**
With owner-only writes, two users can never both have write access to the same project simultaneously, so revision-mismatch conflicts cannot occur. The 409 path is removed from `_handle_post_projects` and `startStaleCheck`/conflict-banner/dialog are removed from `projects.js`. `ConflictError` and `save_project_transactional` in `storage.py` are kept (dead code) until after the cutover QA passes to avoid breaking existing tests; a follow-up cleanup issue can remove them. The `/api/projects/revisions` endpoint (added for the stale poll in the `2026-05-28` entry) is removed.

**D8 — Visibility default change is a DB migration + Python INSERT constant change.**
The `projects` table default changes from `'workspace'` to `'private'` via a new migration file (`supabase/migrations/20260604000001_private_default.sql`). The INSERT in `PostgresStorageBackend.save_project` (storage.py ~L643) hardcodes `'workspace'` — must change to `'private'`. Existing rows keep `'workspace'`; no backfill. The `projects_update` RLS policy is tightened to `owner_user_id = auth.uid()` only (dropping the `visibility = 'workspace' OR ...` alternative).

**D9 — Transfer ownership via guarded server endpoint, not direct RLS.**
`POST /api/projects/{id}/transfer` verifies at the Python layer that (a) the caller is the current owner and (b) the new owner is a workspace member. The single `UPDATE ... WHERE id=... AND owner_user_id=%(caller)s` is atomic and correctly handled by the existing `owner_user_id = auth.uid()` RLS update policy.

**Consequences.**
- Issues 020–024 encode these decisions.
- The QA matrix (`docs/ai/qa-matrix-m5.md`) items C1–C3 (conflict detection) become moot after issue 023 and are replaced with write-protection + presence checks in issue 024.
- `testing-guide.md` "409 conflict" manual smoke item must be removed after issue 023.
