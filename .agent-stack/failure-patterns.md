## 2026-06-03 — Issue 007 — Supabase frontend auth smoke passed

- **Result**: smoke PASS
- **Category**: none — no correctness failure
- **Criteria affected**: Google OAuth login, magic-link login, sign-out, unauthenticated login gate, authenticated app data loading
- **Root cause**: No failure; manual smoke confirmed the frontend Supabase auth flow after issue 005 provider validation.
- **Suggested fix**: Add acceptance-contract coverage for future auth issues before coding-agent so manual smoke criteria are represented by durable contract tests.

## 2026-06-08 — Issue 277-D — sandboxed preload ESM import broke desktop app (smoke FAIL, CI claimed PASS)

- **Result**: smoke FAIL (verification claimed PASS — all CI green incl. electron-mode e2e)
- **Category**: C2 — Wrong contract (test simulated the seam instead of exercising it)
- **Criteria affected**: issue-277-D-electron-data-routing
- **Root cause**: electron/preload.js used ESM `import` but the BrowserWindow runs sandbox:true (Electron 28 default) where preloads must be CommonJS; `"type":"module"` made the .js preload parse as ESM → preload failed to load → window.electronAuth undefined → isElectronMode() false → server fallback → no projects. The 277-D e2e smoke injected window.electronAuth via addInitScript, so it never loaded the real preload (green CI, broken app).
- **Suggested fix**: launch the real Electron app in the smoke (Playwright `_electron` under xvfb) or add a node-level load-test of preload.cjs; never let an injected-shim browser test stand in for real-runtime preload/IPC loading. Fixed in commit f339f21 (preload.js → preload.cjs + require).

## 2026-06-08 — Issue 277-D — injected-shim electron e2e masked FOUR real-app bugs (smoke FAIL→PASS after repair)

- **Result**: manual smoke FAIL (CI/e2e claimed PASS) → PASS after 5 fixes.
- **Category**: C2 ×4 — Wrong contract (test simulated the seam, not the runtime).
- **Bugs found in manual smoke that the e2e missed**: (1) sandboxed preload ESM import → bridge dead; (2) renderer writes lacked session workspace_id → RLS 403 across presence/project/announcement/song/template/settings; (3) sdGetProjects pulled full state JSONB (~27MB) on a 30s poll; (4) inserts sent null id → NOT NULL violation (default never fired).
- **Root cause**: electron-mode-data-routing.spec.ts injects window.electronAuth in a plain browser vs a server-mode webserver and only asserts read-request URLs — it never loads the real preload, logs in as a real member, or does RLS-checked writes.
- **Suggested fix**: real Electron launch (Playwright _electron + xvfb) with authed RLS writes + payload-size assertions. Filed as a follow-up.

## 2026-06-08 — Issue 277-D — extended desktop smoke found 4 more (post-preload) bugs; all C2

After the preload fix, real desktop smoke surfaced a chain the injected-shim e2e never could:
- **workspace_id RLS** (403): renderer writes (announcements/songs/templates/settings/project/presence) omitted the session workspace_id required by every table's WITH CHECK. Fixed by surfacing workspace_id from /api/me + a central _sessionContext() stamp.
- **27MB poll**: sdGetProjects pulled full state JSONB (base64 images) on the 30s poll. Fixed: metadata-only list, state on demand.
- **null id**: inserts sent id:null instead of omitting → NOT NULL violation. Fixed: omit id, let gen_random_uuid default fire.
- **state-shape mismatch (DATA-INTEGRITY)**: DB stores projects.state as a wrapper {id,name,state:<content>,...} (migrated shape, what server.py _pg_row_to_project expects). sdGetProject returned the raw wrapper (editor read wrong level → empty) and sdSaveProject flattened it (would break server-mode reads + risked autosave overwriting a good project with an empty editor). Fixed: unwrap on read, store wrapper on write. Verified 36/39 projects intact (no data loss).
- **meta line**: file list showed "updated —"/no owner (raw snake_case cols, no profiles join). Fixed: camelCase updatedAt + owner labels from members list.
- **Common root**: the electron e2e injects window.electronAuth in a browser vs server-mode webserver and only asserts read-URLs — it cannot catch preload-load, RLS-writes, payload-size, null-id-default, state-shape, or meta-mapping. Follow-up #296 (real _electron launch + authed writes).

## 2026-06-08 — Issue 277-F / #294 — electron login deadlock (supabase-js auth lock); smoke FAIL→PASS

- **Result**: manual smoke FAIL (CI/e2e claimed PASS) → PASS after fix.
- **Category**: C2 — Wrong contract (injected-shim e2e simulated the auth seam; the real supabase-js init path was never exercised).
- **Symptom**: Electron app showed no login prompt, no profile, no working tabs. Live CDP: config + preload + bundle all present, a VALID stored session in localStorage, /api/me 200, yet getCurrentUser()=null and getSession() never resolved.
- **Root cause**: the onAuthStateChange callback was `async` and awaited a Supabase call (initAuth → _applySession → _fetchIdentityWithSession → client.from('workspace_members')). supabase-js dispatches auth events while holding GoTrue's internal auth lock; awaiting a Supabase query inside the callback reentrantly waits on that same lock → deadlocks _initialize() → getSession() hangs forever → startApp() blocks. Diagnostic tell: navigator.locks.query() shows nothing held (the lock is GoTrue-internal, not navigator), and a fresh client with identical options but no event-driven from() call resolves getSession instantly.
- **Suggested fix**: keep onAuthStateChange synchronous; defer Supabase work with setTimeout(0). (Also added an Electron pass-through `lock` to disable navigator.locks for the single-window renderer.) Fixed in commit ac1acd5; 3 regression tests in tests/auth-ui.spec.js. The same injected-shim e2e gap (#296) that masked the 277-D bugs masked this one too — it cannot reach the real getSession/onAuthStateChange path.

## 2026-06-08 — Issue 277-F / electron PDF export — blank pages from printToPDF; smoke FAIL→PASS

- **Result**: manual smoke FAIL (red banner "PDF generation in Electron mode is handled by the main process via IPC") → then blank PDF → PASS after fixes.
- **Category**: C1 — Missing contract (no test exercised the Electron PDF path end-to-end; the renderer never routed to IPC and printToPDF page sizing was never verified).
- **Two bugs**:
  1. Renderer called `fetch('/api/pdf')` directly; in electron the sidecar returns 501 ("use window.electronAPI.generatePdf"). Fixed: mode-aware delivery in projects.js (`_deliverPdfDownload` → Save dialog via IPC in electron / blob `<a download>` in browser; `_pdfBlobForUpload` → base64 bytes for Drive). main.js `pdf:generate` gained `save` flag (dialog+write vs return base64).
  2. printToPDF produced BLANK pages — but the bytes were there. Diagnosed via decompressing the PDF content stream (text present) + `/MediaBox [0 0 10058400 15544799]` vs Chrome's `[0 0 396 612]`. Electron 28's printToPDF `pageSize` Size is treated as INCHES (MediaBox = value×72); passing microns made the page 25400× too large so content sat in a microscopic corner. Fix: pass inches `{width: pageW, height: pageH}` + zero margins.
- **Diagnostic technique**: when a PDF looks blank but has bytes, decompress its `stream...endstream` (zlib) and read the content operators + `/MediaBox` — distinguishes "no content drawn" from "content drawn off-page / wrong page box". Compare against `chrome --headless --print-to-pdf` on the identical HTML to isolate engine vs HTML.
- **Suggested fix**: #296 (real `_electron` launch smoke) should assert a generated PDF's MediaBox == expected page size AND that page 1 contains non-whitespace rendered content — not just that a PDF was produced.
