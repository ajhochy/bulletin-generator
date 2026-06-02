# 003: db.py per-request JWT claims plumbing

**Milestone:** M1  ·  **Plan ref:** issue 7
**Depends on:** 001, 002

## Context

Decision D2 requires that `server.py` connect to Supabase as the `authenticated` role and, per transaction, execute `SET LOCAL role authenticated` and `SET LOCAL request.jwt.claims = '<json>'` so that Postgres RLS policies can see `auth.uid()` and `auth.jwt()`. The connection proven in the foundation work (`db.health_check()` via session pooler aws-1, port 5432) establishes connectivity; this issue adds the per-request claims mechanism and a service_role admin path. Without this, RLS would evaluate `auth.uid()` as NULL and deny all authenticated queries even for valid users.

## Acceptance criteria

- [ ] `db.py` exports a context-manager (e.g. `db.transaction(claims: dict)`) that: opens a psycopg3 connection, executes `SET LOCAL role authenticated` and `SET LOCAL request.jwt.claims = %s` (JSON-serialized claims) at the start of the transaction, and rolls back on exception.
- [ ] The `claims` dict must include at minimum `{"sub": "<user_uuid>"}` to satisfy `auth.uid()` in RLS; the full JWT claims dict (as issued by Supabase) must also pass through so `auth.jwt()` works in future policies.
- [ ] A separate `db.admin_transaction()` path connects using the `service_role` connection string (from a distinct env var, e.g. `SUPABASE_SERVICE_ROLE_URL` or derived from `DATABASE_URL` by replacing the key) and does NOT set JWT claims — this path bypasses RLS and is for seed/migration only.
- [ ] Psycopg3 prepared statements are disabled (`prepare_threshold=None` or `autocommit=False` with explicit connection option) on the session-pooler connection to avoid "prepared statement already exists" errors across pooled sessions. (Note D2: session pooler 5432 was chosen over transaction pooler 6543 precisely to allow `SET LOCAL`; nonetheless, disabling prepared statements avoids edge cases if the pooler reuses a backend connection.)
- [ ] `tests/test_db.py` contains at least: `test_health_check_connects`, `test_transaction_sets_auth_uid`, `test_admin_transaction_bypasses_rls`. All pass against staging DB; all skip gracefully when `DATABASE_URL` is absent.
- [ ] `test_transaction_sets_auth_uid`: within a `db.transaction({"sub": user_A_uuid})` block, `SELECT (select auth.uid())` returns `user_A_uuid`.
- [ ] `python3 -c "import db"` succeeds (no import errors).

## Likely files

- `db.py` (modify — add `transaction()` and `admin_transaction()` context managers)
- `tests/test_db.py` (modify — add the three new tests)
- `.env.example` (modify — document `SUPABASE_SERVICE_ROLE_URL` or equivalent, with a placeholder and a note that it is server-side only)

## Tests / validation

```bash
# Syntax check:
python3 -c "import db"

# With DATABASE_URL set:
DATABASE_URL=<staging_session_pooler> pytest tests/test_db.py -v

# Without (CI):
pytest tests/test_db.py -v
# → all skip

# Full regression:
pytest -v
```

## Data-safety / out of scope

- The `service_role` key / admin connection string must NEVER be committed to the repo, bundled in the Electron app, or logged.
- `db.admin_transaction()` must only be called from seed/migration scripts, never from a request handler in `server.py`.
- Out of scope: route-level auth middleware (that is issue 006); this issue is purely the DB-level transaction helper.
- Out of scope: connection pooling tuning beyond disabling prepared statements — that is a production-ops concern once real load is known.
