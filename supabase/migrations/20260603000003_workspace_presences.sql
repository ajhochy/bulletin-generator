-- Migration: workspace_presences
-- Issue 022: Presence heartbeat table + API endpoints.
--
-- Creates workspace_presences to track which user is editing which project.
-- Records expire via TTL (90-second stale check in application layer).
-- RLS: workspace members can read; users can only upsert their own row.
-- DELETE policy: users can remove their own rows (called on close/sign-out).
--
-- Idempotent: CREATE TABLE IF NOT EXISTS + DROP/CREATE policies.

-- ---- table -------------------------------------------------------------------
create table if not exists public.workspace_presences (
  workspace_id  uuid        not null references public.workspaces(id) on delete cascade,
  user_id       uuid        not null references auth.users(id) on delete cascade,
  project_id    uuid        not null,
  last_seen_at  timestamptz not null default now(),
  primary key (workspace_id, user_id, project_id)
);

create index if not exists workspace_presences_workspace_project_idx
  on public.workspace_presences (workspace_id, project_id);

-- ---- RLS ---------------------------------------------------------------------
alter table public.workspace_presences enable row level security;

-- Workspace members can read all presence rows for their workspace.
drop policy if exists presences_select on public.workspace_presences;
create policy presences_select on public.workspace_presences for select to authenticated
  using ( private.is_workspace_member(workspace_id) );

-- Users can insert their own row only.
drop policy if exists presences_insert on public.workspace_presences;
create policy presences_insert on public.workspace_presences for insert to authenticated
  with check (
    user_id = (select auth.uid())
    and private.is_workspace_member(workspace_id)
  );

-- Users can update their own row only (for heartbeat upsert).
drop policy if exists presences_update on public.workspace_presences;
create policy presences_update on public.workspace_presences for update to authenticated
  using ( user_id = (select auth.uid()) )
  with check ( user_id = (select auth.uid()) );

-- Users can delete their own rows (called on project close / sign-out).
drop policy if exists presences_delete on public.workspace_presences;
create policy presences_delete on public.workspace_presences for delete to authenticated
  using ( user_id = (select auth.uid()) );

-- ---- table privileges --------------------------------------------------------
grant select, insert, update, delete on public.workspace_presences to authenticated;
revoke all on public.workspace_presences from anon;
