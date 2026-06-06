-- Migration: presence_project_id_text
-- Fix: workspace_presences.project_id was created as uuid (see
-- 20260603000003_workspace_presences.sql), but public.projects.id is TEXT in the
-- format proj_<timestamp>_<rand> (e.g. proj_1780694817495_5s3vrh). Binding a TEXT
-- project id against the uuid column made Postgres raise
-- psycopg.errors.InvalidTextRepresentation ("invalid input syntax for type uuid"),
-- 500-ing every presence GET (_handle_get_presence) and heartbeat upsert
-- (_handle_post_presence_heartbeat) for real projects. The frontend swallows
-- presence errors (best-effort), so it was silently broken for all projects.
--
-- Align the column type with public.projects.id (TEXT). uuid -> text is a
-- widening cast (every uuid has a text representation), so existing rows convert
-- losslessly. The primary key (workspace_id, user_id, project_id) and the
-- workspace_presences_workspace_project_idx index are rebuilt automatically.
--
-- Idempotent: only alters when the column is still uuid.

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name   = 'workspace_presences'
      and column_name  = 'project_id'
      and data_type    = 'uuid'
  ) then
    alter table public.workspace_presences
      alter column project_id type text using project_id::text;
  end if;
end $$;
