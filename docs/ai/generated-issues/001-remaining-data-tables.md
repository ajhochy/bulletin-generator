# 001: Remaining multi-tenant data tables

**Milestone:** M1  ·  **Plan ref:** issues 5 (workspace_id threading) + new (remaining tables)
**Depends on:** none (tenancy foundation already applied to staging: workspaces, workspace_members, projects, profiles, RLS helpers, grants)

## Context

The tenancy foundation migration (`supabase/migrations/20260602000001_tenancy_foundation.sql`) is already applied to staging and proven: `workspaces`, `workspace_members`, `profiles`, `projects`, and the `private.is_workspace_member`/`private.shares_workspace_with` SECURITY DEFINER helpers exist with RLS and cross-tenant isolation verified. The remaining data tables from the plan's target architecture — `project_revisions`, `workspace_settings`, `user_settings`, `announcements`, `songs`, `templates`, `fonts` — must be created following the identical `projects` pattern (workspace_id FK + RLS via helper + indexed tenant column + authenticated grants + anon denied).

## Acceptance criteria

- [ ] `supabase/migrations/20260602000002_data_tables.sql` exists and is idempotent (`create table if not exists`, `create index if not exists`, `drop policy if exists` + recreate pattern matching 20260602000001).
- [ ] `project_revisions`: append-only (`project_id text references public.projects(id) on delete cascade`, `workspace_id uuid not null`, `revision_number integer not null`, `state jsonb not null`, `summary text`, `created_at timestamptz`, `created_by_user_id uuid`). No UPDATE policy (append-only). SELECT policy: `private.is_workspace_member(workspace_id)` AND `project_id` is in caller's workspace. INSERT policy: same member check + `created_by_user_id = (select auth.uid())`. Index on `(project_id, revision_number)` and `workspace_id`.
- [ ] `workspace_settings`: `workspace_id uuid primary key references public.workspaces(id)`, `settings jsonb not null default '{}'`. RLS: select/insert/update/delete all gated on `private.is_workspace_member(workspace_id)`. Index on `workspace_id`.
- [ ] `user_settings`: `user_id uuid primary key references auth.users(id) on delete cascade`, `workspace_id uuid not null references public.workspaces(id)`, `settings jsonb not null default '{}'`. RLS: all ops gated on `user_id = (select auth.uid())` (per-user, not per-workspace membership). Index on `workspace_id`.
- [ ] `announcements`: `id uuid primary key default gen_random_uuid()`, `workspace_id uuid not null`, `title text`, `body text`, `state jsonb not null default '{}'`, `created_at timestamptz`, `updated_at timestamptz`, `created_by_user_id uuid`. RLS: select/insert/update/delete all gated on `private.is_workspace_member(workspace_id)`. Index on `workspace_id`.
- [ ] `songs`: `id uuid primary key default gen_random_uuid()`, `workspace_id uuid not null`, `title text not null`, `data jsonb not null default '{}'`, `created_at timestamptz`, `updated_at timestamptz`. RLS: same workspace-member pattern. Index on `workspace_id`.
- [ ] `templates`: `id uuid primary key default gen_random_uuid()`, `workspace_id uuid not null`, `name text not null`, `template_data jsonb not null default '{}'`, `is_default boolean not null default false`, `created_at timestamptz`, `updated_at timestamptz`. RLS: same workspace-member pattern. Index on `workspace_id`.
- [ ] `fonts`: `id uuid primary key default gen_random_uuid()`, `workspace_id uuid not null`, `name text not null`, `storage_path text`, `mime_type text`, `created_at timestamptz`. RLS: same workspace-member pattern. Index on `workspace_id`.
- [ ] All tables: `grant select, insert, update, delete on <table> to authenticated; revoke all on <table> from anon;` — same as `projects`.
- [ ] Migration applied to the staging Supabase project (`dgydekhfzrmeoscpgmvo`) without errors; `supabase migration list` (or MCP list_migrations) shows it as applied.
- [ ] Running the migration a second time (or re-applying via `supabase db push --dry-run`) produces zero errors (idempotency).

## Likely files

- `supabase/migrations/20260602000002_data_tables.sql` (new)
- `docs/ai/project-state.md` (update after applied)

## Tests / validation

```bash
# After applying migration to staging via MCP execute_sql or supabase CLI:
# 1. Verify tables exist:
#    SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'
#    ORDER BY table_name;
#    → should include all 7 new tables

# 2. Verify RLS is enabled on each:
#    SELECT tablename, rowsecurity FROM pg_tables
#    WHERE schemaname = 'public' AND tablename IN
#    ('project_revisions','workspace_settings','user_settings',
#     'announcements','songs','templates','fonts');
#    → rowsecurity = true for all

# 3. Idempotency: re-run the SQL (or supabase db push); zero errors.

# 4. Manual: confirm no anon-role access:
#    As anon role, attempt SELECT on any new table → 0 rows (RLS denies).
```

Note: full cross-tenant isolation tests for the new tables are covered in issue 002 (the dedicated RLS test suite).

## Data-safety / out of scope

- Never commit `.env`, `data/*.json`, or any file containing the service_role key.
- `user_settings` rows are per-user (not workspace-scoped for reads); RLS uses `user_id = auth.uid()` — do NOT accidentally apply the workspace-member policy or users will see each other's settings.
- `project_revisions` is append-only by design; no UPDATE policy should be added.
- Column shapes must match `collab-v1`'s importer shapes (see `tests/test_import_projects.py`, `tests/test_import_settings.py`, `tests/test_import_songs.py`, etc.) so data-migration tooling (issue 015) works without a transform layer.
- This issue covers schema only; wiring `storage.py` to use these tables is issue 004.
