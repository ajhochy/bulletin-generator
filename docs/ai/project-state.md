# Project State

_Last updated: 2026-06-03 (issue 009)_

## Active workflow run (Supabase + Multi-tenant + Electron, milestone #30)

Run branch: `feat/supabase-multitenant-electron` (stacking all issues; one PR for the run). Toolchain: 3.11 venv at `.venv` (gitignored). `ai-workflow checks` now wired via `scripts/run_ai_workflow.py` to the real CI suite (pytest subset + vitest + vite build); `vite.config.js` excludes `.claude/**` so stale agent worktrees no longer inject phantom specs. User authorized psql apply+verify against **staging** `dgydekhfzrmeoscpgmvo` for this run (DATABASE_URL in gitignored `.env`, session pooler). Policy: pause-and-hand-off at any issue needing external setup (Supabase dashboard, OAuth secrets, signing certs).

- **001 (#257) — DONE.** `supabase/migrations/20260602000002_data_tables.sql` (commit `d971025`). 7 tables — `project_revisions` (append-only: select+insert only), `workspace_settings`, `user_settings` (per-user RLS on `auth.uid()`), `announcements`, `songs`, `templates`, `fonts` — on the proven foundation pattern. Applied+verified on staging: 7 tables, RLS on all, append-only/per-user policies confirmed, anon zero-priv, idempotent re-run (exit 0). verification-gate PASS.
- **002 (#258) — DONE.** `tests/test_rls_isolation.py::TestRLSIsolation` (commit `d3e30ba`). Seeds 2 workspaces/users via owner conn, asserts isolation as `authenticated` via `set local role` + `request.jwt.claims` GUC (the D2 mechanism). 23 tests: cross-tenant SELECT=0 both directions × 7 tables, cross-tenant INSERT rejected × 7, within-workspace visible, user_settings per-user, project_revisions cross-tenant. **23 passed on staging; 23 skip without DATABASE_URL** (CI-safe). NOT yet in CI pytest subset — that's issue 019.
- **003 (#259) — DONE.** `db.py` (commit `a2ae6fd`). `transaction(claims=None)` now optionally sets `SET LOCAL role authenticated` + `request.jwt.claims` (D2) — **claims optional, so the 23 existing no-arg callers in auth.py/storage.py are unchanged**. New `admin_transaction()` (uses `SUPABASE_SERVICE_ROLE_URL` else falls back to `DATABASE_URL`; no claims → bypasses RLS; seed/migration only). `get_connection()` adds `prepare_threshold=None` (pooler-safe). `tests/test_db.py::TestDbIntegration` (3 tests, skip w/o DATABASE_URL): 25 test_db + 23 rls = 48 passed on staging. `.env.example` documents `SUPABASE_SERVICE_ROLE_URL`.
- **004 (#260) — DONE.** `storage.py` PostgresStorageBackend rewritten for the multi-tenant schema (commit `04cffe0`, coding-agent + verification-gate). `__init__(workspace_id=None, user_claims=None)` **both optional → fully backward-compatible** (no-arg `get_storage()` + server.py routes + 87 tests unchanged). Methods use `db.transaction(claims)`, add `workspace_id` scoping. Schema reconciliation: `projects.id` is **text** (dropped `::uuid` casts), `created_by_user_id`/`updated_by_user_id` replace old email columns; **attribution preserved via LEFT JOIN to `public.profiles` aliased to legacy keys** (`updatedBy`/`createdBy`, 409 conflict payload, revision `saved_by_*`). Removed dead `_pg_upsert_org_setting`. `tests/test_storage_multi_tenant.py` (12 tests). **262 pass w/o DB; 219 pass on staging** (full DB suite incl. the previously-red `test_migrations` integration tests, now green). **Critical path 001→004 COMPLETE.**
- **005 (#261) — DONE / MANUALLY VALIDATED.** `MANUAL-STEPS.md` documents staging Supabase Auth provider setup: URL configuration, Google OAuth callback URL, email magic-link validation, custom SMTP fields and built-in-mailer limits, leaked-password protection, and manual v1 workspace membership seeding. User reported issue 005 validation complete on 2026-06-03: Google OAuth provider, email magic-link provider/session issuance, SMTP/staging-mailer decision, leaked-password protection status, and seeded membership prerequisites are no longer blocking issue 007. No `server.py`/`auth.py` changes were made for issue 005.
- **006 (#262) — DONE.** Commit `bfd0f44` replaces collab-v1 cookie auth with server-side Supabase JWT verification, resolves workspace membership through `db.admin_transaction()`, scopes protected storage access with `get_storage(workspace_id, user_claims)`, returns `/api/me` identity, disables legacy `/auth/google/*`, and auth-gates `/api/projects/revisions` through scoped storage. Verification on `bfd0f44`: imports OK; stale-reference grep clean; auth/project regression suite 198 passed; `scripts/run_ai_workflow.py checks --level issue` PASS; `checks --level pr` PASS; server-mode smoke returned 401 for unauthenticated `/api/me`, `/api/projects/revisions`, and `/api/bootstrap`; live DB migration integration (`set -a; source .env; APP_MODE=server pytest tests/test_migrations.py -m integration`) passed 2/2 with escalated network.
- **007 (#263) — DONE / MANUAL SMOKE PASS.** Commits `e3bd69e` and `db2ceac` add frontend Supabase login/logout, magic-link support, Bearer token attachment, runtime public Supabase config, and ES256 JWT/PKCE session handling. Verification: static checks pass; `ai-workflow checks --level issue` PASS; `ai-workflow checks --level pr` PASS; login-gate screenshots captured at `/tmp/bulletin-generator-verification/issue-007-login-fixed.png` and `/tmp/bulletin-generator-verification/issue-007-login-after-005.png`. Manual smoke reported by user on 2026-06-03: Google OAuth pass, magic-link pass, sign-out pass. Post-smoke artifact: `.agent-stack/postmortems/2026-06-03-issue-007.json`.
- **009 — DONE.** `storage_assets.py` (new, 196 lines): `extract_and_upload_images()` uploads base64 cover/logo images to Supabase Storage bucket `project-assets` via `urllib.request`, returns public Storage URLs, falls back silently to base64 on any upload failure. `storage.py`: wired into `PostgresStorageBackend.save_project()` and `save_project_transactional()` before JSONB serialization (only when `workspace_id is not None`). `.env.example`: added `SUPABASE_SERVICE_ROLE_KEY` (HTTP JWT service-role key for Storage, distinct from `SUPABASE_SERVICE_ROLE_URL` Postgres URL). `tests/test_storage_assets.py` (29 tests): upload mock, URL return, fallback-to-base64 on network/auth error, desktop bypass, header assertions, env-var reads, storage.py integration wiring — all pass. `ai-workflow checks --level issue` PASS (100 pytest + 71 vitest); `checks --level pr` PASS (+ vite build). Commits: `6c3381c` (feat) + `2358c0d` (docs). **Requires manual setup: `project-assets` bucket must exist and be public in Supabase dashboard; `SUPABASE_SERVICE_ROLE_KEY` must be set in deployment env.** Decision D6 recorded in `docs/ai/decisions.md`.

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

- **Issue 009 Storage pre-requisites (manual):** `project-assets` Supabase Storage bucket must be created and set public in the dashboard; `SUPABASE_SERVICE_ROLE_KEY` (HTTP JWT service-role key, NOT the Postgres URL) must be in the deployment env. Until set, images are stored as base64 in JSONB (safe fallback). No data loss risk.
- stale-poll JS now uses `/api/projects/${id}/revision` (collab-v1, per-project, requires auth). In desktop mode auth is bypassed, so this works fine. In Postgres mode, issue 007 now attaches a Supabase Bearer token from `apiFetch()` and auth smoke has passed.
- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic, but UI behavior (rendering, Template Designer, poll timer) is not automated and needs manual click-through.
- Two DB-dependent integration tests in `tests/test_migrations.py` (`TestIntegration::test_fresh_db_creates_all_tables`, `TestIntegration::test_second_run_is_idempotent`) require `APP_MODE=server` + live DATABASE_URL loaded from `.env`. They pass against staging when run with network access; they still fail/skip in sandboxed or DB-less runs.
- Minor: `server.py` imports the `cgi` module (DeprecationWarning; removed in Python 3.13). Pre-existing; replace before any 3.13 bump.
- **DATABASE_URL is present in gitignored `.env`** and points at the staging Supabase session pooler. Shell-sourcing `.env` emits two harmless `command not found` lines for non-shell-formatted Google placeholders, but the DB variables load sufficiently for integration tests. Network/DNS sandboxing still requires escalation for live Supabase tests.
- **Migration-history reconciliation:** the foundation schema (`20260602000001`) was applied via MCP and `20260602000002_data_tables.sql` via direct `psql` — neither through the CLI, so `supabase_migrations.schema_migrations` does not exist yet. When the CLI is linked (needs DB password), reconcile via `supabase migration repair --status applied 20260602000001 20260602000002` (or `db push`; both files are idempotent).

## Next step

Issue 009 (Storage images) complete. Issue 008 (#264) — membership provisioning on first login — is the next critical-path item. Decide per-workspace allow-list shape before coding (separate `workspace_invites` table vs JSONB on `workspace_settings`). Issue 014 (font files to Storage) depends on this pattern and can follow.

## Resume in a new session

- **Branch:** `feat/supabase-multitenant-electron` (pushed to `origin`). `main` + production untouched.
- **Python:** use a 3.11 venv (`python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest`); system `python3` is 3.9 and cannot import `auth.py`.
- **Supabase:** staging project `dgydekhfzrmeoscpgmvo` (Visalia CRC, us-west-1). `.env` (gitignored) has `DATABASE_URL` via the **session pooler** `aws-1-us-west-1.pooler.supabase.com:5432`. GitHub repo secrets set: `DATABASE_URL`, `SUPABASE_DATABASE_PW`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`. MCP config `.mcp.json` is scoped to the project (re-auth via `/mcp` if `mcp__supabase__*` tools are missing).
- **Issues:** 19 local files in `docs/ai/generated-issues/` (001–019). To create them on GitHub: `bash scripts/create_migration_issues.sh` (idempotent; milestone "Supabase + Multi-tenant + Electron", label `supabase-migration`). NNN prefixes in titles keep the "Depends on" cross-refs resolvable.
- **Start here:** issue **008** membership provisioning on first login. Issues 005, 007, 009 are complete as of 2026-06-03. Issue 009 (Storage images) adds `storage_assets.py` and requires `SUPABASE_SERVICE_ROLE_KEY` (HTTP JWT) in the env and a public `project-assets` bucket in the Supabase dashboard.
- **Decide before coding 008:** per-workspace allow-list shape — separate `workspace_invites` table vs JSONB on `workspace_settings`.
- **Do NOT redo (already done):** branch merge, Supabase provisioning, app↔DB connection, tenancy foundation (`workspaces`/`workspace_members`/`profiles`/`projects` + RLS + cross-tenant isolation proven; captured in `supabase/migrations/20260602000001_tenancy_foundation.sql`).

## Recent coding-agent runs

### 2026-06-03 — storage-assets-image-upload (issue 009)
- Files modified:
  - `storage_assets.py` (new) — `extract_and_upload_images()`, `upload_image()`, `is_base64_data_uri()`, `_parse_data_uri()`. Handles base64→Storage URL replacement via Supabase Storage REST API using `urllib.request`. Falls back to base64 silently on any failure. No-op when `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` are unset (desktop bypass).
  - `storage.py` — Added calls to `extract_and_upload_images()` at the top of `PostgresStorageBackend.save_project()` and `save_project_transactional()`. Only fires when `workspace_id is not None`.
  - `.env.example` — Added `SUPABASE_SERVICE_ROLE_KEY` documentation (HTTP JWT service-role key for Storage uploads, distinct from `SUPABASE_SERVICE_ROLE_URL` Postgres URL).
  - `tests/test_storage_assets.py` (new) — 29 unit tests covering: upload mock, public URL return, fallback-to-base64 on network/auth error, desktop mode bypass (no URL / no key), existing-URL passthrough, header assertions, env-var reads, storage.py integration wiring.
- Checks run:
  - `python3.11 -c "import storage_assets; import storage; import server"` → pass.
  - `.venv/bin/python3.11 -m pytest tests/test_storage_assets.py -v` → 29 passed.
  - `ai-workflow checks --level issue` → PASS: 100 pytest passed; 71 vitest passed.
  - `ai-workflow checks --level pr` → PASS: 100 pytest passed; 71 vitest passed; vite build clean.
- Decisions made:
  - Introduced `SUPABASE_SERVICE_ROLE_KEY` as a new env var (HTTP JWT service-role key) rather than repurposing `SUPABASE_SERVICE_ROLE_URL` (which is a Postgres connection string). These are structurally different — the Storage REST API needs a JWT Bearer token, not a Postgres URL. See also docs/ai/decisions.md.
  - Upload placed in `storage.py` `save_project` / `save_project_transactional` (before `_json.dumps`) so the stored JSONB state never contains base64 after a successful upload. This is the single controlled chokepoint for all project saves.
  - `workspace_id is None` guard prevents upload attempts in un-scoped / desktop-mode calls.
  - Desktop mode bypass: if either `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` is unset, `extract_and_upload_images` returns immediately — existing base64 preserved.
- Deviations from spec:
  - Issue spec named the env var `SUPABASE_SERVICE_ROLE_URL` for Storage HTTP calls; that is already a Postgres connection string. Introduced `SUPABASE_SERVICE_ROLE_KEY` (JWT) instead to avoid ambiguity. Documented in `.env.example` and decisions.md.
  - `save_project_transactional` integration test not added (would require mocking the complex conflict-check / revision-insert SQL chain); the `save_project` integration test confirms the wiring pattern is identical and the unit tests cover the `extract_and_upload_images` function exhaustively.
- Concerns:
  - `SUPABASE_SERVICE_ROLE_KEY` must be set in the deployment environment for uploads to work; without it, images will continue to be stored as base64 in JSONB (safe fallback, not a data-loss risk).
  - The `project-assets` bucket must exist and be configured as public in the Supabase dashboard before URLs will render correctly. This is a manual setup step (out of scope for this issue).
  - `staffLogoUrl` is a workspace-level setting (stored in `workspace_settings` via `/api/settings`), but the project dict also carries a copy (saved in project state for backward compat). The upload here covers the project-state copy. Deduplicated uploads are idempotent due to the `x-upsert: true` header.

### 2026-06-03 — frontend-supabase-login-token-attach (issue 007 / #263)
- Files modified:
  - `package.json`, `package-lock.json` — Added `@supabase/supabase-js` for browser Supabase Auth.
  - `src/js/main.js` — Replaces legacy `auth.js` in the load order with Supabase browser bundle/config/auth UI scripts.
  - `src/js/supabase-browser.js` — Adds a safe placeholder for the local script path; `server.py` dynamically serves this path from the installed `@supabase/supabase-js` UMD browser bundle.
  - `src/js/supabase-config.js` — Adds a safe default browser config file; `server.py` dynamically serves the same path from environment values in server mode.
  - `src/js/auth-ui.js` — Adds `initAuth()`, Google OAuth, magic-link, sign-out, current-session/user accessors, login/app visibility gating, and `/api/me` identity confirmation with the Supabase access token.
  - `src/js/api.js` — Attaches `Authorization: Bearer <access_token>` from `getSession()` to API requests.
  - `index.html` — Replaces the disabled legacy Google-login link with Supabase-driven Google + magic-link login controls and keeps app UI hidden until authenticated.
  - `server.py` — Exposes public Supabase URL/anon key through `_public_config()` and dynamically serves `/src/js/supabase-config.js` with no-store caching.
  - `.env.example` — Documents browser-safe `SUPABASE_URL` and `SUPABASE_ANON_KEY` separately from server-only `SUPABASE_JWT_SECRET`.
  - `tests/auth-ui.spec.js` — Adds the required no-session and active-session `initAuth()` coverage.
- Checks run:
  - `node --check src/js/auth-ui.js` → pass.
  - `node --check src/js/api.js` → pass.
  - `node --check src/js/app.js` → pass.
  - `node --check src/js/main.js` → pass.
  - `.venv/bin/python -c "import server; print('server import OK')"` → pass.
  - `npm test -- tests/auth-ui.spec.js` → 2 passed.
  - `npm run build` → pass.
  - `npm test` → 71 passed.
  - `ai-workflow checks --level issue` → PASS: 100 pytest passed; 71 vitest passed.
  - `ai-workflow checks --level pr` → PASS: 100 pytest passed; 71 vitest passed; vite build passed.
  - Server-mode smoke on `http://localhost:8766/` → `/api/me` returns 401 unauthenticated; `/src/js/supabase-browser.js` and `/src/js/auth-ui.js` served from the patched branch; screenshot captured at `/tmp/bulletin-generator-verification/issue-007-login-fixed.png` (21 KB) showing login gate with Google + magic-link controls and app hidden.
  - 2026-06-03 post-issue-005 rerun: `node --check src/js/auth-ui.js && node --check src/js/api.js && node --check src/js/app.js && node --check src/js/main.js && .venv/bin/python -c "import server"` → pass; `ai-workflow checks --level issue` → PASS (100 pytest passed, 71 vitest passed); `ai-workflow checks --level pr` → PASS (100 pytest passed, 71 vitest passed, vite build passed); visual screenshot `/tmp/bulletin-generator-verification/issue-007-login-after-005.png` (21 KB) shows login gate with Google + magic-link controls and app hidden.
- Decisions made:
  - Kept the app's legacy script loading model: `server.py` serves the installed Supabase UMD browser bundle at `/src/js/supabase-browser.js` before `auth-ui.js`, so the direct static server does not need a browser import map or Vite dev server.
  - Served `/src/js/supabase-config.js` dynamically from `server.py` so public Supabase config comes from environment values without hardcoding deployment keys in source; the checked-in file is an empty safe fallback for Vite builds.
  - `initAuth()` confirms an active Supabase session against `/api/me` before showing the app, so server-side workspace membership from issue 006 still gates data access.
- Deviations from spec: none known.
- Concerns:
  - Issue 005 provider validation and issue 007 app-level auth smoke are complete as of 2026-06-03.
  - Existing `src/js/auth.js` is now unused by the loader but left in place to avoid broad cleanup outside issue 007.
  - Issue 007 had no dedicated `docs/ai/contracts/issue-007.json`; the post-smoke artifact records this as a workflow-adherence gap for future auth issues.

### 2026-06-02 — supabase-jwt-middleware (issue 006 / #262)
- Files modified:
  - `auth.py` — Replaced collab-v1 Google/session-cookie auth with Supabase JWT verification using `SUPABASE_JWT_SECRET`, Bearer header parsing, admin membership lookup, and a disabled legacy `get_request_user` stub for old test monkeypatches.
  - `server.py` — `_require_auth()` now maps verified Bearer tokens to user/workspace identity, returns 401 for missing/invalid/expired tokens and 403 for valid tokens with no workspace membership, returns `/api/me` identity, disables `/auth/google/*`, constructs scoped storage for protected routes, and routes `/api/projects/revisions` through auth + scoped storage in server mode.
  - `storage.py` — `get_storage()` accepts optional `workspace_id` and `user_claims` and passes them into `PostgresStorageBackend`.
  - `.env.example` — Removed legacy `AUTH_GOOGLE_*` app-login placeholders; added server-only `SUPABASE_JWT_SECRET`.
  - `tests/test_auth.py`, `tests/test_auth_middleware.py` — Rewritten around Supabase JWT verification and middleware status boundaries.
  - `tests/test_sessions.py`, `tests/test_oauth_scopes.py` — Removed obsolete collab-v1 session/app-login tests.
  - `tests/test_collab_regression.py`, `tests/test_transactional_save.py` — Updated stale auth expectations and bound the new storage helper in mocked handler tests.
- Checks run:
  - `.venv/bin/python -c "import auth; import server; print('imports OK')"` → imports OK.
  - `.venv/bin/python -m pytest tests/test_auth.py tests/test_auth_middleware.py -q` → 21 passed.
  - `.venv/bin/python -m pytest tests/test_auth.py tests/test_auth_middleware.py tests/test_collab_regression.py tests/test_project_revision_endpoint.py tests/test_project_visibility.py tests/test_project_history.py tests/test_project_ownership.py tests/test_share_project.py -q` → 178 passed.
  - `.venv/bin/python -m pytest tests/test_transactional_save.py -q` → 20 passed.
  - `.venv/bin/python scripts/run_ai_workflow.py checks --level issue` → 100 pytest CI-subset passed; vitest 69 passed; PASS.
  - `DATABASE_URL= SUPABASE_SERVICE_ROLE_URL= .venv/bin/python -m pytest -q` → 829 passed / 30 skipped / 2 DB-only migration integration failures (`tests/test_migrations.py::TestIntegration`, expected without `APP_MODE=server` + live DB).
  - `set -a; source .env; set +a; APP_MODE=server .venv/bin/python -m pytest tests/test_migrations.py -m integration -q --tb=short` with escalated network → 2 passed / 23 deselected.
- Decisions made:
  - Used Supabase's HS256 project JWT secret path rather than JWKS because the issue explicitly allows `SUPABASE_JWT_SECRET` and staging already documents server-side secret setup.
  - Membership lookup uses `db.admin_transaction()` before constructing user-scoped storage, matching the bootstrap trust-boundary requirement.
  - Kept `auth.get_request_user()` as a disabled-by-default stub only so existing unit tests can monkeypatch it; runtime `server.py` does not accept legacy cookies unless the function is explicitly replaced in tests.
- Deviations from spec:
  - No live Supabase JWT integration test was run; issue 007 must add frontend login/token attachment before manual browser smoke can exercise real `/api/me`.
- Concerns:
  - Frontend `apiFetch()` still does not attach Supabase Bearer tokens; server-mode protected routes will return 401 until issue 007 lands.
  - Full local pytest still requires either empty DB env vars or live staging connectivity; `.env` contains `DATABASE_URL`, so DB-only tests can try network under sandbox.

### 2026-06-02 — supabase-auth-provider-runbook (issue 005 / #261)
- Files modified:
  - `MANUAL-STEPS.md` — Added the staging Supabase Auth provider setup runbook with exact dashboard steps for URL configuration, Google OAuth, email magic links, custom SMTP, leaked-password protection, and manual workspace membership seeding.
  - `docs/ai/project-state.md` — Recorded issue 005 status as docs-ready but blocked on human dashboard/Google Cloud actions.
- Checks run:
  - `gh issue view 261 --json number,title,body,state,labels,url` → confirmed issue 005 / #261 scope and acceptance criteria.
  - Official Supabase docs reviewed on 2026-06-02 for Google provider setup, magic links, SMTP restrictions, redirect URLs, and leaked-password protection.
  - No automated tests; issue 005 is dashboard configuration + documentation only and explicitly forbids `server.py` / `auth.py` code changes.
- Decisions made:
  - Kept legacy collab-v1 Google OAuth instructions in `MANUAL-STEPS.md`, but marked them as superseded by Supabase Auth for this migration.
  - Treated Supabase built-in mailer as staging fallback only; custom SMTP remains required before broader multi-church testing.
- Deviations from spec:
  - Dashboard provider toggles were not changed in this session because they require human access to Google OAuth client secrets, SMTP credentials, and Supabase dashboard settings.
- Concerns:
  - Cleared 2026-06-03: user reported issue 005 validation complete.

### 2026-06-02 — storage-multi-tenant (issue 004 / #260)
- Files modified:
  - `storage.py` — Full rewrite of `PostgresStorageBackend` for multi-tenant schema. Added `__init__(workspace_id=None, user_claims=None)` (both optional, None = backward-compat). Added `_transaction()` helper that passes `claims=self.user_claims` to `db.transaction()`. Updated all methods to: (a) use new schema column names; (b) add `workspace_id` defense-in-depth WHERE clauses; (c) removed `::uuid` cast on projects.id (TEXT PK); (d) use profiles LEFT JOIN for attribution (email/display_name). Added `_pg_enrich_project_row()` for RETURNING paths that can't inline the JOIN. Updated `_pg_row_to_project`, `_pg_row_to_template`, `_pg_row_to_song`, `_pg_row_to_font` for new column names. Removed old `org_settings` usage; replaced with `workspace_settings`. `get_storage()` signature unchanged.
  - `tests/test_storage.py` — Updated `TestPostgresStorageBackendNotImplemented` to handle the fact that `list_*` methods now return `[]` gracefully (not raise) when a live DB is reachable and workspace_id is None; `save_*` still raise RuntimeError when workspace_id is None (cannot insert without PK). Added `_pg_no_workspace_ok_or_raises()` helper.
  - `tests/test_storage_multi_tenant.py` (NEW) — Two required tests: `test_get_project_wrong_workspace_returns_none`, `test_save_project_scoped_to_workspace`. Skipped when DATABASE_URL absent. Also adds constructor/backward-compat tests (no DB required).
- Checks run:
  - `.venv/bin/python -c "import storage; import server; print('imports OK')"` → imports OK
  - `env -u DATABASE_URL APP_MODE=server .venv/bin/pytest tests/test_storage.py tests/test_storage_routing.py tests/test_storage_multi_tenant.py -q` → 99 passed (DB tests skip without DATABASE_URL)
- Decisions made:
  - `__init__` backward-compat: both `workspace_id` and `user_claims` default to `None`. No-arg `PostgresStorageBackend()` and `get_storage()` work unchanged.
  - When `workspace_id` is None: `list_*` query without workspace filter (returns all rows for admin use, or empty if DB empty); `save_*` raise RuntimeError (can't INSERT without FK); `get_settings` queries with LIMIT 1.
  - Attribution: profiles LEFT JOIN on created_by_user_id / updated_by_user_id. Maps email → `createdBy`/`updatedBy` camelCase keys. `_pg_enrich_project_row()` handles RETURNING paths.
  - `save_project_transactional` conflict path: fetches server row with profiles JOIN inline for 409 body; workspace_id clause injected dynamically.
  - Test order issue: `test_storage_routing.py` imports `server.py` which loads `.env` → sets `DATABASE_URL` for subsequent tests in the same session. Updated `TestPostgresStorageBackendNotImplemented` to handle both ordered (DB available) and isolated (DB unavailable) runs.
- Deviations from spec:
  - `visibility` default on INSERT: set to `'workspace'` (not `'private'`). The new schema `DEFAULT 'workspace'` aligns with multi-user use; private projects require explicit visibility flag. Flagged below.
  - `save_project` (un-transactional) doesn't insert a project_revisions snapshot — only `save_project_transactional` does. This matches original design; flagged.
- Concerns:
  - `visibility` default: issue spec says new schema default is `'workspace'`. `save_project` inserts `'workspace'` on conflict INSERT. If the product wants new projects to be `'private'` by default, caller must supply `data["visibility"] = "private"`. Needs a product decision (out of scope for 004).
  - `save_project_transactional` inserts `project_revisions` with `workspace_id = self.workspace_id`. If `workspace_id` is None (un-scoped backend), the INSERT will fail at DB level (NOT NULL constraint). This is correct behavior — transactional saves should only be called in scoped context (issues 006/007).
  - `save_settings` / `save_announcements` / `save_songs` / `save_templates` all raise RuntimeError when `workspace_id=None`. Existing server.py callers use the no-arg `get_storage()` which returns un-scoped backend; these endpoints will fail until issue 006/007 wires identity. This is by design per the issue spec.
  - Fonts table in new schema has `name` only (no `slug`, `family`, `storage_path`). `get_font(slug)` matches on `name` column as best-effort. Needs alignment with issue 009/010 (Supabase Storage URLs).

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
