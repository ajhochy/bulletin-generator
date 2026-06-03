# Decisions

Append-only log of architecture / workflow decisions worth preserving across sessions. Most-recent first.

---

## 2026-06-03 — SUPABASE_SERVICE_ROLE_KEY (HTTP JWT) vs SUPABASE_SERVICE_ROLE_URL (Postgres) for Storage uploads

**Context.** Issue 009 calls for server-initiated uploads to Supabase Storage using "SUPABASE_SERVICE_ROLE_URL". That variable is already defined in `db.py` as a Postgres connection string (`postgresql://postgres.<ref>:<pw>@pooler.supabase.com:5432/...`). The Supabase Storage REST API requires an HTTP Bearer token (a JWT), not a Postgres connection string.

**Decision.** Introduce `SUPABASE_SERVICE_ROLE_KEY` as a separate env var for the HTTP service-role JWT. This is the "service_role" key shown in Supabase Dashboard → Settings → API → Project API keys. `SUPABASE_SERVICE_ROLE_URL` (Postgres) is unchanged and still used by `db.admin_transaction()`.

**Consequences.**
- Operators must set two service-role secrets: `SUPABASE_SERVICE_ROLE_URL` (Postgres admin) and `SUPABASE_SERVICE_ROLE_KEY` (Storage HTTP). Both are server-side-only; neither goes into the Electron bundle.
- If `SUPABASE_SERVICE_ROLE_KEY` is unset, `extract_and_upload_images()` is a no-op and images stay as base64 — safe fallback, no data loss.
- Documented in `.env.example` alongside existing secrets.

---

## 2026-06-02 — Schema source of truth = Supabase-managed migrations (refines D1)

**Context.** With the Supabase MCP installed and a staging project provisioned (`bulletin-generator`, ref `dgydekhfzrmeoscpgmvo`, org Visalia CRC, region us-west-1), we have direct DDL access. The earlier plan reuse-map said "keep collab-v1's Python migration runner + `data_migrations` table" for schema.

**Decision.** The Postgres **schema** (multi-tenant tables + RLS) is now owned by **Supabase-managed migrations**: iterate on the staging project via the MCP (`execute_sql`), verify cross-tenant isolation, then capture as versioned SQL under `supabase/migrations/`. collab-v1's Python schema-creation migration (`migrations/v001_initial_schema.py`) is retired for DDL. collab-v1's JSON→Postgres **data importers** are kept but become a one-time data-migration/seed step that inserts into the Supabase-created schema. `data_migrations` table is superseded by Supabase's `supabase_migrations.schema_migrations`.

**Consequences.**
- Supersedes the "reuse migrations/ runner for schema" part of the 2026-06-02 re-platform reuse map; the runner's importers survive, its DDL does not.
- Supabase Auth owns `auth.users` + sessions, so collab-v1's `users`/`sessions` tables are NOT recreated — a `public.profiles` mirror of `auth.users` is used for joins/RLS instead.
- RLS authoring/testing happens against staging directly; isolation must be proven (security-critical) before capture.

---

## 2026-06-02 — Re-platform to Supabase + multi-tenant Workspaces + Electron (build on collab-v1)

**Context.** Goal is to retire the self-hosted Synology/Docker deployment, gain real multi-user with per-church isolation, and ship a desktop client — without a frontend rewrite. The `collab-v1` branch (`claude/amazing-archimedes-122d78`, 37 commits) already implements "Migration A": a `storage.py` backend boundary, `db.py` (psycopg3 via `DATABASE_URL`), `migrations/`, a full Postgres schema, `project_revisions` history, and transactional optimistic-revision saves with a conflict UX — but it is single-tenant and uses a custom Google-only/single-domain auth (`auth.py`). Work lives on integration branch `feat/supabase-multitenant-electron`. Full plan: `docs/ai/current-plan.md`.

**Alternatives.**
- Stay on JSON/Synology. Rejected — the user wants off Docker + real multi-tenant.
- Self-hosted Postgres (as `collab-v1` built it). Rejected — managed Supabase removes ops burden and provides Auth + Storage + RLS; the swap is just `DATABASE_URL`.
- React + Electron rewrite. Rejected for v1 — the existing vanilla-JS UI runs unchanged in Electron's Chromium renderer; the ~11k-line rewrite is deferred.
- Browser talks to Supabase directly (`supabase-js` CRUD, RLS-pure). Deferred — would rewrite every data call; kept `server.py` as the trusted API instead.

**Decisions.**
- **D1** Managed Supabase replaces self-hosted Docker Postgres; drop the postgres compose service on this branch.
- **D2** RLS is enforced through the trusted `server.py`: connect as `authenticated` and `SET LOCAL request.jwt.claims` per transaction so policies see `auth.uid()`/`auth.jwt()`. `service_role` is seed/migration/admin only (it bypasses RLS). Pooling: default session/direct (5432); if connection limits force the transaction pooler (6543), disable psycopg3 prepared statements and keep claim-setting transaction-local.
- **D3** Supabase Auth (Google + email magic link) replaces `auth.py`; `server.py` verifies the Supabase JWT and resolves workspace membership; per-workspace allow-list replaces the hard-coded `visaliacrc.com`.
- **D4** Electron wraps the existing frontend (spawns `server.py` as a PyInstaller sidecar); `webContents.printToPDF` replaces the headless-Chrome dependency; `electron-updater` replaces Watchtower/zip for the desktop build.
- **D5** Cover/logo images and font binaries move from base64-in-JSONB to Supabase Storage (fixes the ~8.6 MB project bloat and enables cross-client sharing).
- **Multi-tenancy** via `workspaces` + `workspace_members` + `workspace_id` on every table + RLS; workspaces seeded manually for v1 (no self-serve onboarding).

**Consequences.**
- Synology + Watchtower + GHCR auto-update are superseded for the desktop distribution; keep them running until cutover QA (plan issue 20) passes (parallel-run, non-destructive migration).
- RLS becomes security-critical: cross-tenant isolation must be proven by tests (plan issue 8), not assumed.
- The `collab-v1` rebase (plan issue 1) is the first real cost — 37 commits diverged at 2026-04-27, with expected conflicts against the volunteer-roles and lightweight-poll work on `main`.
- Open items to confirm before their milestone: offline (assumed online-required v1), seed-data source, membership allow-list vs invite, pooling mode, and per-workspace vs per-user PCO/Google tokens.

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

## 2026-06-03 — Two separate migration tools for two separate schema variants

**Context.** The `migrations/` directory contains `import_projects.py` (and siblings) that reference columns not in the applied Supabase SQL migrations (`imported_from_json`, `created_by_email`, `updated_by_email`, `saved_by_email`, `saved_by_name`). These modules target a schema variant that was designed but never applied to the staging DB.

**Decision.** Rather than reconcile `migrations/import_*.py` in issue 015, a new standalone `scripts/migrate_to_supabase.py` was created that targets only columns actually present in the applied migrations (`20260602000001` + `20260602000002`). The `migrations/` modules are left as-is since they have their own unit tests that mock away the DB; reconciling them is a separate concern.

**Alternatives.**
- Patch `migrations/import_projects.py` to match actual schema. Rejected — would break their unit tests and expand scope beyond issue 015.
- Add the missing columns in a new migration. Rejected — the columns serve a logging purpose that the new architecture doesn't need; `state` JSONB captures provenance instead.

**Consequences.**
- `scripts/migrate_to_supabase.py` is the authoritative operator runbook tool for the Supabase migration.
- `migrations/run_all_migrations.py` and its importers remain as legacy/unused code unless a future issue reconciles them. They should not be called as part of the Supabase migration.
- A future cleanup issue should either delete `migrations/import_*.py` or update them to match the actual schema.
