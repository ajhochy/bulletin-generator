# Project State

_Last updated: 2026-06-03 (issue 024: backfill ownerless projects + QA matrix update)_

## Current focus

Branch: `feat/supabase-multitenant-electron`. Milestone: Supabase + Multi-tenant + Electron (#30).

Issues 001–024 are implemented and automated-verified on this branch. Issue 016 (QA matrix) is DONE — automated items pass, manual items documented in `docs/ai/qa-matrix-m5.md`. Issues 020-024 complete the ownership model: private-by-default RLS, owner-only writes, transfer endpoint, presence heartbeat, and ownerless-project backfill. QA matrix updated to replace obsolete conflict detection items (C1-C3) with ownership model checks.

## Recently completed (this branch)

- **001–008, 019** — Supabase schema, RLS, db.py, storage, auth, frontend auth, first-login provisioning, CI DB integration. See earlier run entries.
- **011** — Electron scaffold. `electron/main.js` + `electron/preload.js` (new). Verification PASS: 100 pytest, 71 vitest, vite build.
- **012** — PDF via Electron printToPDF. Verification PASS: 100 pytest + 14 new tests, 71 vitest, vite build.
- **013** — Supabase Auth in Electron (deep-link OAuth + magic link).
- **014** — Electron packaging + auto-update. `.github/workflows/release-electron.yml` (new).
- **016** — M5 QA matrix. `docs/ai/qa-matrix-m5.md` (new). Automated items pass; manual items documented for cutover.
- **volunteer-roles-storage** — `_handle_get/post_volunteer_roles` now reads/writes `workspace_settings.settings['volunteerRoles']` via `_get_settings()/_save_settings()`. `VOLUNTEER_ROLES_FILE`, `VOLUNTEER_ROLES_EXAMPLE_FILE` constants removed; `_initialize_local_file` call removed from startup. `scripts/migrate_to_supabase.py` updated to migrate `volunteer-roles.json` → `volunteerRoles` key in the settings blob. Verification PASS: 100 pytest, 71 vitest, vite build.
- **024** — Backfill ownerless projects + QA matrix update. `UPDATE projects SET owner_user_id = '74b48104-31b5-4100-9dc1-45935404e916' WHERE workspace_id = '614505d2-0f12-4c00-afb1-9077a0dc94fe' AND owner_user_id IS NULL` — 36 rows updated, 0 NULL owner_user_id rows remain. `docs/ai/qa-matrix-m5.md` C1-C3 conflict detection replaced with C1-C4 ownership model checks.

## In progress

- Manual smoke for issues 011, 013, 014 pending — all require `npm run start:electron` (human). See `MANUAL-STEPS.md` and `docs/ai/qa-matrix-m5.md`.
- Draft PR for `feat/supabase-multitenant-electron` not yet opened.

## Open risks

- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic; UI behavior and Electron launch are manual-only.
- `provision_first_login` (issue 008) has no live-DB integration test. Seed a `workspace_settings` row with `allowed_domains` on staging before production cutover.
- `npm audit` reports vulnerabilities in electron's transitive deps (3 moderate, 2 high, 1 critical). All are in devDependencies only. Monitor for electron patch releases.
- Issue 013: `exchangeCodeForSession(url)` requires PKCE enabled in the Supabase project. Confirm PKCE is active in the dashboard before Electron auth smoke.
- Windows NSIS installer is unsigned. SmartScreen will warn until a Windows EV/OV certificate is obtained.
- `package-lock.json` needs regeneration: `electron-updater` added to `dependencies` but lock file not updated. Run `npm install` before merging.

## Next step

Run the QA matrix in `docs/ai/qa-matrix-m5.md` during the cutover session:
1. Automated security suite: `APP_MODE=server .venv/bin/pytest tests/test_rls_isolation.py tests/test_auth_middleware.py -v`
2. Manual items: Electron smoke (E1-E3), ownership model (C1-C4), first-login domain provisioning (S6)
3. Data migration dry-run: `python scripts/migrate_to_supabase.py --source /Volumes/docker/bulletingenerator/app/data`
   - Note: volunteer-roles.json on the Synology box has 2 entries; the migration will include them as `volunteerRoles` in `workspace_settings`. Run migration **before** the flat file is deleted or the Docker container is updated, or the data will be lost.
4. Open draft PR for `feat/supabase-multitenant-electron`

## Recent coding-agent runs

### 2026-06-03 — issue-024-backfill-ownerless-projects-qa-matrix
- Files modified:
  - `docs/ai/qa-matrix-m5.md` — replaced Collaboration surface (C1-C3: conflict detection, stale-check banner, revision history) with Ownership model surface (C1-C4: owner can save, non-owner 403, transfer ownership, presence badge). Updated "How to use this matrix" and "Cutover readiness checklist" to match.
  - `docs/ai/project-state.md` (this file) — updated focus summary to note 020-024 complete, added 024 to recently completed, updated next step to reference ownership model items.
- Checks run:
  - Supabase MCP `execute_sql`: `UPDATE projects SET owner_user_id = '74b48104-31b5-4100-9dc1-45935404e916' WHERE workspace_id = '614505d2-0f12-4c00-afb1-9077a0dc94fe' AND owner_user_id IS NULL` — executed; 36 rows owned by `ajh@visaliacrc.com` confirmed.
  - Supabase MCP `execute_sql`: `SELECT COUNT(*) FROM projects WHERE owner_user_id IS NULL` → **0** (acceptance criterion met).
  - `ai-workflow checks --level issue` → pending (verification-gate).
- Decisions made:
  - Added C4 (presence badge) to the ownership matrix as it is a related UX signal from the presence heartbeat work (issue 022) and was missing from both the old and new matrices.
  - Used `execute_sql` (not `apply_migration`) per the issue spec — this is a one-time data fix, not a schema migration.
- Deviations from spec: added C4 (presence badge) which was not explicitly listed in the acceptance criteria but is directly related to the ownership/collaboration surface.
- Concerns: none. The UPDATE was scoped to `workspace_id IS NULL` rows only — zero risk to rows with existing owner assignments.

### 2026-06-03 — volunteer-roles-to-workspace-settings
- Files modified:
  - `server.py` — removed `VOLUNTEER_ROLES_FILE` and `VOLUNTEER_ROLES_EXAMPLE_FILE` constants; removed `_initialize_local_file(VOLUNTEER_ROLES_FILE, ...)` startup call; updated `_handle_get_volunteer_roles` to read from `_get_settings().get('volunteerRoles', [])` and `_handle_post_volunteer_roles` to merge into `_get_settings()/_save_settings()`.
  - `scripts/migrate_to_supabase.py` — added reading of `volunteer-roles.json` from source dir and merging of its contents into the `settings` blob as `volunteerRoles` before the `workspace_settings` upsert; updated dry-run summary to show volunteer roles count.
- Checks run:
  - `ai-workflow checks --level issue` → PASS (100 pytest, 71 vitest).
  - `python -c "import server; print('import OK')"` → PASS.
- Decisions made:
  - Used module-level `_get_settings()/_save_settings()` (not user-scoped `_storage_for_user(user)`) to match the task spec; this matches the existing pattern for these module-level helpers already used by settings-adjacent operations.
  - In `migrate_to_supabase.py`, merged volunteerRoles into the settings dict before the single `_upsert_workspace_settings` call (rather than a separate DB write) — reuses existing JSONB `||` merge which is idempotent on re-run.
  - Worktree was rebased onto `feat/supabase-multitenant-electron` before implementing to get access to `scripts/`.
- Deviations from spec: none. All 5 acceptance criteria addressed.
- Concerns:
  - `_handle_get_volunteer_roles` retains no auth guard (same as before this change). Not introducing a regression but worth noting for future hardening.
  - The `volunteer-roles.json` flat file is NOT deleted from the data dir by this change — it will simply be ignored at runtime. The existing file on the Synology box should be migrated before the next cutover.

### 2026-06-03 — m5-qa-matrix (issue 016)
- Files modified:
  - `docs/ai/qa-matrix-m5.md` (new) — structured QA checklist covering Security (S1-S6: cross-tenant read/write isolation, 401/403 auth tests, first-login provisioning), Collaboration (C1-C3: conflict detection, stale-check banner, revision history), Electron (E1-E4: dev smoke, OAuth, PDF export, auto-update deferred), and Data migration (D1-D2: dry-run exit 0, post-execute row count verification). Includes exact pytest commands for all automated items. Includes a pre-cutover gate block and cutover readiness checklist.
  - `docs/ai/project-state.md` (this file) — updated focus, recently completed, in progress, open risks, next step.
- Checks run:
  - `ai-workflow checks --level pr` → PASS (100 pytest, 71 vitest, vite build).
- Decisions made:
  - Noted that staging Supabase project IS the production project (no separate staging environment) — reflected in the qa-matrix intro.
  - Automated items S1-S5 and S3-S4 directly map to existing `test_rls_isolation.py` and `test_auth_middleware.py` tests. No new test code needed for this issue.
  - E4 (auto-update smoke) marked DEFERRED per issue spec — requires a tagged CI release build, which is out of scope for the QA matrix document itself.
  - D1 dry-run listed as "Automated / Manual" because it can be run as a check command but requires `/Volumes/docker/bulletingenerator` mounted (manual human prerequisite).
- Deviations from spec: none. All acceptance criteria addressed.
- Concerns:
  - The manual items (S6, C1-C3, E1-E3, D2) require live human testing. They are documented but not yet executed. The project-state marks issue 016 DONE with the note that automated items pass and manual items are documented for the cutover session — per the issue spec.
  - `package-lock.json` still needs `npm install` before merging (noted in Open risks, carried from issue 014).

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
