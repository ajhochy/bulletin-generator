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

Server mode requires Postgres and Google Workspace for user authentication.

#### Environment variables

Copy the example env file and set all required values before starting:

```bash
cp .env.example .env
```

**Required for server mode:**

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Full Postgres connection URL (auto-built from `POSTGRES_*` vars by default) |
| `POSTGRES_DB` | Postgres database name (default: `bulletindb`) |
| `POSTGRES_USER` | Postgres username (default: `bulletin`) |
| `POSTGRES_PASSWORD` | Postgres password — **change before deploying** |
| `APP_URL` | Public URL of your deployment, e.g. `https://bulletin.yourchurch.org` |
| `AUTH_GOOGLE_CLIENT_ID` | OAuth client ID for app login (Google Workspace identity) |
| `AUTH_GOOGLE_CLIENT_SECRET` | OAuth client secret for app login |
| `AUTH_GOOGLE_REDIRECT_URI` | Must be `APP_URL/auth/google/callback` |
| `GOOGLE_WORKSPACE_DOMAIN` | Domain to restrict logins, e.g. `yourchurch.org` |

**Two separate Google OAuth flows — do not mix them up:**

- **App login** (`AUTH_GOOGLE_*`): authenticates users into the app itself. Uses identity scopes only (`openid email profile`). Redirect URI: `APP_URL/auth/google/callback`.
- **Calendar/Drive integration** (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`): connects the shared Google Calendar feed. Uses calendar+drive scopes. Redirect URI: `APP_URL/oauth/google/callback`.

These may point to the same Google OAuth client or to separate ones. Set them separately.

**Also required (PCO):**

| Variable | Purpose |
|----------|---------|
| `PCO_CLIENT_ID` | Planning Center OAuth client ID |
| `PCO_CLIENT_SECRET` | Planning Center OAuth client secret |

#### First-run steps

1. Copy and edit the env file:

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD, APP_URL, AUTH_GOOGLE_*, GOOGLE_WORKSPACE_DOMAIN,
# GOOGLE_CLIENT_ID/SECRET, PCO_CLIENT_ID/SECRET
```

2. Register OAuth redirect URIs in Google Cloud Console:
   - App login callback: `APP_URL/auth/google/callback`
   - Calendar/Drive callback: `APP_URL/oauth/google/callback`

3. Register the PCO redirect URI in Planning Center:
   - `APP_URL/oauth/pco/callback`

4. Start all services:

```bash
docker compose up -d
```

5. Run the one-time data migration (only needed when upgrading from a pre-Postgres deployment with existing JSON data):

```bash
# Preview what will be migrated (no writes):
docker compose exec app python -m migrations.run_all_migrations --dry-run

# Migrate (creates a timestamped backup first):
docker compose exec app python -m migrations.run_all_migrations
```

The migration creates a backup at `data/backups/TIMESTAMP/` before writing anything to Postgres. On a fresh deployment with no legacy JSON data, skip this step.

6. Open the app:

```text
http://localhost:8080/
```

#### Postgres storage

The `postgres` service uses a named Docker volume (`postgres_data`) for durable database storage. Do not run `docker compose down -v` — the `-v` flag removes named volumes and will destroy your database.

To back up the database:

```bash
docker compose exec postgres pg_dump -U bulletin bulletindb > backup.sql
```

To restore:

```bash
docker compose exec -T postgres psql -U bulletin bulletindb < backup.sql
```

#### What is stored in Postgres (server mode)

- Projects, project revision history
- Settings (shared deployment-wide)
- Announcements, songs, templates
- Font file metadata (binary font files remain on disk)
- Users and sessions (auth)

#### What stays on disk

- Font binary files: `data/fonts/` (mounted into the container via `./data`)
- Migration backups: `data/backups/`

If `DATABASE_URL` is missing when `APP_MODE=server`, the server exits immediately with a clear error message pointing to `.env.example`.

The Docker build runs the frontend `vite` build during image creation, so JS bundle regressions fail at build time rather than at runtime.

#### Rollback

1. Restore Postgres from a `pg_dump` backup.
2. Restore JSON source files from `data/backups/TIMESTAMP/` if needed.
3. Restart the container: `docker compose up -d`.

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

In server mode (`APP_MODE=server`), editable content is stored in Postgres:

- Projects (with full revision history)
- Announcements, songs, templates
- Settings (shared deployment-wide)
- Font file metadata (binary files remain on disk at `data/fonts/`)
- Users and sessions

JSON files in `data/` are only used during the one-time migration from a legacy JSON-backed deployment. Font binary files at `data/fonts/` are always read from disk regardless of mode.

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

The app currently supports two calendar paths:

- local/server dev mode: `.env` calendar defaults via `CALENDAR_ICAL_URLS` and `CALENDAR_EXCLUDE_TITLES`
- packaged desktop mode: bundled Google OAuth credentials in `desktop_config.py`, with users signing into their own Google accounts inside the app

Relevant env values:

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
