# Project State

_Last updated: 2026-06-03 (issue 014 verification PASS)_

## Current focus

Branch: `feat/supabase-multitenant-electron`. Milestone: Supabase + Multi-tenant + Electron (#30).

Issues 011, 013, and 014 are code-complete and automated-verified. All three await manual dev smoke and draft PRs. Issue 012 (PDF via Electron printToPDF) is complete on the parallel PR branch and merged into the worktree history.

## Recently completed (this branch)

- **001–008, 019** — Supabase schema, RLS, db.py, storage, auth, frontend auth, first-login provisioning, CI DB integration. See earlier run entries.
- **011** — Electron scaffold. `electron/main.js` + `electron/preload.js` (new). `package.json`: `"main"`, `"start:electron"`, `"electron": "^28.3.3"` devDep. Verification PASS: 100 pytest, 71 vitest, vite build.
- **013** — Supabase Auth in Electron. `bulletingen://` protocol deep-link, `open-url`/`second-instance` handlers, `electronAuth.onCallback` preload bridge, `exchangeCodeForSession` in `auth-ui.js`. Verification PASS: 100 pytest, 71 vitest, vite build.
- **014** — Electron packaging + auto-update. `electron-builder` config in `package.json` (macOS DMG + notarize, Windows NSIS, extraResources sidecar, GitHub publish), `electron-updater` wired in `electron/main.js`, `.github/workflows/release-electron.yml` (new), `MANUAL-STEPS.md` secrets setup section, `launcher.py` deprecated. Verification PASS: 100 pytest, 71 vitest, vite build, `node --check`, YAML valid.

## In progress

- Manual smoke for issues 011, 013, 014 pending — all require `npm run start:electron` (human). See `MANUAL-STEPS.md` for each checklist.
- Draft PRs for 011, 013, 014 not yet opened.
- `package-lock.json` needs regeneration: `electron-updater` added to `dependencies` but lock file not updated. Run `npm install` before merging.

## Open risks

- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic; UI behavior and Electron launch are manual-only.
- `provision_first_login` (issue 008) has no live-DB integration test. Seed a `workspace_settings` row with `allowed_domains` on staging before production.
- `npm audit` reports vulnerabilities in electron's transitive deps (3 moderate, 2 high, 1 critical). All are in devDependencies only; not in the runtime app surface. Monitor for electron patch releases.
- Issue 013: `exchangeCodeForSession(url)` requires PKCE enabled in the Supabase project. Confirm PKCE is active in the dashboard before Electron auth smoke. See `docs/ai/decisions.md` for rationale.
- Issue 014 PyInstaller `--onefile` path: the CI workflow passes `--onefile --name server` to override the spec's default `COLLECT` layout. This may require a dedicated `server.spec` file if `hiddenimports` (e.g. `rumps` on macOS, excluded on Windows) don't resolve correctly. Monitor first CI run on a tag push.
- Windows NSIS installer is unsigned (`signingHashAlgorithms: null`). SmartScreen will show "Unknown publisher" warning until a Windows EV/OV certificate is obtained. Documented as TODO in `MANUAL-STEPS.md`.
- Notarization uses `mac.notarize.teamId: "${APPLE_TEAM_ID}"` — requires `APPLE_TEAM_ID` GitHub Secret to be set before the first tag push.

## Next step

1. Run `npm install` to regenerate `package-lock.json` with `electron-updater` entry, then commit the updated lock file.
2. Add `bulletingen://auth-callback` to the Supabase dashboard redirect allow-list (see `MANUAL-STEPS.md` — Electron Auth Deep-Link Setup section, step 1).
3. Manual smoke for issues 011 + 013 + 014: `npm run start:electron` → confirm window + tray → Google OAuth → magic-link → confirm update check fires on next packaged build.
4. Open draft PRs for issues 011, 013, 014.
5. Next automated issue: **015** — workspace seeding + data migration (depends on 001–008).

## Recent coding-agent runs

### 2026-06-03 — electron-packaging-auto-update (issue 014)
- Files modified:
  - `package.json` — added `"package:electron"` script; added `"build"` electron-builder config block (appId, productName, files, extraResources for dist/server binary, publish=github, mac dmg + notarize, win nsis + signingHashAlgorithms:null); added `"electron-builder": "^24.13.3"` devDependency; added `"electron-updater": "^6.3.9"` dependency.
  - `electron/main.js` — added `import { autoUpdater } from 'electron-updater'`; added `configureAutoUpdater()` function (guarded by `app.isPackaged`, autoDownload=true, autoInstallOnAppQuit=true, update-available dialog, update-downloaded restart dialog, error logger, `checkForUpdatesAndNotify()`); called from `mainWindow.webContents.once('did-finish-load')` inside `app.whenReady`.
  - `.github/workflows/release-electron.yml` (new) — two jobs: `electron-macos` (macos-latest: PyInstaller sidecar → import cert → `electron-builder --mac --publish always`) and `electron-windows` (windows-latest: PyInstaller sidecar → `electron-builder --win --publish always`). Triggered on `push: tags: v*`.
  - `MANUAL-STEPS.md` — appended "Electron Packaging + Auto-Update Setup (Issue 014)" section: required secrets table, how to export/encode .p12, how to find Team ID, how to create app-specific password, trigger-a-release example, Windows signing TODO, launcher.py deprecation note.
  - `launcher.py` — added DEPRECATED docstring comment explaining that the Electron build (issue 011+014) supersedes this launcher; do-not-delete note for Docker server-mode users.
  - `docs/ai/project-state.md` — this entry.
- Checks run:
  - `node --check electron/main.js` → JS OK.
  - `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-electron.yml'))"` → YAML valid.
  - `python3 scripts/run_ai_workflow.py checks --level issue` → PASS (100 pytest, 71 vitest).
- Decisions made:
  - `electron-updater` added to `dependencies` (not `devDependencies`) because it is imported at runtime inside the packaged app.
  - `electron-builder` added to `devDependencies` because it is only used to build the distributable, not at runtime.
  - `autoUpdater` import uses `electron-updater` package (not the built-in `electron.autoUpdater`) — `electron-updater` supports GitHub Releases publish provider and is the standard choice with electron-builder.
  - `configureAutoUpdater()` is no-op when `!app.isPackaged` — prevents errors in dev mode where no `app-update.yml` exists.
  - `mac.identity: null` in package.json — electron-builder uses the `CSC_LINK` env var from CI (set via GitHub Secret); `null` allows the env-var path to take effect without hardcoding a team identity string.
  - `dmg.sign: false` — electron-builder sometimes double-signs the outer DMG; the app bundle inside is already signed; `sign: false` avoids that.
  - Windows `signingHashAlgorithms: null` — no Windows certificate available; documented as TODO in MANUAL-STEPS.md.
  - PyInstaller `--onefile --name server` flags override the spec's default `COLLECT` layout to produce a single `dist/server` (or `dist/server.exe`) executable — this is what `extraResources` maps into the app bundle. The existing spec produces a directory layout (`dist/BulletinGenerator/`) which electron-builder cannot directly use as a single binary resource.
  - See `docs/ai/decisions.md` for the D4 decision (electron-builder replaces PyInstaller+Watchtower for desktop distribution).
- Deviations from spec:
  - The issue spec says the PyInstaller spec bundles `launcher.py` as the entry point. The CI workflow overrides this with `--onefile --name server` to produce a single binary. This is consistent with how `electron/main.js` expects to find the sidecar at `<resourcesPath>/server`. The spec's `BUNDLE` step (which creates `Bulletin Generator.app`) is not used in the Electron build path.
- Concerns:
  - `electron-updater` is a `dependency` but the worktree `package-lock.json` won't include it until `npm install` is run. CI runs `npm ci` which reads the lock file — the lock file will need to be updated before merging. Run `npm install` locally to regenerate it.
  - The PyInstaller `--onefile` flag is not in the existing spec and may not handle all `hiddenimports` (e.g. `rumps`) correctly on macOS. On Windows, `rumps` is not available at all and must be excluded. The CI macOS job installs `rumps` so PyInstaller can find it; the Windows job does not. The `--onefile` path may need a dedicated `server.spec` file rather than patching the existing spec at invocation time — monitor the first CI run.
  - Notarization uses `mac.notarize.teamId: "${APPLE_TEAM_ID}"` — electron-builder interpolates this from env at build time. Confirm that `APPLE_TEAM_ID` secret is set before the first tag push.
  - Windows builds produce an unsigned NSIS installer; SmartScreen will warn end-users. Documented as TODO in MANUAL-STEPS.md.

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
