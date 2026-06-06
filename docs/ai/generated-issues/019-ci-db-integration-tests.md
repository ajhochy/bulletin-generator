# 019: Wire CI to run DB-integration and RLS isolation tests

**Milestone:** CI  ·  **Plan ref:** new (from today's GitHub secrets work)
**Depends on:** 002, 003

## Context

Two DB-dependent tests in `tests/test_migrations.py::TestIntegration` (`test_fresh_db_creates_all_tables`, `test_second_run_is_idempotent`) have been skipping in CI because `DATABASE_URL` is not set. GitHub Secrets `DATABASE_URL`, `SUPABASE_DATABASE_PW`, `SUPABASE_URL`, and `SUPABASE_ANON_KEY` were added to the repo this session. This issue wires them into `ci.yml` so the DB-integration and RLS isolation tests (from issue 002) run on every PR against `feat/supabase-multitenant-electron` (and on merge to main/the integration branch).

## Acceptance criteria

- [ ] `.github/workflows/ci.yml` has a job step (or a separate job) that sets `DATABASE_URL` from `${{ secrets.DATABASE_URL }}` and runs:
  ```
  pytest tests/test_migrations.py::TestIntegration tests/test_db.py tests/test_rls_isolation.py -v
  ```
  (The `test_rls_isolation.py` and `test_db.py` files exist after issues 002 and 003; this CI issue just wires them. Use `if: github.repository == 'ajhochy/bulletin-generator'` or equivalent to prevent forks from failing on missing secrets.)
- [ ] The existing non-DB pytest job (which covers the 939 passing unit tests) continues to run without `DATABASE_URL` and without DB-dependent tests.
- [ ] The DB-integration job runs after (or in parallel with) the unit test job and is gated: the PR merge button is blocked if either job fails.
- [ ] The `SUPABASE_JWT_SECRET` secret (added in issue 006) is also available to the DB-integration job for auth middleware tests.
- [ ] No secrets are echoed to CI logs (use `${{ secrets.X }}` only, never `echo $DATABASE_URL`).
- [ ] A passing CI run on a PR (with all four secrets set) shows `TestIntegration::test_fresh_db_creates_all_tables` and `TestIntegration::test_second_run_is_idempotent` as PASSED (not skipped).
- [ ] `MANUAL-STEPS.md` documents the required GitHub Secrets for CI (names and where to find the values) — especially important for forks or a future repo transfer.

## Likely files

- `.github/workflows/ci.yml` (modify — add DB-integration job step + secrets injection)
- `MANUAL-STEPS.md` (modify — document required GitHub Secrets for CI)

## Tests / validation

```bash
# Local pre-check (confirm tests skip cleanly without DB):
unset DATABASE_URL
pytest tests/test_migrations.py::TestIntegration tests/test_db.py -v
# → SKIPPED

# With DATABASE_URL:
DATABASE_URL=<staging> pytest tests/test_migrations.py::TestIntegration tests/test_db.py -v
# → PASSED
```

CI validation: open a PR against the integration branch, confirm both the unit-test job and the DB-integration job pass in the GitHub Actions tab. Confirm the DB-integration job shows the integration tests as PASSED (not skipped).

## Data-safety / out of scope

- `DATABASE_URL` in GitHub Secrets points to the **staging** Supabase project — never the production project.
- Secrets must not be printed or logged; the `--tb=short` pytest flag is safe (it does not print env vars).
- Out of scope: parallel CI matrix across multiple Supabase regions — single staging project is sufficient.
- Out of scope: performance benchmarks or load tests in CI — correctness only.
