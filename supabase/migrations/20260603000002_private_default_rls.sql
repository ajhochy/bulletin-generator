-- Migration: private_default_rls
-- Issue 020: private-by-default + tighten RLS write policy on projects.
--
-- Changes:
--   1. projects.visibility column DEFAULT changed from 'workspace' to 'private'.
--      Existing rows are NOT changed — this is a DEFAULT change only.
--   2. projects_update policy tightened: only the project's owner_user_id can
--      UPDATE a project (previously any workspace member could update any
--      workspace-visible project).
--
-- Unchanged:
--   * projects_select — already correctly handles private vs workspace visibility:
--       workspace members see all 'workspace' projects; only owner sees 'private'.
--   * projects_insert — any workspace member can create; they become owner via
--       owner_user_id = auth.uid() in the WITH CHECK.
--   * projects_delete — already owner-only.
--
-- Idempotent: ALTER COLUMN DEFAULT is a no-op if already 'private';
-- drop policy if exists + recreate is safe to re-run.

-- ---- 1. Change column default -------------------------------------------------
alter table public.projects
  alter column visibility set default 'private';

-- ---- 2. Tighten projects_update: owner-only -----------------------------------
drop policy if exists projects_update on public.projects;
create policy projects_update on public.projects for update to authenticated
  using (
    private.is_workspace_member(workspace_id)
    and owner_user_id = (select auth.uid())
  )
  with check (
    private.is_workspace_member(workspace_id)
    and owner_user_id = (select auth.uid())
  );
