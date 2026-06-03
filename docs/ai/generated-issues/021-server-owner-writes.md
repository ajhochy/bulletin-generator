# 021: Server + storage — enforce owner-only writes + add transfer endpoint

**Milestone:** M5  ·  **Plan ref:** Issue 021 (D9)
**Depends on:** 020

## Context

With the DB-layer RLS tightened in issue 020, this issue adds the Python-side enforcement layer that gives non-owners a clean HTTP 403 before any SQL is even attempted, and removes the now-unnecessary conflict-detection save path.

Three sub-tasks are bundled here because they all touch the same `_handle_post_projects` code path in `server.py` and the `can_write_project` helper in `storage.py`:

1. **Owner-only writes:** `can_write_project` is updated to mirror the logic already in `can_delete_project` — only the `owner_user_id` may write. Non-owner POSTs to workspace-visible projects get a 403.
2. **Conflict path removal (server side):** `save_project_transactional` is replaced with `save_project` in the normal save path. `_clientRevision` is no longer read from the POST body. `ConflictError` is left in `storage.py` as dead code (it has test coverage; a later cleanup issue can remove it).
3. **Transfer endpoint:** `POST /api/projects/{id}/transfer` lets the current owner hand the project to another workspace member atomically.

Desktop mode (`JsonStorageBackend`) is entirely unaffected — all new code is gated on `PostgresStorageBackend` / `not IS_DESKTOP`.

## Acceptance criteria

- [ ] **AC-021-1:** `POST /api/projects` by a non-owner of a workspace-visible project returns HTTP 403 (not 200, not 409).
- [ ] **AC-021-2:** `POST /api/projects` by the project owner returns HTTP 200 and the saved project dict is returned.
- [ ] **AC-021-3:** `POST /api/projects` without `_clientRevision` in the payload saves successfully — no `ConflictError` is raised; the 409 path is unreachable via the normal save route.
- [ ] **AC-021-4:** `POST /api/projects/{id}/transfer { "new_owner_user_id": "<uuid>" }` by the current owner returns 200 with the project dict showing `owner_user_id` equal to the new owner.
- [ ] **AC-021-5:** The same transfer call by a non-owner returns 403.
- [ ] **AC-021-6:** Transferring to a user who is not a workspace member returns 403 (workspace membership verified server-side before the UPDATE).
- [ ] **AC-021-7:** Desktop mode (`APP_MODE=desktop`, `APP_MODE=electron`, or `IS_DESKTOP=True`) is unaffected — `JsonStorageBackend.save_project` is called without any ownership checks; no 403 is ever raised in desktop mode.
- [ ] **AC-021-8:** `python3 -c "import server"` passes without syntax errors.
- [ ] **AC-021-9:** `pytest tests/test_server_utils.py` (and/or `tests/test_ownership.py` if new) passes — covers: non-owner 403, owner 200, transfer success, transfer by non-owner 403, transfer to non-member 403.

## Likely files

- `storage.py` — update `can_write_project`; replace `save_project_transactional` call with `save_project` in the normal save path; add `transfer_project_ownership` method to `PostgresStorageBackend`
- `server.py` — update `_handle_post_projects` to call `can_write_project` and return 403 on failure; remove `_clientRevision` read; add route handler for `POST /api/projects/{id}/transfer`; add route dispatch in `do_POST`
- `tests/test_server_utils.py` (modify) or `tests/test_ownership.py` (new) — ownership and transfer tests
- `docs/ai/decisions.md` (append — record D9: transfer endpoint design)
- `docs/ai/project-state.md` (update — reflect 021 landed)

## Tests / validation

```bash
# Syntax check
python3 -c "import server"

# Run existing + new ownership tests
pytest tests/test_server_utils.py tests/test_ownership.py -v
# → all pass

# Full test suite must not regress
pytest -v
```

Manual smoke (two browser tabs, staging):
1. Log in as User A (owner). Create a new project — it is private.
2. Share the project (set `visibility='workspace'` via settings).
3. Log in as User B (same workspace, not owner). Open project list — project is visible.
4. User B attempts to save a change → receives 403; save button should be disabled (after issue 023 lands, but the 403 is testable here via DevTools / curl).
5. User A calls `POST /api/projects/{id}/transfer` with User B's `user_id` → User B is now owner.
6. User A can no longer save the project (403); User B can.

## Data-safety / out of scope

- `save_project_transactional` and `ConflictError` are left in `storage.py` as dead code — they are not removed in this issue. Removing them is a separate cleanup after the full cutover QA passes (per plan D7).
- The `project_revisions` table and revision history/restore feature (issue 019) are entirely untouched. This issue only removes the *save-side* conflict check, not revision records.
- The transfer UPDATE is atomic: `UPDATE projects SET owner_user_id=%(new)s WHERE id=... AND owner_user_id=%(current)s`. If the caller is no longer the owner by the time the UPDATE runs, rowcount=0 → 403.
- Desktop mode data files (`data/projects.json`) are never touched by any code path introduced in this issue.
- Out of scope: frontend read-only UI state, save-button disable, presence badge — those are issue 023.
- Out of scope: the transfer UI — this issue adds only the API endpoint. A future issue or the same coding-agent pass can wire the UI.
