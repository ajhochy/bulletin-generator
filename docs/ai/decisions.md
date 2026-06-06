# Decisions

Append-only log of architecture / workflow decisions worth preserving across sessions. Most-recent first.

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
