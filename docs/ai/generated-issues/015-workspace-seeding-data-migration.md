# 015: Workspace seeding + data-migration tool

**Milestone:** M5  ·  **Plan ref:** issue 19
**Depends on:** 002, 008, 009, 010

## Context

Before cutover QA (issue 016) can run with real data, the existing Visalia CRC data (JSON files from the Synology Docker deployment) must be imported into Supabase as workspace-scoped rows. `collab-v1` has JSON→Postgres importers in `migrations/` (`import_projects.py`, `import_settings.py`, `import_songs.py`, etc.) — these survive the schema-source-of-truth decision but must be adapted to write into the new multi-tenant schema (add `workspace_id`, use `db.admin_transaction()`, skip collab-v1 `users`/`sessions` tables). The tool must be non-destructive: dry-run first, write a backup, verify row counts before committing.

## Acceptance criteria

- [ ] `migrations/seed_workspace.py` (new or adapted) is a CLI script (runs with `python3 migrations/seed_workspace.py --workspace-name "Visalia CRC" --data-dir ./data [--dry-run]`) that:
  - In `--dry-run` mode: reads the source JSON files, prints what would be inserted (counts per table), and exits without writing anything.
  - In live mode: creates a backup of each source JSON file to `./data/backups/<timestamp>/`, then inserts rows into `workspaces`, `workspace_members`, `projects`, `project_revisions`, `workspace_settings`, `announcements`, `songs`, `templates`, `fonts` — all using `db.admin_transaction()` (service_role).
  - Is idempotent: re-running with the same source data does not create duplicate rows (use `ON CONFLICT DO NOTHING` or existence checks).
- [ ] Row count verification: after insertion, the script queries Supabase and prints a comparison of source-JSON counts vs. inserted counts for each table; exits with a non-zero code if counts differ.
- [ ] Base64 image migration: calls `migrate_base64_images_for_project()` from issue 009 for each project that has a base64 cover/logo.
- [ ] Font migration: calls `migrate_local_fonts_for_workspace()` from issue 010 for each workspace.
- [ ] `MANUAL-STEPS.md` documents the exact command sequence: (1) export JSON from Synology, (2) dry-run, (3) inspect output, (4) live run, (5) verify counts, (6) add allowed domain to `workspace_settings` for first-login.
- [ ] `python3 -c "import migrations.seed_workspace"` succeeds.
- [ ] `pytest tests/test_import_projects.py tests/test_import_settings.py tests/test_import_songs.py tests/test_import_announcements.py tests/test_import_fonts.py tests/test_import_templates.py -v` — all existing importer tests pass (they verify the import logic; the script wires them together).

## Likely files

- `migrations/seed_workspace.py` (new)
- `migrations/import_projects.py` (modify — add workspace_id param, use db.admin_transaction)
- `migrations/import_settings.py` (modify — same)
- `migrations/import_songs.py` (modify — same)
- `migrations/import_announcements.py` (modify — same)
- `migrations/import_fonts.py` (modify — same)
- `migrations/import_templates.py` (modify — same)
- `MANUAL-STEPS.md` (modify — migration runbook)
- `tests/test_import_projects.py` (modify if constructor signature changes)
- (similar for other importer tests)

## Tests / validation

```bash
python3 -c "import migrations.seed_workspace"

# Dry-run test (no DB needed — reads local JSON fixtures):
python3 migrations/seed_workspace.py --data-dir tests/fixtures/data --dry-run

# With DATABASE_URL (staging):
DATABASE_URL=<staging> SUPABASE_SERVICE_ROLE_URL=<service_role_url> \
  python3 migrations/seed_workspace.py \
  --workspace-name "Test Church" \
  --data-dir tests/fixtures/data \
  --dry-run
# → prints expected counts, no rows inserted.

# Existing importer unit tests:
pytest tests/test_import_*.py -v
```

Manual smoke (against staging, using real Synology data export):
1. Export data from Synology to `./data/`.
2. Run `--dry-run` — inspect counts.
3. Run live — confirm backup written to `./data/backups/<timestamp>/`.
4. Verify row counts in Supabase dashboard match source JSON counts.

## Data-safety / out of scope

- The backup step is mandatory (non-negotiable per AGENTS.md data-safety rules) and must run before any live insertion.
- `service_role` credentials are used only in this admin script; they must not be committed or logged.
- Never delete source JSON files as part of this script — they are the rollback source if migration fails.
- Out of scope: multi-workspace migration in one run — v1 seeds one workspace at a time.
- Out of scope: incremental sync after initial migration — that is a post-cutover operational concern.
