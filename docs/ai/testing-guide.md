# Testing Guide

This repo has no automated test suite. Validation is a layered checklist agents should run before claiming work is done.

## Install / setup assumptions

- Python 3.11+, with `requirements.txt` installed in a venv.
- `cp .env.example .env` and fill PCO + Google OAuth creds (server mode), or `cp desktop_config.py.example desktop_config.py` (desktop bundle).
- Node available for syntax checks: `node --check src/js/<file>.js`.

## Commands

### Syntax / static checks

```bash
python3 -c "import server"         # server.py imports cleanly
node --check src/js/templates.js   # repeat per file changed
```

### Run the app locally

- Quick check via the workflow's preview server: it's configured in `.claude/launch.json` (`bulletin-generator`, port `8766`).
- Manual:

```bash
python3 server.py            # port 8080 by default
python3 server.py 8766       # alternate port
```

### Docker (server mode)

```bash
docker compose up --build
```

### Desktop build

```bash
pyinstaller bulletin-generator.spec
# Output: dist/Bulletin Generator.app
```

### Electron desktop (dev mode)

Requires Node + the `electron` devDependency (`npm install`).

```bash
npm run start:electron
# Equivalent: ./node_modules/.bin/electron .
```

What to expect:
- A terminal window shows `[server] Serving on port 8765` once server.py is up.
- A BrowserWindow opens pointing to `http://localhost:8765/`.
- A tray icon appears; right-click shows "Open Bulletin Generator" and "Quit".
- Clicking "Quit" from the tray kills the Python sidecar and exits cleanly.

If the server fails to start within 20 s, an error dialog appears and the app quits.

> **Packaged mode path (future):** when building the final `.app`, the PyInstaller
> `server` binary will be placed at `<app>.app/Contents/Resources/server`.
> `electron/main.js` already probes for that path via `process.resourcesPath`.

## Manual-only checks

These cannot be automated and must be smoke-tested by a human before merge:

- **Template Designer click-through**: open Templates → Design on any template. Click every selectable element type (cover, section heading, song title, song lyrics, song copyright, label, liturgy, announcement title/body/QR, calendar day/title/time/location, serving week/service-time/team/role/name, volunteer-role title/body/URL, staff name/role/email). Each click should outline the element with 2px accent + 4 corner handles, populate the per-element formatting panel, and the aria-label should describe the element.
- **PDF export**: round-trip a project to PDF and visually verify pagination, page breaks, footers, cover, and any QR codes.
- **Project save/load + conflict**: in server mode, edit the same project in two browsers, save in one, save in the other → confirm 409 banner appears with diff and "Reload latest" works.
- **PCO import + calendar fetch**: token-refresh paths only fire on real network errors; spot-check on real creds before shipping changes to `pco.js` or `calendar.js`.
- **Console must be clean**: open DevTools, exercise the changed surface, confirm no new errors / warnings.

## Health probes

The app has no dedicated `/health` endpoint. Acceptable substitute: `GET /api/bootstrap` returns 200 with a JSON body once the server is ready.

## Pre-handoff verification

Before opening a PR or claiming done:

1. Syntax checks above (every file changed).
2. Start the app (`python3 server.py` or the preview server) and load `/`.
3. Console must be clean after the changed flow runs.
4. If the change touches Template Designer wiring, exercise at least one element of every zone — not just the one you changed.
