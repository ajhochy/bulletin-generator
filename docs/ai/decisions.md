# Decisions

Append-only log of architecture / workflow decisions worth preserving across sessions. Most-recent first.

---

## 2026-06-03 — M4/M5 deferred items confirmed: custom SMTP, Windows signing, staging=production

**Context.** Issue 017 (operator runbook) required documenting the current deployment posture to avoid confusion between staging and production and to record items that are explicitly deferred rather than forgotten.

**Decisions recorded:**

- **Custom SMTP deferred.** Supabase's built-in mailer (rate-limited, project-team-only) is acceptable for the current single-church deployment. Custom SMTP (Resend / AWS SES / Postmark) must be configured before expanding to multi-church testing. This is a known operational gap, not a bug. See `docs/operator-runbook.md` section 1.3 for setup steps.

- **Windows code signing deferred.** Issue 014 (packaging + auto-update) will produce a signed macOS `.app` via `electron-builder`. Windows code signing (EV certificate, Microsoft Partner Center submission) is deferred until there is a Windows user base. Unsigned Windows builds will show a SmartScreen warning; this is acceptable for v1.

- **Staging = production confirmed.** The Supabase project `dgydekhfzrmeoscpgmvo` is the sole Supabase deployment for this app — it serves as both "staging" (for pre-release smoke testing on the branch) and "production" (for the Visalia CRC deployment). There is no separate production project. A new project would only be created if the user base grows beyond Supabase's free tier limits or if a second fully-isolated tenant environment is needed.

**Consequences.**
- `docs/operator-runbook.md` and `MANUAL-STEPS.md` both reference the staging/production project ID directly — this is intentional.
- Before multi-church testing, the SMTP gap must be resolved. The runbook includes the setup steps so any operator can complete it without code changes.
- Packaging issues (014) should note the Windows signing gap and include a placeholder in the CI workflow.

---

## 2026-06-03 — Issue 012: HTTP 501 + TODO instead of live Python↔Node IPC for `/api/pdf` in electron mode

**Context.** The issue spec offered two paths for PDF generation in Electron mode: (A) full IPC between the Python sidecar and the Electron main process (e.g. a local socket or temp-file polling), or (B) the "simpler alternative" — detect `APP_MODE=electron` in `server.py`, return HTTP 501 with a redirect message, and implement the IPC handler in `electron/main.js` so the renderer can call `window.electronAPI.generatePdf()` directly.

**Decision.** Chose option B. The renderer's existing PDF export flow (in `src/js/preview.js`) will be updated in issue 013 to call `window.electronAPI.generatePdf()` instead of `POST /api/pdf` when `window.electronAPI` is present. The Python sidecar therefore never needs to be the PDF intermediary; the renderer owns the PDF request entirely in electron mode.

**`IS_DESKTOP = True` for `APP_MODE=electron`.** Electron is a desktop variant — single-user, no collaboration features, no DATABASE_URL required. All `IS_DESKTOP` guards in `server.py` should apply identically.

**`CHROME_PATH` deferred.** `CHROME_PATH = _find_chrome()` is called at module load time and raises `RuntimeError` when Chrome isn't installed. In electron mode Chrome is never used. The fix: `None if APP_MODE == electron else _find_chrome()`. This is evaluated from `os.environ` directly (before the `IS_ELECTRON` alias is defined) to keep the deferred evaluation correct at import time.

**Page dimensions.** Electron's `printToPDF` `pageSize` field uses microns, not inches. Conversion: `Math.round(inches * 25400)`. Existing server.py defaults (5.5 × 8.5 in) are preserved as the fallback.

**Temp-dir cleanup.** `fs.mkdtempSync` in `pdf:generate` creates the output directory but does not clean it up — the caller (issue 013 JS wiring) must delete after the save-dialog resolves. Documented as a concern; not a blocker for this issue.

**Consequences.**
- Issue 013 (Supabase auth in Electron) must also wire the call-site: detect `window.electronAPI?.generatePdf`, call it, handle the returned path to trigger a save dialog. Until then the IPC handler is present but unreachable from the running UI.
- If a non-renderer process (e.g. a CLI migration script) ever needs PDF generation in electron mode, a local socket IPC path can be added to `_handle_pdf` per the TODO comment in `server.py`.

---

## 2026-06-03 — ESM syntax in `electron/main.js`; packaged-mode sidecar path scaffolded early

**Context.** Root `package.json` has `"type": "module"`, making Node treat all `.js` files in the tree as ESM. Electron 28+ supports ESM main entry points. The alternative — CJS `require()` in `main.js` — would require either a `.cjs` extension or a local `package.json` override in `electron/` (neither is wrong, but both add complexity).

**Decision.** Use ESM `import` syntax in `electron/main.js` and `electron/preload.js`. Requires the `fileURLToPath(import.meta.url)` pattern to derive `__dirname` in ESM context.

**Packaged-mode path.** `resolveSidecar()` in `main.js` probes `process.resourcesPath + '/server'` for the PyInstaller binary. The binary doesn't exist until issue 014 (packaging). Scaffolding the path now means issue 014 only needs to place the binary — no main-process changes required.

**Consequences.**
- Issue 014 (packaging) can focus on PyInstaller spec changes and `electron-builder` config; `main.js` path logic is already correct.
- If Electron's ESM support has edge-cases in the packaged `.asar` context, fall back to `electron/main.cjs` with `require()` + an `electron/` local `package.json` override.

---

## 2026-05-28 — Separate `/api/projects/revisions` endpoint for the stale-check poll

**Context.** The 30s stale-check poll (`startStaleCheck` in `src/js/projects.js`) called `GET /api/projects`, which returns the entire `projects.json` — ~8.6 MB because project `state` embeds base64 cover/logo images. With multiple browser tabs open this transferred ~279 GB over a few weeks and inflated server RSS (repeated multi-MB JSON parse/serialize). The poll only reads `revision`/`updatedAt`/`updatedBy`.

**Alternatives.**
- Add a `?fields=meta` query param to `/api/projects`. Rejected — the route is exact-match (`path == '/api/projects'`); supporting a variant would mean parsing query strings in the handler, and a distinct path is clearer and cache-friendlier.
- Strip `state` from the existing `/api/projects` response. Rejected — startup (`loadAllFromServer`) and the explicit "Reload latest" handlers genuinely need full `state`.
- Gzip the response. Rejected — reduces bytes but still re-parses/re-serializes 8.6 MB server-side every cycle; doesn't fix RSS.

**Decision.** Added `_project_revision_summary(projects)` (metadata-only: id/revision/updatedAt/updatedBy) and an exact-match `GET /api/projects/revisions` route → `_handle_get_project_revisions`. The poll now hits the new endpoint (~799 bytes vs 8.6 MB, ~10,800× smaller). The two explicit user-triggered "Reload latest" handlers and startup load still use full `/api/projects`.

**Consequences.**
- Stale-check bandwidth is now negligible; the Cloudflare-vs-Tailscale choice can be made on features/security rather than data volume.
- Any future field the poll needs must be added to `_project_revision_summary`, not assumed present.

---

## 2026-05-19 — Adopt the AI workflow `AGENTS.md` + `docs/ai/*` contract

**Context.** Agent runs were degrading because the orchestrator's "self-heal before doing anything else" step kept finding the seven required workflow files missing, and either skipped the check (bad) or bootstrapped placeholder content inline in unrelated PRs (also bad).

**Alternatives.**
- Keep everything in `CLAUDE.md`. Rejected — single file conflates architectural reference (durable) with planning state (volatile), and the orchestrator looks for `docs/ai/*` by name.
- Skip the contract and let each agent re-derive context. Rejected — wastes tokens and produces inconsistent assumptions across runs.

**Decision.** Adopt the standard layout:
- `AGENTS.md` — operating contract.
- `docs/ai/project-state.md` — current focus + recent work.
- `docs/ai/repo-map.md` — grep index.
- `docs/ai/architecture.md` — boundaries.
- `docs/ai/testing-guide.md` — validation commands + manual-only checks.
- `docs/ai/current-plan.md` — what's being worked on right now.
- `docs/ai/decisions.md` — this file.

`CLAUDE.md` stays as the canonical detailed architecture reference; the new files reference it instead of duplicating.

**Consequences.**
- Future agent sessions can skip the bootstrap step and dispatch specialists directly.
- `project-state.md` becomes the source of truth for "what's in flight" — must be updated by `project-state-updater` after every completed unit of work, not just at release time.
- Anyone editing `CLAUDE.md` should sanity-check that `architecture.md` / `repo-map.md` haven't drifted.
