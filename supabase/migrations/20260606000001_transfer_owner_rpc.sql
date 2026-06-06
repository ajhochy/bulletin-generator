-- Migration: transfer_owner_rpc
-- Issue #277-B. Adds a SECURITY DEFINER RPC so the renderer (supabase-js + the
-- publishable/anon key under the caller's JWT, RLS enforced) can transfer
-- project ownership to another workspace member WITHOUT the owner-role
-- DATABASE_URL connection that issue #277 removes from the desktop build.
--
-- Why an RPC is required: the projects_update RLS policy's WITH CHECK requires
-- owner_user_id = auth.uid() on the NEW row (20260602000001_tenancy_foundation.sql).
-- A plain UPDATE under the caller's JWT therefore CANNOT set owner_user_id to a
-- different user, so transfer is impossible via direct table writes. The prior
-- implementation used admin_transaction() (owner role, bypasses RLS) from the
-- Python sidecar — exactly the credential path #277 eliminates. This function
-- re-implements the server's guards in the database (caller must be the current
-- owner; target must be a member of the project's workspace), runs as the
-- definer so it can pass the WITH CHECK, and is executable only by the
-- `authenticated` role.
--
-- Security notes:
--   * SECURITY DEFINER + `set search_path = ''` (every identifier is fully
--     schema-qualified) prevents search_path hijacking.
--   * auth.uid() still resolves to the *calling* session's JWT subject under a
--     definer function, so the owner check is enforced against the real caller.
--   * EXECUTE is granted to `authenticated` only; revoked from public/anon.
--
-- Idempotent: CREATE OR REPLACE + revoke/grant are safe to re-run.

create or replace function public.transfer_project_owner(
  p_project_id text,
  p_to_user_id uuid
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_caller    uuid := (select auth.uid());
  v_workspace uuid;
  v_owner     uuid;
begin
  if v_caller is null then
    raise exception 'authentication required' using errcode = '28000';
  end if;

  select p.workspace_id, p.owner_user_id
    into v_workspace, v_owner
    from public.projects p
   where p.id = p_project_id;

  if not found then
    raise exception 'project not found' using errcode = 'P0002';
  end if;

  -- Only the current owner may transfer.
  if v_owner is distinct from v_caller then
    raise exception 'caller is not the project owner' using errcode = '42501';
  end if;

  -- Target must be a member of the project's workspace.
  if not exists (
    select 1
      from public.workspace_members wm
     where wm.workspace_id = v_workspace
       and wm.user_id = p_to_user_id
  ) then
    raise exception 'target user is not a workspace member' using errcode = '23514';
  end if;

  update public.projects
     set owner_user_id      = p_to_user_id,
         updated_at         = now(),
         updated_by_user_id = v_caller
   where id = p_project_id;

  return p_to_user_id;
end;
$$;

revoke all on function public.transfer_project_owner(text, uuid) from public;
revoke all on function public.transfer_project_owner(text, uuid) from anon;
grant execute on function public.transfer_project_owner(text, uuid) to authenticated;
