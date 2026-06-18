---
date: 2026-06-05
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# Presence project_id is TEXT, not uuid (fix forward migration, not edit-in-place)

**Context.** `workspace_presences.project_id` was declared `uuid` in `20260603000003_workspace_presences.sql`, but project ids are application-generated TEXT (`proj_<timestamp>_<rand>`) and `public.projects.id` is `text`. Every presence read/heartbeat 500'd with `InvalidTextRepresentation`; the frontend's best-effort error swallowing hid it.

**Decision.** Fix via a **new additive migration** (`20260605000002_presence_project_id_text.sql`) that idempotently `ALTER COLUMN project_id TYPE text`, rather than editing the original applied migration. Consistent with AGENTS.md's "migrations are idempotent and additive" rule — never rewrite an applied migration. A fresh DB applies both in order (create uuid → alter to text); existing DBs convert losslessly.

**Consequences.**
- The fix lives only in `supabase/migrations/*` (the Supabase-platform migration track), not the Python `migrations/runner.py` track — the presence table belongs to the former.
- No `server.py` query change: the handlers bind `project_id` as a plain string param (no `::uuid` cast), so the column-type change is the whole fix. Corrected the handlers' `<uuid>` docstrings to `<project-id>` so the wrong assumption isn't reintroduced.
- **Rule for any future table keyed by a project id: use `text`, never `uuid`.** Project ids are not uuids.
