# 012: PDF generation via Electron webContents.printToPDF

**Milestone:** M4  ·  **Plan ref:** issue 16
**Depends on:** 011

## Context

`server.py`'s `/api/pdf` route spawns a headless Chrome process (`_find_chrome()`) to render HTML to PDF. This is a brittle dependency: Chrome must be installed and discoverable on the host; it blocks server startup if not found; and it is redundant when running inside Electron which already embeds Chromium. D4: replace `/api/pdf` with `Electron webContents.printToPDF`, which renders the existing print-ready HTML at native Chromium fidelity. The print-HTML pipeline (`src/js/preview.py`'s `renderPrintHTML()` and the `POST /api/pdf { html, filename, pageWidth, pageHeight }` contract) stays unchanged.

## Acceptance criteria

- [ ] `electron/main.js` handles an IPC message `print-to-pdf` from the renderer: creates a hidden `BrowserWindow`, loads the print HTML (passed as a data URL or a temporary `file://` path), calls `webContents.printToPDF({printBackground: true, pageSize: {width, height}})`, returns the PDF buffer to the renderer via IPC reply.
- [ ] `electron/preload.js` exposes `window.electronAPI.printToPDF(html, pageWidth, pageHeight, filename)` via `contextBridge`.
- [ ] `src/js/preview.js` (or a new `src/js/pdf.js`) detects Electron (`window.electronAPI?.printToPDF`) and uses it in preference to `POST /api/pdf`. Falls back to `POST /api/pdf` in browser/server mode (no regression).
- [ ] The Electron PDF output matches the current Chrome-headless output for a known test bulletin: correct pagination, footers, cover image, QR codes. (Manual visual comparison required.)
- [ ] `/api/pdf` route in `server.py` is kept but marked as a fallback for non-Electron deployments (server/Docker mode); `_find_chrome()` continues to work for those deployments.
- [ ] `npm run build` succeeds; `node --check src/js/preview.js` (or the affected file) passes.

## Likely files

- `electron/main.js` (modify — add `print-to-pdf` IPC handler)
- `electron/preload.js` (modify — expose `printToPDF` via contextBridge)
- `src/js/preview.js` (modify — Electron detection + fallback)
- `server.py` (no change required, but verify `/api/pdf` still works for server mode)

## Tests / validation

```bash
node --check src/js/preview.js
npm run build
npm run electron
```

Manual smoke (Electron):
1. Open a bulletin project with a cover image, section headings, song lyrics, and a QR code.
2. Click "Export PDF" — confirm the PDF opens/downloads without error.
3. Visually compare: pagination matches Chrome-headless output; cover renders; QR code present; footers correct.
4. Test with both portrait and landscape page sizes (if supported).

Manual smoke (server/browser mode, no regression):
5. Run `python3 server.py`; open in a browser; export PDF — confirm `/api/pdf` still works.

## Data-safety / out of scope

- The hidden BrowserWindow for PDF rendering must be destroyed after use (no memory leak accumulation per export).
- Do not pass the user's Supabase session token to the hidden BrowserWindow — PDF rendering only needs the print HTML.
- Out of scope: print dialog UI or print preview UX changes — the PDF export button flow remains identical.
- Out of scope: PDF password protection or DRM — not planned.
