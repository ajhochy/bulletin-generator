# Stale draft beta crashed a real download (Exit code 1) — release hygiene

**Date:** 2026-07-22
**Context:** issue — user-reported desktop crash

## Symptom

AJ downloaded the release at `releases/tag/untagged-23515b698d8258690af4`
(= draft `electron-supabase-beta-v0.0.4`, built 2026-06-04) and got:

> Bulletin Generator — Server Error
> The background server stopped unexpectedly. Exit code: 1
> The app will now quit.

## Root cause (reproduced)

Ran the packaged sidecar directly
(`/Applications/Bulletin Generator.app/Contents/Resources/server 8765`,
`APP_MODE=electron`) and captured the traceback:

```
run_server → _public_config → _get_settings → storage.get_settings
  → db.transaction → get_connection → psycopg.connect
psycopg.OperationalError: connection failed ...
FATAL: (ENOTFOUND) tenant/user postgres.dgydekhfzrmeoscpgmvo not found
```

That beta's **old** `server.py` connected to Postgres at startup (to log
`pcoConfigured`) **before** binding the port, and the bundled `.env` carried a
`DATABASE_URL` for a Supabase tenant that has since been deleted/rotated. The
connect failure was uncaught → exit code 1 → Electron's crash dialog. It is not
the port-in-use path (that exits 3).

## Why current `main` is NOT affected

- `storage.get_storage()` returns `JsonStorageBackend` in electron mode
  (`is_desktop = app_mode in ("desktop", "electron")`) — the sidecar never
  opens a Postgres connection. `PostgresStorageBackend` is server-mode only.
- `run_server()` binds the port first; `_public_config()` runs after the bind
  and reads only local settings in desktop/electron mode.
- `release-electron.yml` no longer bundles `DATABASE_URL` (#277-F); the `.env`
  write step embeds only PCO/Google client creds + `SUPABASE_URL`/anon key.

## Decision / actions

- Deleted the draft releases `electron-supabase-beta-v0.0.4` and `v0.0.0`, and
  removed the 4 stale `electron-supabase-beta-v0.0.1..4` git tags (remote+local).
- Pushed `electron-supabase-beta-v0.0.5` off `main` to produce a clean,
  signed/notarized build (macOS arm64 + x64, Windows NSIS).
- Filed a task to rotate the Supabase DB password: the leaked v0.0.4 DMG
  contained owner-role `DATABASE_URL` creds (RLS-bypassing). Tenant currently
  reads "not found", but rotate to be safe if it exists anywhere.

## Lesson

Old draft betas that bundle credentials are both a security risk and a crash
risk once the backing resource is rotated. Prune draft betas promptly and
always hand users the newest published release, not a lingering draft URL.
