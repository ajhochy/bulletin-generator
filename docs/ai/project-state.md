# Project State

_Last updated: 2026-06-03 (issue 019 done)_

## Active workflow run (Supabase + Multi-tenant + Electron, milestone #30)

Run branch: `feat/supabase-multitenant-electron`. Toolchain: 3.11 venv at `.venv`. `ai-workflow checks` wired via `scripts/run_ai_workflow.py`.

- **001–007 — DONE.** See main `docs/ai/project-state.md` for details on schema, RLS, db.py, storage, auth, and frontend auth issues.
- **019 — DONE.** `.github/workflows/ci.yml` gains a `db-integration` job (DATABASE_URL + SUPABASE_JWT_SECRET secrets, APP_MODE=server, fork-guard). `docs/ai/testing-guide.md` documents two-job CI structure. verification-gate PASS: 100 pytest / 71 vitest / vite build clean / /api/bootstrap 200.

## Current focus

Issue 019 (CI DB integration) complete. Next: issue 008 — membership provisioning on first login.

## Open risks

- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic; UI behavior (rendering, Template Designer, poll timer) is manual-only.
- `db-integration` CI job connects to staging Supabase. If staging is torn down or session-pooler DNS changes, the job will fail.

## Next step

Issue 008 (#264): membership provisioning on first login. Decide per-workspace allow-list shape before coding (separate `workspace_invites` table vs JSONB on `workspace_settings`).

## Recent coding-agent runs

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
- Concerns: The `db-integration` job connects to the staging Supabase project. If staging is torn down or the session-pooler DNS changes, the job will fail. No test-isolation cleanup is performed by `test_db.py::test_admin_transaction_bypasses_rls` — it inserts and deletes within the same tx, so this is safe.

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
