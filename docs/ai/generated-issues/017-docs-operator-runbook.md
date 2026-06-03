# 017: Documentation + operator runbook

**Milestone:** M5  ·  **Plan ref:** issue 21
**Depends on:** 016

## Context

After QA passes, the project documentation must reflect the new architecture so the next operator (or AI agent) can set up, seed, and operate the system without reverse-engineering the code. The Synology/Watchtower deployment model is deprecated for the desktop distribution; this issue captures that change and provides a complete Supabase-first runbook.

## Acceptance criteria

- [ ] `docs/ai/architecture.md` updated to reflect the new four-layer architecture (Electron renderer → server.py → Supabase Postgres/Auth/Storage) and the two remaining deployment modes (Electron desktop, Docker server).
- [ ] `docs/ai/decisions.md` has final entries for any decisions made during M4/M5 that are not yet recorded (e.g. pooler mode confirmed, custom SMTP vendor chosen, Windows signing deferred).
- [ ] `docs/ai/testing-guide.md` updated: (a) the "no automated test suite" note is removed/corrected to reflect pytest + vitest + Supabase integration tests; (b) Electron build + launch verification steps added; (c) `DATABASE_URL` and `SUPABASE_JWT_SECRET` env vars documented.
- [ ] `CLAUDE.md`: key-files table updated to include `electron/main.js`, `electron/preload.js`, `auth.py` (new JWT-verify role), `db.py` (transaction helper), `storage.py` (multi-tenant), `migrations/seed_workspace.py`. Deployment modes section updated (Synology/Watchtower deprecated for desktop; Docker server mode still supported).
- [ ] `README.md` or `MANUAL-STEPS.md`: complete Supabase project setup runbook — from creating a new Supabase project to seeding the first workspace and onboarding the first user. Synology/Watchtower section marked "deprecated as of v2.0 for desktop distribution; Docker server mode still works."
- [ ] `docs/ai/repo-map.md` updated to include new files from M1–M4.
- [ ] No placeholder sections — every "TODO" in documentation from the M1–M4 issues is resolved.

## Likely files

- `docs/ai/architecture.md`
- `docs/ai/decisions.md`
- `docs/ai/testing-guide.md`
- `docs/ai/repo-map.md`
- `CLAUDE.md`
- `README.md` and/or `MANUAL-STEPS.md`
- `docs/ai/project-state.md` (update — mark docs done)

## Tests / validation

Documentation review only (no automated tests):
1. A new developer can follow the Supabase setup runbook from scratch and reach a working local development environment in under 30 minutes.
2. `CLAUDE.md` key-files table matches the actual file list (`ls -1 *.py electron/ src/js/ migrations/`).
3. `docs/ai/testing-guide.md` commands are copy-pasteable and correct (spot-check: `pytest -v`, `npm test`, `npm run electron`).

## Data-safety / out of scope

- Never commit real credentials, real user data, or workspace-specific settings in documentation.
- `MANUAL-STEPS.md` must NOT include the actual `DATABASE_URL` or `SUPABASE_JWT_SECRET` values — only placeholder format strings.
- Out of scope: video tutorials, user-facing help docs, or changelog. This is operator/developer documentation only.
