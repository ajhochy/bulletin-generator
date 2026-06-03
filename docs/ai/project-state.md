# Project State

_Last updated: 2026-06-03 (issue 012 coding-agent run complete)_

## Current focus

Branch: `feat/supabase-multitenant-electron`. Milestone: Supabase + Multi-tenant + Electron (#30).

Issue 012 (PDF via Electron printToPDF) coding-agent run complete; awaiting verification-gate. Manual dev smoke (`npm run start:electron` + PDF export round-trip) required before closing.

## Recently completed (this branch)

- **001–008, 019** — Supabase schema, RLS, db.py, storage, auth, frontend auth, first-login provisioning, CI DB integration. See earlier run entries.
- **011** — Electron scaffold. `electron/main.js` + `electron/preload.js` (new). `package.json`: `"main"`, `"start:electron"`, `"electron": "^28.3.3"` devDep. `docs/ai/testing-guide.md`: Electron dev launch section. Verification PASS: 100 pytest, 71 vitest, vite build.
- **012** — PDF via Electron printToPDF. `electron/main.js`: `pdf:generate` IPC handler. `electron/preload.js`: `window.electronAPI.generatePdf()` bridge. `server.py`: `APP_MODE=electron` accepted, `IS_ELECTRON` flag, Chrome not required at startup, `/api/pdf` returns 501 with IPC redirect message. `tests/test_pdf.py` (new): 14 tests, all pass.

## In progress

- Issue 012 coding-agent run done; awaiting verification-gate PASS.
- Issue 011 manual dev smoke and draft PR still pending.

## Open risks

- Automated coverage is partial: pytest covers server.py utilities/handlers and vitest covers `src/js/modules/*` pure logic; UI behavior and Electron launch are manual-only.
- `provision_first_login` (issue 008) has no live-DB integration test. Seed a `workspace_settings` row with `allowed_domains` on staging before production.
- `npm audit` reports vulnerabilities in electron's transitive deps (3 moderate, 2 high, 1 critical). All are in devDependencies only; not in the runtime app surface. Monitor for electron patch releases.
- Issue 012 PDF path: manual smoke is required to confirm `webContents.printToPDF()` produces correct pagination/footers/QR — this cannot be automated.

## Next step

1. Verification-gate for issue 012.
2. Manual dev smoke: `npm run start:electron` → export a PDF → confirm pagination/footers/QR match the headless-Chrome output.
3. Open draft PRs for issues 011 + 012.
4. Next issue: **013** — Supabase auth in Electron (deep-link/custom-protocol). Depends on 011 + 012.

## Recent coding-agent runs

### 2026-06-03 — electron-pdf (issue 012)
- Files modified:
  - `electron/main.js` — added `ipcMain` + `os` imports; added `pdf:generate` IPC handler. Creates a hidden offscreen BrowserWindow, loads the print HTML via `loadFile()`, calls `webContents.printToPDF({ pageSize: { width, height } (microns), printBackground, margins: none })`, writes PDF bytes to a temp file, resolves with the path. Hidden window is always destroyed in a `finally` block.
  - `electron/preload.js` — replaced the stub with a real `contextBridge.exposeInMainWorld('electronAPI', { generatePdf })` bridge. `generatePdf(opts)` calls `ipcRenderer.invoke('pdf:generate', opts)`.
  - `server.py` — (1) `APP_MODE` validation now accepts `"electron"` alongside `"server"` and `"desktop"`. (2) `IS_ELECTRON = APP_MODE == "electron"` flag added. (3) `IS_DESKTOP` now `True` for both `"desktop"` and `"electron"`. (4) `CHROME_PATH` deferred: `None` when `APP_MODE=electron`, `_find_chrome()` otherwise (avoids RuntimeError at startup when Chrome isn't installed in Electron mode). (5) `_handle_pdf`: early return with HTTP 501 + TODO comment when `IS_ELECTRON` is True.
  - `tests/test_pdf.py` (new) — 14 pytest tests covering: APP_MODE=electron flag values, IS_ELECTRON/IS_DESKTOP, CHROME_PATH=None in electron mode, `_handle_pdf` returns 501 in electron mode, auth guard fires before 501, input validation (400/413) unchanged in non-electron modes, route registration.
  - `docs/ai/project-state.md` — this entry.
- Checks run:
  - `node --check electron/main.js && node --check electron/preload.js` → JS syntax OK.
  - `APP_MODE=electron python -c "import server; ..."` → APP_MODE=electron, IS_ELECTRON=True, IS_DESKTOP=True, CHROME_PATH=None. Confirmed for desktop and server modes too.
  - `pytest tests/test_pdf.py -v` → 14 passed.
  - `ai-workflow checks --level issue` → PASS (100 pytest, 71 vitest).
- Decisions made:
  - Accepted the "simpler alternative" from the issue spec: HTTP 501 + TODO in server.py for the electron IPC path, rather than full Python↔Node IPC plumbing. The `pdf:generate` IPC handler in main.js is the production path; the renderer calls `window.electronAPI.generatePdf()` directly (issue 013 will wire this call site in the JS).
  - `IS_DESKTOP` kept True for `APP_MODE=electron` — electron is a desktop variant; all single-user guards and desktop-only code paths should apply.
  - Page dimensions for `printToPDF` converted from inches to microns (Electron API requires microns): `Math.round(pageW * 25400)`. The existing server.py defaults of 5.5 × 8.5 in are preserved.
  - Offscreen BrowserWindow destroyed in `finally` to prevent leaks even on `printToPDF` rejection.
  - Preload: migrated from the comment-stub to a real `contextBridge.exposeInMainWorld` using ESM `import` (matches the file's existing style; root `package.json` has `"type": "module"`).
- Deviations from spec: none. All three acceptance criteria addressed (IPC handler, server.py detection, tests).
- Concerns:
  - PDF quality/pagination can only be confirmed by manual smoke — `webContents.printToPDF()` may produce subtly different output than headless Chrome (font rendering, CSS variable resolution). Manual round-trip required before closing issue 012.
  - The renderer call site (`window.electronAPI.generatePdf()`) is wired in preload but not yet called from the JS UI — that wiring is issue 013's scope. Until then the new IPC handler is present but unreachable from the running app.
  - Temp directory created by `fs.mkdtempSync` is not cleaned up after the caller reads the PDF file. Issue 013 should add cleanup after the save-dialog resolves.

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
