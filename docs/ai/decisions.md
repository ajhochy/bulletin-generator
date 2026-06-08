# Decisions

Append-only log of architecture / workflow decisions worth preserving across sessions. Most-recent first.

---

## 2026-06-08 — next-week-offering: per-project opt-* gate, first-line cause rule, offering decoupled from volunteer checkbox

**Context.** Visalia CRC's bulletin OFFERING text comes from the selected week's PCO note; the "next week's offering is for X" line was typed by hand. Automate it: on import + re-sync, pull the next plan's OFFERING note and append the line to this week's OFFERING item.

**Decision — gate is a per-project `opt-next-week-offering` checkbox, not a global `settings.autoNextWeekOffering`.** The task floated a global setting, but there is no exported frontend settings getter (`_serverSettings` is module-private in `api.js`), and the user asked for the toggle to live in the Document Options dropdown alongside the existing `opt-*` page-inclusion checkboxes. Implemented exactly like the siblings: `state.js` DOM ref, `projects.js` collect (`!!checked`) + restore in both `applyProjectState` blocks (`!== false`, default ON) + reset-to-true in `clearEditorForNewProject`, `formatting.js` change listener (renderPreview + persist). Read at import time via the DOM ref. **Consequence:** the toggle is per-project (saved in project state), not a workspace/global default — matches the other Document Options toggles. Server mode unchanged.

**Decision — cause = first non-empty line of the next OFFERING note** (strip surrounding `*`/`**`/`***`), per the user. Not "first bolded token." `deriveNextWeekOfferingCause` returns '' for blank/non-string so callers skip cleanly.

**Decision — pure logic in `pco-core.js`, exposed via the `main.js` globalThis bridge.** `deriveNextWeekOfferingCause` + `applyNextWeekOfferingLine` are pure and vitest-tested (7 contract tests c1–c7). `applyNextWeekOfferingLine` always strips any existing managed line (matched by the `NEXT_WEEK_OFFERING_PREFIX` constant) before appending, so re-running is idempotent and a new cause replaces the old in place; an empty cause removes-only. This is what makes re-sync non-duplicating even though the re-sync merge restores the user's prior detail (which already contains the previous line).

**Decision — offering refresh is decoupled from the volunteer checkbox.** `pcoFetchAndApplyServing` is invoked from the resync diff dialog's Apply handler **only when the volunteer checkbox is checked** (`serveCallback`). The offering line must refresh on every applied re-sync regardless, so a separate `offeringCallback` param was added to `showResyncDiffDialog` and is invoked unconditionally (after conflict resolution, so it sees the OFFERING item's final detail). On the import path and the no-changes resync path it is called directly next to `pcoFetchAndApplyServing`.

**Decision — underivable/missing cases silently skip** (no next plan, no next OFFERING note, no OFFERING item, empty cause, feature toggled off): the wiring early-returns and leaves detail untouched, per the "silently skip" requirement, rather than stripping a stale line. The whole next-plan fetch is wrapped in try/catch (best-effort) mirroring `pcoFetchAndApplyServing`, so a failure never breaks the import.

**Consequences.** New `pcoFetchAndApplyNextWeekOffering` in `pco.js`; one extra param on `showResyncDiffDialog`; additive `opt-*` checkbox. c8–c11 (live import/re-sync behavior, gate suppression, best-effort failure) are manual-smoke only — no module seam around `pcoGet`/DOM.

---

## 2026-06-06 — Issues #279 + #280: PID lock file for stale-sidecar detection; onedir for cold-start

**Context.** Issue #279: if the Electron app crashes (bypassing `before-quit`), the Python sidecar stays alive holding port 8765. On next launch, the new sidecar bind fails with a raw OSError traceback → Electron shows "Exit code 1". Issue #280: PyInstaller `--onefile` unpacks the whole runtime to a temp dir on every launch; `--onedir` copies once and stays.

**Decision — #279 server.py:** Catch `OSError` at the `ThreadingHTTPServer(...)` constructor, check `errno.EADDRINUSE` (98 on POSIX) or `WSAEADDRINUSE` (10048 on Windows, obtained via `getattr` so it's safe on non-Windows), print a distinct `[server] FATAL: port <PORT> already in use — another instance or a stale sidecar is running.` to stderr, and exit with code 3. Exit code 3 was chosen as a recognizable sentinel distinct from Python's standard 1 (unhandled exception) and 2 (CLI misuse). All other `OSError` variants re-raise unchanged.

**Decision — #279 electron/main.js:** PID lock file at `os.tmpdir()/bulletin-generator-sidecar.pid`. Written immediately after `spawn()` returns the child PID; removed on `killSidecar()` (clean quit) and on the sidecar's `exit` event. At `app.whenReady`, `reapStaleSidecar()` reads the file, calls `process.kill(pid, 0)` to confirm the process is still alive, sends `SIGTERM` if so, and waits 1500ms for the OS to release the port. **Why PID lock over HTTP probe:** an HTTP probe to 127.0.0.1:8765 cannot distinguish our orphaned sidecar from any other service the user is running on that port (e.g. another app or a previous dev server). The PID lock positively identifies the process we spawned. **Why `os.tmpdir()`:** survives app crashes (not cleaned on crash), writable on both macOS and Windows without special permissions, and distinct from the app bundle location which varies between dev and packaged modes. **PID-reuse risk noted but accepted:** the OS recycles PIDs slowly; a collision between a killed-sidecar PID and an unrelated new process only occurs during crash recovery, not normal launch.

**Decision — #280 PyInstaller onedir:** `--onedir` places all shared libraries alongside the executable in `dist/server/` instead of packing them into a single fat binary that must be re-extracted to a tmp dir on every launch. The `resolveSidecar()` packaged path changes from `<resourcesPath>/server` to `<resourcesPath>/server/server`. The `extraResources` config in `package.json` changes from a single-file filter to copying the entire `dist/server/` directory tree into `<app>/Contents/Resources/server/`. Cold-start speedup (no per-launch unpack) and the executable path change are only verifiable in a packaged build.

**Consequences.**
- `server.py`: cleaner error for the most common desktop crash-recovery scenario.
- `electron/main.js`: ~80 lines of new helpers; app startup adds `reapStaleSidecar()` (≈0ms normally, 1.5s only on crash recovery).
- `release-electron.yml`: both macOS and Windows build steps are `--onedir` now; `ls dist/server/` replaces `ls -lh dist/server` as the post-build check.
- `package.json` extraResources: the glob change means no single-file `server`/`server.exe` at the resource root any more — only the `server/` subdirectory. Old packaged builds will not find `<resourcesPath>/server` (file) but `resolveSidecar()` correctly falls back to dev-mode for that case.

---

## 2026-06-06 — Issue #277: S2 hybrid for anon-key desktop path; sidecar keeps OAuth callbacks + PCO/Cal/PDF

**Context.** Issue #277 requires removing DATABASE_URL from the Electron desktop build. Two candidate shapes: S1 (sidecar calls PostgREST via anon key) and S2 (renderer does CRUD directly via supabase-js). Planning investigation confirmed all data tables have correct RLS policies for the `authenticated` role. Security advisor shows no RLS gaps. The only structural blocker is `transfer_project_owner`, which uses `admin_transaction()` because the `projects_update` WITH CHECK requires `owner_user_id = auth.uid()` on the NEW row — impossible when the caller transfers ownership to a different user.

**Decision.** Use **S2 hybrid**:
- Renderer (`supabase-data.js`) handles all routine CRUD: projects, announcements, songs, workspace_settings, project_revisions, workspace_presences, templates, fonts metadata, workspace_members.
- The `transfer_project_owner` operation is implemented as a **SECURITY DEFINER RPC** in a new migration (`transfer_project_owner_rpc.sql`). The renderer calls `supabase.rpc('transfer_project_owner', {...})`. The function validates caller = current owner + target is workspace member, then UPDATEs. No DATABASE_URL needed.
- The sidecar keeps: static serving, PCO proxy, Google Calendar fetch, PDF generation, OAuth callbacks (PCO/Google — unauthenticated redirects that cannot use a user JWT at the callback moment; sidecar writes tokens via owner-role which is acceptable since that path runs only on the server anyway and is not bundled in the Electron binary).
- `APP_MODE=electron` is treated as desktop-equivalent in `_validate_server_config()` (no DATABASE_URL required at boot). Sidecar endpoints that touch psycopg return 501/no-op in electron mode.

**S1 rejected.** Rewriting psycopg queries to HTTP REST in Python gains nothing architecturally — the sidecar still needs DATABASE_URL and the renderer still can't bypass the sidecar.

**Consequences.**
- New file: `src/js/supabase-data.js`.
- New migration: `supabase/migrations/20260606000001_transfer_owner_rpc.sql`.
- `server.py` `_validate_server_config()`: add `IS_ELECTRON` bypass.
- `release-electron.yml`: remove `DATABASE_URL` from the `.env` step (after all sub-issues land).
- Server (Docker) mode is entirely unaffected — psycopg + DATABASE_URL kept.
- Old draft prereleases (v0.0.1/2/3) carry DATABASE_URL in bundled .env — delete them after the new build lands and DB password is rotated.

---

## 2026-06-06 — #216 revision snapshots: application-level, not a DB trigger

**Context.** #216 requires appending a `project_revisions` snapshot on every successful save (regression: only the `/restore` path snapshotted). The initial plan (and the 277-D deferral note) assumed a DB trigger so it would cover both the server (psycopg) and renderer (supabase-js) write paths uniformly.

**Decision.** Implement it **application-level** in `PostgresStorageBackend.save_project` (mirroring `save_project_transactional`), plus a unique index on `project_revisions (project_id, revision_number)`. A DB trigger was rejected for three reasons:
1. **Summary.** `project_revisions.summary` is a stored column produced by `revisions.generate_summary` (Python). A trigger can't run that, so a trigger-based snapshot would lose the #217 summaries (or require porting 176 lines of diff logic to plpgsql).
2. **Deploy gate.** The `supabase/migrations` track isn't applied by CI and the agent is (correctly) blocked from a direct live apply — so a trigger couldn't be verified live by the agent.
3. **Live-regression window.** Removing the existing app-level `/restore` snapshot in favor of an undeployed trigger would stop snapshots in production until the trigger is deployed.

**Consequences.**
- `save_project` now does a 4-statement sequence (SELECT prev state → upsert RETURNING → profiles enrich → INSERT project_revisions), matching the transactional path. Existing `save_project` mocks (`test_project_metadata`, `test_storage_assets`) were updated for the new sequence.
- A unique index migration (`20260606000002_project_revisions_unique_revision.sql`) hard-enforces "unique revision numbers per project" (verified: zero existing dupes). Needs a live `supabase db push` (human-authorized, like 277-B).
- **Renderer (electron) path still needs its own snapshot.** Electron saves go renderer→Supabase, bypassing `save_project`, so they won't snapshot until `supabase-data.js` `sdSaveProject` (277-C/D) inserts a `project_revisions` row. Tracked as a follow-up on the #277 stack.
- Also wired the previously-orphaned `tests/test_revision_snapshots.py` into the CI `python` job (it ran nowhere before).

---

## 2026-06-05 — Presence project_id is TEXT, not uuid (fix forward migration, not edit-in-place)

**Context.** `workspace_presences.project_id` was declared `uuid` in `20260603000003_workspace_presences.sql`, but project ids are application-generated TEXT (`proj_<timestamp>_<rand>`) and `public.projects.id` is `text`. Every presence read/heartbeat 500'd with `InvalidTextRepresentation`; the frontend's best-effort error swallowing hid it.

**Decision.** Fix via a **new additive migration** (`20260605000002_presence_project_id_text.sql`) that idempotently `ALTER COLUMN project_id TYPE text`, rather than editing the original applied migration. Consistent with AGENTS.md's "migrations are idempotent and additive" rule — never rewrite an applied migration. A fresh DB applies both in order (create uuid → alter to text); existing DBs convert losslessly.

**Consequences.**
- The fix lives only in `supabase/migrations/*` (the Supabase-platform migration track), not the Python `migrations/runner.py` track — the presence table belongs to the former.
- No `server.py` query change: the handlers bind `project_id` as a plain string param (no `::uuid` cast), so the column-type change is the whole fix. Corrected the handlers' `<uuid>` docstrings to `<project-id>` so the wrong assumption isn't reintroduced.
- **Rule for any future table keyed by a project id: use `text`, never `uuid`.** Project ids are not uuids.

## 2026-06-04 — Abandoned Share-to-Workspace; confirmed visibility model A (workspace-visible by default + hand-off)

**Context.** The "private-by-default + explicit share-to-workspace" model planned in issues 020/023 was only partly realized: `PostgresStorageBackend.save_project` hard-codes `visibility = 'workspace'` on INSERT (storage.py), so new projects were always workspace-visible despite the issue-020 migration setting the column *default* to `'private'`. No Share UI was ever built — the `POST /api/projects/{id}/share` endpoint had no frontend caller.

**Decision (model A).** Keep it that way. Projects are **workspace-visible by default** (every workspace member sees them read-only); only the owner can edit (owner-only-write RLS retained); **hand-off** (`POST /api/projects/{id}/transfer`, wired via the Hand-off button) reassigns the sole editor. There is no per-project private/share toggle. Share-to-Workspace is abandoned (GitHub #211 closed not-planned).

**Consequences.**
- Removed dead code: `_handle_share_project` (server.py) + its dispatch, `share_project_to_workspace` (abstract + Json + Postgres backends in storage.py), and `tests/test_share_project.py`.
- Issue 020's "private-by-default" is **obsolete**. The `'private'` column default (migration `20260603000002_private_default_rls.sql`) is harmless but **vestigial** — `save_project`'s explicit `'workspace'` overrides it. The owner-only-write RLS policy from that migration is **kept** (still correct for model A). Not reverting the migration: it would need a new idempotent migration for no functional gain.
- Duplicate creates a new **workspace-visible** project owned by the current user (not private), since `save_project` forces `'workspace'`.
- The read-only banner + presence badge still apply (non-owners viewing a workspace project).

## 2026-06-03 — Project ownership model: private-by-default, presence via DB heartbeat, conflict detection removed

> **SUPERSEDED 2026-06-04 (see entry above):** the "private-by-default" half was abandoned in favor of model A (workspace-visible by default + hand-off). The presence/heartbeat and conflict-detection-removal decisions below still stand.

**Context.** New planning effort (issues 020–024) introduces a formal ownership and sharing model to replace the concurrent-edit assumption that underpinned 409 conflict detection.

**D6 — Presence via `workspace_presences` table with 60s heartbeat / 90s TTL read filter.**
Supabase Realtime (WebSocket Broadcast/Presence channels) was explicitly excluded from scope ("no WebSockets"). A simple `workspace_presences` table with per-user upsert and a `last_seen > now() - 90s` read filter is the entire implementation. No background cleanup job required for v1 — rows expire from the query's perspective. The heartbeat interval matches the removed stale-check poll interval (30s) so the network budget is identical.

**D7 — Conflict detection removed; `save_project_transactional` / `ConflictError` left as dead code temporarily.**
With owner-only writes, two users can never both have write access to the same project simultaneously, so revision-mismatch conflicts cannot occur. The 409 path is removed from `_handle_post_projects` and `startStaleCheck`/conflict-banner/dialog are removed from `projects.js`. `ConflictError` and `save_project_transactional` in `storage.py` are kept (dead code) until after the cutover QA passes to avoid breaking existing tests; a follow-up cleanup issue can remove them. The `/api/projects/revisions` endpoint (added for the stale poll in the `2026-05-28` entry) is removed.

**D8 — Visibility default change is a DB migration + Python INSERT constant change.**
The `projects` table default changes from `'workspace'` to `'private'` via a new migration file (`supabase/migrations/20260604000001_private_default.sql`). The INSERT in `PostgresStorageBackend.save_project` (storage.py ~L643) hardcodes `'workspace'` — must change to `'private'`. Existing rows keep `'workspace'`; no backfill. The `projects_update` RLS policy is tightened to `owner_user_id = auth.uid()` only (dropping the `visibility = 'workspace' OR ...` alternative).

**D9 — Transfer ownership via guarded server endpoint, not direct RLS.**
`POST /api/projects/{id}/transfer` verifies at the Python layer that (a) the caller is the current owner and (b) the new owner is a workspace member. The single `UPDATE ... WHERE id=... AND owner_user_id=%(caller)s` is atomic and correctly handled by the existing `owner_user_id = auth.uid()` RLS update policy.

**Consequences.**
- Issues 020–024 encode these decisions.
- The QA matrix (`docs/ai/qa-matrix-m5.md`) items C1–C3 (conflict detection) become moot after issue 023 and are replaced with write-protection + presence checks in issue 024.
- `testing-guide.md` "409 conflict" manual smoke item must be removed after issue 023.

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

---

## 2026-06-05 — Carry workspace id through a signed OAuth `state` for the CONNECT path

**Context.** Commit 67bb9ca scoped the OAuth *read* path (proxy/refresh/config) to
the authenticated workspace, but the *connect* (write) path was still un-scoped:
`_handle_pco_oauth_callback` / `_handle_google_oauth_callback` are unauthenticated
browser redirects (no Bearer/session), so they wrote tokens via `_get_settings()`/
`_save_settings()` → `workspace_settings LIMIT 1`. With multiple workspaces, connecting
in workspace B could write tokens into workspace A's row.

**Decision.**
- The SPA passes its Supabase access token to `/oauth/{pco,google}/start` as a `?token=`
  query param (the start endpoint is a top-level navigation with no Authorization header).
  The start handler verifies it via `auth.authenticate_authorization_header`, resolves
  workspace membership, and signs the workspace id into the OAuth `state` with
  HMAC-SHA256 (`_sign_oauth_state`). The provider echoes `state` back to the callback,
  which verifies it (`_verify_oauth_state`, constant-time) and builds workspace-scoped
  storage `get_storage(workspace_id=…, user_claims=None)` for the token write.
- HMAC key precedence: `OAUTH_STATE_SECRET` → `SUPABASE_JWT_SECRET` → concatenated
  OAuth client secrets. This is never empty in a correctly-configured server deployment
  and requires zero new config for existing deployments.
- Missing/invalid/forged `state` in server mode is **refused** (error redirect, no write)
  rather than falling back to an arbitrary workspace.
- Desktop mode is single-workspace: `getSession()` is null → no `?token=` → start emits
  no `state` → callback uses default desktop storage (unchanged behavior).

**Alternatives considered.**
- *Server-minted single-use nonce* instead of the raw access token in the query string —
  avoids exposing the (short-lived) token in URL/history/logs, but adds a server-side
  nonce store and lifecycle. Deferred; the access token is short-lived and the endpoint
  302-redirects immediately. Start handlers must not log the query string.
- *Per-user token rows / proper RLS service path for `workspace_settings` writes* — the
  callback write uses `user_claims=None`, i.e. the owner-role DATABASE_URL connection that
  bypasses RLS for the upsert (the same path the prior un-scoped fallback used). A future
  hardening (issue #277 family) could move OAuth tokens off the owner connection.

**Consequences.**
- Token writes land in the connecting user's workspace; A/B isolation holds for connect.
- New optional env `OAUTH_STATE_SECRET` (documented precedence). No migration required.
- The earlier "members can't use PCO → blame workspace_settings RLS" diagnosis was wrong;
  the real cause was the un-scoped LIMIT 1 *read*, fixed in 67bb9ca. This change fixes the
  symmetric *write* gap.

---

## 2026-06-06 — New-member workspace resolution is read-after-write sensitive (presence e2e flake)

**Context.** The `e2e-core` presence test (`server-mode-behaviors.spec.ts`) flaked
intermittently: a second workspace member (B), added via `createWorkspaceMember`
immediately before signing in, sometimes received **403** on `GET/DELETE /api/presence`
(and an empty `/api/projects`) because `auth.resolve_workspace_membership(B)` found no
membership row yet. Cross-run contrast confirmed it intermittent (B saw the project on
one run, nothing on another). The membership write (Supabase PostgREST, service role) and
the read (`db.admin_transaction`, psycopg via the 6543 transaction pooler) are different
connection paths; B's first authenticated request can race ahead of the new row's
visibility, and the frontend does **not** auto-retry a 403 (the project list stays empty).

**Decision.** Treat this as a **test-setup race**, fixed in the test (PR #283): after B
signs in, reload B until A's project resolves into B's Files list before driving the UI.
In production a member is invited well before their first login, so the window is not
normally hit.

**Latent product consideration (not yet actioned).** A freshly-provisioned/invited member
whose *first* authenticated request lands before membership is visible will get a 403 and
an **empty workspace with no automatic recovery** until they manually reload. If real
invite-then-immediately-login flows are expected, consider: (a) a short server-side retry
in `resolve_workspace_membership` / `authenticate_authorization_header` before returning
403, or (b) a frontend re-fetch on an initial 403/empty-workspace. Worth verifying during
the #272 multi-tenant QA. No code change made now.

**Consequences.** Presence e2e is deterministic; the product behavior is documented for
follow-up rather than silently masked.
