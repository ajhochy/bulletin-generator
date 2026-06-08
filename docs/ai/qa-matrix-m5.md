# M5 End-to-End Multitenant QA Matrix

_Created: 2026-06-03 (issue 016)_
_Updated: 2026-06-06 (issue #272 M5 cutover QA — smoke-test-writer pass)_

> **Note on environment:** The staging Supabase project IS the production project. All
> automated tests run against it (guarded by `DATABASE_URL`). Manual items are
> performed in the same project. No separate staging environment exists; treat every
> test as a production-readiness gate.

---

## How to use this matrix

- **Automated** items run via `pytest` or `npx playwright test`. Mark pass/fail after the
  run and record the date.
- **Manual** items require a human with live credentials. Perform them in a single
  cutover-readiness session and initial the checkbox.
- A cross-tenant **read or write leak in any Security surface item is a hard blocker**.
  Do not cut over until all Security items are green.
- Ownership model and Electron items are regression-blockers; if any fail, file a follow-up
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
| S7 | Cross-tenant isolation (e2e API+UI) | **Automated (E2E)** | `E2E_PYTHON=.venv/bin/python npx playwright test --project=core -g "Cross-tenant isolation"` | Workspace-B user sees 0 projects in Files list; `/api/projects` returns empty array for B; A's project name absent — **BLOCKER** | [x] PASS 2026-06-06 |

**Full automated security suite (shortcut):**
```bash
set -a; source .env; set +a
APP_MODE=server .venv/bin/pytest tests/test_rls_isolation.py tests/test_auth_middleware.py -v
```
All tests must pass (currently: 3x7 + 1 RLS class + 6 auth_middleware + 3 first-login = ~33 tests when DATABASE_URL is set).

---

## Ownership model surface

> **Note:** Conflict detection (409 on stale `_clientRevision`) was removed in issue 021.
> Items C1-C3 previously covered conflict detection; they have been replaced with
> ownership model checks reflecting the owner-only write policy (issues 020-021).

| # | Item | Type | Steps | Pass criteria | Status |
|---|------|------|-------|---------------|--------|
| C1 | Owner can save their own project | Manual | 1. Sign in as `ajh@visaliacrc.com`. 2. Open any project. 3. Make an edit and save. | Save succeeds (HTTP 200); project state persists on reload | [ ] |
| C2 | Non-owner sees read-only indication | **Automated (E2E)** | `E2E_PYTHON=.venv/bin/python npx playwright test --project=core -g "Ownership model and transfer"` | Read-only banner visible; `#readonly-banner` contains "changes won't save" | [x] PASS 2026-06-06 |
| C3 | Transfer ownership works | **Automated (E2E)** | `E2E_PYTHON=.venv/bin/python npx playwright test --project=core -g "Ownership model and transfer"` | `POST /api/projects/{id}/transfer` returns 200; new owner saves OK; old owner gets 403 | [x] PASS 2026-06-06 |
| C4 | Presence badge appears for workspace viewers | **Automated (E2E)** | `E2E_PYTHON=.venv/bin/python npx playwright test --project=core -g "presence"` (see `server-mode-behaviors.spec.ts`) | `#presence-badge` visible to second member; confirmed present in server-mode-behaviors.spec.ts | [x] PASS (existing spec, confirmed) |
| C5 | Non-owner save → 403 (API) | **Automated (E2E)** | `E2E_PYTHON=.venv/bin/python npx playwright test --project=core -g "Ownership model and transfer"` | Direct POST as non-owner returns HTTP 403 | [x] PASS 2026-06-06 |
| C6 | Duplicate creates non-owner copy | **Automated (E2E)** | `E2E_PYTHON=.venv/bin/python npx playwright test --project=core -g "Ownership model and transfer"` | After click on `#readonly-duplicate-btn`, read-only banner hidden; new project id differs from original | [x] PASS 2026-06-06 |
| C7 | Revision history: N saves → N entries; restore works | **Automated (E2E)** | `E2E_PYTHON=.venv/bin/python npx playwright test --project=core -g "Revision history"` | `GET /api/projects/{id}/history` returns ≥3 entries after 3 saves; `POST .../restore` returns 200 with project | [x] PASS 2026-06-06 |

---

## E2E coverage map (automated, `@core`, server mode)

All specs are in `tests/e2e/features/`. Run with:
```bash
E2E_PYTHON=.venv/bin/python npx playwright test --project=core
```

| Spec file | What it verifies |
|-----------|-----------------|
| `flows/smoke.spec.ts` | App boots, authenticates, navigates all tabs, persists a project, exports PDF |
| `projects.spec.ts` | Create / list / open / select / delete projects |
| `server-mode-behaviors.spec.ts` | Read-only banner for non-owners; presence badge (existing) |
| `multitenant-isolation.spec.ts` | **NEW** Cross-tenant isolation (S7); ownership + 403 + duplicate + transfer (C2/C3/C5/C6); revision history (C7) |
| `editor-order-of-worship.spec.ts` | Item add/edit/reorder |
| `editor-sections.spec.ts` | Section heading create/delete |
| `format.spec.ts` | Per-type and per-item formatting |
| `announcements.spec.ts` | Announcement card CRUD |
| `song-database.spec.ts` | Song lookup and save |
| `settings-branding.spec.ts` | Branding settings round-trip |
| `templates.spec.ts` | Template selection and preview |
| `calendar.spec.ts` | Calendar events UI |
| `electron-mode-data-routing.spec.ts` | Electron renderer uses supabase-data.js (not server API) for project/song reads |

---

## Manual items (not automatable in server mode)

| # | Item | Why manual | Steps to verify | Pass criteria |
|---|------|-----------|----------------|---------------|
| M1 | PDF export visual fidelity | Requires human visual inspection of rendered PDF | Open any project with songs + announcements + cover. Click "Export PDF". | Pagination, page breaks, footers, cover, and any QR codes visually correct | [ ] |
| M2 | PCO import (live creds) | Requires real PCO OAuth tokens — out of e2e scope | Connect PCO. Click "Import from PCO". Select a real service plan. | Songs, sections, order of worship load correctly; notes/media items hidden | [ ] |
| M3 | Google Calendar fetch (live creds) | Requires real Google OAuth tokens | Connect Google Calendar. Fetch events for the current week. | Events filtered by Sun–Sat window; correct titles/times appear | [ ] |
| M4 | Image/font Storage isolation (direct URL) | Requires inspecting signed URL scope | Upload a logo as workspace A. Attempt to access the Storage URL as workspace B (without re-signing). | B cannot access A's storage objects without a fresh signed URL | [ ] |
| M5 | Electron auto-update across app restart | Requires packaged runtime + new release tag | Tag a new version; push. Open old packaged app. | Auto-updater dialog appears; install + restart completes cleanly | DEFERRED |
| M6 | Cross-tenant isolation in packaged Electron (renderer→Supabase) | Packaged runtime required; `electron-mode-data-routing.spec.ts` proves data routing in dev | Build the `.app` bundle; sign in as workspace A and B in two Electron windows | B cannot see A's projects or storage objects | [ ] |
| M7 | First-login domain provisioning (S6 above) | Requires a new `@visaliacrc.com` account with no prior membership row | Create a net-new Google account `@visaliacrc.com` and sign in | Auto-provisioned into workspace; no 403 page | [ ] |

---

## UNVERIFIED items (failing placeholder tests)

There are no placeholder failing tests required: every previously-manual item in the
ownership model is now automated (C2–C7). The remaining manual items (M1–M7) all have
clear "why manual" justifications:

- M1 (PDF): subjective visual; cannot be deterministic.
- M2 (PCO): requires real OAuth tokens; `pco-live.spec.ts` covers the connected state.
- M3 (Google Calendar): requires real OAuth tokens.
- M4 (Storage isolation): requires signed URL mechanics; DB-level covered by pytest.
- M5 (Electron auto-update): packaged-runtime gated.
- M6 (Packaged Electron cross-tenant): packaged-runtime gated.
- M7 (Domain provisioning): net-new account gated; non-automatable in current CI.

To make M4 deterministic: add a signed-URL scope assertion in the Supabase RLS policy
test suite (verify that storage policies restrict bucket access per workspace_id).

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

# 3. E2E core lane (requires .env.e2e with SUPABASE_* keys)
E2E_PYTHON=.venv/bin/python npx playwright test --project=core

# 4. Migration dry-run
python scripts/migrate_to_supabase.py \
  --source /Volumes/docker/bulletingenerator
```

---

## Cutover readiness sign-off (issue #272 M5)

### Verified by CI / automated e2e (2026-06-06)

| Item | Spec / command | Result |
|------|---------------|--------|
| **[BLOCKER] Cross-tenant API+UI isolation** | `multitenant-isolation.spec.ts` — "Cross-tenant isolation" | **PASS** |
| **[BLOCKER] Non-owner save → 403** | `multitenant-isolation.spec.ts` — "Ownership model and transfer" | **PASS** |
| Read-only banner for non-owners | `multitenant-isolation.spec.ts` + `server-mode-behaviors.spec.ts` | **PASS** |
| Duplicate to own copy | `multitenant-isolation.spec.ts` — "Ownership model and transfer" | **PASS** |
| Transfer ownership | `multitenant-isolation.spec.ts` — "Ownership model and transfer" | **PASS** |
| Presence badge (second member) | `server-mode-behaviors.spec.ts` — "presence" | **PASS** |
| Revision history (≥3 after 3 saves) | `multitenant-isolation.spec.ts` — "Revision history" | **PASS** |
| Restore to prior revision | `multitenant-isolation.spec.ts` — "Revision history" | **PASS** |

### Requires human sign-off before cutover

- [ ] All Security surface items S1–S6 green (pytest RLS + auth_middleware suite)
- [ ] All Electron items E1–E3 green (E4 deferred)
- [ ] Data migration D1 green; D2 completed on a rehearsal run
- [ ] Manual items M1–M7 as applicable (M4, M6, M7 are lower priority for initial cutover)
- [ ] `npm install` run and `package-lock.json` committed (electron-updater in lock file)
- [ ] `bulletingen://auth-callback` added to Supabase redirect allow-list
- [ ] PKCE confirmed active in Supabase Auth dashboard
- [ ] `APPLE_TEAM_ID`, `CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_APP_SPECIFIC_PASSWORD` GitHub Secrets set
- [ ] `npm audit` reviewed; no new critical issues in runtime dependencies
- [ ] Supabase project URL and anon key in `.env` / GitHub Secrets match the production project

---

_Items marked DEFERRED are not blocking for the initial M5 cutover. They should be
completed before the first public release tag._
