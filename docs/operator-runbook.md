# Bulletin Generator — Operator Runbook

This runbook covers every human-operator action required to deploy and verify
the Bulletin Generator in the Supabase multi-tenant + Electron configuration.
It supersedes the old Watchtower/Docker single-tenant setup for the desktop
distribution.

> **Staging = production.** The staging Supabase project
> `dgydekhfzrmeoscpgmvo` (`https://dgydekhfzrmeoscpgmvo.supabase.co`) is the
> production project for this deployment. There is no separate production
> project. Do not create one unless the user base grows beyond Supabase's free
> tier limits.

---

## Table of contents

1. [Supabase project setup from scratch](#1-supabase-project-setup-from-scratch)
2. [Electron build verification](#2-electron-build-verification)
3. [Docker server mode (browser deployments)](#3-docker-server-mode-browser-deployments)
4. [Environment variables reference](#4-environment-variables-reference)
5. [First-login provisioning — domain allow-list](#5-first-login-provisioning--domain-allow-list)
6. [Backup and restore](#6-backup-and-restore)

---

## 1. Supabase project setup from scratch

Use this section when deploying Bulletin Generator for a **new church** that
needs its own Supabase project. If you are working with the existing
`dgydekhfzrmeoscpgmvo` project, skip to [section 1.4](#14-apply-migrations).

### 1.1 Create the Supabase project

1. Log in at [supabase.com](https://supabase.com) and create a new project.
   - Note the **Project Ref** (e.g. `abcdefghijklmnopqrst`) — you will need it
     for `DATABASE_URL` and `SUPABASE_SERVICE_ROLE_URL`.
   - Choose a strong database password and store it in a password manager.
   - Select the region closest to your users.

2. In **Dashboard → Settings → API**, collect:
   - **Project URL** → `SUPABASE_URL`
   - **Anon / public key** → `SUPABASE_ANON_KEY`
   - **JWT Secret** (under "JWT Settings") → `SUPABASE_JWT_SECRET`
   - **service_role secret key** → `SUPABASE_SERVICE_ROLE_KEY`

3. In **Dashboard → Settings → Database → Connection string**, collect the
   direct (port 5432) Postgres URL → `DATABASE_URL`. Use the **session-mode**
   direct connection, not the transaction-mode pooler (port 6543).

### 1.2 Configure `.env`

Copy `.env.example` to `.env` and fill in the Supabase values:

```bash
cp .env.example .env
```

At minimum for Supabase connectivity:

```dotenv
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=<anon-or-publishable-key>
SUPABASE_JWT_SECRET=<jwt-secret>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

### 1.3 Configure Auth providers

#### URL Configuration

In **Dashboard → Authentication → URL Configuration**:

- Set **Site URL** to the primary app origin (e.g. `http://localhost:8766` for
  local smoke, or `https://bulletin.yourchurch.org` for production).
- Under **Redirect URLs**, add every callback URL the app will use:
  - `http://localhost:8766` (local dev / smoke)
  - `http://localhost:8766/auth/callback` (if a browser callback route is used)
  - `bulletingen://auth-callback` (Electron deep-link — required for auth to
    complete inside the desktop app)

#### Google OAuth

In **Google Cloud Console → APIs & Services → Credentials**:

1. Create (or select) an OAuth 2.0 Client ID of type **Web application**.
2. Authorized JavaScript origins:
   - `https://<ref>.supabase.co`
   - Your local smoke origin (e.g. `http://localhost:8766`)
3. Authorized redirect URI:
   - `https://<ref>.supabase.co/auth/v1/callback`
4. Copy the **Client ID** and **Client Secret**.

In **Dashboard → Authentication → Providers → Google**:

1. Enable Google.
2. Paste the Client ID and Client Secret.
3. Save.

Validation:
- Trigger a Google OAuth sign-in from the app.
- Confirm the user appears in **Authentication → Users**.

#### Email magic links

In **Dashboard → Authentication → Providers → Email**:

- Keep the Email provider enabled.
- Use magic-link (passwordless) sign-in.
- Leave the default one-hour OTP expiry unless requirements change.

Validation:
- Request a magic link for a test email address.
- Click the link from the email.
- Confirm a session is issued and the user appears in **Authentication → Users**.

#### Custom SMTP (required before multi-church testing)

Supabase's built-in mailer is rate-limited and restricted to project team
addresses. It is a staging fallback only.

Before broader testing, configure a transactional email provider (Resend, AWS
SES, Postmark, SendGrid, ZeptoMail, or Brevo) in **Dashboard → Authentication →
SMTP Settings**:

| Field | Example value |
|-------|--------------|
| SMTP host | `smtp.resend.com` |
| SMTP port | `587` |
| SMTP username | `resend` (varies by provider) |
| SMTP password | `<provider API key>` |
| Sender email | `no-reply@auth.yourchurch.org` |
| Sender name | `Bulletin Generator` |

Operational notes:
- Store SMTP credentials only in the Supabase dashboard or a secret manager.
- Configure SPF, DKIM, and DMARC for the sending domain.
- Custom SMTP is deferred in the current deployment; the staging project uses
  Supabase's built-in mailer for now (see [decisions.md](ai/decisions.md) —
  "Custom SMTP deferred").

#### Leaked-password protection

In **Dashboard → Authentication → Security / Password Security**:
- Enable leaked-password protection if the Supabase plan supports it.
- Google OAuth and magic links are the intended v1 login methods; password
  login is not enabled. This toggle is a belt-and-suspenders measure.

### 1.4 Apply migrations

From the repo root, with `.env` sourced:

```bash
set -a && source .env && set +a

# Apply all Supabase migrations in order:
APP_MODE=server .venv/bin/python -m db migrate
```

Alternatively, paste each SQL file from `supabase/migrations/` into
**Dashboard → SQL Editor** in filename order:

1. `20260602000001_tenancy_foundation.sql`
2. `20260602000002_data_tables.sql`
3. `20260603000001_storage_buckets.sql`

Verify in **Dashboard → Table Editor** that `workspaces`, `workspace_members`,
`projects`, `announcements`, `songs`, `workspace_settings`, etc. all exist.

### 1.5 Seed the first workspace and user

Run the workspace-seed script as `service_role` (bypasses RLS):

```bash
set -a && source .env && set +a
APP_MODE=server .venv/bin/python scripts/migrate_to_supabase.py \
  --source ./data \
  --workspace-name "My Church" \
  --workspace-domain "mychurch.org" \
  --dry-run
```

Review the dry-run output, then execute:

```bash
APP_MODE=server .venv/bin/python scripts/migrate_to_supabase.py \
  --source ./data \
  --workspace-name "My Church" \
  --workspace-domain "mychurch.org" \
  --execute
```

The script is idempotent (`ON CONFLICT DO NOTHING`). Re-running after a partial
failure is safe.

**What to verify after seeding:**

1. Open **Dashboard → Table Editor → workspaces** — confirm the workspace row.
2. Open `workspace_settings` — confirm the `allowed_domains` JSONB contains
   your domain.
3. Open `projects`, `announcements`, `songs` — confirm migrated row counts.

**Note:** OAuth tokens (`pcoAccessToken`, `pcoRefreshToken`, `googleAccessToken`,
`googleRefreshToken`) are excluded from the migration. They are secrets and must
be re-issued for the multi-tenant deployment.

---

## 2. Electron build verification

### 2.1 Prerequisites

- Node.js (LTS) installed.
- Python 3.11+ with `requirements.txt` installed in a `.venv` virtual
  environment.
- `.env` populated with Supabase values (see section 4).

```bash
# Install Node dependencies (first time only):
npm install

# Verify the electron binary is present:
./node_modules/.bin/electron --version   # expect v28.x
```

### 2.2 Start in dev mode

```bash
npm run start:electron
# Equivalent: ./node_modules/.bin/electron .
```

**What to expect:**

1. A terminal line `[server] Serving on port 8765` appears once `server.py` is
   up (within ~5 s).
2. A `BrowserWindow` (1280 x 900) opens pointing to `http://localhost:8765/`.
3. A tray icon appears in the macOS menu bar. Right-click shows
   "Open Bulletin Generator" and "Quit".
4. The login screen is displayed (Supabase Auth).

If the server fails to start within 20 s, an error dialog appears and the app
quits. Check that Python 3 is in PATH and that `.venv` dependencies are
installed.

### 2.3 Confirm server started

Open a browser (or DevTools in the Electron window) and verify:

```
GET http://localhost:8765/api/bootstrap
```

Expected: `200 OK` with a JSON body including `"appMode": "electron"`.

### 2.4 Confirm login works

1. On the login screen, click **Sign in with Google** (or enter an email for a
   magic link).
2. Complete the OAuth flow in the default browser. The `bulletingen://auth-callback`
   deep link should return focus to the Electron window.
3. Confirm the authenticated user's name appears in the nav bar.

If the deep-link redirect does not fire, verify that `bulletingen://auth-callback`
is in the Supabase redirect allow-list (see section 1.3).

### 2.5 Confirm graceful quit

Click "Quit" from the tray menu. Verify that:
- The BrowserWindow closes.
- The Python sidecar process exits (no zombie `python3` process).
- Electron exits cleanly (no crash report).

### 2.6 Packaged-mode path (future — issue 014)

When building the final `.app` bundle, the PyInstaller `server` binary will be
placed at `<app>.app/Contents/Resources/server`. `electron/main.js` already
probes for this path via `process.resourcesPath` — no main-process changes are
required for issue 014 to complete packaging.

---

## 3. Docker server mode (browser deployments)

Docker server mode still works for self-hosted browser deployments. It is the
right choice for churches that want a shared multi-user app in a browser without
installing a desktop client.

### 3.1 Start

```bash
cp .env.example .env   # fill in all values (see section 4)
docker compose up -d
```

The compose file starts the app container (port 8080). The old `postgres`
service has been removed from this branch; Supabase Postgres is the database.

### 3.2 Verify health

```bash
curl http://localhost:8080/api/bootstrap
```

Expected: `200 OK` with `"appMode": "server"`.

### 3.3 Data migration (existing JSON data)

If migrating from the previous JSON/Docker deployment:

```bash
set -a && source .env && set +a
APP_MODE=server .venv/bin/python scripts/migrate_to_supabase.py \
  --source /path/to/data \
  --dry-run
# Review, then:
APP_MODE=server .venv/bin/python scripts/migrate_to_supabase.py \
  --source /path/to/data \
  --execute
```

See `MANUAL-STEPS.md` for the full data migration walkthrough.

### 3.4 Auto-update — Watchtower/zip is deprecated for the Electron distribution

The Watchtower sidecar + GitHub zip download auto-update path is **deprecated**
for the Electron desktop distribution. Electron updates will be delivered via
`electron-updater` (issue 014).

Watchtower still works for the Docker server-mode container (it watches for new
GHCR image tags). The GHCR package must remain **public** — Watchtower has no
credentials; a private package causes silent 403 failures even with `Scanned=1`.

The `launcher.py` macOS menu-bar wrapper is deprecated; it will be removed in
issue 014.

### 3.5 Session persistence + rollback

- Data is stored in Supabase Postgres, not local JSON files. The Synology
  `docker-compose.yml` bind-mount (`./data:/app/data`) can be retired after
  cutover QA (issue 020).
- Rollback plan: if Supabase is unavailable, restore from a `pg_dump` taken
  before the cutover. See `MANUAL-STEPS.md` for the rollback procedure.

---

## 4. Environment variables reference

All variables are read from `.env` (or from the host/container environment).
Copy `.env.example` to `.env` and fill in every value before running the app.

### Required for all modes

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Public HTTPS URL of the Supabase project. Get from Dashboard → Settings → API → Project URL. Example: `https://abcdef.supabase.co` |
| `SUPABASE_ANON_KEY` | Browser-safe anon/publishable JWT. Used by `src/js/supabase-browser.js` and `src/js/auth-ui.js`. Get from Dashboard → Settings → API → anon (public). Safe to ship to the Electron renderer. |
| `SUPABASE_JWT_SECRET` | Server-side JWT signing secret. Used by `server.py` to verify Supabase access tokens sent as `Authorization: Bearer <token>`. Get from Dashboard → Settings → API → JWT Secret. **Never expose to frontend JS or Electron renderer.** |
| `PCO_CLIENT_ID` | Planning Center OAuth app client ID. For connecting the bulletin app to PCO service plans. |
| `PCO_CLIENT_SECRET` | Planning Center OAuth app client secret. **Server-side only.** |

### Required for server mode (`APP_MODE=server`)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres connection URL. Use the **session-mode / direct** connection (port 5432), not the transaction-mode pooler (6543). Example: `postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require` |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role JWT (HTTP API key). Used by `storage.py` for server-initiated Storage uploads (cover/logo images, font binaries). Get from Dashboard → Settings → API → service_role (secret). **Never bundle into Electron, commit a real value, or log it.** |
| `APP_URL` | Public URL of the server (used for OAuth redirect URIs). Leave blank for local/desktop use. Example: `https://bulletin.yourchurch.org` |

### Optional for server mode

| Variable | Description |
|----------|-------------|
| `OAUTH_STATE_SECRET` | Explicit HMAC key for signing the OAuth `state` parameter in PCO and Google Calendar/Drive OAuth flows. Falls back to `SUPABASE_JWT_SECRET` if unset. Recommended: set a dedicated value so the OAuth signing key has its own rotation schedule. Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `SUPABASE_SERVICE_ROLE_URL` | Postgres URL using service_role credentials. For RLS-bypassing admin work only (seed + migration tooling via `db.admin_transaction()`). If unset, `db.admin_transaction()` falls back to `DATABASE_URL`. Format: `postgresql://postgres.<ref>:<service_role_pw>@aws-1-<region>.pooler.supabase.com:5432/postgres?sslmode=require` |
| `POSTGRES_DB` | Postgres database name for the **local Docker postgres service** (not Supabase). Used in the default `DATABASE_URL` in `.env.example`. Default: `bulletindb`. |
| `POSTGRES_USER` | Postgres username for the local Docker postgres service. Default: `bulletin` |
| `POSTGRES_PASSWORD` | Postgres password for the local Docker postgres service. Change before deploying. |

> **Note:** `POSTGRES_*` vars are used by the `postgres` container in
> `docker-compose.yml` only when you run a local bundled Postgres. They are
> **not** used when `DATABASE_URL` points directly to a Supabase project.

### Optional / Google Calendar integration

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID for Calendar + Drive integration (separate from Supabase Auth login). |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret for Calendar + Drive. Callback: `APP_URL/oauth/google/callback`. |
| `CALENDAR_ICAL_URLS` | JSON array of iCal feed URLs to import. |
| `CALENDAR_EXCLUDE_TITLES` | JSON array of event titles to suppress from the "This Week" page. |
| `WATCHTOWER_TOKEN` | HTTP API token for Watchtower (Docker server mode auto-update). Default: `bulletin-updater`. Only reachable within the Docker network. |

### Mode detection

`APP_MODE` controls which code paths are active:

| Value | Meaning |
|-------|---------|
| `server` | Multi-user Docker/server deployment. Requires `DATABASE_URL`. |
| `desktop` | Legacy macOS `.app` bundle via `launcher.py` + PyInstaller. Single-user. |
| `electron` | New Electron desktop distribution. Single-user. `CHROME_PATH` is unused; PDF generated via `webContents.printToPDF()`. |

`IS_DESKTOP` is `True` for both `desktop` and `electron` modes — single-user
guards apply to both.

---

## 5. First-login provisioning — domain allow-list

After issue 008 lands, new users whose verified email domain is on the
allow-list are automatically provisioned as `editor` in the matching workspace
on first login.

> **Security note:** Domain matching is performed on the **verified JWT email
> claim** from Supabase Auth, not from user-editable `user_metadata`. The server
> derives the domain after verifying the token signature. Auto-provisioned users
> receive the `editor` role. To grant `owner` or `viewer`, update the row
> manually after provisioning.

### Check the current allow-list

Run in **Dashboard → SQL Editor** (or `psql` with service_role credentials):

```sql
SELECT workspace_id, settings->'allowed_domains' AS allowed_domains
FROM public.workspace_settings
WHERE settings ? 'allowed_domains';
```

### Add a domain

```sql
-- Replace <workspace-id> with the target workspace UUID and
-- <domain> with the lowercase domain string, e.g. 'visaliacrc.com'.
UPDATE public.workspace_settings
SET settings = jsonb_set(
    settings,
    '{allowed_domains}',
    COALESCE(settings->'allowed_domains', '[]'::jsonb) || to_jsonb('<domain>'::text)
)
WHERE workspace_id = '<workspace-id>'::uuid;
```

If no `workspace_settings` row exists yet for the workspace, insert one:

```sql
INSERT INTO public.workspace_settings (workspace_id, settings)
VALUES ('<workspace-id>'::uuid, '{"allowed_domains": ["<domain>"]}'::jsonb)
ON CONFLICT (workspace_id) DO UPDATE
SET settings = jsonb_set(
    workspace_settings.settings,
    '{allowed_domains}',
    COALESCE(workspace_settings.settings->'allowed_domains', '[]'::jsonb)
    || to_jsonb('<domain>'::text)
);
```

### Remove a domain

```sql
UPDATE public.workspace_settings
SET settings = jsonb_set(
    settings,
    '{allowed_domains}',
    (
        SELECT jsonb_agg(d)
        FROM jsonb_array_elements_text(settings->'allowed_domains') AS d
        WHERE lower(d) != '<domain>'
    )
)
WHERE workspace_id = '<workspace-id>'::uuid;
```

### Grant workspace access to a specific user (without allow-list)

For a one-off invite (when domain allow-list is not applicable):

```sql
INSERT INTO public.workspace_members (workspace_id, user_id, role)
VALUES (
    '<workspace-id>'::uuid,
    '<supabase-auth-user-uuid>'::uuid,
    'editor'   -- or 'owner', 'viewer'
)
ON CONFLICT (workspace_id, user_id) DO NOTHING;
```

Find the user's UUID in **Dashboard → Authentication → Users**.

### Workspace membership strategy for v1

No self-serve workspace UI is planned for v1. Workspace access is granted by:

1. **Domain allow-list auto-provisioning** (issue 008): new users with a
   matching verified email domain are added as `editor` automatically on first
   login.
2. **Manual insertion**: use the SQL above to add specific users by UUID.

Never put authorization decisions in user-editable Supabase `user_metadata`.
Membership must come from database rows only.

---

## 6. Backup and restore

### 6.1 What needs to be backed up

In server mode, all application data lives in Supabase — not on local disk.
A complete backup covers two stores:

| Store | What it holds | How to back up |
|-------|--------------|----------------|
| Supabase Postgres | Projects, songs, announcements, templates, fonts metadata, workspace settings, workspace members | `pg_dump` via `scripts/backup.sh` |
| Supabase Storage | Cover/logo images (`project-assets` bucket), font binaries (`workspace-fonts` bucket) | Supabase CLI or Dashboard export |

### 6.2 Postgres backup with `scripts/backup.sh`

The repo ships three helper scripts in `scripts/`:

| Script | Use |
|--------|-----|
| `scripts/backup.sh` | Runs `pg_dump` from the host (or inside the container) |
| `scripts/backup-compose.sh` | Runs `backup.sh` inside the running Docker container via `docker compose exec` |
| `scripts/restore.sh` | Restores a `pg_dump` backup using `pg_restore` |

All scripts read `DATABASE_URL` from the environment — secrets are never passed
as command-line arguments (no shell history exposure).

**Prerequisites:**

- `postgresql-client` installed on the host (`pg_dump` and `pg_restore` must be
  in PATH). On Debian/Ubuntu: `apt-get install postgresql-client`.
- `DATABASE_URL` exported in the shell (or in `.env`).

**Run from the host (bare server or NAS host):**

```bash
# Load DATABASE_URL from .env:
set -a && source .env && set +a

# Run backup (outputs to data/backups/YYYYMMDD_HHMMSS/):
./scripts/backup.sh

# Optional: specify a custom output directory:
./scripts/backup.sh /path/to/backups
```

Output directory contains:

- `db.dump` — Postgres custom-format dump (binary, compressed). Restore with
  `pg_restore`.

**Run inside the Docker container:**

```bash
# Passes DATABASE_URL from the host environment into the container:
export DATABASE_URL='postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require'
./scripts/backup-compose.sh

# Or with a custom destination inside the container:
./scripts/backup-compose.sh /app/data/backups
```

### 6.3 Scheduling regular backups

For unattended backups, add a cron job on the host:

```bash
# Edit the crontab:
crontab -e
```

Add a daily backup at 02:00, writing to a directory that persists on the host:

```cron
0 2 * * * set -a; source /path/to/.env; set +a; /path/to/scripts/backup.sh /path/to/backups >> /var/log/bulletin-backup.log 2>&1
```

Rotate old backups to cap disk usage (keep 30 days):

```bash
find /path/to/backups -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
```

### 6.4 Supabase Storage backup

`pg_dump` captures Postgres rows but not the binary files stored in Supabase
Storage buckets (`project-assets`, `workspace-fonts`).

**Option A — Supabase CLI (recommended):**

```bash
# Install the Supabase CLI if not already installed:
# https://supabase.com/docs/guides/cli

# Pull all objects from a bucket to a local directory:
supabase storage cp --project-ref <ref> \
  'ss://project-assets' ./backups/storage/project-assets --recursive

supabase storage cp --project-ref <ref> \
  'ss://workspace-fonts' ./backups/storage/workspace-fonts --recursive
```

**Option B — Supabase Dashboard:**

1. Open Dashboard → Storage → select the bucket (`project-assets` or
   `workspace-fonts`).
2. Use the bucket browser to select and download files.
3. Repeat for each bucket.

> **Frequency note:** Cover/logo images and fonts change infrequently. A weekly
> Storage backup is sufficient for most deployments. Postgres data (projects,
> songs, etc.) changes with every edit and warrants daily backups.

### 6.5 Restore from a Postgres backup

```bash
# Load DATABASE_URL:
set -a && source .env && set +a

# Run the restore script (prompts for confirmation before writing):
./scripts/restore.sh data/backups/YYYYMMDD_HHMMSS
```

The restore script runs `pg_restore --clean --if-exists`, which drops and
recreates all objects in the dump before restoring rows. This is safe for a
full-restore scenario but will destroy any data added after the backup was taken.

**Restore to a fresh Supabase project:**

1. Create the new Supabase project and apply all schema migrations (section 1.4).
2. Set `DATABASE_URL` to the new project's connection string.
3. Run `./scripts/restore.sh <backup_dir>`.

> Re-applying the schema migrations first ensures the table structure matches
> what `pg_restore` expects. If the dump was taken after a migration that the
> new project has not applied, `pg_restore` will fail with "relation does not
> exist" errors.

### 6.6 Restore Supabase Storage files

After a Postgres restore, re-upload Storage files using the Supabase CLI:

```bash
# Re-upload project assets:
supabase storage cp --project-ref <ref> \
  ./backups/storage/project-assets 'ss://project-assets' --recursive

# Re-upload fonts:
supabase storage cp --project-ref <ref> \
  ./backups/storage/workspace-fonts 'ss://workspace-fonts' --recursive
```

### 6.7 Full rollback procedure

Use this sequence if a deployment goes wrong and you need to revert to a known
good state:

1. Stop the container: `docker compose down`.
2. Restore Postgres: `./scripts/restore.sh <backup_dir>`.
3. Re-upload Storage files (section 6.6) if needed.
4. Restart: `docker compose up -d`.
5. Verify: `curl http://localhost:8080/api/bootstrap` → `200 OK`.

---

## See also

- `MANUAL-STEPS.md` — detailed walkthrough of Supabase Auth provider setup,
  Google OAuth credentials, SMTP config, and the Electron deep-link setup.
- `docs/ai/decisions.md` — architecture decisions (D1–D5, M4/M5 deferred items).
- `docs/ai/testing-guide.md` — automated test commands and manual smoke checklist.
- `.env.example` — annotated template for all environment variables.
