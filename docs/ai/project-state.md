# Project State

_Last updated: 2026-06-03 (issue 021: owner-only writes + transfer endpoint — PASS)_

## Current focus

Branch: `feat/supabase-multitenant-electron`. Milestone: Supabase + Multi-tenant + Electron (#30).

Issues 001–021 are implemented and automated-verified on this branch. Issue 016 (QA matrix) is DONE — automated items pass, manual items documented in `docs/ai/qa-matrix-m5.md`. Issue 020 (private-by-default + tighten RLS write policy) is DONE — migration applied to staging, 25/25 RLS isolation tests pass. Issue 021 (owner-only writes + transfer) is DONE — Verification PASS after repair loop (3 related test files updated to reflect new behavior).

## Recently completed (this branch)

- **001–008, 019** — Supabase schema, RLS, db.py, storage, auth, frontend auth, first-login provisioning, CI DB integration. See earlier run entries.
- **011** — Electron scaffold. `electron/main.js` + `electron/preload.js` (new). Verification PASS: 100 pytest, 71 vitest, vite build.
- **012** — PDF via Electron printToPDF. Verification PASS: 100 pytest + 14 new tests, 71 vitest, vite build.
- **013** — Supabase Auth in Electron (deep-link OAuth + magic link).
- **014** — Electron packaging + auto-update. `.github/workflows/release-electron.yml` (new).
- **016** — M5 QA matrix. `docs/ai/qa-matrix-m5.md` (new). Automated items pass; manual items documented for cutover.
- **020** — Private-by-default + owner-only update RLS. `supabase/migrations/20260603000002_private_default_rls.sql` (new). `projects.visibility` DEFAULT changed to `'private'`; `projects_update` policy tightened to owner-only. Applied to staging. Verification PASS: 25/25 RLS tests, 100 pytest, 71 vitest, vite build.
- **021** — Owner-only writes + transfer endpoint. `server.py` + `storage.py` + 4 test files. `POST /api/projects` now enforces owner-only; `_clientRevision` ignored; `save_project_transactional` call removed from handler. New `POST /api/projects/{id}/transfer` endpoint. New `PostgresStorageBackend.transfer_project_owner()`. Verification PASS (100 pytest, 71 vitest, vite build) after repair loop — 3 related test files (`test_project_visibility.py`, `test_transactional_save.py`, `test_collab_regression.py`) updated to reflect new owner-only behavior. See run entry below.
- **volunteer-roles-storage** — `_handle_get/post_volunteer_roles` now reads/writes `workspace_settings.settings['volunteerRoles']` via `_get_settings()/_save_settings()`. `VOLUNTEER_ROLES_FILE`, `VOLUNTEER_ROLES_EXAMPLE_FILE` constants removed; `_initialize_local_file` call removed from startup. `scripts/migrate_to_supabase.py` updated to migrate `volunteer-roles.json` → `volunteerRoles` key in the settings blob. Verification PASS: 100 pytest, 71 vitest, vite build.

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
2. Manual items (Electron smoke, first-login domain provisioning). **Note: C1 (conflict detection) in the QA matrix is obsolete** — conflict detection (409 on stale `_clientRevision`) was removed in issue 021. Skip or remove C1 from the checklist.
3. Data migration dry-run: `python scripts/migrate_to_supabase.py --source /Volumes/docker/bulletingenerator/app/data`
   - Note: volunteer-roles.json on the Synology box has 2 entries; the migration will include them as `volunteerRoles` in `workspace_settings`. Run migration **before** the flat file is deleted or the Docker container is updated, or the data will be lost.
4. Open draft PR for `feat/supabase-multitenant-electron`

## Recent coding-agent runs

### 2026-06-03 — issue-021-owner-only-writes-transfer (PASS after repair loop)
- Files modified:
  - `storage.py` — added `PostgresStorageBackend.transfer_project_owner(project_id, from_user_id, to_user_id)`.
  - `server.py` — rewrote `_handle_post_projects` server-mode block: drops `save_project_transactional`; calls `save_project` for all writes; owner-only 403 on existing projects; `_clientRevision` discarded. New `_handle_post_transfer_project` handler for `POST /api/projects/{id}/transfer`.
  - `tests/test_project_ownership.py` — full rewrite: 18 tests covering new/existing project saves, non-owner 403, `_clientRevision` ignored, legacy no-owner allowed, and `TestTransferProjectOwner` (6 tests).
  - `tests/test_project_visibility.py` — `TestPostProjectsSave` updated: helper uses `save_project`; `test_both_users_can_save_workspace_project` → `test_only_owner_can_save_workspace_project` (non-owners now 403).
  - `tests/test_transactional_save.py` — `TestPostProjectsServerMode` updated: `save_project_transactional` assertions → `save_project`; conflict/409 tests removed (behavior removed per spec); new `test_client_revision_is_ignored` and `test_missing_client_revision_is_ignored`.
  - `tests/test_collab_regression.py` — `_call_save_project` helper uses `save_project`; `test_user_b_can_save_workspace_project` → `test_user_b_cannot_save_workspace_project_owned_by_user_a`.
- Repair loop: initial commit passed ownership tests (18/18) but 9 tests in 3 related files failed because they asserted old behavior (workspace-member writes, save_project_transactional, 409 conflict). Those tests were updated to reflect the new owner-only policy. Final PR-level check: PASS (100 pytest, 71 vitest, vite build).
- Commits: `ba4732c` (implementation), `fb439f1` (related test fixes).
- Decisions made: see inline notes above and `docs/ai/decisions.md` (entry: owner-only write policy replaces workspace-member write access).
- Deviations from spec: none. All 6 acceptance criteria addressed.
- Concerns:
  - `save_project_transactional` and `ConflictError` remain as dead code in `storage.py` — referenced by `test_transactional_save.py` storage-unit tests (not the handler tests). Cleanup is a follow-up.
  - Frontend `_clientRevision` append code in `projects.js` is now dead. Safe to remove in a follow-up; no functional regression.
  - TOCTOU on new/existing detection mitigated by DB upsert semantics (owner set only on INSERT).
  - QA matrix item C1 (conflict detection) in `docs/ai/qa-matrix-m5.md` is now obsolete — conflict detection removed per issue 021. Should be updated/removed before cutover.

### 2026-06-03 — issue-020-private-default-rls
- Files modified:
  - `supabase/migrations/20260603000002_private_default_rls.sql` (new) — changes `projects.visibility` DEFAULT to `'private'`; replaces `projects_update` policy to `owner_user_id = auth.uid()` only.
  - `tests/test_rls_isolation.py` — added `test_owner_can_update_own_project` and `test_non_owner_cannot_update_others_project`.
- Checks run:
  - `pytest tests/test_rls_isolation.py -q` → 25 passed (23 original + 2 new) against staging DB.
  - `ai-workflow checks --level issue` → PASS (100 pytest, 71 vitest).
- Decisions made:
  - Used `private.is_workspace_member(workspace_id)` in the new `projects_update` policy (consistent with existing helpers). The issue spec listed `private.get_workspace_id()` which does not exist in the schema; `is_workspace_member` is the correct and established form.
  - `projects_select` left unchanged — it already correctly filters private projects to owner-only via `(visibility = 'workspace' OR owner_user_id = auth.uid())`.
  - `WITH CHECK` on `projects_update` also scoped to owner, preventing a non-owner from updating `owner_user_id` to reassign ownership.
- Deviations from spec: Issue spec referenced `private.get_workspace_id()` (non-existent). Used `private.is_workspace_member(workspace_id)` instead (established pattern). No functional difference in intent.
- Concerns: None. Migration is idempotent and additive (existing rows unaffected). Applied and verified on staging dgydekhfzrmeoscpgmvo.

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
