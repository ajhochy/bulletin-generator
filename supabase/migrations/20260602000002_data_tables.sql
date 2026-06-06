-- Migration: data_tables
-- Remaining multi-tenant data tables (issue 001 / #257), built on the proven
-- pattern from 20260602000001_tenancy_foundation.sql:
--   * workspace_id FK -> public.workspaces(id) on delete cascade, indexed
--   * RLS TO authenticated, gated by private.is_workspace_member(workspace_id)
--   * (select auth.uid()) for per-statement caching; USING + WITH CHECK on writes
--   * grants to authenticated; anon revoked entirely
--
-- Idempotent: create table/index if not exists + drop policy if exists/recreate.
-- Safe to re-run (db push / second apply) as a no-op.
--
-- Special cases (do NOT "simplify" into the generic pattern):
--   * project_revisions is APPEND-ONLY: select + insert policies only, no
--     update/delete policy, so RLS denies mutation even though the table grant
--     mirrors the others.
--   * user_settings is PER-USER: every policy is gated on user_id = auth.uid(),
--     NOT on workspace membership, so members cannot read each other's settings.
--
-- Column shapes intentionally match collab-v1's importer expectations
-- (tests/test_import_*.py) so issue 015 migration tooling needs no transform.

-- ============================================================================
-- project_revisions  (append-only history of project saves)
-- ============================================================================
create table if not exists public.project_revisions (
  id uuid primary key default gen_random_uuid(),
  project_id text not null references public.projects(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  revision_number integer not null,
  state jsonb not null,
  summary text,
  created_at timestamptz not null default now(),
  created_by_user_id uuid references auth.users(id)
);
create index if not exists project_revisions_project_rev_idx
  on public.project_revisions (project_id, revision_number);
create index if not exists project_revisions_workspace_id_idx
  on public.project_revisions (workspace_id);

-- ============================================================================
-- workspace_settings  (one row per workspace; workspace_id is the PK)
-- ============================================================================
create table if not exists public.workspace_settings (
  workspace_id uuid primary key references public.workspaces(id) on delete cascade,
  settings jsonb not null default '{}'::jsonb
);
-- workspace_id is the primary key, so it is already indexed (no extra index).

-- ============================================================================
-- user_settings  (one row per user; per-user RLS, not workspace membership)
-- ============================================================================
create table if not exists public.user_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  settings jsonb not null default '{}'::jsonb
);
create index if not exists user_settings_workspace_id_idx
  on public.user_settings (workspace_id);

-- ============================================================================
-- announcements
-- ============================================================================
create table if not exists public.announcements (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  title text,
  body text,
  state jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by_user_id uuid references auth.users(id)
);
create index if not exists announcements_workspace_id_idx
  on public.announcements (workspace_id);

-- ============================================================================
-- songs
-- ============================================================================
create table if not exists public.songs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  title text not null,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists songs_workspace_id_idx
  on public.songs (workspace_id);

-- ============================================================================
-- templates
-- ============================================================================
create table if not exists public.templates (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  name text not null,
  template_data jsonb not null default '{}'::jsonb,
  is_default boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists templates_workspace_id_idx
  on public.templates (workspace_id);

-- ============================================================================
-- fonts  (metadata; the file itself lives in Supabase Storage, issue 010)
-- ============================================================================
create table if not exists public.fonts (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  name text not null,
  storage_path text,
  mime_type text,
  created_at timestamptz not null default now()
);
create index if not exists fonts_workspace_id_idx
  on public.fonts (workspace_id);

-- ============================================================================
-- RLS
-- ============================================================================
alter table public.project_revisions enable row level security;
alter table public.workspace_settings enable row level security;
alter table public.user_settings     enable row level security;
alter table public.announcements      enable row level security;
alter table public.songs              enable row level security;
alter table public.templates          enable row level security;
alter table public.fonts              enable row level security;

-- ---- project_revisions: append-only (select + insert only) -------------------
drop policy if exists project_revisions_select on public.project_revisions;
create policy project_revisions_select on public.project_revisions for select to authenticated
  using ( private.is_workspace_member(workspace_id) );
drop policy if exists project_revisions_insert on public.project_revisions;
create policy project_revisions_insert on public.project_revisions for insert to authenticated
  with check ( private.is_workspace_member(workspace_id)
               and created_by_user_id = (select auth.uid()) );
-- No update/delete policy by design: RLS denies mutation -> append-only.

-- ---- workspace_settings: full workspace-member CRUD --------------------------
drop policy if exists workspace_settings_select on public.workspace_settings;
create policy workspace_settings_select on public.workspace_settings for select to authenticated
  using ( private.is_workspace_member(workspace_id) );
drop policy if exists workspace_settings_insert on public.workspace_settings;
create policy workspace_settings_insert on public.workspace_settings for insert to authenticated
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists workspace_settings_update on public.workspace_settings;
create policy workspace_settings_update on public.workspace_settings for update to authenticated
  using ( private.is_workspace_member(workspace_id) )
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists workspace_settings_delete on public.workspace_settings;
create policy workspace_settings_delete on public.workspace_settings for delete to authenticated
  using ( private.is_workspace_member(workspace_id) );

-- ---- user_settings: per-user (user_id = auth.uid()), NOT membership ----------
drop policy if exists user_settings_select on public.user_settings;
create policy user_settings_select on public.user_settings for select to authenticated
  using ( user_id = (select auth.uid()) );
drop policy if exists user_settings_insert on public.user_settings;
create policy user_settings_insert on public.user_settings for insert to authenticated
  with check ( user_id = (select auth.uid()) );
drop policy if exists user_settings_update on public.user_settings;
create policy user_settings_update on public.user_settings for update to authenticated
  using ( user_id = (select auth.uid()) )
  with check ( user_id = (select auth.uid()) );
drop policy if exists user_settings_delete on public.user_settings;
create policy user_settings_delete on public.user_settings for delete to authenticated
  using ( user_id = (select auth.uid()) );

-- ---- announcements: full workspace-member CRUD -------------------------------
drop policy if exists announcements_select on public.announcements;
create policy announcements_select on public.announcements for select to authenticated
  using ( private.is_workspace_member(workspace_id) );
drop policy if exists announcements_insert on public.announcements;
create policy announcements_insert on public.announcements for insert to authenticated
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists announcements_update on public.announcements;
create policy announcements_update on public.announcements for update to authenticated
  using ( private.is_workspace_member(workspace_id) )
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists announcements_delete on public.announcements;
create policy announcements_delete on public.announcements for delete to authenticated
  using ( private.is_workspace_member(workspace_id) );

-- ---- songs: full workspace-member CRUD ---------------------------------------
drop policy if exists songs_select on public.songs;
create policy songs_select on public.songs for select to authenticated
  using ( private.is_workspace_member(workspace_id) );
drop policy if exists songs_insert on public.songs;
create policy songs_insert on public.songs for insert to authenticated
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists songs_update on public.songs;
create policy songs_update on public.songs for update to authenticated
  using ( private.is_workspace_member(workspace_id) )
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists songs_delete on public.songs;
create policy songs_delete on public.songs for delete to authenticated
  using ( private.is_workspace_member(workspace_id) );

-- ---- templates: full workspace-member CRUD -----------------------------------
drop policy if exists templates_select on public.templates;
create policy templates_select on public.templates for select to authenticated
  using ( private.is_workspace_member(workspace_id) );
drop policy if exists templates_insert on public.templates;
create policy templates_insert on public.templates for insert to authenticated
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists templates_update on public.templates;
create policy templates_update on public.templates for update to authenticated
  using ( private.is_workspace_member(workspace_id) )
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists templates_delete on public.templates;
create policy templates_delete on public.templates for delete to authenticated
  using ( private.is_workspace_member(workspace_id) );

-- ---- fonts: full workspace-member CRUD ---------------------------------------
drop policy if exists fonts_select on public.fonts;
create policy fonts_select on public.fonts for select to authenticated
  using ( private.is_workspace_member(workspace_id) );
drop policy if exists fonts_insert on public.fonts;
create policy fonts_insert on public.fonts for insert to authenticated
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists fonts_update on public.fonts;
create policy fonts_update on public.fonts for update to authenticated
  using ( private.is_workspace_member(workspace_id) )
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists fonts_delete on public.fonts;
create policy fonts_delete on public.fonts for delete to authenticated
  using ( private.is_workspace_member(workspace_id) );

-- ============================================================================
-- Table privileges (RLS restricts rows; anon gets nothing)
-- project_revisions keeps the uniform grant, but with no update/delete policy
-- those operations remain RLS-denied -> append-only is preserved.
-- ============================================================================
grant select, insert, update, delete on public.project_revisions  to authenticated;
grant select, insert, update, delete on public.workspace_settings to authenticated;
grant select, insert, update, delete on public.user_settings      to authenticated;
grant select, insert, update, delete on public.announcements      to authenticated;
grant select, insert, update, delete on public.songs              to authenticated;
grant select, insert, update, delete on public.templates          to authenticated;
grant select, insert, update, delete on public.fonts              to authenticated;

revoke all on public.project_revisions, public.workspace_settings, public.user_settings,
              public.announcements, public.songs, public.templates, public.fonts
  from anon;
