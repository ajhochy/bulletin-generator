# Bulletin Generator — Cutover and Rollback Plan

_Last updated: 2026-06-03 (issue 018)_

This document is the operator checklist for cutting over production users from
the Synology/Docker JSON-file deployment to the new Supabase-backed Electron
app. It is written for the single operator (ajhochy) and covers pre-cutover
verification, the cutover sequence, rollback conditions, rollback procedure,
and post-cutover archival.

**Key context:** The staging Supabase project (`dgydekhfzrmeoscpgmvo`) is the
production project — there is no separate production project to provision.
Cutover means: merge `feat/supabase-multitenant-electron` to `main`, build and
distribute the Electron `.dmg`, run the data migration from Synology JSON files,
and verify in Supabase.

---

## 1. Pre-Cutover Checklist

Complete every item before proceeding to Section 2.

### 1.1 Supabase project health

- [ ] All schema migrations are applied to `dgydekhfzrmeoscpgmvo`. Confirm
      in Supabase Dashboard → SQL Editor:

      ```sql
      SELECT name, executed_at
      FROM supabase_migrations.schema_migrations
      ORDER BY name;
      ```

      Expected migrations (in order):
      - `20260602000001_tenancy_foundation.sql`
      - `20260602000002_data_tables.sql`
      - Any later migrations added after issue 019

- [ ] RLS is enabled on all data tables. Confirm:

      ```sql
      SELECT tablename, rowsecurity
      FROM pg_tables
      WHERE schemaname = 'public'
        AND tablename IN (
          'projects','project_revisions','announcements',
          'songs','workspace_settings','user_settings','fonts'
        );
      ```

      All rows must show `rowsecurity = true`.

- [ ] The Visalia CRC workspace row exists:

      ```sql
      SELECT id, name, slug
      FROM workspaces
      WHERE id = '614505d2-0f12-4c00-afb1-9077a0dc94fe';
      ```

### 1.2 GitHub Secrets

Confirm the following secrets are set in the repo
(Settings → Secrets → Actions):

| Secret | Source |
|--------|--------|
| `SUPABASE_URL` | Supabase Dashboard → Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | Supabase Dashboard → Settings → API → `anon` key |
| `SUPABASE_JWT_SECRET` | Supabase Dashboard → Settings → API → JWT Secret |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Dashboard → Settings → API → `service_role` key |
| `DATABASE_URL` | Supabase session-pooler URL with `authenticated` role creds |
| `SUPABASE_SERVICE_ROLE_URL` | Supabase session-pooler URL with `service_role` creds |

No secret value is ever committed to the repo. Verify the CI build passes with
these secrets before tagging a release.

### 1.3 Electron build downloadable from GitHub Releases

- [ ] The CI pipeline on `main` (after merge) produces a signed `.dmg`.
- [ ] The `.dmg` is attached to the GitHub Release for the target tag.
- [ ] Download and open the `.dmg` on a clean Mac to confirm it mounts and
      the app launches.
- [ ] Verify the build version string in the app's About dialog matches
      the release tag.

### 1.4 Data migration dry-run

Run the dry-run **before** the cutover to confirm the source data parses
cleanly. From the repo root:

```bash
set -a && source .env && set +a

.venv/bin/python scripts/migrate_to_supabase.py \
  --source /Volumes/docker/bulletingenerator \
  --dry-run
```

Expected output includes row counts:
- `projects`: the number of project objects in `projects.json`
- `project_revisions`: same count (one initial revision per project)
- `announcements`: the number of objects in `announcements.json`
- `songs`: the number of objects in `song_database.json`
- `workspace_settings`: 1 row

If the output shows **parse errors**, fix the source data or the parser
before proceeding to `--execute`. A dry-run exit code of 0 means no errors.

### 1.5 Pre-cutover backup

The JSON files on the Synology NAS are the rollback source.
Before executing the migration, snapshot them:

```bash
# SSH to Synology
ssh <synology-host>

# Create a timestamped archive (adjust path to your data directory)
tar czf /volume1/backups/bulletingenerator-precutover-$(date +%Y%m%d_%H%M%S).tar.gz \
  /Volumes/docker/bulletingenerator/projects.json \
  /Volumes/docker/bulletingenerator/announcements.json \
  /Volumes/docker/bulletingenerator/song_database.json \
  /Volumes/docker/bulletingenerator/settings.json
```

An existing backup is already available at:
`/Volumes/docker/bulletingenerator/backups/bulletin-20260512-2115/`

Contents: `announcements.json`, `migrations.json`, `projects.json`,
`settings.json`, `song_database.json`.

---

## 2. Cutover Steps

Execute in order. Do not skip steps.

### Step 1 — Merge the feature branch to main

```bash
# Final PR review: confirm all CI checks green on feat/supabase-multitenant-electron
gh pr view --web   # review in GitHub

# Merge (manual — do not auto-merge)
# Use GitHub "Merge pull request" button to preserve PR reference in history
```

### Step 2 — Tag the release

```bash
# After merge, from main:
git pull origin main
git tag v<NEXT_VERSION> -m "Supabase multitenant Electron release"
git push origin v<NEXT_VERSION>
```

The tag push triggers the CI release workflow, which builds the signed
`.dmg` and attaches it to the GitHub Release.

### Step 3 — Verify CI release build succeeds

In GitHub → Actions → release workflow: confirm the `.dmg` artifact is
attached to the release for `v<NEXT_VERSION>`.

### Step 4 — Distribute the Electron .dmg to users

Download the `.dmg` from the GitHub Release page. Distribute to each
Visalia CRC user via the usual channel (shared link, email, etc.).

Install instructions for users:
1. Download `BulletinGenerator-<version>.dmg` from the release link.
2. Open the `.dmg` and drag the app to Applications.
3. Launch the app — it will prompt for Google sign-in or magic-link.
4. Sign in with your `@visaliacrc.com` Google account.

### Step 5 — Execute the data migration

This step writes the Synology JSON data into Supabase. It is idempotent —
re-running is safe.

```bash
# From the repo root (main branch, after merge):
set -a && source .env && set +a

.venv/bin/python scripts/migrate_to_supabase.py \
  --source /Volumes/docker/bulletingenerator \
  --execute
```

The script uses `ON CONFLICT DO NOTHING` for `projects`, `announcements`,
and `songs`. The `workspace_settings` row is merged (not replaced).
OAuth tokens (`pcoAccessToken`, `googleAccessToken`, etc.) are excluded
from the migration — users must reconnect PCO and Google Calendar after
cutover.

### Step 6 — Verify row counts in Supabase

Open Supabase Dashboard → `bulletin-generator` → Table Editor. Confirm:

| Table | Expected row count |
|-------|--------------------|
| `projects` | Matches count from dry-run |
| `project_revisions` | Same count as `projects` (one initial revision each) |
| `announcements` | Matches count from dry-run |
| `songs` | Matches count from dry-run |
| `workspace_settings` | 1 row for workspace `614505d2-0f12-4c00-afb1-9077a0dc94fe` |

Also spot-check 3 projects:
- Verify `name` is correct.
- Open the `state` JSONB column for one project — confirm it contains
  recognizable content (items list, church name).
- Confirm `workspace_id = '614505d2-0f12-4c00-afb1-9077a0dc94fe'`.

Alternatively, run the SQL row-count query:

```sql
SELECT
  (SELECT count(*) FROM projects)           AS projects,
  (SELECT count(*) FROM project_revisions)  AS revisions,
  (SELECT count(*) FROM announcements)      AS announcements,
  (SELECT count(*) FROM songs)              AS songs,
  (SELECT count(*) FROM workspace_settings) AS workspace_settings;
```

### Step 7 — One end-to-end smoke per user

Each user:
1. Opens the new Electron app.
2. Signs in with their `@visaliacrc.com` Google account.
3. Loads a bulletin project (confirms migrated data is visible).
4. Makes a small edit and saves (confirms writes work under RLS).
5. Exports a PDF (confirms printToPDF pipeline is functional).

The Synology Docker container remains running during this period
(parallel-run). Users should not make production edits in the old app
during cutover smoke — changes made to the old app will not be reflected
in Supabase.

### Step 8 — Mark cutover complete

After all users have successfully smoke-tested the new app, update
`docs/ai/project-state.md` to record the cutover date and status.

---

## 3. Rollback Trigger Conditions

Roll back to the Synology Docker setup if any of the following occur
within 7 days of cutover:

| Condition | Severity |
|-----------|----------|
| User authentication fails for any `@visaliacrc.com` user | Critical — immediate rollback |
| Migrated projects are missing or corrupted in the new app | Critical — immediate rollback |
| PDF export produces blank or malformed output for any user | Critical — immediate rollback |
| Supabase service outage lasting more than 2 hours during Sunday morning | Critical — immediate rollback |
| Data written in the new app is not persisted after restart | Critical — immediate rollback |
| Any cross-workspace data leak (user A sees user B's private projects) | Critical — immediate rollback + security review |
| PCO import or Google Calendar fetch fails for all users | High — triage first; rollback if unresolvable in 24 hours |
| Intermittent save errors (non-data-loss) | Medium — triage; rollback optional if workaround exists |

**Do not rollback for:**
- PCO / Google Calendar token expiry (users must reconnect OAuth — expected post-migration)
- Cosmetic UI differences

---

## 4. Rollback Procedure

The Synology Docker container remains running during the 7-day parallel period.
To roll back, direct users back to the Synology URL and stop writing to Supabase.

### 4.1 Notify users immediately

Send users the old Synology app URL and tell them to stop using the new
Electron app until further notice. Their data is safe — the Synology JSON
files have not been modified.

### 4.2 Stop writes to Supabase

If the new Electron app is still running on users' machines, it will
continue to write to Supabase. To prevent further writes:
- Direct users to quit the Electron app.
- Do NOT delete data from Supabase — preserve for post-incident diagnosis.

### 4.3 Restore from JSON backup (if Synology data was accidentally modified)

The backup at `/Volumes/docker/bulletingenerator/backups/bulletin-20260512-2115/`
contains the pre-cutover snapshot. Restore with:

```bash
# On Synology — SSH in
cp /Volumes/docker/bulletingenerator/backups/bulletin-20260512-2115/projects.json \
   /Volumes/docker/bulletingenerator/projects.json

cp /Volumes/docker/bulletingenerator/backups/bulletin-20260512-2115/announcements.json \
   /Volumes/docker/bulletingenerator/announcements.json

cp /Volumes/docker/bulletingenerator/backups/bulletin-20260512-2115/settings.json \
   /Volumes/docker/bulletingenerator/settings.json

cp /Volumes/docker/bulletingenerator/backups/bulletin-20260512-2115/song_database.json \
   /Volumes/docker/bulletingenerator/song_database.json
```

### 4.4 Restart the Synology Docker container (if it was stopped)

```bash
# On Synology — in the bulletingenerator project directory
docker compose up -d

# Verify health
curl http://<synology-ip>:<port>/api/health
```

Or use Synology Container Manager to start the container manually.

### 4.5 Verify rollback

- Open the old app URL in a browser.
- Confirm a project loads with current content.
- Confirm the "Projects" list shows all expected projects.

### 4.6 Post-rollback

- File a GitHub issue describing what failed.
- Do NOT delete the Supabase data — preserve for diagnosis.
- The feature branch `feat/supabase-multitenant-electron` remains intact
  on GitHub for the fix.

---

## 5. Post-Cutover Archival (after 7 days stable)

After 7 days of stable operation with no rollback triggers:

### 5.1 Stop the Synology Docker container

```bash
# On Synology
docker compose down
```

Do NOT delete the container, the image, or the data directory yet.

### 5.2 Archive the JSON data to cold storage

```bash
# On Synology — create a final archive
tar czf /volume1/backups/bulletingenerator-final-archive-$(date +%Y%m%d).tar.gz \
  /Volumes/docker/bulletingenerator/projects.json \
  /Volumes/docker/bulletingenerator/announcements.json \
  /Volumes/docker/bulletingenerator/song_database.json \
  /Volumes/docker/bulletingenerator/settings.json \
  /Volumes/docker/bulletingenerator/backups/
```

Move or copy the archive to long-term cold storage (e.g. Synology Hyper Backup
or an external drive). Keep it for at least 6 months.

### 5.3 Mark the Synology Docker deployment as deprecated

In the repo:
- Add a `DEPRECATED` notice to `docker-compose.yml` (top-of-file comment).
- Update `docs/ARCHITECTURE.md` to note that the Docker/JSON deployment is
  deprecated as of the cutover date.
- Update `docs/ai/project-state.md` to record archival complete.

The `docker-compose.yml` file is NOT deleted from the repo — it remains as
a reference for rollback and historical documentation. The Docker images on
GHCR (used by Watchtower) are also left in place.

### 5.4 Notify users

Send users a brief note that the old Synology URL is offline, the new
Electron app is the sole production path, and any bookmarks to the old URL
should be removed.

---

## 6. Reference

| Item | Value |
|------|-------|
| Supabase project | `dgydekhfzrmeoscpgmvo` (`https://dgydekhfzrmeoscpgmvo.supabase.co`) |
| Visalia CRC workspace ID | `614505d2-0f12-4c00-afb1-9077a0dc94fe` |
| Source data (NAS) | `/Volumes/docker/bulletingenerator/` |
| Existing backup | `/Volumes/docker/bulletingenerator/backups/bulletin-20260512-2115/` |
| Migration script | `scripts/migrate_to_supabase.py` |
| Data restore script | `scripts/restore.sh` |
| Auth providers MANUAL-STEPS | `MANUAL-STEPS.md` — Supabase Auth Provider Setup section |
| Pre-cutover parallel period | 7 days |
