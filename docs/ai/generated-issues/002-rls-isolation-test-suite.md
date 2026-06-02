# 002: Automated RLS cross-tenant isolation test suite

**Milestone:** M1  ·  **Plan ref:** issue 8
**Depends on:** 001 (all data tables created with RLS)

## Context

Cross-tenant isolation is the security-critical guarantee of this migration: workspace A must never be able to read or write workspace B's data. The tenancy foundation already verified isolation manually on `projects` (simulated-JWT tests showed cross-tenant read=0, write=0). This issue extends that into an automated, CI-runnable test suite covering ALL tables, both read and write paths, in both directions (A→B and B→A), using `SET LOCAL request.jwt.claims` to simulate authenticated users — the same mechanism `server.py` will use (D2).

## Acceptance criteria

- [ ] `tests/test_rls_isolation.py` exists and contains at minimum one test class `TestRLSIsolation`.
- [ ] Test setup creates two workspaces (workspace_A, workspace_B) and two users (user_A member of workspace_A only, user_B member of workspace_B only) using the `service_role` connection (bypasses RLS for seed).
- [ ] For each table in `{projects, project_revisions, workspace_settings, announcements, songs, templates, fonts}`: cross-tenant SELECT by user_A on workspace_B rows returns 0 rows (not an error — RLS filters silently).
- [ ] For each writable table: cross-tenant INSERT by user_A with `workspace_id = workspace_B_id` is rejected (raises psycopg3 exception or returns 0 rows affected with `WITH CHECK` violation).
- [ ] For each table: within-workspace SELECT by user_A on workspace_A rows returns the seeded row count (not 0).
- [ ] `user_settings`: user_A cannot SELECT user_B's row (per-user isolation, not workspace isolation).
- [ ] `project_revisions`: user_A cannot SELECT revisions belonging to workspace_B projects.
- [ ] Tests are skipped gracefully (pytest `skip`) when `DATABASE_URL` env var is absent, matching the pattern in `tests/test_migrations.py::TestIntegration`.
- [ ] `pytest tests/test_rls_isolation.py` passes (all non-skipped) against the staging Supabase project with `DATABASE_URL` set.
- [ ] Test teardown removes all seeded rows (or uses a dedicated test schema / unique prefix) so repeated runs are idempotent.

## Likely files

- `tests/test_rls_isolation.py` (new)
- `tests/fixtures/` (new fixture helpers for seeding test workspaces/users if not already present)
- `db.py` (read — understand the claims-setting transaction helper from issue 003, which this test depends on)

## Tests / validation

```bash
# With DATABASE_URL set to the staging project session-pooler URL:
DATABASE_URL=<staging_session_pooler> pytest tests/test_rls_isolation.py -v

# Without DATABASE_URL (CI without DB):
pytest tests/test_rls_isolation.py -v
# → all tests should show SKIPPED (not FAILED)

# Full suite regression check:
pytest -v
```

Note: this test file is the primary deliverable — a passing run is the acceptance proof. Manual re-verification against staging is also required before M1 sign-off (security-critical per AGENTS.md + plan).

## Data-safety / out of scope

- Tests use `service_role` only for seed/teardown; all isolation assertions run as `authenticated` with `SET LOCAL request.jwt.claims`.
- `service_role` key must never appear in committed test fixtures or `.env.example` — pass via environment variable only.
- Cross-tenant isolation failures are blockers; do not merge if any cross-tenant read or write succeeds.
- Out of scope: testing RLS on `profiles`, `workspaces`, `workspace_members` (those were verified in the tenancy foundation session). This issue covers the data tables from issue 001.
- Out of scope: performance benchmarks; this is a correctness-only suite.
