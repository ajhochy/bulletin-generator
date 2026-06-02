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
- **Supabase MCP installed** (`.mcp.json`, scoped to `?project_ref=dgydekhfzrmeoscpgmvo`, browser-OAuth, no secret committed).
- **Staging Supabase project provisioned:** `bulletin-generator` · ref `dgydekhfzrmeoscpgmvo` · org Visalia CRC · region us-west-1 · Postgres 17. API URL `https://dgydekhfzrmeoscpgmvo.supabase.co`; publishable key `sb_publishable_qrAHj2Kj5yKeWxeqy5vifA_ufX6rOzJ` (RLS-protected, not secret).
- **Tenancy foundation + RLS applied to staging** and captured at `supabase/migrations/20260602000001_tenancy_foundation.sql`: `public.profiles` (+ `handle_new_user` signup trigger, EXECUTE revoked from API roles), `workspaces`, `workspace_members`, `projects` (central), `private.is_workspace_member()` / `private.shares_workspace_with()` SECURITY DEFINER helpers, RLS policies on all four, indexes, and `authenticated` grants (anon denied). **Cross-tenant read AND write isolation verified** via simulated-JWT tests (user A/B each see only their workspace; cross-tenant read=0, write=0 rows). Security advisor clean except the leaked-password Auth toggle. This satisfies the security-critical core of plan issue 8 on the central table.
- **App ↔ Supabase connection verified (plan issue 3):** `DATABASE_URL` wired in gitignored `.env` using the **session pooler** `aws-1-us-west-1.pooler.supabase.com:5432` (the IPv6 direct host has no route from this machine; `aws-0` is the wrong pooler prefix). `db.health_check()` → `{connected: True}` and the app's psycopg stack read the new schema (APP_MODE=server). Session mode chosen per D2 for `SET LOCAL` JWT claims.

## In progress

- `feat/supabase-multitenant-electron` — integration branch. Merge independently re-verified by verification-gate in a **Python 3.11 venv** (HEAD `0feb5e0`): 939 pytest pass / 2 DB-only failures; 123 vitest pass; vite build clean; `/api/bootstrap` 200; zero conflict markers; union confirmed (collab tip is an ancestor of HEAD). **Supported interpreter is Python 3.11+** — the repo's system `python3` is 3.9 and cannot import `auth.py`; use a 3.11 venv (`pip install -r requirements.txt pytest`). Ready for the next Supabase migration issue.

## Open risks

- `_handle_get_project_revisions` (the bulk `/api/projects/revisions` endpoint from main's lightweight-poll) still reads directly from JSON file rather than routing through storage. In Postgres mode it would return all projects without auth gating. TODO marker added in server.py. This is safe for desktop mode (single-user) but must be addressed before enabling Postgres mode in production.
- stale-poll JS now uses `/api/projects/${id}/revision` (collab-v1, per-project, requires auth). This endpoint requires `_require_auth()`. In desktop mode auth is bypassed, so this works fine. In Postgres mode, the stale-poll will now require a valid session cookie.
- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic, but UI behavior (rendering, Template Designer, poll timer) is not automated and needs manual click-through.
- Two DB-dependent integration tests in `tests/test_migrations.py` (`TestIntegration::test_fresh_db_creates_all_tables`, `TestIntegration::test_second_run_is_idempotent`) require `APP_MODE=server` + live DATABASE_URL. Expected failures without a DB (provisioned in plan issue 2/3).
- `auth.py` (from collab-v1) uses `dict | None` annotations without `from __future__ import annotations`, so it hard-requires Python 3.10+ at import time. Matches the documented 3.11+ requirement but breaks on the system 3.9. Candidate one-line follow-up: add the future import for resilience.
- Minor: `server.py` imports the `cgi` module (DeprecationWarning; removed in Python 3.13). Pre-existing; replace before any 3.13 bump.
- **DB password still needed** to build the app's `DATABASE_URL` (for gitignored `.env`); the MCP cannot expose it. Without it the app can't yet connect to Supabase (the 2 DB-integration tests stay red). Schema work proceeds via MCP without it.
- **Migration-history reconciliation:** the foundation schema was applied to staging via MCP `execute_sql` (not the CLI), and the matching `supabase/migrations/*.sql` file is hand-written. When the CLI is linked (needs DB password), reconcile via `supabase migration repair --status applied 20260602000001` (or `db push`; SQL is idempotent).
- **Leaked-password protection disabled** (Supabase Auth dashboard toggle). Low priority (OAuth/magic-link focused) but enable before any password auth.

## Next step

Build the remaining Supabase data tables — `project_revisions`, `workspace_settings`, `user_settings`, `announcements`, `songs`, `templates`, `fonts` — following the verified `projects` pattern (`workspace_id` + RLS via `private.is_workspace_member` + grants; `user_settings` is per-user, `project_revisions` append-only). Then Supabase Auth provider config (issues 9–12, needs dashboard setup) and adapting `storage.py`/`db.py` to set per-request `request.jwt.claims` against the new schema (issue 7). Connection + tenancy foundation + isolation are proven.

## Resume in a new session

- **Branch:** `feat/supabase-multitenant-electron` (pushed to `origin`). `main` + production untouched.
- **Python:** use a 3.11 venv (`python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest`); system `python3` is 3.9 and cannot import `auth.py`.
- **Supabase:** staging project `dgydekhfzrmeoscpgmvo` (Visalia CRC, us-west-1). `.env` (gitignored) has `DATABASE_URL` via the **session pooler** `aws-1-us-west-1.pooler.supabase.com:5432`. GitHub repo secrets set: `DATABASE_URL`, `SUPABASE_DATABASE_PW`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`. MCP config `.mcp.json` is scoped to the project (re-auth via `/mcp` if `mcp__supabase__*` tools are missing).
- **Issues:** 19 local files in `docs/ai/generated-issues/` (001–019). To create them on GitHub: `bash scripts/create_migration_issues.sh` (idempotent; milestone "Supabase + Multi-tenant + Electron", label `supabase-migration`). NNN prefixes in titles keep the "Depends on" cross-refs resolvable.
- **Start here:** issue **001** (critical path 001→004 = finish schema + wire the app to it). Issue 005 (Auth dashboard config) and 011 (Electron scaffold) can run in parallel.
- **Decide before coding 008:** per-workspace allow-list shape — separate `workspace_invites` table vs JSONB on `workspace_settings`.
- **Do NOT redo (already done):** branch merge, Supabase provisioning, app↔DB connection, tenancy foundation (`workspaces`/`workspace_members`/`profiles`/`projects` + RLS + cross-tenant isolation proven; captured in `supabase/migrations/20260602000001_tenancy_foundation.sql`).

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
