# Project State

_Last updated: 2026-06-05 (presence endpoint 500 fixed — workspace_presences.project_id uuid→text)_

## Current focus

Branch: `feat/supabase-multitenant-electron`. Milestone: Supabase + Multi-tenant + Electron (#30).

Issues 001–023 are implemented and automated-verified on this branch. Issue 023 (remove conflict detection, add presence heartbeat + read-only mode for non-owners) is DONE.

Side branch `test/e2e-playwright-foundation` holds the Playwright E2E suite; its Projects spec surfaced the presence 500 (see below).

## Recently completed

- **Presence endpoint 500 fixed (branch `test/e2e-playwright-foundation`).** `workspace_presences.project_id` was created as `uuid` (migration `20260603000003_workspace_presences.sql`) but `public.projects.id` is **TEXT** (`proj_<ts>_<rand>`). Binding a TEXT project id against the uuid column raised `psycopg.errors.InvalidTextRepresentation`, 500-ing every `GET /api/presence` and `POST /api/presence/heartbeat` for real projects — silently, because the frontend swallows presence errors (best-effort). Presence was fully broken for all projects. **Fix:** new additive migration `supabase/migrations/20260605000002_presence_project_id_text.sql` idempotently alters the column to `text` (uuid→text is a lossless widening cast; PK + index rebuilt automatically). Applied live to the Supabase project. Also corrected two now-misleading `<uuid>` docstrings in `server.py` presence handlers (the false "uuid" assumption is what caused the bug). **No Python query change needed** — handlers bind `project_id` as a plain string with no `::uuid` cast. **Verified:** live column `data_type=text`; faithful DB round-trip through the exact heartbeat-upsert + GET query shapes with a TEXT `proj_...` id returned the row with no error (old uuid column would have raised); `ai-workflow checks --level issue` and `--level pr` both PASS (vite build + pytest + vitest). Surfaced by `tests/e2e/features/projects.spec.ts`. Full HTTP-level E2E confirmation (live auth session) belongs in manual smoke.

- **Abandoned Share-to-Workspace; confirmed visibility model A (workspace-visible by default + hand-off).** Removed dead code: `_handle_share_project` + dispatch (server.py), `share_project_to_workspace` (all 3 storage backends), `tests/test_share_project.py`. Issue 020's private-by-default is obsolete (the `'private'` column default is vestigial — `save_project` forces `'workspace'`; owner-only-write RLS retained). Docs reconciled (decisions.md, architecture.md, current-plan.md, issue #272). GitHub #211 closed not-planned. See `decisions.md` 2026-06-04. NOTE: `python -c "import server"` OK; project/auth tests unchanged (108 pass; 1 pre-existing test-ordering pollution failure in `test_project_visibility.py::TestGetProjectsList` that also fails on committed code — unrelated, worth a separate isolation fix).
- **Packaged Electron app made to actually boot (v0.0.4, verified working).** The released DMGs (v0.0.1) had never been boot-tested; five latent build defects surfaced in sequence on macOS 26.5/arm64. All fixed on `feat/supabase-multitenant-electron`, shipped via tags `electron-supabase-beta-v0.0.2/3/4` (draft prereleases):
  1. `release-electron.yml` never `pip install -r requirements.txt` → `ModuleNotFoundError: psycopg`. Fixed: install requirements + `--collect-all psycopg --collect-all psycopg_binary` (commit `bc64b19`).
  2. No Supabase/DB config bundled (`desktop_config.py` is only read by deprecated `launcher.py`, unused by Electron). Fixed: workflow writes `.env` from secrets + `--add-data ".env:."`; `server.py:309` `_load_dotenv(BASE_DIR/.env)` loads it (`bc64b19`).
  3. Packaged `resolveSidecar()` passed no port arg → `server.py:3441` defaulted to 8080 while Electron polls 8765. Fixed: `args:[String(PORT)]` in `electron/main.js` (`bc64b19`).
  4. `entitlements.plist` missing `com.apple.security.cs.allow-jit` → under hardened runtime on Apple Silicon V8 aborts at `Isolate::Init` (`FatalProcessOutOfMemory`, CodeRange). Fixed: added entitlement (`acecadf`). Verified by ad-hoc re-signing the .app with the entitlement (survived past V8 init).
  5. `@supabase/supabase-js` UMD served by `server.py` from `node_modules/` (404 in bundle) → broke the renderer module graph → window loads but auth never starts, inert UI. Fixed: `--add-data` the UMD (`4963cbe`). Verified locally: route serves 200 / 203 KB.
  - Also fixed preview bug (`9020e2d`): empty announcements zone rendered a blank page that OOW merged onto, leaving a gap above the first OOW item — `renderAnnouncementsZone()` now bails when no announcements + no welcome. User-confirmed.
  - v0.0.4 manual smoke PASS: app opens (slow — onefile unpack), PCO creds inherited, PDF export works, Google Calendar required one-time re-auth (expected: per-install tokens, fresh data dir). `APP_MODE=server` is correct (Supabase-connected); no app rewiring needed.
  - **Recurring lesson:** every defect was "packaged build doesn't replicate what dev provides" (deps / `.env` / `node_modules` assets / entitlements / port). Boot-test packaged builds, don't just build them. The dev path (`npm run start:electron`) masks all of these because it has the venv, repo `.env`, repo `node_modules`, no hardened runtime, and passes the port arg.
- **Electron beta release run with Intel Mac support** — Tag `electron-supabase-beta-v0.0.1` was re-pointed to PR branch `feat/supabase-multitenant-electron` without merging to `main`. Workflow commits `557036b` and `e774624` split macOS into a matrix (`x64` on `macos-15-intel`, `arm64` on `macos-latest`) and removed the package-level mac arch list so `--mac --x64` / `--mac --arm64` are authoritative. First retry run `26927056676` failed because Electron Builder still packaged arm64 inside the x64 job; final retry run `26927391284` passed with Windows, macOS arm64, macOS x64, and publish jobs all successful. Draft prerelease `electron-supabase-beta-v0.0.1` contains Intel DMG (`Bulletin.Generator-0.0.1.dmg`), arm64 DMG (`Bulletin.Generator-0.0.1-arm64.dmg`), blockmaps, Windows installer, `latest.yml`, and `latest-mac.yml`; no raw `server.exe` asset is published.
- **Electron beta release workflow prep** — `release-electron.yml` now accepts `electron-supabase-beta-v*` tags, builds the Electron sidecar from `server.py` directly instead of the deprecated `launcher.py` spec, handles Windows `server.exe` packaging, and maps existing Apple signing/notary secrets (`APPLE_CERTIFICATE*`, `APPLE_NOTARY_KEY_*`) to Electron Builder inputs. Added `scripts/watch_github_release_run.py` to poll a release run by tag and notify on pass/fail.
- **Electron icon options** — Added three app icon candidates under `assets/app-icons/electron/` (`bulletin-blueprint`, `bulletin-warm-print`, `bulletin-calendar-slate`) with SVG sources, 1024 PNG previews, and macOS ICNS outputs. `bulletin-blueprint` is wired as the Electron macOS/Windows package icon in `package.json`; a Windows ICO was generated for that default.
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
- **🔴 Chrome required at startup (not yet fixed).** `server.py:529` resolves `_find_chrome()` eagerly at import in `APP_MODE=server`; it raises if Chrome/Chromium is absent → sidecar exits 1 → "Server Error" on any machine without Google Chrome. PDF export also always POSTs `/api/pdf` (server-side Chrome); the Electron `printToPDF` IPC bridge in `electron/preload.js` is dead code (`server.py:2754` TODO confirms). Recommended: make Chrome resolution lazy (resolve in `_handle_pdf` at request time, clear error if missing) so the app starts everywhere; longer-term wire renderer → `window.electronAPI.generatePdf`. Not blocking the developer (has Chrome); a distribution landmine.
- **🔴 Extractable DB creds in DMG (issue [#277](https://github.com/ajhochy/bulletin-generator/issues/277)).** Bundled `.env` contains `DATABASE_URL` (DB-owner role, bypasses RLS) — extractable from the distributed binary. Accepted as ship-now tradeoff for a *private* distribution. Keep releases draft/non-public; rotate DB password if a build leaks. Proper fix = anon-key + RLS data path (renderer via supabase-js).
- **Orphaned sidecar holds port 8765.** If the app crashes (vs. clean quit), its Python sidecar can be orphaned and keep 8765 bound, causing "Exit code 1" on the next launch (bind fails). `main.js` before-quit kills the sidecar but a crash bypasses it. Harden: sidecar should fail fast with a clear message on bind error, and/or main process should detect/clear a stale listener on startup.
- **Slow startup** — PyInstaller `--onefile` unpacks the runtime to a temp dir every launch. Switch to `--onedir` (packaged inside the .app) for faster cold start if startup time matters.
- **Old draft betas carry secrets** — delete draft prereleases `electron-supabase-beta-v0.0.1/2/3` (their DMGs bundle the extractable `DATABASE_URL`); keep only the latest verified build.

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
