# Collaboration V1: Postgres, Google Auth, and Workspace Sharing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move server mode from shared JSON files to authenticated, per-user project ownership with explicit workspace sharing, revision history, and a safe migration path for old data.

**Architecture:** Desktop mode keeps the current local file-backed behavior. Server mode uses Postgres for structured app data, Google Workspace OAuth for identity, and transactional project saves with optimistic revision checks. Large binary/font files remain on disk for v1, with Postgres storing metadata and paths.

**Tech Stack:** Python `http.server` app, vanilla JS frontend, Docker Compose, Postgres 16, psycopg 3 or equivalent Python driver, signed HTTP-only session cookies, Google OAuth 2.0 / OpenID Connect.

---

## Current State Summary

- `server.py` reads and writes `data/projects.json`, `data/announcements.json`, `data/settings.json`, `data/song_database.json`, and `data/templates.json`.
- Server mode already has coarse project revision conflict protection using `project.revision` and `_clientRevision`.
- Google OAuth currently stores one shared server token in `settings.json`; it is used for Calendar and Drive, not for app login.
- Frontend startup currently loads the remembered active project, then falls back to the newest server project, which can surprise users in a shared deployment.
- Desktop and server mode are already separate concepts through `APP_MODE`.

## Target Data Ownership

### Move to Postgres in server mode

- Users and sessions.
- Projects, project ownership, visibility, current state, current revision.
- Project revision snapshots and audit metadata.
- Organization-level settings currently in `settings.json`.
- Per-user settings split out of current global settings where needed.
- Announcements.
- Song database.
- Templates and template metadata.
- Font metadata.
- Migration bookkeeping and import status.

### Keep on filesystem in server mode

- Uploaded font binary files under `data/fonts/user`.
- Cached Google Font CSS and downloaded font assets under `data/fonts/cache`.
- Optional exported PDFs/ZIPs if future work persists generated output.

### Keep JSON/local files in desktop mode

- Existing desktop behavior for projects, settings, announcements, songs, templates, and fonts.
- No required Google login in desktop mode.

## Proposed Postgres Tables

```sql
users (
  id uuid primary key,
  google_sub text unique not null,
  email text unique not null,
  display_name text not null,
  avatar_url text,
  domain text not null,
  last_login_at timestamptz not null,
  created_at timestamptz not null
)

sessions (
  id uuid primary key,
  user_id uuid not null references users(id) on delete cascade,
  token_hash text unique not null,
  expires_at timestamptz not null,
  created_at timestamptz not null
)

projects (
  id text primary key,
  name text not null,
  owner_user_id uuid references users(id),
  owner_email text,
  visibility text not null check (visibility in ('private', 'workspace')),
  state jsonb not null,
  revision integer not null,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  created_by_user_id uuid references users(id),
  updated_by_user_id uuid references users(id),
  imported_from_json boolean not null default false
)

project_revisions (
  id bigserial primary key,
  project_id text not null references projects(id) on delete cascade,
  revision integer not null,
  state jsonb not null,
  saved_at timestamptz not null,
  saved_by_user_id uuid references users(id),
  saved_by_email text,
  saved_by_name text,
  summary text not null,
  unique(project_id, revision)
)

org_settings (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null,
  updated_by_user_id uuid references users(id)
)

user_settings (
  user_id uuid not null references users(id) on delete cascade,
  key text not null,
  value jsonb not null,
  updated_at timestamptz not null,
  primary key (user_id, key)
)

announcements (
  id text primary key,
  title text not null,
  body text not null,
  url text not null,
  sort_order integer not null,
  updated_at timestamptz not null,
  updated_by_user_id uuid references users(id)
)

songs (
  id text primary key,
  title text not null,
  author text not null,
  lyrics text not null,
  copyright text not null,
  source text,
  date_added timestamptz,
  updated_at timestamptz not null,
  updated_by_user_id uuid references users(id)
)

templates (
  id text primary key,
  name text not null,
  built_in boolean not null,
  template jsonb not null,
  owner_user_id uuid references users(id),
  visibility text not null check (visibility in ('workspace')),
  updated_at timestamptz not null,
  updated_by_user_id uuid references users(id)
)

fonts (
  slug text primary key,
  family text not null,
  source text not null check (source in ('user', 'cache')),
  css_url text not null,
  file_path text,
  metadata jsonb not null default '{}'::jsonb,
  uploaded_at timestamptz,
  uploaded_by_user_id uuid references users(id)
)

data_migrations (
  id text primary key,
  applied_at timestamptz not null,
  details jsonb not null default '{}'::jsonb
)
```

## JSON File Handling Plan

- `projects.json`: migrate into `projects` and initial `project_revisions`. Existing projects become `visibility='workspace'` by default because they previously lived in the shared server shelf. `owner_user_id` is null unless `createdBy` / `updatedBy` can be mapped to a known user later.
- `announcements.json`: migrate into `announcements`. Treat as workspace-level shared content for v1.
- `settings.json`: split into `org_settings` and `user_settings`.
  - Organization settings: church name, staff data, serving team filters, type formats, doc template, default give URL, calendar URL fallback/exclude defaults, Google Drive shared folder ID if the deployment continues using a shared Drive export connection.
  - Per-user settings: editor display name legacy value, selected Google calendars if app integrations become per-user, personal OAuth tokens if retained.
  - Secrets/tokens: avoid storing OAuth tokens in generic settings long term; move shared integration tokens into dedicated secure rows or keep them file-backed until the auth split is designed.
- `song_database.json`: migrate into `songs`. Treat as workspace-level shared content for v1, because the song database is currently global.
- `templates.json`: migrate into `templates`. Built-ins remain protected. User-created templates become workspace-visible for v1 to match current shared behavior.
- `fonts/`: keep files on disk; insert rows in `fonts` for discoverability and audit. Migration scans existing `data/fonts/user/*` and `data/fonts/cache/*`.
- `migrations.json`: replace with `data_migrations` in server mode; keep `migrations.json` for desktop mode.

## Milestones and Atomic GitHub Issues

### Milestone 1: Collaboration V1 - Server Postgres Foundation

1. Add Postgres service and server environment configuration.
2. Add Python database dependency and connection helper.
3. Add schema migration runner and `data_migrations` table.
4. Add storage boundary so server routes stop directly reading JSON in server mode.
5. Add health/readiness endpoint for database-backed server mode.

### Milestone 2: Collaboration V1 - JSON Data Migration

6. Migrate projects JSON into Postgres with workspace visibility.
7. Migrate settings JSON into org/user settings.
8. Migrate announcements JSON into Postgres.
9. Migrate song database JSON into Postgres.
10. Migrate templates JSON into Postgres.
11. Inventory font files into Postgres while keeping binaries on disk.
12. Add backup, dry-run, and idempotency support for migrations.

### Milestone 3: Collaboration V1 - Google Workspace Login

13. Add separate app-login Google OAuth flow.
14. Restrict login to `@visaliacrc.com`.
15. Add signed server sessions and `/api/me`.
16. Protect server-mode API routes behind login.
17. Add frontend login/logout shell.
18. Split app identity from existing Calendar/Drive integration identity.

### Milestone 4: Collaboration V1 - Private and Workspace Projects

19. Add owner and visibility fields to project API responses.
20. Default new projects to private owner workspace.
21. Add "Share to Workspace" endpoint and UI.
22. Replace startup newest-project fallback with user-safe restore behavior.
23. Add Files page views for My Projects and Workspace Projects.
24. Enforce project visibility in list/load/save/delete routes.

### Milestone 5: Collaboration V1 - Revision History and Conflict UX

25. Make project saves transactional with optimistic revision checks.
26. Append full revision snapshots and audit metadata on each save.
27. Generate high-level change summaries for revision records.
28. Add project history API and restore endpoint.
29. Replace current conflict banner with Review latest / Save as my copy / Replace with latest.
30. Add shared-project stale polling using authenticated user metadata.

### Milestone 6: Collaboration V1 - Shared Data, Hardening, and Release

31. Route announcements, songs, templates, settings, and fonts through Postgres storage in server mode.
32. Add authorization and regression tests for all migrated APIs.
33. Add migration tests using representative legacy JSON fixtures.
34. Update Docker, `.env.example`, README, and architecture docs.
35. Add an admin backup/export command for Postgres data.
36. Run end-to-end server-mode QA with two signed-in users.

## Acceptance Criteria

- A user with `@visaliacrc.com` can sign in and access the server app.
- A non-`@visaliacrc.com` Google account is rejected.
- New projects are private to the signed-in user.
- A private project can be shared to the workspace.
- Workspace projects are visible and editable by every signed-in workspace user.
- Private projects are not visible to other users.
- Concurrent saves cannot silently overwrite another user's changes.
- Conflict UI lets a user preserve their work as a private copy.
- Every workspace save records who saved it, when, revision number, full snapshot, and high-level summary.
- Existing `projects.json`, `settings.json`, `announcements.json`, `song_database.json`, `templates.json`, and font directories migrate without data loss.
- Desktop mode still runs without Postgres and keeps local file-backed behavior.

