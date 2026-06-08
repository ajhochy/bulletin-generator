-- Migration: project_revisions_unique_revision
-- Issue #216. Enforce "revision numbers are unique per project" at the database
-- level. Previously uniqueness relied solely on application logic (revision is
-- incremented on each save). A unique index makes a duplicate (project_id,
-- revision_number) impossible regardless of the write path (server psycopg or
-- the renderer's supabase-js), which also hard-guards against any double-snapshot
-- bug (e.g. both save_project and a future trigger inserting the same revision).
--
-- Safe + idempotent: verified there are zero existing duplicate
-- (project_id, revision_number) pairs before adding this; CREATE UNIQUE INDEX
-- IF NOT EXISTS is a no-op on re-apply.

create unique index if not exists project_revisions_project_revision_uniq
  on public.project_revisions (project_id, revision_number);
