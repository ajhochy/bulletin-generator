# Architecture

See `CLAUDE.md` for the canonical, detailed reference. This file is the high-level summary for agents.

## App summary

Church bulletin generator. Imports a service plan from Planning Center Online, pulls events from Google Calendar / iCal, lets a user arrange order-of-worship and announcements, and exports a print-ready PDF (headless Chrome).

## Two deployment modes

- **`desktop`** (default in `.app` bundle): single-user, port 8765, `launcher.py` manages server lifecycle, OAuth creds bundled in `desktop_config.py`, data at `~/Library/Application Support/BulletinGenerator/`. Updates via GitHub zip download.
- **`server`**: multi-user, port 8080, Docker-managed, data at `/app/data` bind-mounted to `./data`, OAuth creds from env vars. Updates via Watchtower sidecar. Adds 409 conflict detection (revision + editor attribution).

Mode is decided by `APP_MODE` env var. JS-side check: `isServerMode()` in `api.js`. Python-side: `APP_MODE` / `IS_DESKTOP` in `server.py`.

## Data flow

```
PCO + Google Cal + iCal  ──►  server.py (proxy/fetch)  ──►  src/js/* (state)
                                                              │
                                                              ▼
                       collectCurrentProjectState() ──► POST /api/projects ──► data/projects.json
                                                              │
                                                              ▼
                       renderPreview() ──► page-split ──► print-ready HTML ──► /api/pdf ──► headless Chrome
```

## Major boundaries

- **server.py ↔ frontend**: REST JSON API on the same port; no separate API gateway. Route dispatch is manual `startswith` in `do_GET` / `do_POST`.
- **frontend ↔ state**: `state.js` owns top-level globals (`items[]`, `annData[]`, `vrData[]`, `servingSchedule`, `calEvents`). Modules read/write directly — no Redux/store layer.
- **Preview vs Template Designer**: `preview.js` renders the live preview canvas the user prints. `templates.js` reuses that same DOM but adds a selectable-element overlay (`inferCanvasElement()` + `TPL_SELECTABLE_SELECTOR`). New zones must be wired in both.
- **Editor cards vs preview elements**: Each section type often has two unrelated DOM trees — the side-panel editor card (e.g. `.vr-card` in `volunteer-roles.js`) and the preview element (e.g. `.vr-entry-*` in `preview.js`). The Template Designer operates on the preview tree, not the editor card.

## External dependencies

- **Runtime**: Planning Center API, Google Calendar API, `api.qrserver.com` (QR images), headless Chrome (PDF), GitHub Releases API (update checks).
- **Python**: stdlib only for HTTP; `rumps` for desktop menu bar.
- **JS**: no framework, no bundler. DaisyUI / Tailwind classes appear in markup; styling rules live in `index.html` / `styles.css`.

## Conflict + sync model (server mode)

`_clientRevision` posted with each save → server compares to stored revision → 409 if stale, returning `{ serverRevision, serverUpdatedBy, serverUpdatedAt }`. Frontend tracks `_loadedRevision` in `projects.js` and shows a conflict banner with a "Reload latest" link that fetches fresh from the server.
