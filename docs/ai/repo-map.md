# Repo Map

See `CLAUDE.md` "Key Files" table for the full annotated list. This file is a quick orientation index for grep targets.

## Top-level

- `server.py` — Python stdlib `http.server`, all API routes, OAuth, PDF gen, ~1,485 lines.
- `launcher.py` — macOS desktop launcher + menu bar (rumps). **Deprecated** — Electron replaces this (issue 014 will remove it).
- `index.html` — single-page shell, loads `src/js/*` directly via `<script>` tags. No bundler.
- `bulletin-generator.spec` — PyInstaller spec for `.app` build.
- `docker-compose.yml` — server-mode container + Watchtower sidecar.
- `requirements.txt`, `desktop_config.py(.example)`, `.env(.example)`.

## `electron/`

- `electron/main.js` — Electron main process. Spawns `server.py` sidecar (dev: `python3 server.py 8765`; packaged: `<resourcesPath>/server`). Opens BrowserWindow to `http://localhost:8765/`. Tray icon. Kills sidecar on quit. Error dialog on crash.
- `electron/preload.js` — Minimal preload. contextIsolation=true, nodeIntegration=false. No APIs exposed to renderer (HTTP-only to sidecar).

## `src/js/` (no bundler — files served as-is, `Cache-Control: no-store`)

| File | Owns |
|---|---|
| `app.js` | Entry point, tab switching, init |
| `state.js` | Global state, page-size presets, localStorage keys, type formats |
| `api.js` | `apiFetch`, server-settings cache, mode detection |
| `projects.js` | Save/load/delete, 409 conflict detection, autosave |
| `editor.js` | Cover/logo, church name, item list rendering, page breaks |
| `preview.js` | Live preview + page-split algorithm + print-ready HTML |
| `formatting.js` | Per-item / per-type formatting; `getEffectiveFmt(item)` |
| `pco.js` | Planning Center OAuth + service plan import |
| `songs.js` | Song DB, title normalization, ProPresenter matching |
| `propresenter.js` | Minimal `.pro6library` protobuf + RTF extraction |
| `calendar.js` | iCal + Google Calendar OAuth/fetch/filter |
| `announcements.js` | Announcement cards, formatting, page-break toggles |
| `volunteer-roles.js` | Volunteer Roles cards UI (editor side panel) |
| `staff.js` | Staff page rendering, role display, email linking |
| `text-renderer.js` | Markdown → HTML, lyric/copyright splitting |
| `update.js` | GitHub version check, Watchtower / desktop update UI |
| `templates.js` | **Template Gallery + Template Designer canvas**. `inferCanvasElement()` maps DOM clicks → `{ binding, elementKey }`. `TPL_SELECTABLE_SELECTOR` is the click-delegation selector. Adding a new previewable section requires updating both. |
| `utils.js` | Timestamps, status notifications, DOM helpers |

## `data/`

Runtime JSON (NOT committed): `projects.json`, `settings.json`, `announcements.json`, `song_database.json`, `migrations.json`. Their `.example.json` siblings ARE committed.

## `docs/`

- `docs/ARCHITECTURE.md` — deployment-mode notes + GitHub label strategy.
- `docs/ai/*` — agent memory (this folder).
- `docs/testing/` — manual smoke checklists (when present).

## Common search terms

- `binding:` — selectable-element registry entries in `templates.js`.
- `ZONE_RENDERERS` / `DEFAULT_PREVIEW_ZONE_ORDER` — preview zone registry in `preview.js`.
- `_write_json` — atomic JSON write helper in `server.py`.
- `_clientRevision` — server-side conflict detection.
- `isServerMode()` — JS mode check; `APP_MODE` / `IS_DESKTOP` in Python.

## Generated / ignored

`dist/`, `build/`, `__pycache__/`, `data/*.json` (not `.example.json`), `.env`, `desktop_config.py`.
