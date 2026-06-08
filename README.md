# Bulletin Generator

Bulletin Generator is a local-first church bulletin builder for creating printable worship booklets.

It combines a browser-based editor with a small Python server so you can:

- build a bulletin page-by-page in a live preview
- import order-of-worship data from Planning Center
- pull calendar content into a weekly events page
- manage a reusable song database
- generate a print-ready PDF

The app is designed around real bulletin workflow, not just raw document editing. It keeps service structure, announcements, songs, volunteers, calendar content, and booklet layout in one place.

## What the app does

The main editing experience is split across a few core areas:

- `Booklet Editor`: build the actual bulletin content and preview pages live
- `Projects`: save, load, version, and manage bulletin drafts
- `Song Database`: manage reusable song lyrics/copyright records
- `Format`: set document size and formatting behavior
- `Settings`: manage integrations and app-level defaults

Typical workflow:

1. Import a service plan from Planning Center or start from scratch.
2. Edit announcements, order of worship, calendar, volunteers, and staff sections.
3. Pull in song content from the song database.
4. Adjust layout and formatting.
5. Export the finished bulletin to PDF.

## Current feature set

- live booklet preview with page splitting
- project save/load workflow
- announcement editor
- order-of-worship editor
- staff page
- Planning Center service import
- volunteer/schedule import from Planning Center
- ProPresenter song database import
- weekly calendar rendering
- song database management
- PDF generation through headless Chrome/Chromium
- in-app update system (desktop launcher + Docker Watchtower)
- template designer with CSS variable-based formatting
- Tailwind CSS + DaisyUI UI
- JS test suite (vitest) and Python test suite (pytest)
- CI pipeline (GitHub Actions) with automated Docker + macOS releases on tag push

## Deployment modes

The project supports two deployment modes from one codebase:

- `desktop`: packaged macOS app for single-user installs
- `server`: shared self-hosted deployment for browser access on a local network or server

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the deployment-mode plan, issue labels, and milestone structure.

## Quick start

### Local run

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Update `.env` with your local values:

- `PCO_CLIENT_ID` and `PCO_CLIENT_SECRET` for Planning Center OAuth access
- `CALENDAR_ICAL_URLS` if you want default calendar feeds
- `CALENDAR_EXCLUDE_TITLES` if you want to suppress recurring default event titles

3. Start the server:

```bash
python3 server.py
```

Install frontend dependencies and run tests:

```bash
npm install
npm test
npm run build
```

4. Open the app:

```text
http://localhost:8080/
```

On first run, the app creates local working files in `data/` from the committed example files if those local files do not already exist.

### Packaged desktop build

The desktop app ships as a signed and notarized macOS `.app` bundle with project-owned OAuth credentials bundled in.

1. Copy the desktop config template:

```bash
cp desktop_config.py.example desktop_config.py
```

2. Fill in `desktop_config.py` with the app's Planning Center and Google OAuth client credentials.

3. Build the app bundle:

```bash
pyinstaller bulletin-generator.spec
```

If `bulletin Generator icon.svg` exists in the repo root, the build spec will
convert it into the `.icns` bundle icon automatically during the macOS build.
If that conversion cannot run, the build falls back to `Bulletin Generator.icns`.

4. Distribute `dist/Bulletin Generator.app`.

Users sign in with their own Planning Center and Google accounts through the packaged app. They do not need to create or paste their own API keys or OAuth client credentials.

### Docker (server mode)

Server mode uses [Supabase](https://supabase.com) for Postgres storage, Auth,
and file assets. User authentication is handled by Supabase Auth (Google OAuth
and email magic links). There is no separate app-login Google OAuth flow.

#### Environment variables

Copy the example env file and set all required values before starting:

```bash
cp .env.example .env
```

**Required for server mode:**

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Supabase Postgres direct connection URL (port 5432, session mode). Get from Dashboard → Settings → Database → Connection string. |
| `SUPABASE_URL` | Public HTTPS URL of the Supabase project. Get from Dashboard → Settings → API → Project URL. |
| `SUPABASE_ANON_KEY` | Browser-safe anon/publishable JWT. Get from Dashboard → Settings → API → anon (public). Safe to ship to the browser/Electron client. |
| `SUPABASE_JWT_SECRET` | Server-side JWT signing secret. Used by `auth.py` to verify Supabase access tokens. Get from Dashboard → Settings → API → JWT Secret. **Never expose to frontend JS.** |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role API key (JWT) for Supabase Storage uploads. Used by `storage_assets.py` and `storage.py`. Get from Dashboard → Settings → API → service_role. **Server-side only.** |
| `APP_URL` | Public URL of your deployment, e.g. `https://bulletin.yourchurch.org` |
| `PCO_CLIENT_ID` | Planning Center OAuth client ID |
| `PCO_CLIENT_SECRET` | Planning Center OAuth client secret |

**Optional but recommended:**

| Variable | Purpose |
|----------|---------|
| `OAUTH_STATE_SECRET` | HMAC key for signing the OAuth `state` parameter (PCO and Google Calendar OAuth). Falls back to `SUPABASE_JWT_SECRET` if unset. Set an explicit value to isolate the OAuth signing key. |
| `SUPABASE_SERVICE_ROLE_URL` | Postgres URL using service_role credentials — for RLS-bypassing admin work only (`db.admin_transaction()`). Falls back to `DATABASE_URL` if unset. |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID for Calendar + Drive integration. |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret for Calendar + Drive. |
| `POSTGRES_DB` | Postgres database name used by the local `postgres` service in `docker-compose.yml`. Default: `bulletindb` |
| `POSTGRES_USER` | Postgres username for the local `postgres` service. Default: `bulletin` |
| `POSTGRES_PASSWORD` | Postgres password for the local `postgres` service. Required if running the bundled `postgres` container. |

**Google OAuth flows — there is only one calendar/drive flow:**

| Flow | Env vars | Scopes | Callback path |
|------|----------|--------|---------------|
| User login (Supabase Auth) | Configured in Supabase Dashboard only — not in `.env` | `openid email profile` | Supabase-managed |
| Calendar/Drive integration | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | `calendar drive` | `APP_URL/oauth/google/callback` |

The old `AUTH_GOOGLE_*` and `GOOGLE_WORKSPACE_DOMAIN` variables are **not
used**. User authentication is delegated to Supabase Auth. Configure Google
OAuth in the Supabase Dashboard (Authentication → Providers → Google).

**OAuth redirect URIs to register:**

| Provider | URI to register |
|----------|-----------------|
| Planning Center | `APP_URL/oauth/pco/callback` |
| Google Calendar/Drive | `APP_URL/oauth/google/callback` |
| Google (Supabase Auth) | `https://<supabase-ref>.supabase.co/auth/v1/callback` |

#### First-run steps

1. Copy and edit the env file:

```bash
cp .env.example .env
# Set DATABASE_URL, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET,
# SUPABASE_SERVICE_ROLE_KEY, APP_URL, PCO_CLIENT_ID/SECRET
```

2. Apply Supabase schema migrations (SQL files in `supabase/migrations/`) via
   the Supabase Dashboard SQL editor or the Supabase CLI.

3. Register OAuth redirect URIs (see table above).

4. Start the container:

```bash
docker compose up -d
```

5. (One-time) If migrating from a legacy JSON-backed deployment, run the data
   migration script to import existing JSON data into Supabase Postgres:

```bash
# Preview what will be migrated (no writes):
set -a && source .env && set +a
APP_MODE=server .venv/bin/python scripts/migrate_to_supabase.py \
  --source ./data --dry-run

# Execute migration:
APP_MODE=server .venv/bin/python scripts/migrate_to_supabase.py \
  --source ./data --execute
```

The script migrates projects, announcements, settings, songs, and templates
from JSON files into Postgres. OAuth tokens are excluded — they must be
re-issued after migration. The script is idempotent: re-running is safe.

On a fresh deployment with no legacy JSON data, skip this step.

6. Open the app:

```text
http://localhost:8080/
```

#### What is stored in Supabase (server mode)

| Store | Contents |
|-------|----------|
| Supabase Postgres | Projects, project revision history, announcements, songs, templates, font metadata, workspace settings, workspace members |
| Supabase Storage (`project-assets`) | Cover images and staff logo images (base64 data URIs are uploaded on first save) |
| Supabase Storage (`workspace-fonts`) | User-uploaded font binary files |
| Supabase Auth | Users and sessions |

Nothing from the app is stored on the container's local disk in server mode.
The `./data:/app/data` bind-mount is retained as a working directory for
migration backups (`data/backups/`) but holds no live application data.

If `DATABASE_URL` is missing when `APP_MODE=server`, the server exits
immediately with a clear error message pointing to `.env.example`.

The Docker build runs the frontend `vite` build during image creation, so JS
bundle regressions fail at build time rather than at runtime.

#### Backup and restore

Use `pg_dump` against the Supabase Postgres database:

```bash
# Set DATABASE_URL from your .env:
export DATABASE_URL='postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require'

# Run the backup script (outputs to data/backups/YYYYMMDD_HHMMSS/):
./scripts/backup.sh

# Or inside the running Docker container:
./scripts/backup-compose.sh
```

The backup scripts create a timestamped directory containing `db.dump` (Postgres
custom-format dump, restorable with `pg_restore`). Supabase Storage assets
(cover/logo images, fonts) must be exported separately from the Supabase
Dashboard (Storage → Download) or via the Supabase CLI.

To restore:

```bash
export DATABASE_URL='...'
./scripts/restore.sh data/backups/YYYYMMDD_HHMMSS
```

See `docs/operator-runbook.md` for the full backup and restore runbook.

#### Rollback

1. Restore Postgres from a `pg_dump` backup: `./scripts/restore.sh <backup_dir>`.
2. Restart the container: `docker compose up -d`.

## Data and storage

### Desktop mode

The app uses JSON-backed local state for all editable content.

Common local files include:

- `data/projects.json`
- `data/announcements.json`
- `data/settings.json`
- `data/song_database.json`

Committed example files are included as safe templates:

- `data/projects.example.json`
- `data/announcements.example.json`
- `data/settings.example.json`

In packaged desktop mode, the server stores writable data in the application support directory on macOS (`~/Library/Application Support/BulletinGenerator/`).

### Server mode

In server mode (`APP_MODE=server`), all application data is stored in Supabase:

- **Supabase Postgres**: projects (with full revision history), announcements,
  songs, templates, font metadata, workspace settings, workspace members.
- **Supabase Storage `project-assets` bucket**: cover images and staff logo
  images. Base64 data URIs are extracted and uploaded on first project save.
- **Supabase Storage `workspace-fonts` bucket**: user-uploaded font binary files.
- **Supabase Auth**: user accounts and sessions.

JSON files in `data/` are only used during the one-time migration from a legacy
JSON-backed deployment. After migration, nothing is written to `data/` in server
mode (the bind-mount is kept for migration backup output only).

## CI and releases

GitHub Actions runs two workflows:

- **CI** (`ci.yml`): runs on every push and pull request — JS tests (`npm test`), JS build (`npm run build`), and Python tests (`pytest`)
- **Release** (`release.yml`): triggered by a version tag (`v*`) — builds and pushes a Docker image to GHCR, and builds a signed and notarized macOS `.app` bundle attached to the GitHub Release

## Integrations

### Planning Center

Planning Center access is handled server-side.

- local/server dev mode: set `PCO_CLIENT_ID` and `PCO_CLIENT_SECRET` in `.env`, then restart the server
- packaged desktop mode: bundle `PCO_CLIENT_ID` and `PCO_CLIENT_SECRET` in `desktop_config.py`
- the frontend talks to the local server, which proxies the PCO requests or runs the desktop OAuth flow

### Google Calendar / calendar feeds

The app supports two calendar paths:

- local/server dev mode: `.env` calendar defaults via `CALENDAR_ICAL_URLS` and `CALENDAR_EXCLUDE_TITLES`
- Google Calendar API: connected via the Calendar/Drive OAuth flow (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`). The OAuth callback is `APP_URL/oauth/google/callback`.
- packaged desktop mode: bundled Google OAuth credentials in `desktop_config.py`

Relevant env values:

- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — for Calendar/Drive OAuth
- `CALENDAR_ICAL_URLS`
- `CALENDAR_EXCLUDE_TITLES`

## Repo layout

- [server.py](server.py): local backend, API routes, PDF generation, integration proxying
- [launcher.py](launcher.py): macOS menu bar app — single-instance management, server lifecycle
- [index.html](index.html): single-page app shell
- [src/js/main.js](src/js/main.js): JS entry point (module loader, bootstrap)
- [src/js/app.js](src/js/app.js): tab switching, initialization, event wiring
- [src/js/templates.js](src/js/templates.js): template designer — built-in templates and CSS variable system
- [src/js/template-registry.js](src/js/template-registry.js): template registry — apply/manage templates
- [src/js/modules/](src/js/modules/): extracted testable core modules (calendar, preview, projects, formatting, PCO, text)
- [src/js/](src/js/): remaining frontend JavaScript modules
- [src/css/](src/css/): frontend stylesheets
- [bulletin-generator.spec](bulletin-generator.spec): PyInstaller build config for macOS desktop app
- [Dockerfile](Dockerfile): container build
- [docker-compose.yml](docker-compose.yml): local/shared Docker run setup
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): deployment mode design notes
- `data/*.example.json`: safe starter data committed to Git
- [.env.example](.env.example): starter environment configuration

## What stays local

These should remain machine-local and out of Git:

- `.env`
- real `data/*.json` working files
- live song database exports
- Planning Center debug exports
- machine/editor artifacts such as `.DS_Store`, `.vscode/`, `.idea/`

## Notes for development

- The app is intentionally local-first and JSON-backed.
- PDF generation depends on Chrome/Chromium availability.
- Docker is the easiest path when you want consistent Chromium/PDF behavior.
- Current planning is tracked in GitHub using `mode:*`, `area:*`, and milestone labels.
