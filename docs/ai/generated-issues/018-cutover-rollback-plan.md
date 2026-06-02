# 018: Cutover + rollback plan

**Milestone:** M5  ·  **Plan ref:** issue 22
**Depends on:** 016, 017

## Context

The current production deployment is the Synology/Docker stack writing to JSON files. The new Supabase-backed stack has been validated in staging (issues 001–016). This issue executes the production cutover: export from Synology → import to Supabase production project → switch users → document rollback path. The cutover is non-destructive (parallel-run first; JSON data preserved until confirmed stable).

## Acceptance criteria

- [ ] A Supabase **production** project is provisioned (separate from the staging project `dgydekhfzrmeoscpgmvo`). All migrations applied. GitHub Secrets updated to production values.
- [ ] The data export + import sequence is rehearsed on staging first:
  - Export JSON from Synology (`projects.json`, `settings.json`, `announcements.json`, `song_database.json`).
  - Run `migrations/seed_workspace.py --dry-run` against the production Supabase project — confirm expected row counts.
  - Run live migration — confirm row counts match source.
  - Spot-check 3 projects in the Supabase dashboard (name, state content, revision).
- [ ] Users switch to the new Electron desktop client or browser URL (pointing at the new stack). The existing Synology Docker container remains running (read-only, no new writes) for 1 week as a fallback.
- [ ] Rollback procedure is documented: if any critical issue is found in production within 1 week, users are directed back to the Synology URL; the JSON files on Synology have not been modified.
- [ ] After 1 week of stable operation: the Synology Docker container is stopped (not deleted); the JSON backup files are archived to cold storage. Document the archiving step.
- [ ] `MANUAL-STEPS.md` contains the complete cutover checklist, including: pre-cutover verification, DNS/URL switch, user notification template, rollback trigger conditions, and post-cutover archival.
- [ ] `docs/ai/project-state.md` updated to reflect cutover complete (or in-progress with date).

## Likely files

- `MANUAL-STEPS.md` (modify — production cutover checklist)
- `docs/ai/project-state.md` (update)
- `.github/secrets` (production DATABASE_URL + SUPABASE_* — documented in MANUAL-STEPS, not committed)
- Supabase dashboard: new production project (manual step)

## Tests / validation

Pre-cutover automated checks:
```bash
# Confirm staging integration tests green:
DATABASE_URL=<staging> pytest tests/test_rls_isolation.py tests/test_db.py -v

# Confirm full test suite green:
pytest -v
npm test
```

Manual cutover validation (human, against production):
1. Dry-run migration → inspect counts match source JSON.
2. Live migration → row counts verified.
3. One user completes a full flow: login, PCO import, edit, save, PDF export, logout.
4. A second user in the same workspace: opens the same project, sees the edit, conflict UX fires on concurrent save.
5. Synology container still running (parallel-run confirmed).
6. After 1 week: no critical issues → stop Synology container, archive JSON backups.

## Data-safety / out of scope

- The Synology JSON files must NOT be deleted until after the 1-week parallel-run period and explicit confirmation from the user.
- The production `service_role` key must never be committed — it exists only in the production environment and the operator's secure notes.
- Out of scope: multi-region Supabase setup — single-region (us-west-1 matching staging) is v1.
- Out of scope: Synology NAS decommission — that is an infrastructure decision after stable operation, not part of this issue.
