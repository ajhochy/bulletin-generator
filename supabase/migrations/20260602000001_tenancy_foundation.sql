-- Migration: tenancy_foundation
-- Multi-tenant Workspaces + central projects table + RLS.
--
-- STATUS: already applied to the staging project (ref dgydekhfzrmeoscpgmvo) via the
-- Supabase MCP while iterating; cross-tenant read/write isolation verified; security
-- advisor clean (except the project-level "leaked password protection" Auth toggle).
-- When the Supabase CLI is linked (needs the DB password), reconcile with:
--   supabase migration repair --status applied 20260602000001   (it's already on staging)
-- or `supabase db push` (this SQL is idempotent, so a re-run is a safe no-op).
--
-- Design notes:
--   * Supabase Auth owns auth.users + sessions; we mirror users into public.profiles.
--   * Membership checks use SECURITY DEFINER helpers in the unexposed `private` schema
--     to avoid RLS recursion on workspace_members (and to stay off the public API).
--   * RLS uses (select auth.uid()) for per-statement caching, TO authenticated, and
--     both USING + WITH CHECK on writes. Tenant columns are indexed.
--   * Workspace/member creation is service_role/seed-only in v1 (no authenticated write
--     policies) — "architect for many, seed manually".

-- ---- schemas ------------------------------------------------------------------
create schema if not exists private;

-- ---- profiles (mirror of auth.users) ------------------------------------------
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  avatar_url text,
  created_at timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, email, display_name, avatar_url)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', new.email),
    new.raw_user_meta_data->>'avatar_url'
  )
  on conflict (id) do nothing;
  return new;
end; $$;
-- Not a public RPC: only the trigger should invoke it.
revoke execute on function public.handle_new_user() from public, anon, authenticated;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users for each row execute function public.handle_new_user();

-- ---- workspaces + membership --------------------------------------------------
create table if not exists public.workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text unique,
  created_at timestamptz not null default now(),
  created_by_user_id uuid references auth.users(id)
);

create table if not exists public.workspace_members (
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'editor' check (role in ('owner','editor','viewer')),
  created_at timestamptz not null default now(),
  primary key (workspace_id, user_id)
);
create index if not exists workspace_members_user_id_idx on public.workspace_members (user_id);

-- ---- SECURITY DEFINER membership helpers (unexposed; avoid RLS recursion) ------
create or replace function private.is_workspace_member(ws uuid)
returns boolean language sql security definer set search_path = '' stable as $$
  select exists (
    select 1 from public.workspace_members m
    where m.workspace_id = ws and m.user_id = (select auth.uid())
  );
$$;

create or replace function private.shares_workspace_with(target uuid)
returns boolean language sql security definer set search_path = '' stable as $$
  select exists (
    select 1
    from public.workspace_members m1
    join public.workspace_members m2 on m1.workspace_id = m2.workspace_id
    where m1.user_id = (select auth.uid()) and m2.user_id = target
  );
$$;

-- ---- projects (central data table) --------------------------------------------
create table if not exists public.projects (
  id text primary key,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  name text not null,
  owner_user_id uuid references auth.users(id),
  visibility text not null default 'workspace' check (visibility in ('private','workspace')),
  state jsonb not null default '{}'::jsonb,
  revision integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by_user_id uuid references auth.users(id),
  updated_by_user_id uuid references auth.users(id)
);
create index if not exists projects_workspace_id_idx on public.projects (workspace_id);
create index if not exists projects_owner_user_id_idx on public.projects (owner_user_id);

-- ---- RLS ----------------------------------------------------------------------
alter table public.profiles          enable row level security;
alter table public.workspaces        enable row level security;
alter table public.workspace_members enable row level security;
alter table public.projects          enable row level security;

drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles for select to authenticated
  using ( id = (select auth.uid()) or private.shares_workspace_with(id) );
drop policy if exists profiles_update on public.profiles;
create policy profiles_update on public.profiles for update to authenticated
  using ( id = (select auth.uid()) ) with check ( id = (select auth.uid()) );

drop policy if exists workspaces_select on public.workspaces;
create policy workspaces_select on public.workspaces for select to authenticated
  using ( private.is_workspace_member(id) );

drop policy if exists workspace_members_select on public.workspace_members;
create policy workspace_members_select on public.workspace_members for select to authenticated
  using ( user_id = (select auth.uid()) or private.is_workspace_member(workspace_id) );

drop policy if exists projects_select on public.projects;
create policy projects_select on public.projects for select to authenticated
  using ( private.is_workspace_member(workspace_id)
          and (visibility = 'workspace' or owner_user_id = (select auth.uid())) );
drop policy if exists projects_insert on public.projects;
create policy projects_insert on public.projects for insert to authenticated
  with check ( private.is_workspace_member(workspace_id) and owner_user_id = (select auth.uid()) );
drop policy if exists projects_update on public.projects;
create policy projects_update on public.projects for update to authenticated
  using ( private.is_workspace_member(workspace_id)
          and (visibility = 'workspace' or owner_user_id = (select auth.uid())) )
  with check ( private.is_workspace_member(workspace_id) );
drop policy if exists projects_delete on public.projects;
create policy projects_delete on public.projects for delete to authenticated
  using ( private.is_workspace_member(workspace_id) and owner_user_id = (select auth.uid()) );

-- ---- table privileges (RLS restricts rows; anon gets nothing) -----------------
grant select, insert, update, delete on public.projects          to authenticated;
grant select                          on public.workspaces        to authenticated;
grant select                          on public.workspace_members to authenticated;
grant select, update                  on public.profiles          to authenticated;
revoke all on public.projects, public.workspaces, public.workspace_members, public.profiles from anon;
