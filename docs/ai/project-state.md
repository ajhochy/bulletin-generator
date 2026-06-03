# Project State

_Last updated: 2026-05-28_

## Current focus

Performance/bandwidth fix: the 30s stale-check poll was downloading the full ~8.6 MB `projects.json` every cycle (root cause of ~279 GB transferred over a few weeks). Fixed on branch `fix/lightweight-projects-poll` — see "Recent coding-agent runs" below and the 2026-05-28 entry in `decisions.md`. Pending: manual smoke + draft PR.

Prior focus — stabilizing the Volunteer Roles feature added in releases 1.12.9 / 1.12.10 (PRs #251, #252). Recent fixes:

- #252 — Volunteer Roles cards now render after server data loads (deferred-render bug).
- #251 — Volunteer Roles render in preview + added Document menu toggle.
- (in flight) #253 — Volunteer Roles elements are selectable / formattable in the Template Designer canvas. Branch `fix/template-editor-volunteer-roles-not-selectable`.

## Recently completed

- 1.12.10 release tagged (commit `b0b5f32`).
- Watchtower scope label typo + periodic polling enabled (`d09dbce`).

## In progress

- `fix/lightweight-projects-poll` — lightweight stale-check endpoint. Verified (pytest 95, vitest 83, vite build, server smoke). Awaiting draft PR + manual smoke (observe Network tab: 30s poll should hit `/api/projects/revisions`, small response).
- Draft PR #253 awaiting manual smoke + merge.

## Open risks

- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic, but UI behavior (rendering, Template Designer, poll timer) is not automated and needs manual click-through. Easy to miss regressions in adjacent zones (Announcements, Calendar, Staff, Serving) when touching shared code.
- Memory note re: "Do NOT create PRs unless explicitly asked" is overly broad and has caused agents to skip the workflow's terminal step. Should be scoped to "without an explicit instruction or workflow that requires it."

## Next step

Manual smoke the poll fix (confirm `/api/projects/revisions` is used and small), open its draft PR. Then manual smoke #253, merge, and close out 1.12.x by tagging a release if any further volunteer-roles polish lands.

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
