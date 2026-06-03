# Project State

_Last updated: 2026-06-03 (issue 008 done)_

## Active workflow run (Supabase + Multi-tenant + Electron, milestone #30)

Run branch: `feat/supabase-multitenant-electron`. Toolchain: 3.11 venv at `.venv`. `ai-workflow checks` wired via `scripts/run_ai_workflow.py`.

- **001–007 — DONE.** See main `docs/ai/project-state.md` for details on schema, RLS, db.py, storage, auth, and frontend auth issues.
- **019 — DONE.** `.github/workflows/ci.yml` gains a `db-integration` job (DATABASE_URL + SUPABASE_JWT_SECRET secrets, APP_MODE=server, fork-guard). `docs/ai/testing-guide.md` documents two-job CI structure. verification-gate PASS: 100 pytest / 71 vitest / vite build clean / /api/bootstrap 200.
- **008 — DONE.** Commits `0074566` + `9eb881e`. `auth.provision_first_login(user_id, email)` added: queries `workspace_settings.settings->'allowed_domains'` JSONB array for domain match (derived from verified JWT email claim), inserts `workspace_members` row with `role='editor'` via `db.admin_transaction()` (ON CONFLICT DO NOTHING for race-safety), returns new membership. Wired into `authenticate_authorization_header()` after `resolve_workspace_membership()` returns None — existing members skip provisioning entirely. `tests/test_auth_middleware.py` gains `TestFirstLoginProvisioning` (3 tests). `MANUAL-STEPS.md` section 7 documents allow-list management SQL. Verification: 100 pytest + 71 vitest + vite build PASS. No live-DB integration test for provisioning path (staging smoke needed before production).

## Current focus

Issues 008 and 019 complete. Next: next issue in sequence (check `docs/ai/generated-issues/`).

## Open risks

- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic; UI behavior (rendering, Template Designer, poll timer) is manual-only.
- `db-integration` CI job connects to staging Supabase. If staging is torn down or session-pooler DNS changes, the job will fail.
- `provision_first_login` has no live-DB integration test. Before production, seed a `workspace_settings` row with `allowed_domains` on staging and smoke-test a new user sign-in from that domain.

## Next step

Issues 008 and 019 are done. Move to the next issue in sequence. Before smoke-testing issue 008 end-to-end on staging, seed a `workspace_settings` row with an `allowed_domains` entry per `MANUAL-STEPS.md` section 7, then sign in with a new user from that domain and confirm auto-provisioning fires.

## Resume in a new session

- **Branch:** `feat/supabase-multitenant-electron` (pushed to `origin`). `main` + production untouched.
- **Python:** use a 3.11 venv (`python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest`); system `python3` is 3.9 and cannot import `auth.py`.
- **Supabase:** staging project `dgydekhfzrmeoscpgmvo` (Visalia CRC, us-west-1). `.env` (gitignored) has `DATABASE_URL` via the **session pooler** `aws-1-us-west-1.pooler.supabase.com:5432`. GitHub repo secrets set: `DATABASE_URL`, `SUPABASE_DATABASE_PW`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`. MCP config `.mcp.json` is scoped to the project (re-auth via `/mcp` if `mcp__supabase__*` tools are missing).
- **Issues:** 19 local files in `docs/ai/generated-issues/` (001–019). To create them on GitHub: `bash scripts/create_migration_issues.sh` (idempotent; milestone "Supabase + Multi-tenant + Electron", label `supabase-migration`). NNN prefixes in titles keep the "Depends on" cross-refs resolvable.
- **Start here:** next issue after 008. Issues 005, 007, 008, 019 are complete as of 2026-06-03.
- **Do NOT redo (already done):** branch merge, Supabase provisioning, app↔DB connection, tenancy foundation, JWT middleware, frontend auth, first-login provisioning, CI DB integration.

## Recent coding-agent runs

### 2026-06-03 — first-login-provisioning (issue 008 / #264)
- Files modified:
  - `auth.py` — Added `provision_first_login(user_id, email)` helper. Queries `workspace_settings.settings->'allowed_domains'` JSONB array for domain match, inserts `workspace_members` row (`role='editor'`) via `db.admin_transaction()`, returns new membership dict. Wired into `authenticate_authorization_header()` after `resolve_workspace_membership()` returns None.
  - `tests/test_auth_middleware.py` — Added `TestFirstLoginProvisioning` class (3 tests): allow-listed domain gets editor membership, unlisted domain gets 403, existing member skips provisioning.
  - `MANUAL-STEPS.md` — Added section 7: allow-list management SQL (add/remove domain, UPSERT for new workspace rows, verify query) with security notes.
- Checks run:
  - `.venv/bin/python -c "import auth"` → pass.
  - `.venv/bin/python -m pytest tests/test_auth_middleware.py -v` → 16 passed (13 original + 3 new).
  - `scripts/run_ai_workflow.py checks --level issue` → PASS (100 pytest CI-subset, 71 vitest).
  - `scripts/run_ai_workflow.py checks --level pr` → PASS (100 pytest, 71 vitest, vite build).
- Decisions made:
  - Used JSONB `allowed_domains` key on existing `workspace_settings.settings` column rather than a new table — avoids a schema migration for a key that only operators write to. See `docs/ai/decisions.md` 2026-06-03 entry.
  - `COALESCE(settings->'allowed_domains', '[]'::jsonb)` in the SQL guard prevents errors when the key is absent.
  - `ON CONFLICT (workspace_id, user_id) DO NOTHING` in INSERT makes the provisioning path race-safe.
  - Domain is extracted from the verified JWT `email` claim, never from `user_metadata`.
  - `provision_first_login` is called from `authenticate_authorization_header` only when `resolve_workspace_membership` returns None — no change to the happy-path for existing members.
- Deviations from spec: none.
- Concerns:
  - `provision_first_login` requires `db.admin_transaction()` which needs `SUPABASE_SERVICE_ROLE_URL` or `DATABASE_URL` in env. In desktop mode `IS_DESKTOP=True` skips `_get_authenticated_user()` entirely, so provisioning is never called. Safe.
  - No DB-live integration test for provisioning (would require staging with `workspace_settings` row). The unit tests mock the DB layer. A live smoke would be needed to validate the SQL against the actual staging schema.

### 2026-06-03 — ci-db-integration (issue 019)
- Files modified:
  - `.github/workflows/ci.yml` — Added `db-integration` job: runs `pytest tests/test_migrations.py tests/test_rls_isolation.py tests/test_db.py -m integration -q` with `DATABASE_URL`, `SUPABASE_JWT_SECRET` from GitHub Secrets and `APP_MODE=server`. Guarded by `if: github.repository == 'ajhochy/bulletin-generator'` so forks without secrets do not fail.
  - `docs/ai/testing-guide.md` — Updated intro sentence and added "CI structure (two jobs)" section documenting the `js`, `python`, and `db-integration` jobs, their DB requirements, fork-safety, and local equivalent command.
- Checks run:
  - `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` → YAML valid.
  - `ai-workflow checks --level issue` → PASS: 100 pytest passed (0 DB), 71 vitest passed.
- Decisions made:
  - `db-integration` is a separate job (not a step in `python`) so forks see the two non-DB jobs as always-green and the conditional DB job as simply skipped. This matches the standard pattern for secrets-gated CI.
  - `pip install -r requirements.txt` before the test step because `psycopg[binary]` is required to connect; base `pytest` install alone is insufficient.
  - Only `SUPABASE_JWT_SECRET` added beyond `DATABASE_URL`; `SUPABASE_URL` and `SUPABASE_ANON_KEY` are browser-safe and not needed server-side for these tests. `SUPABASE_DATABASE_PW` is embedded in `DATABASE_URL` already.
- Deviations from spec: none.
- Concerns: The `db-integration` job connects to the staging Supabase project. If staging is torn down or the session-pooler DNS changes, the job will fail.

### 2026-05-28 — lightweight-projects-poll
- Files modified:
  - `server.py` — added `_project_revision_summary(projects)` helper and `_handle_get_project_revisions` handler + exact-match GET route `/api/projects/revisions` (metadata-only: id/revision/updatedAt/updatedBy, omits heavy base64-image `state`).
  - `src/js/projects.js` — `startStaleCheck()` 30s poll now calls `/api/projects/revisions` instead of `/api/projects`. The two explicit "Reload latest" click handlers still fetch full `/api/projects` (they need full state).
  - `tests/test_server_utils.py` — added `TestProjectRevisionSummary` (5 contract tests).
  - `docs/ai/contracts/lightweight-projects-poll.json` — acceptance contract.
- Why: the 30s stale-check poll downloaded the entire projects.json (~8.4 MB, base64 cover/logo images) every cycle. Across multiple open tabs this transferred ~279 GB over a few weeks and inflated RSS. The poll only needs revision metadata.
- Checks run: `pytest tests/test_server_utils.py::TestProjectRevisionSummary` → 5 passed (red→green confirmed). Full verification pending verification-gate.
- Deviations from spec: none.
- Concerns: frontend poll behavior (contract criterion `lightweight-poll-c3`) is manual-smoke-only — no module seam for the polling timer. Confirm via browser Network tab that the 30s poll hits `/api/projects/revisions` with a small response.
