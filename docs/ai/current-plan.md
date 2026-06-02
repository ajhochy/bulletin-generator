# Current Plan

_Last updated: 2026-06-02_

> **Active effort:** Migrate Bulletin Generator to a Supabase-backed, multi-tenant,
> Electron-wrapped desktop app. Long-lived integration branch:
> `feat/supabase-multitenant-electron`. This supersedes the Volunteer-Roles plan
> (that work is complete/in-PR; see `project-state.md`).

---

## User request

Re-platform the app so that:

1. **Supabase Postgres** replaces the self-hosted Docker/Synology database.
2. **Supabase Auth** (Google OAuth + email magic link) with **Row-Level Security** is the identity + access-control layer.
3. **Multi-tenant "Workspaces"** isolate each church's data (so a second church can test). Architect for many; seed workspaces manually for v1.
4. The **existing vanilla-JS frontend is wrapped in Electron** (no React rewrite) to ship a desktop client.
5. All of the above is built on a **fork/integration branch and tested before replacing the production app**.

## Goal (one sentence)

Ship a desktop (Electron) client whose existing UI is unchanged, backed by Supabase Postgres + Auth + RLS, with each church isolated in its own Workspace — reusing the already-built `collab-v1` Postgres/storage/collaboration work and replacing only its auth and single-tenant assumptions.

## In scope

- Reuse of `collab-v1` (branch `claude/amazing-archimedes-122d78`): `storage.py` boundary, `db.py`, `migrations/`, Postgres schema skeleton, `project_revisions` history + conflict UX, route-through-storage refactor.
- New `workspaces` + `workspace_members` tables; `workspace_id` on every data table; RLS policies on every table.
- Replacing `auth.py` (Google-only, single hard-coded domain, custom session cookies) with Supabase Auth + server-side JWT verification.
- Per-request JWT-claims plumbing so RLS is enforced *for real* through the trusted `server.py` data path.
- Moving cover/logo images and font binaries out of base64-in-JSONB into **Supabase Storage** (the one piece of "Migration A" `collab-v1` did not do).
- Electron shell: spawn local `server.py` (PyInstaller sidecar), `printToPDF`, OAuth/magic-link redirect handling, auto-update.
- Manual workspace seeding/data-migration tooling (service_role).

## Non-goals (explicit)

- **No React rewrite.** The existing `src/js/*` runs unchanged in the Electron renderer. (Deferred to a possible future effort.)
- **No self-serve onboarding** (signup→workspace, invite UI, billing, roles admin). Workspaces are seeded manually for v1.
- **No offline mode** in v1. Electron + Supabase is online-required (see Known Ambiguities — flagged for confirmation).
- Not retiring the current Synology/Docker production deployment until cutover QA passes. Parallel-run first.
- Not changing PCO / Google Calendar / Drive *integration* OAuth (that is separate from app-login identity; `collab-v1` already split the two).

## Hard constraints

- **Data-safety (`AGENTS.md`):** never delete/commit/overwrite user data files; atomic writes only; migrations idempotent + additive. The Supabase migration must be **non-destructive** — export + dry-run + backup before any cutover.
- **RLS must be the real boundary**, not just Python-side checks — that was the explicit reason for choosing Supabase Auth + RLS.
- **service_role key must never ship to clients** and must never be the normal query path (it bypasses RLS). It is for seeding/migration/admin scripts only.
- Reuse existing toolchain: Python stdlib `http.server` (no Flask), psycopg3, pytest + vitest + vite (the repo now has real automated tests despite the stale note in `testing-guide.md`).
- Conventional Commits; feature-branch only; draft PRs; manual merge.

## Design tensions

- **Minimal frontend change** (wrap existing UI) **vs. RLS-as-primary-boundary.** Resolved by keeping `server.py` as the trusted data API but having it execute queries under the user's JWT claims so RLS still applies — instead of moving all CRUD to `supabase-js` in the browser.
- **Connection pooling for many desktop clients** **vs. per-request `SET LOCAL` session state.** Supabase's transaction-mode pooler (6543) can break session state / prepared statements; this directly affects how per-request JWT claims are set. See Decision D2.
- **Reuse `collab-v1` as-is** **vs. its single-tenant assumptions.** `collab-v1` is hard-wired single-org; multi-tenancy threads `workspace_id` through its schema and replaces its auth. Reuse the seams, not the tenancy model.

## Cheapest version that proves the idea (spike first)

Before any multi-tenancy or Electron work: **rebase `collab-v1`, point `DATABASE_URL` at a Supabase project, and run the app in server mode against Supabase with `collab-v1`'s existing auth.** If projects/settings/songs round-trip to Supabase Postgres unchanged, the core thesis ("Supabase is a `DATABASE_URL` swap for the data layer") is proven. Everything else (RLS, Supabase Auth, Storage, Electron) layers on top. This is Milestone 0 (issues 1–3).

## Prior Art

> **Method note:** the planning prior-art swarm could not run — Haiku research subagents overflowed their context on tool results, and episodic-memory had a Node module-version mismatch. The patterns below are well-established; items marked **(verify)** should be confirmed against current Supabase docs during the relevant issue.

- **Multi-tenant RLS (standard pattern):** a `workspaces` table + a `workspace_members(user_id, workspace_id, role)` join table; every data table carries `workspace_id`; RLS policies allow a row only if the requesting user is a member of that row's workspace. Use **both** `USING` (read/update visibility) **and** `WITH CHECK` (insert/update integrity) — omitting `WITH CHECK` is a classic cross-tenant write leak. **(verify)**
- **RLS performance:** wrap `auth.uid()` as `(select auth.uid())` so Postgres evaluates it once per query, and index `workspace_id` on every table. Membership checks should hit an indexed join, not a per-row function call. **(verify)**
- **Enforcing RLS from a trusted backend (the crux):** connect as the `authenticated` role and, per transaction, `SET LOCAL request.jwt.claims = '<json>'` (and `SET LOCAL role authenticated`) so `auth.uid()`/`auth.jwt()` resolve inside policies — RLS then applies even though `server.py` is the connector. The `service_role` key bypasses RLS entirely and is reserved for seeding/migration. **(verify exact claim plumbing for psycopg3)**
- **Supabase pooler caveat:** the transaction-mode pooler (port 6543) does not preserve session state and conflicts with psycopg3's automatic prepared statements; either use a **session-mode/direct connection (5432)** or disable prepared statements (`prepare_threshold=None`) and keep all claim-setting inside a single transaction with `SET LOCAL`. Decision D2. **(verify)**
- **Electron + local server:** Electron main spawns the backend child process, polls a readiness endpoint (here `GET /api/bootstrap`), then `loadURL('http://localhost:<port>')`. Python backends are commonly shipped as a PyInstaller "sidecar" binary inside the Electron resources. **(verify packaging details)**
- **Supabase Auth in Electron:** desktop OAuth/magic-link typically uses a **custom-protocol deep link** (`bulletingen://auth-callback`) or a loopback `http://localhost` redirect; use the PKCE flow and persist the session via `@supabase/supabase-js`. Magic links open in the system browser and must hand the session back to the app via the registered deep link. **(verify)**
- **`printToPDF`:** Electron's `webContents.printToPDF()` renders the existing print HTML at native Chromium fidelity, removing the external headless-Chrome dependency (`_find_chrome` currently blocks server startup without a Chrome binary).
- **Repo memory (already known):** GHCR package must stay public for Watchtower; Synology bind-mount keeps data across pulls; revision-based 409 conflict model exists. The Supabase cutover supersedes Watchtower/GHCR auto-update for the desktop distribution (replaced by `electron-updater`).

## Target architecture

```
┌──────────────── Electron app (one per user, per workspace) ───────────────┐
│ Renderer (existing vanilla-JS UI, unchanged)     Main process (Node)       │
│   • login screen via @supabase/supabase-js  IPC  • spawn server.py sidecar │
│   • apiFetch attaches Supabase JWT  ───────────► • printToPDF              │
│   • loadURL(http://localhost:PORT)               • OAuth/magic-link deep-  │
│                                                    link redirect handling  │
└───────────────┬───────────────────────────────────────────────────────-──┘
                │  HTTP (localhost) + Bearer JWT
                ▼
        server.py (trusted local API — reused from collab-v1)
                │  verifies JWT, resolves workspace membership
                │  psycopg3: SET LOCAL role authenticated + request.jwt.claims
                ▼
┌──────────────────────────── Supabase ─────────────────────────────────────┐
│ Postgres: workspaces, workspace_members, projects, project_revisions,      │
│   workspace_settings, user_settings, announcements, songs, templates,      │
│   fonts, data_migrations  — ALL with workspace_id + RLS policies           │
│ Auth: Google OAuth + email magic link (PKCE)                               │
│ Storage: cover/logo images, font files                                     │
└────────────────────────────────────────────────────────────────────────-──┘
   (replaces self-hosted Docker Postgres + Synology + Watchtower)
```

## Architecture decisions (also appended to `decisions.md`)

- **D1 — Managed Supabase over self-hosted Postgres.** `collab-v1` introduced self-hosted Postgres in Docker; we point its `DATABASE_URL` at Supabase instead and delete the postgres compose service on this branch.
- **D2 — RLS enforced via backend-set JWT claims; pooling mode chosen accordingly.** `server.py` connects as `authenticated` and sets `request.jwt.claims` per transaction; `service_role` only for admin/seed. Default to session-mode/direct connection (5432) for correctness; if connection limits force the transaction pooler (6543), disable psycopg3 prepared statements and keep claim-setting transaction-local. (Validated in Milestone 1.)
- **D3 — Supabase Auth replaces `auth.py`.** Custom Google-only single-domain sessions are removed; `server.py` verifies Supabase JWTs and maps `sub` → user → workspace membership. Per-workspace domain allow-list / invite replaces the hard-coded `visaliacrc.com`.
- **D4 — Electron wraps the existing frontend.** No React rewrite. `printToPDF` replaces headless Chrome; `electron-updater` replaces Watchtower/zip for the desktop distribution.
- **D5 — Binaries move to Supabase Storage.** Cover/logo images and font files leave base64-in-JSONB (fixes the ~8.6 MB project bloat and makes assets shareable across clients).

## collab-v1 reuse map

| Keep (reuse) | Change | Add |
|---|---|---|
| `storage.py` `StorageBackend` ABC + `PostgresStorageBackend` | `db.py` (Supabase URL/SSL/pooler/claims/prepared-stmt) | `workspaces`, `workspace_members` tables |
| `migrations/` runner + importers | schema: `org_settings` → `workspace_settings` | `workspace_id` FK on all data tables |
| `project_revisions` history + restore + summaries | route guards → JWT/membership-based | RLS policies on every table |
| transactional optimistic-revision saves + conflict UX | `auth.py` → Supabase Auth + JWT verify | per-request claims plumbing |
| route-through-storage refactor | hard-coded domain → per-workspace allow-list | Supabase Storage for images + fonts |
| pytest test scaffolding | | Electron shell + packaging + auto-update |

## Milestone / issue table

| Order | Title | Goal | Likely files | Tests / evaluation | Dependencies |
|---|---|---|---|---|---|
| **M0 — Foundation & spike** ||||||
| 1 | Rebase collab-v1 onto integration branch | Bring 37 collab-v1 commits onto `feat/supabase-multitenant-electron`, resolving conflicts with volunteer-roles + lightweight-poll work that landed on main since 2026-04-27 | `server.py`, `src/js/projects.js`, `src/js/volunteer-roles.js`, `storage.py`, `db.py`, `migrations/`, `docs/ai/*` | Full pytest + vitest + `vite build` green; `python3 -c "import server"`; app boots in desktop mode (JSON) unchanged | — |
| 2 | Provision Supabase project + env wiring | Create staging Supabase project; set `DATABASE_URL` + keys; remove postgres service from `docker-compose.yml` on this branch; document env | `.env.example`, `docker-compose.yml`, `README.md`, `MANUAL-STEPS.md` | `db.health_check()` connects to Supabase; document-only otherwise | 1 |
| 3 | Adapt `db.py` for Supabase + prove round-trip | SSL, pooler vs session decision (D2), psycopg3 prepared-stmt handling; run app in server mode against Supabase with collab-v1 auth; CRUD round-trips | `db.py` | New `tests/test_db.py` cases hit Supabase test DB; manual: create/edit/load a project persists in Supabase | 2 |
| **M1 — Multi-tenant schema + RLS** ||||||
| 4 | Add workspaces + memberships schema | `workspaces`, `workspace_members(user_id, workspace_id, role)` + migration | `migrations/v00X_workspaces.py`, `migrations/runner.py` | `tests/test_migrations.py` applies idempotently; rollback/backup dry-run | 3 |
| 5 | Thread `workspace_id` through all tables | Add `workspace_id` FK + index to projects, project_revisions, settings→workspace_settings, announcements, songs, templates, fonts; backfill a default workspace | `migrations/*`, `storage.py` | Migration tests on legacy fixtures; backfill assigns all existing rows to the seed workspace | 4 |
| 6 | Enable RLS + policies on every table | `USING` + `WITH CHECK` policies keyed on membership; service_role seed path | `migrations/v00X_rls.py` | RLS unit tests: member reads/writes allowed | 5 |
| 7 | Per-request JWT-claims plumbing | `db.py`/`storage.py` set `role authenticated` + `SET LOCAL request.jwt.claims` per transaction; thread auth context from routes | `db.py`, `storage.py`, `server.py` | Tests prove queries run under claims; service_role still seeds | 6 |
| 8 | Cross-tenant isolation test suite | Prove workspace A cannot read/write workspace B; same-workspace sharing works | `tests/test_workspace_isolation.py` | pytest: cross-tenant denied (RLS), same-tenant allowed; **security-critical** | 7 |
| **M2 — Supabase Auth (replace auth.py)** ||||||
| 9 | Configure Supabase Auth providers | Google OAuth + email magic link; custom SMTP for magic-link deliverability; per-workspace domain allow-list strategy | `MANUAL-STEPS.md`, Supabase dashboard | Manual: both providers issue a session in staging | 3 |
| 10 | Server-side JWT verification middleware | Verify Supabase JWT (JWKS/secret), map `sub`→user, resolve membership; replace `auth.py` sessions; keep `/api/me` | `server.py`, `auth.py` (replace), `tests/test_auth*.py` | pytest: valid token → identity+claims; invalid/expired rejected; non-member 403 | 7, 9 |
| 11 | Frontend login + token attach | Login/logout via `@supabase/supabase-js`; `apiFetch` attaches Bearer token; gate app behind auth | `src/js/api.js`, `src/js/app.js`, new `src/js/auth-ui.js`, `index.html` | Manual smoke: login → app loads; logout → gated; console clean | 10 |
| 12 | Membership provisioning on first login | Map authenticated user → `workspace_members` via allow-list/invite; remove hard-coded `visaliacrc.com` | `auth.py`/`server.py`, `migrations/*` | pytest: allow-listed domain joins workspace; others rejected | 11 |
| **M3 — Binaries to Storage** ||||||
| 13 | Move cover/logo images to Supabase Storage | Extract base64 from project state → Storage; store URLs; migration for existing images | `storage.py`, `src/js/editor.js`, `src/js/projects.js`, `migrations/*` | Migration test extracts base64 fixtures; manual: image renders + PDF correct | 7 |
| 14 | Move font files to Supabase Storage | User fonts + cache → Storage; `fonts` table → Storage URLs | `server.py` (fonts routes), `storage.py`, `migrations/*` | Tests for font inventory→Storage; manual: custom font renders | 7 |
| **M4 — Electron desktop shell** ||||||
| 15 | Electron scaffold + spawn server sidecar | Main spawns `server.py` (PyInstaller sidecar), polls `/api/bootstrap`, `loadURL` localhost | new `electron/` (main.js, preload.js), `package.json`, `bulletin-generator.spec` | `npm run build` / electron launches; app loads existing UI | 1 |
| 16 | PDF via `printToPDF` | Replace `/api/pdf` headless-Chrome dependency with Electron `webContents.printToPDF`; keep print-HTML pipeline | `electron/main.js`, `src/js/preview.js`, `server.py` (`/api/pdf` fallback) | Manual: PDF round-trip matches current pagination/footers/QR | 15 |
| 17 | Supabase auth in Electron | Deep-link/custom-protocol (or loopback) redirect for Google + magic link; PKCE; session persistence | `electron/main.js`, `electron/preload.js`, `src/js/auth-ui.js` | Manual: Google + magic-link login complete inside the desktop app | 11, 15 |
| 18 | Packaging + auto-update | `electron-updater`; macOS sign/notarize + Windows build; retire `launcher.py` for this distribution | `package.json`, CI workflow, `bulletin-generator.spec` | CI builds signed artifacts; manual update round-trip | 15, 16, 17 |
| **M5 — Hardening, migration, cutover** ||||||
| 19 | Workspace seeding + data migration tool | service_role script: create a church workspace + migrate its existing JSON data; idempotent + dry-run + backup | `migrations/seed_workspace.py`, `MANUAL-STEPS.md` | Dry-run on real export; verify counts; backup written first | 8, 12, 13, 14 |
| 20 | End-to-end multi-tenant QA | Two workspaces × two users: isolation, in-workspace sharing, conflict UX, revision history, PDF, PCO/calendar | — (manual smoke matrix) | Documented smoke matrix all-pass; cross-tenant leak = blocker | 18, 19 |
| 21 | Docs + operator runbook | Update `architecture.md`, `decisions.md`, `testing-guide.md`, `CLAUDE.md`; Supabase setup + seeding runbook; Synology/Watchtower deprecation | `docs/ai/*`, `CLAUDE.md`, `README.md`, `MANUAL-STEPS.md` | Docs review | 20 |
| 22 | Cutover + rollback plan | Parallel-run staging; export from Synology → import to Supabase; switch; documented rollback | `MANUAL-STEPS.md` | Rehearsed on staging; rollback verified | 20, 21 |

## Validation strategy

- **Per issue:** `python3 -c "import server"`; `node --check` on changed JS; `pytest` (relevant module + full before PR); `vitest`; `vite build`.
- **DB/RLS:** integration tests against a Supabase **test** schema/project; **issue 8 is security-critical** — cross-tenant isolation must be proven, not assumed.
- **Manual-only (per `testing-guide.md`):** Template Designer click-through, PDF export round-trip, project save/load + 409 conflict, PCO import + calendar fetch, clean DevTools console — re-run for any issue touching those surfaces.
- **Electron:** build + launch verification is part of `verification-gate`, not manual smoke; manual smoke covers behavior (login, PDF, sync).

## Data-safety notes

- The Supabase migration is **additive + reversible**: export current Synology data, dry-run import, write a backup, verify row counts before any cutover. Never delete the JSON/Synology data until cutover QA (issue 20) passes.
- `service_role` key: server-side seed/migration scripts only — never in the Electron bundle, never the normal query path.
- Desktop-bundle secrets: prefer NOT shipping OAuth client secrets in the Electron binary (Supabase Auth keeps them server-side); the anon key + RLS is the only client-shippable credential.
- Magic-link mailer: Supabase's built-in mailer is rate-limited; configure custom SMTP before real multi-church testing.

## Clarification interview

Completed via the upfront-alignment round earlier this session (4 questions: scope, tenancy depth, fork mechanics, auth providers — all answered). Residual decisions that did not block planning are surfaced below rather than forcing another round (per the two-round cap), since the user asked to resume.

## Known ambiguities / open questions (confirm before the relevant milestone)

1. **Offline (M4):** plan assumes **online-required** v1 (Electron + Supabase). A church with flaky Sunday wifi would be blocked. Confirm acceptable, or add a local cache/sync layer as a later effort.
2. **Seed data (M5):** assumed the first workspace = the existing Visalia CRC data migrated in. Confirm.
3. **Membership model (M2):** per-workspace **domain allow-list** vs **explicit email invite**. Plan supports allow-list first; invites are the self-serve path (out of scope for v1).
4. **Pooling mode (D2/M1):** session-mode (5432) vs transaction pooler (6543) depends on expected concurrent client count — decide during issue 3/7 with real numbers.
5. **PCO/Google integration tokens (M2):** keep as a shared per-workspace connection (matches today) vs per-user. Plan assumes per-workspace shared; confirm.

## Next in chain

Hand off to **`issue-writer`** to convert this table into GitHub-ready issues (with per-issue acceptance criteria + likely files + tests) under `docs/ai/generated-issues/`, in dependency order, starting with issue 1 (rebase). Do **not** create remote GitHub issues until the user asks. Issue 1 (rebase) and issues touching RLS (6–8) and auth (10) warrant `acceptance-contract` before `coding-agent`.
