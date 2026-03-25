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
- Planning Center service import
- volunteer/schedule import from Planning Center
- weekly calendar rendering
- song database management
- PDF generation through headless Chrome/Chromium

## Deployment modes

This project is moving toward two supported deployment modes from one codebase:

- `desktop`: packaged local app for single-user installs and testing
- `server`: shared self-hosted deployment for browser access on a local network/server

See [docs/ARCHITECTURE.md](/Users/ajhochhalter/Documents/Bulletin Generator - 1.04/docs/ARCHITECTURE.md) for the current deployment-mode plan, issue labels, and milestone structure.

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

4. Open the app:

```text
http://localhost:8080/
```

On first run, the app creates local working files in `data/` from the committed example files if those local files do not already exist.

### Packaged desktop build

Desktop test builds are expected to ship with project-owned OAuth credentials bundled in the app.

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

Desktop testers should sign in with their own Planning Center and Google accounts through the packaged app. They should not need to create or paste their own API keys or OAuth client credentials.

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

## Data and storage

The app uses JSON-backed local state for most editable content.

Common local files include:

- `data/projects.json`
- `data/announcements.json`
- `data/settings.json`
- local song database/export files as needed

Committed example files are included as safe templates:

- `data/projects.example.json`
- `data/announcements.example.json`
- `data/settings.example.json`

In packaged desktop mode, the server is expected to store writable data outside the app bundle. The current code already supports using an application support directory on macOS.

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

- [server.py](/Users/ajhochhalter/Documents/Bulletin Generator - 1.04/server.py): local backend, API routes, PDF generation, integration proxying
- [worship-booklet.html](/Users/ajhochhalter/Documents/Bulletin Generator - 1.04/worship-booklet.html): main frontend/editor UI
- [Dockerfile](/Users/ajhochhalter/Documents/Bulletin Generator - 1.04/Dockerfile): container build
- [docker-compose.yml](/Users/ajhochhalter/Documents/Bulletin Generator - 1.04/docker-compose.yml): local/shared Docker run setup
- `data/*.example.json`: safe starter data committed to Git
- [.env.example](/Users/ajhochhalter/Documents/Bulletin Generator - 1.04/.env.example): starter environment configuration

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
