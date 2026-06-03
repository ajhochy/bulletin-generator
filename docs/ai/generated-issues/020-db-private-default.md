# 020: DB migration — private-by-default + tighten RLS write policy

**Milestone:** M5  ·  **Plan ref:** Issue 020 (D8)
**Depends on:** — (no prior issue; apply first)

## Context

The `projects` table currently defaults `visibility` to `'workspace'`, meaning every new project is visible (and writable) to all workspace members at creation time. The new ownership model requires new projects to be private by default — the owner explicitly shares them when ready.

Additionally, the `projects_update` RLS policy currently allows any workspace member to update a workspace-visible project. Under the new model, only the project owner (`owner_user_id = auth.uid()`) may write a project at all. This migration tightens that boundary at the DB layer, which is the real enforcement boundary — the Python-side check in issue 021 provides clean 403 UX on top.

Two changes are bundled into one migration because they are logically atomic: changing the default without tightening RLS would briefly expose existing projects to the new default while the old permissive policy is still live.

## Acceptance criteria

- [ ] **AC-020-1:** After the migration is applied, `INSERT INTO projects (...) VALUES (...)` without an explicit `visibility` value produces a row with `visibility='private'`.
- [ ] **AC-020-2:** A user who is NOT `owner_user_id` cannot `UPDATE` a project row under the `authenticated` role — RLS rejects the write (affected rowcount = 0). The project owner can update.
- [ ] **AC-020-3:** All existing rows with `visibility='workspace'` are unchanged by the migration (no backfill of the default value).
- [ ] **AC-020-4:** The migration is idempotent — applying it twice in sequence is a no-op (no errors, no duplicate constraint violations).
- [ ] **AC-020-5:** The migration file follows the naming convention `supabase/migrations/YYYYMMDDHHMMSS_private_default.sql` and is committed under `supabase/migrations/`.
- [ ] **AC-020-6:** `python3 -c "import server"` and `node --check src/js/projects.js` pass without errors after the migration file is added (no Python/JS changes required in this issue, but verify nothing is broken).

## Likely files

- `supabase/migrations/20260604000001_private_default.sql` (new — the migration itself)
- `docs/ai/decisions.md` (append — record D8: visibility default change + RLS tightening)
- `docs/ai/project-state.md` (update — reflect 020 landed)

## Tests / validation

```bash
# Syntax check — no Python/JS changes in this issue
python3 -c "import server"
node --check src/js/projects.js

# Apply migration to staging and run RLS isolation tests:
# (DATABASE_URL must point to staging, never production)
DATABASE_URL=<staging> pytest tests/test_rls_isolation.py -v -k "ownership or write or update"
```

Manual DB verification (Supabase SQL Editor, staging):
```sql
-- 1. Confirm default changed
INSERT INTO public.projects (id, workspace_id, title, state, owner_user_id)
VALUES (gen_random_uuid(), '<workspace_id>', 'test-default-check', '{}', '<your_uid>');
SELECT visibility FROM public.projects WHERE title = 'test-default-check';
-- → should return 'private'

-- 2. Confirm non-owner cannot UPDATE (run as non-owner JWT)
UPDATE public.projects SET title = 'hacked' WHERE id = '<project_id_owned_by_other>';
-- → rowcount = 0

-- 3. Confirm existing workspace rows unchanged
SELECT count(*) FROM public.projects WHERE visibility = 'workspace';
-- → same count as before migration
```

## Data-safety / out of scope

- This migration changes the column DEFAULT only — no `UPDATE` statement touches existing rows. All pre-existing `'workspace'`-visibility projects keep their value unchanged.
- The RLS policy change affects write enforcement only; `SELECT` (read) policies are untouched. Non-owners can still read workspace-visible projects.
- The migration must be applied via `supabase/migrations/` (Supabase CLI `db push` or `apply_migration` MCP tool) — never as a one-time hotfix in the SQL editor.
- Out of scope: backfilling `owner_user_id` on ownerless projects — that is handled in issue 024.
- Out of scope: Python-side `can_write_project` check — that is issue 021.
- Out of scope: any frontend changes — those are issue 023.
