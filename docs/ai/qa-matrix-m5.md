# M5 End-to-End Multitenant QA Matrix

_Created: 2026-06-03 (issue 016)_

> **Note on environment:** The staging Supabase project IS the production project. All
> automated tests run against it (guarded by `DATABASE_URL`). Manual items are
> performed in the same project. No separate staging environment exists; treat every
> test as a production-readiness gate.

---

## How to use this matrix

- **Automated** items run via `pytest` or `ai-workflow checks`. Mark pass/fail after the
  run and record the date.
- **Manual** items require a human with live credentials. Perform them in a single
  cutover-readiness session and initial the checkbox.
- A cross-tenant **read or write leak in any Security surface item is a hard blocker**.
  Do not cut over until all Security items are green.
- Collaboration and Electron items are regression-blockers; if any fail, file a follow-up
  issue before merging.

---

## Security surface

| # | Item | Type | Command / steps | Pass criteria | Status |
|---|------|------|----------------|---------------|--------|
| S1 | Cross-tenant read isolation | Automated | `APP_MODE=server .venv/bin/pytest tests/test_rls_isolation.py::TestRLSIsolation::test_cross_tenant_select_blocked -v` | 7 parametrized cases pass (one per workspace-scoped table); 0 rows returned across all | [ ] |
| S2 | Cross-tenant write isolation | Automated | `APP_MODE=server .venv/bin/pytest tests/test_rls_isolation.py::TestRLSIsolation::test_cross_tenant_insert_blocked -v` | 7 parametrized cases pass; every INSERT raises `InsufficientPrivilege` | [ ] |
| S3 | Unauthenticated requests → 401 | Automated | `APP_MODE=server .venv/bin/pytest tests/test_auth_middleware.py::TestRequireAuth::test_no_token_returns_401 tests/test_auth_middleware.py::TestRequireAuth::test_invalid_or_expired_token_returns_401 -v` | Both tests pass; `_send_json` called with status 401 | [ ] |
| S4 | Valid JWT, no workspace membership → 403 | Automated | `APP_MODE=server .venv/bin/pytest tests/test_auth_middleware.py::TestRequireAuth::test_valid_token_without_membership_returns_403 -v` | Test passes; `_send_json` called with status 403 | [ ] |
| S5 | Within-workspace SELECT is visible | Automated | `APP_MODE=server .venv/bin/pytest tests/test_rls_isolation.py::TestRLSIsolation::test_within_workspace_select_visible -v` | 7 parametrized cases pass; each table returns >= 1 row for owner | [ ] |
| S6 | First-login domain provisioning | Manual | Sign in to the app with a `@visaliacrc.com` Google account that has no prior `workspace_members` row. Observe auto-provisioning. | User lands in the app with the Visalia CRC workspace loaded; no 403 page shown; `workspace_members` row appears in Supabase dashboard | [ ] |

**Full automated security suite (shortcut):**
```bash
set -a; source .env; set +a
APP_MODE=server .venv/bin/pytest tests/test_rls_isolation.py tests/test_auth_middleware.py -v
```
All tests must pass (currently: 3x7 + 1 RLS class + 6 auth_middleware + 3 first-login = ~33 tests when DATABASE_URL is set).

---

## Collaboration surface

| # | Item | Type | Steps | Pass criteria | Status |
|---|------|------|-------|---------------|--------|
| C1 | Two users, same workspace project — conflict detection | Manual | 1. Open the same project in two browser tabs as two different workspace members. 2. Edit project in tab A, save. 3. Edit project in tab B (without reloading), save. | Tab B shows the 409 conflict banner ("Another editor saved...") with diff and "Reload latest" link | [ ] |
| C2 | Stale-check banner appears within 30 s | Manual | 1. Open the project in tab A and tab B. 2. Save in tab A. 3. Wait up to 30 s without touching tab B. | Tab B shows the stale banner within 30 s of tab A's save (driven by the 30 s poll hitting `/api/projects/revisions`) | [ ] |
| C3 | Revision history preserved across saves | Manual | 1. Save the same project 3 times with distinct edits. 2. In the Supabase dashboard, query `project_revisions` for that project_id. | At least 3 revision rows exist with distinct `revision_number` values; `state` column reflects each edit | [ ] |

---

## Electron surface

| # | Item | Type | Steps | Pass criteria | Status |
|---|------|------|-------|---------------|--------|
| E1 | `npm run start:electron` -- server starts, window opens | Manual (dev smoke) | `npm run start:electron` in the repo root | Terminal shows `[server] Serving on port 8765`; BrowserWindow opens to the app; tray icon appears; right-click tray shows "Open Bulletin Generator" and "Quit" | [ ] |
| E2 | Google OAuth completes in Electron app | Manual | From the Electron app's login screen, click "Sign in with Google". Complete consent in the system browser. | Deep link `bulletingen://auth-callback` fires; app receives the PKCE code; user is logged in and sees the workspace UI (requires `bulletingen://auth-callback` added to Supabase redirect allow-list -- see `MANUAL-STEPS.md`) | [ ] |
| E3 | PDF export via Electron printToPDF | Manual | With a project open in Electron, click "Export PDF". | PDF file is saved locally; pagination, page breaks, footers, cover, and any QR codes are visually correct (matches browser-based export) | [ ] |
| E4 | Auto-update: bump version + push tag -> update detected | Manual -- deferred to first release | Tag a new version, push. Wait for the GitHub release CI to complete. Open the old packaged app. | Auto-updater dialog appears offering the new version; install + restart completes cleanly | DEFERRED |

> **E2 prerequisite:** Add `bulletingen://auth-callback` to the Supabase project's
> Auth -> URL Configuration -> Redirect URLs list before running this item. See
> `MANUAL-STEPS.md` -- "Electron Auth Deep-Link Setup (Issue 013)" section.

---

## Data migration

| # | Item | Type | Command / steps | Pass criteria | Status |
|---|------|------|----------------|---------------|--------|
| D1 | `scripts/migrate_to_supabase.py --dry-run` exits 0 | Automated / Manual | `python scripts/migrate_to_supabase.py --source /Volumes/docker/bulletingenerator` (default is dry-run) | Script exits 0; output shows row counts to be inserted with no errors; no DB writes | [ ] |
| D2 | Post-execute row counts match source JSON | Manual | After `--execute`: run row-count queries in Supabase dashboard against `projects`, `announcements`, `songs` | Counts match the dry-run output; spot-check 2-3 project names and announcement titles in the Supabase table viewer | [ ] |

**D1 automated check command** (usable without a live source mount):
```bash
python scripts/migrate_to_supabase.py --dry-run 2>&1; echo "exit: $?"
```

---

## Full-suite automated run (pre-cutover gate)

Run this block before the cutover session. Every line must exit 0.

```bash
set -a; source .env; set +a

# 1. Non-DB suite (always runs)
.venv/bin/python scripts/run_ai_workflow.py checks --level pr

# 2. DB integration suite (requires DATABASE_URL)
APP_MODE=server .venv/bin/pytest \
  tests/test_migrations.py \
  tests/test_rls_isolation.py \
  tests/test_db.py \
  tests/test_auth_middleware.py \
  -m integration \
  -q

# 3. Migration dry-run
python scripts/migrate_to_supabase.py \
  --source /Volumes/docker/bulletingenerator
```

---

## Cutover readiness checklist

Before switching production traffic to the Supabase backend, all items below must be checked:

- [ ] All Security surface items (S1-S6) green
- [ ] All Collaboration surface items (C1-C3) green
- [ ] Electron items E1-E3 green (E4 deferred)
- [ ] Data migration D1 green; D2 completed on a rehearsal run
- [ ] `npm install` run and `package-lock.json` committed (electron-updater in lock file)
- [ ] `bulletingen://auth-callback` added to Supabase redirect allow-list
- [ ] PKCE confirmed active in Supabase Auth dashboard
- [ ] `APPLE_TEAM_ID`, `CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_APP_SPECIFIC_PASSWORD` GitHub Secrets set
- [ ] `npm audit` reviewed; no new critical issues in runtime dependencies
- [ ] Supabase project URL and anon key in `.env` / GitHub Secrets match the production project

---

_Items marked DEFERRED are not blocking for the initial M5 cutover. They should be
completed before the first public release tag._
