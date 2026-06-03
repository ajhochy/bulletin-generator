# Project State

_Last updated: 2026-06-03 (issue 011 done)_

## Current focus

Branch: `feat/supabase-multitenant-electron`. Milestone: Supabase + Multi-tenant + Electron (#30).

Issue 011 (Electron scaffold) is done. `electron/main.js` and `electron/preload.js` committed; `package.json` updated with electron 28 devDep. Dev smoke (`npm run start:electron`) is manual-only — requires a human to confirm BrowserWindow opens and tray icon appears.

## Recently completed (this branch)

- **001–008, 019** — Supabase schema, RLS, db.py, storage, auth, frontend auth, first-login provisioning, CI DB integration. See earlier run entries.
- **011** — Electron scaffold. `electron/main.js` + `electron/preload.js` (new). `package.json`: `"main"`, `"start:electron"`, `"electron": "^28.3.3"` devDep. `docs/ai/testing-guide.md`: Electron dev launch section. Verification PASS: 100 pytest, 71 vitest, vite build.

## In progress

- Issue 011 verified; awaiting manual dev smoke (`npm run start:electron`) and draft PR before marking fully closed.

## Open risks

- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic; UI behavior and Electron launch are manual-only.
- `provision_first_login` (issue 008) has no live-DB integration test. Seed a `workspace_settings` row with `allowed_domains` on staging before production.
- `npm audit` reports vulnerabilities in electron's transitive deps (3 moderate, 2 high, 1 critical). All are in devDependencies only; not in the runtime app surface. Monitor for electron patch releases.

## Next step

1. Manual dev smoke for issue 011: `npm run start:electron` — confirm BrowserWindow opens to `http://localhost:8765/`, tray icon visible, Quit kills sidecar.
2. Open draft PR for issue 011.
3. Next issue: **012** — PDF generation via `Electron webContents.printToPDF` (replaces headless Chrome in `/api/pdf`). Depends on 011.

## Recent coding-agent runs

### 2026-06-03 — electron-scaffold (issue 011)
- Files modified:
  - `electron/main.js` (new) — Electron main process. Spawns `server.py` sidecar on port 8765 (`python3 server.py 8765` in dev; `<resourcesPath>/server` in packaged mode). `waitForServer()` polls http://localhost:8765/ up to 20 s. Opens BrowserWindow (1280×900, contextIsolation on, nodeIntegration off, preload wired). Creates tray icon from `menubar-icon.png` with "Open Bulletin Generator" + separator + "Quit". Kills sidecar on `before-quit`; shows error dialog if sidecar crashes.
  - `electron/preload.js` (new) — Intentionally minimal. contextIsolation boundary. No APIs exposed to renderer (app talks to Python sidecar directly over HTTP). Comments scaffold the `contextBridge.exposeInMainWorld` extension point.
  - `package.json` — Added `"main": "electron/main.js"`, `"start:electron": "electron ."` script, `"electron": "^28.3.3"` devDependency.
  - `docs/ai/testing-guide.md` — Added "Electron desktop (dev mode)" section: `npm run start:electron`, expected behaviors, packaged-mode path note.
- Checks run:
  - `node --check electron/main.js && node --check electron/preload.js` → JS syntax OK.
  - `./node_modules/.bin/electron --version` → v28.3.3.
  - `ai-workflow checks --level issue` → PASS (100 pytest, 71 vitest).
- Decisions made:
  - Used ESM `import` syntax in `main.js` (root package.json has `"type": "module"`). Electron 28 supports ESM main entry points.
  - Dev-mode sidecar command: `python3 server.py 8765` (passes port as argv, matching server.py's existing `sys.argv[1]` port override). Packaged-mode path probes `process.resourcesPath/server` — scaffolded now, binary doesn't exist until issue 014.
  - `sidecarExited` boolean prevents double-kill races between `before-quit` and the `exit` handler.
  - Tray keeps app alive on macOS when BrowserWindow is closed (standard macOS convention).
- Deviations from spec: none.
- Concerns:
  - Dev smoke (`npm run start:electron`) requires Python 3 in PATH and `server.py` dependencies installed. Full end-to-end smoke is manual only — not automated.
  - `launcher.py` NOT deleted per spec — deprecation deferred to issue 014.
  - Vulnerabilities reported by `npm audit` are in electron's own transitive deps; none are in the runtime app surface. Not blocking for a devDependency-only install.

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
