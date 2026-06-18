---
date: 2026-06-04
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# Abandoned Share-to-Workspace; confirmed visibility model A (workspace-visible by default + hand-off)

**Context.** The "private-by-default + explicit share-to-workspace" model planned in issues 020/023 was only partly realized: `PostgresStorageBackend.save_project` hard-codes `visibility = 'workspace'` on INSERT (storage.py), so new projects were always workspace-visible despite the issue-020 migration setting the column *default* to `'private'`. No Share UI was ever built — the `POST /api/projects/{id}/share` endpoint had no frontend caller.

**Decision (model A).** Keep it that way. Projects are **workspace-visible by default** (every workspace member sees them read-only); only the owner can edit (owner-only-write RLS retained); **hand-off** (`POST /api/projects/{id}/transfer`, wired via the Hand-off button) reassigns the sole editor. There is no per-project private/share toggle. Share-to-Workspace is abandoned (GitHub #211 closed not-planned).

**Consequences.**
- Removed dead code: `_handle_share_project` (server.py) + its dispatch, `share_project_to_workspace` (abstract + Json + Postgres backends in storage.py), and `tests/test_share_project.py`.
- Issue 020's "private-by-default" is **obsolete**. The `'private'` column default (migration `20260603000002_private_default_rls.sql`) is harmless but **vestigial** — `save_project`'s explicit `'workspace'` overrides it. The owner-only-write RLS policy from that migration is **kept** (still correct for model A). Not reverting the migration: it would need a new idempotent migration for no functional gain.
- Duplicate creates a new **workspace-visible** project owned by the current user (not private), since `save_project` forces `'workspace'`.
- The read-only banner + presence badge still apply (non-owners viewing a workspace project).
