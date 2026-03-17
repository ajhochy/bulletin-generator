# Bulletin Generator

This repo is prepared for a public GitHub upload. Source code and safe example data are committed. Real ministry data, local settings, exported files, and secrets stay local.

## Public repo layout

- `server.py`, `worship-booklet.html`, `Dockerfile`, `docker-compose.yml`: application source
- `data/*.example.json`: sanitized starter data committed to Git
- `.env.example`: starter environment configuration committed to Git
- `data/*.json`, `.env`, exported song databases, and other machine-local files: ignored and kept out of Git

## First-time setup

1. Copy the environment file:

```bash
cp .env.example .env
```

2. Review and update `.env` with your local values:
   `PCO_APP_ID` and `PCO_SECRET` for Planning Center access
   `CALENDAR_ICAL_URLS` and `CALENDAR_EXCLUDE_TITLES` if you want default calendar feeds

3. Start the app once. On startup, the server will create local working files in `data/` from the committed `*.example.json` files if the local files do not already exist.

4. Optionally replace the generated local files with your own copies:

```bash
cp data/announcements.example.json data/announcements.json
cp data/projects.example.json data/projects.json
cp data/settings.example.json data/settings.json
```

## What is committed

- Application code
- Safe example data
- Documentation and ignore rules

## What stays local

- `.env` and any secret-bearing env files
- Real `data/*.json` working files
- Planning Center debug exports
- exported song database files such as `song-database.json`
- editor and OS artifacts like `.DS_Store`, `__MACOSX`, `.vscode/`, `.idea/`

## Secret handling

Planning Center credentials are now server-side only.

- Set `PCO_APP_ID` and `PCO_SECRET` in `.env`
- Restart the server after changing them
- The frontend no longer stores Planning Center credentials in `localStorage`
- The server injects Planning Center auth when proxying `/pco-proxy/*`

## Data handling

- Treat `data/*.json` as private local state
- Commit only `data/*.example.json`
- Use the example files as templates for local working copies

## Docker

`docker-compose.yml` expects a local `.env` file for runtime secrets. `.dockerignore` excludes `.env` and live `data/*.json` so secrets and local content are not baked into the image.
