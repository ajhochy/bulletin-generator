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
