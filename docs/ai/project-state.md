# Project State

_Last updated: 2026-06-03 (issue 023: presence badge + read-only mode — PASS)_

## Current focus

Branch: `feat/supabase-multitenant-electron`. Milestone: Supabase + Multi-tenant + Electron (#30).

Issues 001–023 are implemented and automated-verified on this branch. Issue 023 (remove conflict detection, add presence heartbeat + read-only mode for non-owners) is DONE.

## Recently completed

- **001–021** — See earlier run entries (Supabase schema, RLS, auth, owner-only writes, transfer endpoint, volunteer-roles consolidation).
- **022** — Presence heartbeat API on server (`POST /api/presence/heartbeat`, `GET /api/presence`, `DELETE /api/presence`).
- **023** — Frontend: removed `_clientRevision` / `_loadedRevision` / `startStaleCheck` / conflict banner/dialog. Added presence heartbeat, 30s interval, `DELETE` on unload. Non-owner viewing workspace project enters read-only mode (autosave blocked, banner + Duplicate button). 403 on save shows toast. Verification PASS: 30 vitest (worktree), 71 vitest (main), 100 pytest, vite build.

## In progress

- Manual smoke for issue 023 pending — requires live Supabase session + two users:
  1. Owner opens workspace project → no readonly-banner, autosave fires.
  2. Non-owner opens same project → readonly-banner appears, edits suppressed, Duplicate creates private copy.
  3. Network tab: 30s `POST /api/presence/heartbeat`, `DELETE /api/presence` on tab close.
  4. Presence badge `● X is editing` visible when another user has project open.
- Draft PR for `feat/supabase-multitenant-electron` not yet opened.

## Open risks

- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic; UI behavior and Electron launch are manual-only.
- `provision_first_login` (issue 008) has no live-DB integration test. Seed a `workspace_settings` row with `allowed_domains` on staging before production cutover.
- `npm audit` reports vulnerabilities in electron's transitive deps (3 moderate, 2 high, 1 critical). All are in devDependencies only. Monitor for electron patch releases.
- Issue 013: `exchangeCodeForSession(url)` requires PKCE enabled in the Supabase project. Confirm PKCE is active in the dashboard before Electron auth smoke.
- Windows NSIS installer is unsigned. SmartScreen will warn until a Windows EV/OV certificate is obtained.
- `package-lock.json` needs regeneration: `electron-updater` added to `dependencies` but lock file not updated. Run `npm install` before merging.
- `worship-booklet.html` (9111-line legacy standalone file) still contains old `_loadedRevision`/`startStaleCheck` code — it is not part of the active modular codebase and would need a separate migration. Not a runtime risk.

## Next step

Run the QA matrix in `docs/ai/qa-matrix-m5.md` during the cutover session:
1. Automated security suite: `APP_MODE=server .venv/bin/pytest tests/test_rls_isolation.py tests/test_auth_middleware.py -v`
2. Manual items (issue 023 presence smoke, Electron smoke, first-login domain provisioning).
3. Data migration dry-run: `python scripts/migrate_to_supabase.py --source /Volumes/docker/bulletingenerator/app/data`
4. Open draft PR for `feat/supabase-multitenant-electron`

## Recent coding-agent runs

### 2026-06-03 — issue-023-presence-badge-readonly (PASS)
- Files modified:
  - `src/js/modules/projects-core.js` — removed `deriveProjectSaveSuccess` (no longer needed); updated `buildProjectSaveRequest` to drop `_clientRevision`; updated `deriveProjectSaveFailure` to handle 403 → "forbidden" type; restored `deriveStartupRestore` export (was accidentally dropped).
  - `src/js/main.js` — updated import block: removed `deriveProjectSaveSuccess`; added `deriveStartupRestore`.
  - `src/js/state.js` — replaced `_loadedRevision`/`_staleCheckTimer` with `_presenceTimer`/`_isReadOnly`.
  - `src/js/projects.js` — removed: `_updateFileDirtyDot`, `buildConflictSummary`, `showConflictDialog`, `_closeConflictDialog`, `buildSyncDiffMessage`, `startStaleCheck`, `_loadedRevision` references. Added: `enterReadOnlyMode`, `exitReadOnlyMode`, `_duplicateProjectForCurrentUser`, `_startPresenceHeartbeat`, `_stopPresenceHeartbeat`, `_showPresenceBadge`, `_hidePresenceBadge`. Updated: `saveProjectToServer` (403 → toast, no conflict branch), `autosaveProjectState` (skip when `_isReadOnly`), `loadProjectById` (owner check → read-only, starts presence), `restoreOnStartup` (uses `deriveStartupRestoreCore`), `saveCurrentProject` (remove `_loadedRevision = null`), `clearEditorForNewProject` (stop presence + exit read-only), `initProjects` (pagehide/beforeunload listeners for presence DELETE).
  - `index.html` — removed `stale-banner` and `conflict-banner` divs; added `presence-badge` div inside File dropdown; added `readonly-banner` div between editor toolbar and main editor.
  - `tests/projects-core.spec.js` — removed revision/conflict tests; added 403-forbidden toast test and _clientRevision-absence assertion.
- Checks run:
  - `node --check src/js/projects.js` → PASS
  - `node --check src/js/state.js` → PASS
  - `node --check src/js/main.js` → PASS
  - `python -c "import server"` → PASS
  - `npm test` (worktree) → 30/30 PASS
  - `npm run build` (worktree) → clean build
  - `ai-workflow checks --level issue` (main repo) → PASS (100 pytest, 71 vitest)
- Decisions made:
  - `presence-badge` placed inside the File dropdown panel (same row as project-meta) — most visible without taking permanent toolbar space.
  - `readonly-banner` placed as a narrow strip between editor-toolbar and the main editor, always visible when non-owner is viewing.
  - `_stopPresenceHeartbeat` sends `DELETE /api/presence` best-effort (no await, errors swallowed) — consistent with "best-effort" spec requirement.
  - `restoreOnStartup` in the worktree had a hand-rolled startup flow (not using `deriveStartupRestoreCore`); updated to match the pattern already established in the shared checkout.
- Deviations from spec: none. All acceptance criteria addressed.
- Concerns:
  - The `deriveStartupRestore` function was inadvertently dropped from `projects-core.js` during the edit and caught by the vite build check. Restored before commit.
  - Read-only mode only checks `project.owner_user_id` from the loaded project object. If the server sends the project without that field (legacy projects), read-only mode won't activate (safe default — non-owners can't save anyway since server enforces 403).
  - Manual smoke needed: open a workspace project as a non-owner and verify: readonly-banner appears, editing is visually inhibited, Duplicate creates a private copy, presence badge shows when owner is active.

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
