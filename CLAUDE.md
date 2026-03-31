# Bulletin Generator — CLAUDE.md

Quick reference for AI agents. Read this before exploring the codebase.

---

## What This App Is

A church bulletin generator. Users import their service plan from Planning Center Online (PCO), pull calendar events from Google Calendar or iCal, edit the order of worship and announcements, then export a print-ready PDF. Runs in two modes: a packaged macOS desktop app, or a self-hosted Docker server for multi-user teams.

---

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Core backend — Flask-like HTTP server (uses stdlib `http.server`). All API routes, OAuth flows, PCO proxy, calendar fetching, PDF generation via headless Chrome, update system. ~1,485 lines. |
| `launcher.py` | macOS desktop launcher. Manages server process lifecycle on port 8765, menu bar icon via `rumps`, single-instance detection, version mismatch restarts. |
| `index.html` | Single-page app shell. |
| `src/js/app.js` | Tab switching, initialization, event wiring. Entry point. |
| `src/js/state.js` | All global state objects (`items[]`, `annData[]`, `servingSchedule`, `calEvents`, `activeProjectId`), page size presets, localStorage keys, type format system. |
| `src/js/api.js` | `apiFetch()` wrapper with error status propagation. Server settings cache. Mode detection helpers (`isServerMode()`). |
| `src/js/projects.js` | Project save/load/delete, conflict detection (409 handling), `collectCurrentProjectState()`, `applyProjectState()`, autosave debounce. |
| `src/js/editor.js` | Cover/logo image handling, church name, item list rendering, page break insertion. |
| `src/js/preview.js` | Live preview rendering, page-split algorithm (chunk-based binary search), print-ready HTML generation. |
| `src/js/formatting.js` | Per-item and per-type formatting UI. `getEffectiveFmt(item)` merges type defaults with item overrides. |
| `src/js/pco.js` | Planning Center OAuth, service plan loading, order-of-worship and volunteer import, note parsing. |
| `src/js/songs.js` | Song DB management (`song_database.json`), title normalization, ProPresenter matching, copyright tracking. |
| `src/js/propresenter.js` | ProPresenter `.pro6library` import — minimal protobuf decode + RTF text extraction. |
| `src/js/calendar.js` | iCal URL management, Google Calendar OAuth + event fetching, week-window filtering, manual events. |
| `src/js/announcements.js` | Announcement card UI, move/delete, formatting, page-break toggles. |
| `src/js/staff.js` | Staff page rendering, role-based display, email linking. |
| `src/js/text-renderer.js` | Markdown→HTML, lyric/copyright splitting, text utilities. |
| `src/js/update.js` | GitHub API version checks, update UI progress, Watchtower/desktop update triggers. |
| `src/js/utils.js` | Timestamp formatting, status notifications, DOM helpers. |
| `bulletin-generator.spec` | PyInstaller spec for macOS `.app` bundle. |
| `docker-compose.yml` | App + Watchtower sidecar for server mode auto-updates. |
| `data/` | Runtime JSON files: `projects.json`, `settings.json`, `announcements.json`, `song_database.json`, `migrations.json`. `*.example.json` files are safe committed defaults copied on first run. |
| `docs/ARCHITECTURE.md` | Deployment mode design notes and GitHub issue labeling strategy. |

---

## Deployment Modes

```
APP_MODE=desktop  (default in .app bundle)
├─ Single-user, port 8765
├─ launcher.py manages server process
├─ OAuth creds bundled in desktop_config.py
├─ Data at ~/Library/Application Support/BulletinGenerator/
└─ Updates via GitHub zip download

APP_MODE=server
├─ Multi-user, browser-based, port 8080
├─ Docker-managed, data at /app/data (mounted ./data)
├─ OAuth creds from env vars
├─ 409 conflict detection (revision tracking + editor attribution)
└─ Updates via Watchtower
```

Check mode in JS with `isServerMode()` (in `api.js`). Check in Python with `APP_MODE` env var / `IS_DESKTOP` flag in `server.py`.

---

## Data Flow

### Project Save/Load

```
User edits → scheduleProjectPersist() (1s debounce)
           → collectCurrentProjectState()  [projects.js]
           → POST /api/projects  (includes _clientRevision in server mode)
           → server.py increments revision, atomic write to projects.json

Load → GET /api/projects → applyProjectState(state)  [projects.js]
     → restores items[], annData[], servingSchedule, calEvents, images
     → triggers renderPreview()
```

### Conflict Detection (Server Mode)

```
Both editors load project at revision=5
Editor A saves → server bumps to revision=6
Editor B saves with _clientRevision=5 → server returns 409:
  { serverRevision: 6, serverUpdatedAt: ..., serverUpdatedBy: "Editor A" }
UI shows conflict banner with "Reload latest" link
```

- `_loadedRevision` (projects.js) tracks the last known server revision
- `apiFetch()` in `api.js` attaches `e.status = res.status` to thrown errors so callers can check `err.status === 409`
- Conflict banner uses `innerHTML = ''` before rebuild — no duplicate links

### Autosave + Preview Refresh

Two independent debounce timers:
- **Preview**: 300ms — `schedulePreviewUpdate()` → `renderPreview()`
- **Persist**: 1s — `scheduleProjectPersist()` → `saveProjectToServer()`

### Calendar

```
calFetchAll(force) → GET /cal
Server: Google Calendar API (if connected) OR iCal URLs
  ├─ Google: returns None on 401/403, [] on empty — only retry on None
  └─ iCal: fetch + parse + filter by week window (Sun–Sat)
Frontend caches for 15 minutes
```

### PDF Generation

```
POST /api/pdf { html, filename, pageWidth, pageHeight }
Server writes HTML to tempfile → headless Chrome --print-to-pdf → return PDF
```

---

## Item Types

Items live in `items[]`. Each has a `type` field:

| Type | Meaning |
|------|---------|
| `'section'` | Heading (e.g. "GATHERING") |
| `'song'` | Worship song with lyrics + copyright |
| `'label'` | Generic liturgy text |
| `'liturgy'` | Named liturgical text (Lord's Prayer, etc.) |
| `'page-break'` | Forces a PDF page break |
| `'note'` | PCO internal note — hidden from print |
| `'media'` | PCO media item — hidden from print |

`migrateItemType(oldType)` in `projects.js` maps legacy types on load.

---

## Formatting System

```javascript
// Per-type defaults stored in typeFormats[type]
// Per-item overrides stored in item._fmt
// Merged at render time:
getEffectiveFmt(item)  // item._fmt keys win over typeFormats[item.type]

// _fmt shape:
{
  titleBold, titleItalic,
  titleAlign, titleSize, titleColor,
  bodyAlign, bodySize, bodyColor
}
```

---

## Page-Split Algorithm (preview.js)

- Builds "chunks" from items — sections, stanzas, etc.
- Each chunk carries flags: `forceBreak`, `stickyToNext`, `noBreakBefore`, `separatorItemIdx`
- Binary search fits chunks onto pages respecting heights + break rules
- Section headings are sticky — they follow their first item to the next page rather than orphan

---

## API Routes (server.py)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/bootstrap` | GET | Startup config, public settings, mode |
| `/api/projects` | GET/POST/DELETE | Project CRUD |
| `/api/announcements` | GET/POST | Announcements bank |
| `/api/settings` | GET/POST | User settings (tokens, formatting, staff, calendar) |
| `/api/songs` | GET/POST | Song database |
| `/api/pdf` | POST | Generate PDF via headless Chrome |
| `/api/admin/check-update` | GET | Check GitHub for newer version |
| `/api/admin/trigger-update` | POST | Trigger Watchtower or desktop zip update |
| `/oauth/pco/start` | GET | Redirect to PCO OAuth consent |
| `/oauth/pco/callback` | GET | Exchange PCO auth code for tokens |
| `/oauth/google/start` | GET | Redirect to Google OAuth consent |
| `/oauth/google/callback` | GET | Exchange Google auth code for tokens |
| `/pco-proxy/*` | GET/POST | Authenticated proxy to PCO API |
| `/cal` | GET | Fetch + filter calendar events |

All API handlers are methods on `Handler` class in `server.py`. Routes dispatched in `do_GET` / `do_POST` via `startswith` matching.

---

## Server.py Internals

- Uses `threading.Lock()` (`_lock`) for all JSON file I/O
- `_read_json(path, default)` / `_write_json(path, data)` — atomic write via tmp file
- `_initialize_local_file()` — copies `.example.json` on first run
- `run_migrations()` — idempotent, tracks applied migrations in `migrations.json`
- `DATA_DIR` — points to `./data` (server) or `~/Library/Application Support/BulletinGenerator/` (desktop)

---

## Dev Workflow

```bash
# Run locally (no build step needed)
cp .env.example .env   # fill in PCO + Google OAuth creds
python3 server.py      # serves at http://localhost:8080

# JS/CSS changes: no rebuild — files served with Cache-Control: no-store

# Docker
docker compose up --build

# Build desktop .app
cp desktop_config.py.example desktop_config.py   # add OAuth creds
pyinstaller bulletin-generator.spec
# Output: dist/Bulletin Generator.app
```

---

## Common Gotchas

- **No framework**: server.py uses Python's stdlib `http.server`, not Flask/FastAPI. Route matching is manual `startswith` in `do_GET`/`do_POST`.
- **No JS bundler**: JS files are loaded directly via `<script>` tags in `index.html`. No webpack/vite.
- **Atomic writes**: Always use `_write_json()` in server.py — never write JSON files directly.
- **Mode checks**: Use `isServerMode()` in JS (not raw env checks). Use `IS_DESKTOP` / `APP_MODE` in Python.
- **409 errors**: `apiFetch()` sets `e.status` on thrown errors — check `err.status === 409`, not string matching.
- **Calendar empty vs auth failure**: `fetch_google_cal_events()` returns `None` on 401/403, `[]` on legitimately empty. Only retry token refresh on `None`.
- **rumps** is required for desktop menu bar — must be in PyInstaller spec and requirements.
