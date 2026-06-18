---
date: 2026-06-03
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# Issue 012: HTTP 501 + TODO instead of live Python↔Node IPC for `/api/pdf` in electron mode

**Context.** The issue spec offered two paths for PDF generation in Electron mode: (A) full IPC between the Python sidecar and the Electron main process (e.g. a local socket or temp-file polling), or (B) the "simpler alternative" — detect `APP_MODE=electron` in `server.py`, return HTTP 501 with a redirect message, and implement the IPC handler in `electron/main.js` so the renderer can call `window.electronAPI.generatePdf()` directly.

**Decision.** Chose option B. The renderer's existing PDF export flow (in `src/js/preview.js`) will be updated in issue 013 to call `window.electronAPI.generatePdf()` instead of `POST /api/pdf` when `window.electronAPI` is present. The Python sidecar therefore never needs to be the PDF intermediary; the renderer owns the PDF request entirely in electron mode.

**`IS_DESKTOP = True` for `APP_MODE=electron`.** Electron is a desktop variant — single-user, no collaboration features, no DATABASE_URL required. All `IS_DESKTOP` guards in `server.py` should apply identically.

**`CHROME_PATH` deferred.** `CHROME_PATH = _find_chrome()` is called at module load time and raises `RuntimeError` when Chrome isn't installed. In electron mode Chrome is never used. The fix: `None if APP_MODE == electron else _find_chrome()`. This is evaluated from `os.environ` directly (before the `IS_ELECTRON` alias is defined) to keep the deferred evaluation correct at import time.

**Page dimensions.** Electron's `printToPDF` `pageSize` field uses microns, not inches. Conversion: `Math.round(inches * 25400)`. Existing server.py defaults (5.5 × 8.5 in) are preserved as the fallback.

**Temp-dir cleanup.** `fs.mkdtempSync` in `pdf:generate` creates the output directory but does not clean it up — the caller (issue 013 JS wiring) must delete after the save-dialog resolves. Documented as a concern; not a blocker for this issue.

**Consequences.**
- Issue 013 (Supabase auth in Electron) must also wire the call-site: detect `window.electronAPI?.generatePdf`, call it, handle the returned path to trigger a save dialog. Until then the IPC handler is present but unreachable from the running UI.
- If a non-renderer process (e.g. a CLI migration script) ever needs PDF generation in electron mode, a local socket IPC path can be added to `_handle_pdf` per the TODO comment in `server.py`.
