# 011: Electron scaffold + spawn server.py sidecar

**Milestone:** M4  ·  **Plan ref:** issue 15
**Depends on:** none (can begin in parallel with M2/M3; the renderer just needs `server.py` to be running)

## Context

Decision D4: Electron wraps the existing vanilla-JS frontend — no React rewrite. The Electron main process spawns a PyInstaller-compiled `server.py` binary as a sidecar, polls `GET /api/bootstrap` until it responds 200, then calls `mainWindow.loadURL('http://localhost:<port>')`. The existing UI renders unchanged in Electron's Chromium renderer. `launcher.py` is the macOS-specific predecessor and is retired for this distribution (it will remain for the legacy `.app` bundle until cutover QA passes).

## Acceptance criteria

- [ ] `electron/` directory created with at minimum `main.js` and `preload.js`.
- [ ] `package.json` updated with `electron`, `electron-builder` (or equivalent packaging tool) as devDependencies; an `npm run electron` script launches the app in development mode (spawning a local `server.py` process from the repo root).
- [ ] `electron/main.js`: spawns the server sidecar (in dev: `python3 server.py`; in packaged: `resources/server/server` binary); polls `GET /api/bootstrap` with a 200ms interval and a 30-second timeout; on success calls `mainWindow.loadURL('http://localhost:8765')` (matching `launcher.py`'s port); on timeout shows an error dialog.
- [ ] `electron/main.js`: when the Electron app quits, the spawned server process is killed (no zombie processes).
- [ ] `electron/preload.js`: exposes a minimal `contextBridge` API — at minimum `ipcRenderer.invoke('print-to-pdf', ...)` for issue 012. No `nodeIntegration: true` (security: renderer isolation must be maintained).
- [ ] `npm run electron` launches the app and the existing UI loads at `http://localhost:8765` in the Electron window. DevTools console is clean.
- [ ] `bulletin-generator.spec` (PyInstaller) is updated to produce a `server` binary in a location that `electron/main.js` can find in packaged mode (e.g. `resources/server/server`).
- [ ] `electron-builder` config (in `package.json` or `electron-builder.yml`) includes the PyInstaller output as an `extraResource`.

## Likely files

- `electron/main.js` (new)
- `electron/preload.js` (new)
- `package.json` (modify — devDependencies, scripts)
- `bulletin-generator.spec` (modify — output path for packaging as Electron resource)
- `electron-builder.yml` or `package.json` build config (new/modify)
- `docs/ai/project-state.md` (update)

## Tests / validation

```bash
npm run electron
# → Electron window opens, existing UI loads, DevTools console clean.

npm run build
# → vite build still succeeds (renderer assets built to dist/).
```

Manual smoke:
1. `npm run electron` — app opens, loads the bulletin UI.
2. Navigate through tabs (Order of Worship, Announcements, Calendar, Templates) — no console errors.
3. Quit the Electron app — confirm the `python3 server.py` process is no longer running (`ps aux | grep server.py`).
4. Simulate a slow-starting server (add a `time.sleep(5)` to `server.py` startup in dev) — confirm the Electron window waits and then loads rather than showing a blank page.

Note: issue 012 (printToPDF) and issue 013 (Electron auth) depend on this scaffold; smoke tests for those features are deferred.

## Data-safety / out of scope

- `nodeIntegration` must remain `false` in the renderer; all Node APIs exposed to the renderer go through `contextBridge` only.
- The server sidecar binary (PyInstaller output) must not be committed to the repo — it is built by CI (issue 014).
- Out of scope: macOS code signing, Windows build, or auto-update (issue 014).
- Out of scope: replacing `launcher.py` in production — that is issue 014 (packaging + cutover).
