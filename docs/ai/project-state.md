# Project State

_Last updated: 2026-06-03 (issue 013 verification PASS)_

## Current focus

Branch: `feat/supabase-multitenant-electron`. Milestone: Supabase + Multi-tenant + Electron (#30).

Issue 013 (Supabase Auth in Electron) is verified PASS (100 pytest, 71 vitest, vite build, `node --check` all files). Awaiting manual smoke (Google OAuth + magic-link in Electron) and draft PR before marking fully closed. See `MANUAL-STEPS.md` — "Electron Auth Deep-Link Setup" for the smoke checklist.

## Recently completed (this branch)

- **001–008, 019** — Supabase schema, RLS, db.py, storage, auth, frontend auth, first-login provisioning, CI DB integration. See earlier run entries.
- **011** — Electron scaffold. `electron/main.js` + `electron/preload.js` (new). `package.json`: `"main"`, `"start:electron"`, `"electron": "^28.3.3"` devDep. Verification PASS: 100 pytest, 71 vitest, vite build.
- **013** — Supabase Auth in Electron. `electron/main.js`: `bulletingen` protocol + `open-url` (macOS) + `second-instance` (Windows) handlers. `electron/preload.js`: `contextBridge.exposeInMainWorld('electronAuth', { onCallback })`. `src/js/auth-ui.js`: `_isElectronMode()`, `_authRedirectUrl()` returns `bulletingen://auth-callback` in Electron, `initAuth()` registers `electronAuth.onCallback` + calls `exchangeCodeForSession(url)`. `MANUAL-STEPS.md`: redirect allow-list step activated + Issue 013 smoke section added. Verification PASS: 100 pytest, 71 vitest, vite build.

## In progress

- Manual smoke for issue 013 pending (Electron auth flows require human to run `npm run start:electron`).

## Open risks

- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic; UI behavior and Electron launch are manual-only.
- `provision_first_login` (issue 008) has no live-DB integration test. Seed a `workspace_settings` row with `allowed_domains` on staging before production.
- `npm audit` reports vulnerabilities in electron's transitive deps (3 moderate, 2 high, 1 critical). All are in devDependencies only; not in the runtime app surface. Monitor for electron patch releases.
- Issue 013: `exchangeCodeForSession(url)` requires PKCE enabled in the Supabase project. Confirm PKCE is active in the dashboard before Electron auth smoke. See `docs/ai/decisions.md` for rationale.

## Next step

1. Add `bulletingen://auth-callback` to the Supabase dashboard redirect allow-list (see `MANUAL-STEPS.md` — Electron Auth Deep-Link Setup section, step 1).
2. Manual smoke for issue 013: `npm run start:electron` → Google OAuth → magic-link in Electron.
3. Open draft PR for issues 011 + 013.
4. Next issue: **012** — PDF generation via `Electron webContents.printToPDF` (replaces headless Chrome in `/api/pdf`). Depends on 011.

## Recent coding-agent runs

### 2026-06-03 — electron-auth-deep-link (issue 013)
- Files modified:
  - `electron/main.js` — added `app.setAsDefaultProtocolClient('bulletingen')`, `extractDeepLinkUrl()`, `handleDeepLink()` helpers; `open-url` event handler (macOS); `requestSingleInstanceLock()` + `second-instance` event handler (Windows/Linux). Updated JSDoc to list responsibility 6.
  - `electron/preload.js` — replaced stub with `contextBridge.exposeInMainWorld('electronAuth', { onCallback(cb) })`. Imports `contextBridge` and `ipcRenderer` from `electron`.
  - `src/js/auth-ui.js` — added `_isElectronMode()` (checks `window.electronAuth?.onCallback`); updated `_authRedirectUrl()` to return `bulletingen://auth-callback` when in Electron mode; added Electron callback block in `initAuth()` that calls `client.auth.exchangeCodeForSession(url)` when a deep-link fires.
  - `MANUAL-STEPS.md` — updated "bulletingen://auth-callback" redirect URL note from conditional to instructional; added "Electron Auth Deep-Link Setup (Issue 013)" section with 4 smoke-test steps.
- Checks run:
  - `node --check electron/main.js && node --check electron/preload.js && node --check src/js/auth-ui.js` → JS OK.
  - `ai-workflow checks --level issue` → PASS (100 pytest, 71 vitest).
- Decisions made:
  - Used `client.auth.exchangeCodeForSession(url)` (Supabase JS v2 PKCE API) rather than manually parsing the URL fragment. If implicit flow is in use, `onAuthStateChange` will still fire a SIGNED_IN event as Supabase detects the fragment, so both flows are covered.
  - `_isElectronMode()` checks `window.electronAuth?.onCallback` at call time rather than at module init — future-safe if the bridge is injected asynchronously.
  - `requestSingleInstanceLock()` placed at module top-level (before `whenReady`) so it runs on process start, matching Electron documentation requirement.
  - `_isDesktopMode()` logic unchanged: returns true only when `BULLETIN_SUPABASE_CONFIG.url` is absent. The legacy desktop (no Supabase) still bypasses auth; the new Electron mode with Supabase configured goes through the Supabase auth path.
- Deviations from spec: none.
- Concerns:
  - `exchangeCodeForSession` requires PKCE to be enabled in the Supabase project; implicit-flow deployments would need `setSession` instead. Confirm dashboard setting.
  - The `onCallback` listener is never explicitly removed (no `off` mechanism used), but it's a single stable registration per `initAuth()` call and the BrowserWindow lifetime bounds the preload context.
  - Manual smoke (Google OAuth + magic-link completing in Electron) is required before marking done.

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
