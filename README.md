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

Optional frontend verification:

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

### Docker

Run with Docker Compose:

```bash
docker compose up --build
```

Then open:

```text
http://localhost:8080/
```

The Compose setup mounts `./data` into the container so working data survives container rebuilds.
The Docker build now also runs the frontend `vite` build, so JS bundle regressions fail during image creation instead of only at runtime.

## Data and storage

The app uses JSON-backed local state for most editable content.

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
