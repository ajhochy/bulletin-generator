# 024: Backfill ownerless projects + update QA matrix

**Milestone:** M5  ·  **Plan ref:** Issue 024
**Depends on:** 021, 022

## Context

After issues 020–023 land, any `'workspace'`-visibility project that has `owner_user_id IS NULL` is in an ambiguous state: the tighter RLS policy (`owner_user_id = auth.uid()`) means no one can write it, because the NULL never equals any user's `auth.uid()`. These are legacy projects created before the ownership model existed.

This issue provides a controlled backfill script that assigns the workspace's founding member as owner for each ownerless workspace-visible project, with a mandatory `--dry-run` gate. It also updates the QA matrix document to retire the now-moot C1–C3 conflict detection checks and replace them with write-protection and presence badge checks.

Both tasks are in the same issue because they are post-merge bookkeeping that makes the cut-over complete: data consistent + QA matrix current.

## Acceptance criteria

- [ ] **AC-024-1:** `python3 scripts/migrate_to_supabase.py --backfill-owners --dry-run` prints a count of projects matching `visibility='workspace' AND owner_user_id IS NULL`, a list of affected project IDs and titles, and exits 0 without writing any rows.
- [ ] **AC-024-2:** After running without `--dry-run`, no row in the `projects` table has `visibility='workspace' AND owner_user_id IS NULL` (except any rows the script explicitly marks as intentionally unowned and skips — see data-safety note).
- [ ] **AC-024-3:** The backfill script is idempotent — running it a second time with the same data finds zero ownerless rows and exits 0 with a "Nothing to do" message.
- [ ] **AC-024-4:** The script uses the `service_role` Supabase client (bypasses RLS) for the backfill UPDATE, not the anon/authenticated client.
- [ ] **AC-024-5:** `docs/ai/qa-matrix-m5.md` no longer contains the C1 ("Conflict detection"), C2 ("Stale revision poll"), and C3 ("Conflict banner / dialog") test cases.
- [ ] **AC-024-6:** `docs/ai/qa-matrix-m5.md` contains new test cases covering: (a) owner-write enforcement (non-owner save attempt returns 403 / save button disabled), (b) presence badge appears when owner is editing, (c) presence badge disappears after TTL expires.
- [ ] **AC-024-7:** `python3 -c "import scripts.migrate_to_supabase"` (or equivalent import check) succeeds — the script has no syntax errors.

## Likely files

- `scripts/migrate_to_supabase.py` (modify — add `--backfill-owners` flag + backfill logic; add `--dry-run` support if not already present)
- `docs/ai/qa-matrix-m5.md` (modify — remove C1–C3; add write-protection + presence checks)
- `docs/ai/project-state.md` (update — reflect 024 landed; note M5 cutover complete)
- `docs/ai/decisions.md` (append — note that C1–C3 conflict checks are retired and replaced)

## Tests / validation

```bash
# Syntax check
python3 -c "import server"
python3 scripts/migrate_to_supabase.py --backfill-owners --dry-run
# → prints ownerless count and project list, exits 0, no DB writes

# Idempotency check (after a live run)
python3 scripts/migrate_to_supabase.py --backfill-owners --dry-run
# → "Nothing to do. 0 ownerless workspace-visible projects found."
```

Manual verification (Supabase SQL Editor, staging — after live run):
```sql
-- Confirm no ownerless workspace-visible projects remain
SELECT count(*) FROM public.projects
WHERE visibility = 'workspace' AND owner_user_id IS NULL;
-- → 0

-- Spot-check: previously ownerless project now has an owner
SELECT id, title, owner_user_id, visibility FROM public.projects
WHERE title = '<known previously ownerless project>';
-- → owner_user_id is not null
```

QA matrix review: open `docs/ai/qa-matrix-m5.md` and confirm:
- No rows with IDs C1, C2, or C3 (or equivalent conflict-detection checks).
- New rows for owner-write enforcement and presence badge behavior are present and actionable.

## Data-safety / out of scope

- The backfill script MUST require `--dry-run` to be explicitly negated (e.g., `--no-dry-run` or absence of the flag causes live run with a confirmation prompt). Accidental live runs must not be possible.
- The service_role credentials used by the backfill script must not be committed or logged. Pass via environment variable (`SUPABASE_SERVICE_ROLE_KEY`).
- The backfill assigns the workspace's **founding member** (earliest `workspace_members` row for the workspace) as owner. If a workspace has no members at all (orphaned workspace), skip the project and log a warning — do not fail.
- This script does NOT delete any project data. It only sets `owner_user_id` on rows where it is currently NULL. Projects themselves are never removed.
- `ConflictError` and `save_project_transactional` in `storage.py` are still present as dead code after this issue. A separate cleanup issue should remove them once the cutover QA confirms the new ownership model is stable.
- Out of scope: migrating `'private'`-visibility ownerless projects — by definition, private projects with no owner are invisible to everyone; they can be addressed in a follow-up cleanup issue.
- Out of scope: UI for workspace membership management or invite flows — explicitly excluded from this plan.
