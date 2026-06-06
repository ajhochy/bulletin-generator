# 004: Adapt storage.py to multi-tenant schema

**Milestone:** M1  ·  **Plan ref:** issues 5 + 7 (combined)
**Depends on:** 001, 003

## Context

`storage.py`'s `PostgresStorageBackend` was written for `collab-v1`'s single-tenant schema: it references `collab-v1`'s `users`/`sessions` tables (replaced by Supabase Auth + `public.profiles`), lacks `workspace_id` scoping on every query, and does not call `db.transaction(claims)` to set per-request JWT claims. This issue adapts it to the new multi-tenant schema so that every read/write is scoped to the caller's workspace and executed under their JWT claims — making RLS the real enforcement layer (D2).

## Acceptance criteria

- [ ] Every `PostgresStorageBackend` method that reads or writes a data table (`projects`, `project_revisions`, `workspace_settings`, `announcements`, `songs`, `templates`, `fonts`) uses `db.transaction(claims)` from issue 003 — no raw connection calls that skip claim-setting.
- [ ] All queries include an explicit `workspace_id = %(workspace_id)s` WHERE clause (or INSERT column) — defense-in-depth on top of RLS, not instead of it.
- [ ] References to `collab-v1`'s `users` table are replaced by `auth.users` / `public.profiles` lookups; references to `collab-v1`'s `sessions` table are removed (Supabase Auth owns sessions).
- [ ] `PostgresStorageBackend.__init__` accepts a `workspace_id: str` and a `user_claims: dict` (the decoded Supabase JWT payload) so that route handlers can instantiate it per-request with the verified identity.
- [ ] `get_project(project_id)` returns `None` (not an exception) when the project exists but belongs to a different workspace (RLS will return 0 rows; `storage.py` should not leak the difference between "not found" and "forbidden").
- [ ] `tests/test_storage.py` and `tests/test_storage_routing.py` pass without modification OR are updated to match the new constructor signature; no existing passing tests are newly broken.
- [ ] New test: `tests/test_storage_multi_tenant.py` — at minimum `test_get_project_wrong_workspace_returns_none` and `test_save_project_scoped_to_workspace` (skip if no DATABASE_URL).
- [ ] `python3 -c "import storage"` succeeds.

## Likely files

- `storage.py` (modify — workspace_id scoping, db.transaction(claims) calls, remove collab-v1 users/sessions references)
- `db.py` (read — use transaction helper from issue 003)
- `tests/test_storage.py` (modify — update constructor calls if needed)
- `tests/test_storage_routing.py` (modify — same)
- `tests/test_storage_multi_tenant.py` (new)

## Tests / validation

```bash
python3 -c "import storage"

# With DATABASE_URL:
DATABASE_URL=<staging> pytest tests/test_storage.py tests/test_storage_routing.py tests/test_storage_multi_tenant.py -v

# Without DATABASE_URL:
pytest tests/test_storage.py tests/test_storage_routing.py tests/test_storage_multi_tenant.py -v
# → DB-dependent tests skip; others pass

# Full regression:
pytest -v
```

Manual smoke (server mode, after issue 006 adds auth middleware): load a project, save a change, confirm it round-trips in the Supabase dashboard.

## Data-safety / out of scope

- The `user_claims` dict passed to `PostgresStorageBackend` must come from a verified JWT (see issue 006), never from a raw client header.
- Never pass `service_role` credentials through `PostgresStorageBackend`; that path is `db.admin_transaction()` for seed scripts only.
- Out of scope: Supabase Storage URL handling for images/fonts (issues 009 and 010); this issue only covers database table queries.
- Out of scope: the `_handle_get_project_revisions` auth-gate open risk (noted in project-state.md) — that is a server.py route concern, not a storage.py concern.
