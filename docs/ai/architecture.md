# Architecture

See `CLAUDE.md` for the canonical, detailed reference. This file is the high-level summary for agents.

## App summary

Church bulletin generator. Imports a service plan from Planning Center Online, pulls events from Google Calendar / iCal, lets a user arrange order-of-worship and announcements, and exports a print-ready PDF (headless Chrome).

## Two deployment modes

- **`desktop`** (default in `.app` bundle): single-user, port 8765, `launcher.py` manages server lifecycle, OAuth creds bundled in `desktop_config.py`, data at `~/Library/Application Support/BulletinGenerator/`. Updates via GitHub zip download.
- **`server`**: multi-user, port 8080, Docker-managed, data at `/app/data` bind-mounted to `./data`, OAuth creds from env vars. Updates via Watchtower sidecar. Owner-only write enforcement (403 for non-owners), presence heartbeat, read-only mode for non-owners.

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

## Ownership + presence model (server mode)

- **Owner-only writes**: `POST /api/projects` returns 403 for non-owners. Frontend shows toast: "Only the project owner can edit this bulletin."
- **Read-only mode**: When a non-owner loads a workspace project, `_isReadOnly = true`, autosave is suppressed, a `#readonly-banner` strip appears with the owner's name and a Duplicate button.
- **Duplicate**: Creates a new private project (`visibility='private'`) with the same state, assigns it to the current user, exits read-only mode.
- **Presence heartbeat**: On project open, `POST /api/presence/heartbeat` fires immediately and then every 30s. `GET /api/presence?project_id=<uuid>` is polled once on open to show `#presence-badge` if another user is active. `DELETE /api/presence` fires on `pagehide` / `beforeunload`. All presence calls are best-effort (errors swallowed). Desktop mode: all presence calls are skipped.
- No `_clientRevision` is sent in save requests. No conflict detection / stale-check poll.
