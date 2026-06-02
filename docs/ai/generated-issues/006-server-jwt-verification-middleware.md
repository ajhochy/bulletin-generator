# 006: Server-side Supabase JWT verification middleware

**Milestone:** M2  ·  **Plan ref:** issue 10
**Depends on:** 003, 004, 005

## Context

`auth.py` (from `collab-v1`) validates a custom Google-only session cookie against a hardcoded domain. This must be replaced with server-side Supabase JWT verification: `server.py` receives a `Bearer <token>` header, verifies the JWT signature using Supabase's JWKS or shared secret, extracts the `sub` (user UUID), resolves workspace membership from `workspace_members`, and passes verified claims to `db.transaction(claims)` so RLS applies. This is the trust boundary — client JWTs are untrusted until verified here.

## Acceptance criteria

- [ ] A `_verify_supabase_jwt(token: str) -> dict | None` function (or class-based equivalent) in `auth.py` (or a new `jwt_middleware.py`) verifies the Supabase JWT using the project's JWT secret (from `SUPABASE_JWT_SECRET` env var) or JWKS URL. Returns the decoded claims dict on success, `None` on invalid/expired.
- [ ] `server.py`'s `_require_auth()` (or equivalent) is updated to extract the `Authorization: Bearer <token>` header, call `_verify_supabase_jwt`, and, if valid, resolve the user's workspace membership from `workspace_members` (via `db.admin_transaction()` — service_role lookup of membership is acceptable here since this is a server-side check, not a user query). Returns a `(user_id, workspace_id, claims)` tuple.
- [ ] Requests with no token, an invalid token, or an expired token receive HTTP 401.
- [ ] Requests with a valid token but no membership in any workspace receive HTTP 403.
- [ ] The `/api/me` endpoint returns `{"user_id": ..., "email": ..., "workspace_id": ..., "role": ...}` for an authenticated request.
- [ ] `auth.py`'s custom Google-only session-cookie path is removed or feature-flagged off on this branch (not left as a dead code path that could bypass the new middleware).
- [ ] `tests/test_auth_middleware.py` (adapt existing) and/or new tests cover: valid token → 200 + identity, invalid token → 401, expired token → 401, valid token + no membership → 403.
- [ ] `python3 -c "import server"` and `python3 -c "import auth"` succeed.
- [ ] `SUPABASE_JWT_SECRET` is documented in `.env.example` with a placeholder and a note ("from Supabase dashboard → Settings → API → JWT Secret; server-side only").

## Likely files

- `auth.py` (replace/rewrite — remove custom Google session logic, add Supabase JWT verify)
- `server.py` (modify — update `_require_auth()` or equivalent, update all guarded routes to use new identity tuple)
- `tests/test_auth_middleware.py` (modify/extend)
- `tests/test_auth.py` (modify — update or retire tests for removed session logic)
- `.env.example` (modify — add `SUPABASE_JWT_SECRET`)

## Tests / validation

```bash
python3 -c "import server"
python3 -c "import auth"

# Unit tests (mock JWT, no DB needed):
pytest tests/test_auth_middleware.py tests/test_auth.py -v

# With DATABASE_URL + a real Supabase JWT from a logged-in test user:
DATABASE_URL=<staging> SUPABASE_JWT_SECRET=<secret> pytest tests/test_auth_middleware.py -v -k "integration"

# Full regression:
pytest -v
```

Manual smoke (after issue 007 adds frontend login): log in via the browser, confirm `GET /api/me` returns correct identity, confirm an unauthenticated request to `/api/projects` receives 401.

## Data-safety / out of scope

- `SUPABASE_JWT_SECRET` is a server-side-only secret; it must never appear in frontend JS, Electron preload, or the anon/publishable key.
- The `service_role` lookup for workspace membership in `_require_auth()` must use `db.admin_transaction()`, not the user's own claims context (bootstrapping problem: we need membership to set up the claims context).
- Out of scope: frontend login UI (issue 007); this issue covers only the server-side verification pipeline.
- Out of scope: `_handle_get_project_revisions` auth-gate open risk — that route must be updated as part of this issue (it is currently not auth-gated; adding `_require_auth()` there closes the open risk noted in project-state.md).
