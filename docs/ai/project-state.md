# Project State

_Last updated: 2026-06-02_

## Current focus

Supabase multi-tenant + Electron migration. Branch `feat/supabase-multitenant-electron` now holds the integrated union of:
- main's Volunteer Roles stabilization (PRs #251–#253), lightweight-poll endpoint, and planning docs
- collab-v1's full Postgres storage layer, auth system, project history/revisions, multi-user conflict UX, and admin tooling

Merge commit: `b16b842` on `feat/supabase-multitenant-electron`.

Prior focus — stabilizing the Volunteer Roles feature added in releases 1.12.9 / 1.12.10 (PRs #251, #252). Recent fixes:

- #252 — Volunteer Roles cards now render after server data loads (deferred-render bug).
- #251 — Volunteer Roles render in preview + added Document menu toggle.
- #253 — Volunteer Roles elements are selectable / formattable in the Template Designer canvas. Merged.

## Recently completed

- 1.12.12 release tagged.
- collab-v1 branch merged into `feat/supabase-multitenant-electron` (commit `b16b842`). All 3 content conflicts resolved with UNION strategy.

## In progress

- `feat/supabase-multitenant-electron` — integration branch. Merge independently re-verified by verification-gate in a **Python 3.11 venv** (HEAD `0feb5e0`): 939 pytest pass / 2 DB-only failures; 123 vitest pass; vite build clean; `/api/bootstrap` 200; zero conflict markers; union confirmed (collab tip is an ancestor of HEAD). **Supported interpreter is Python 3.11+** — the repo's system `python3` is 3.9 and cannot import `auth.py`; use a 3.11 venv (`pip install -r requirements.txt pytest`). Ready for the next Supabase migration issue.

## Open risks

- `_handle_get_project_revisions` (the bulk `/api/projects/revisions` endpoint from main's lightweight-poll) still reads directly from JSON file rather than routing through storage. In Postgres mode it would return all projects without auth gating. TODO marker added in server.py. This is safe for desktop mode (single-user) but must be addressed before enabling Postgres mode in production.
- stale-poll JS now uses `/api/projects/${id}/revision` (collab-v1, per-project, requires auth). This endpoint requires `_require_auth()`. In desktop mode auth is bypassed, so this works fine. In Postgres mode, the stale-poll will now require a valid session cookie.
- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic, but UI behavior (rendering, Template Designer, poll timer) is not automated and needs manual click-through.
- Two DB-dependent integration tests in `tests/test_migrations.py` (`TestIntegration::test_fresh_db_creates_all_tables`, `TestIntegration::test_second_run_is_idempotent`) require `APP_MODE=server` + live DATABASE_URL. Expected failures without a DB (provisioned in plan issue 2/3).
- `auth.py` (from collab-v1) uses `dict | None` annotations without `from __future__ import annotations`, so it hard-requires Python 3.10+ at import time. Matches the documented 3.11+ requirement but breaks on the system 3.9. Candidate one-line follow-up: add the future import for resilience.
- Minor: `server.py` imports the `cgi` module (DeprecationWarning; removed in Python 3.13). Pre-existing; replace before any 3.13 bump.

## Next step

Supabase migration plan (`docs/ai/current-plan.md`): **issue 2 — provision a staging Supabase project + wire `DATABASE_URL`/keys** (also unblocks the 2 DB-integration tests), or first route to `issue-writer` to generate the full GitHub-ready issue set. Awaiting user direction.

## Recent coding-agent runs

### 2026-06-02 — supabase-integration-merge (issue 1)
- Files modified:
  - `server.py` — resolved route table conflict: kept both `/api/projects/revisions` (exact-match, main's bulk poll endpoint) and `/api/projects/` (prefix-match, collab-v1's history/revision subrouter). Added TODO comment to `_handle_get_project_revisions` noting it should route through storage for Postgres mode.
  - `src/js/projects.js` — resolved stale-poll conflict: adopted collab-v1's per-project `/api/projects/${id}/revision` endpoint over main's bulk-list approach; endpoint is targeted and handles 403/404 gracefully. "Reload latest" links still fetch full `/api/projects`.
  - `tests/test_server_utils.py` — resolved test-class conflict: included both `TestProjectRevisionSummary` (5 tests, from main) and `TestValidateServerConfig` (5 tests, from collab-v1).
- Checks run:
  - `python3 -c "import server"` → clean
  - `node --check src/js/projects.js` → clean
  - `pytest` → 939 passed, 2 DB-dependent failures (test_migrations.py::TestIntegration, no DATABASE_URL)
  - `npm test` (vitest) → 123 passed
  - `npm run build` → vite build clean
  - `APP_MODE=desktop python3 server.py` + `GET /api/bootstrap` → HTTP 200
- Decisions made: adopted collab-v1's per-project stale-poll endpoint (more targeted, auth-gated) over main's bulk-list approach since the rest of the function body already used the per-project API shape. Left TODO on bulk endpoint for future storage routing.
- Deviations from spec: none. Merge commit `b16b842`.
- Concerns: `_handle_get_project_revisions` is not auth-gated (returns all projects' metadata). Safe for desktop-only, must fix before Postgres mode production use.

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
