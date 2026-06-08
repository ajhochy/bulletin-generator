# Architecture Notes

## Deployment Modes

This project supports two first-class deployment modes from one codebase.

### Desktop Mode

- packaged local app
- optimized for single-user installs and testing
- local data storage (JSON files in `~/Library/Application Support/BulletinGenerator/`)
- simple onboarding
- no required multi-user collaboration features
- updates should come from app releases, not raw Git operations

### Server Mode

- shared self-hosted deployment (Docker)
- browser access for multiple users
- Supabase Postgres + Supabase Storage for all application data
- Supabase Auth for user authentication (Google OAuth and email magic links)
- ownership model with presence heartbeat and read-only mode for non-owners
- admin-only deployment/update controls
- updates via Watchtower sidecar

---

## collab-v1 Server Architecture

### Storage Layer (`storage.py`)

All route handlers in `server.py` call a `StorageBackend` interface rather than reading or writing files directly. The concrete implementation is chosen at startup based on `APP_MODE`:

- `JsonStorageBackend`: reads/writes JSON files in `DATA_DIR`. Used in desktop mode and local dev.
- `PostgresStorageBackend`: reads/writes Supabase Postgres. Used in server mode (`APP_MODE=server`).

Call `get_storage()` to obtain the active backend. The interface covers projects, settings, announcements, songs, templates, and font metadata.

**What is stored in Supabase (server mode):**

| Store | Table / bucket | Contents |
|-------|---------------|----------|
| Postgres | `projects` | All bulletin projects, with visibility and owner info |
| Postgres | `project_revisions` | Full revision history for every project save |
| Postgres | `workspace_settings` | Per-workspace settings (OAuth tokens, calendar config, etc.) |
| Postgres | `announcements` | Announcement bank |
| Postgres | `songs` | Song database |
| Postgres | `templates` | Bulletin layout templates |
| Postgres | `fonts` | Font file metadata (family name, MIME type, Storage path) |
| Postgres | `workspaces` | Workspace records |
| Postgres | `workspace_members` | Member roles within each workspace |
| Postgres | `workspace_presences` | Active editor presence heartbeats |
| Storage | `project-assets` | Cover images and staff logo images (uploaded on first save) |
| Storage | `workspace-fonts` | User-uploaded font binary files |
| Supabase Auth | — | User accounts and sessions |

**What stays on disk:**

- `data/backups/` — migration backup output (created by `scripts/backup.sh` and the migration script)
- Desktop mode: all editable JSON files (no Postgres or Storage)

In server mode, `data/fonts/` is **not** used. Font binaries are stored in the Supabase Storage `workspace-fonts` bucket.

### Auth Layer (`auth.py`)

Server mode uses **Supabase Auth** for user authentication. The frontend receives
a Supabase access token (JWT) and sends it as `Authorization: Bearer <token>` on
every API request. `auth.py` verifies the token signature using `SUPABASE_JWT_SECRET`.

- `SUPABASE_URL` — project URL, used to fetch the JWKS for token verification
- `SUPABASE_JWT_SECRET` — signing secret (HS256), used as a fallback verifier

The old `auth.py` Google-OpenID-Connect app-login flow (`/auth/google/login`,
`/auth/google/callback`, `AUTH_GOOGLE_*` env vars, `GOOGLE_WORKSPACE_DOMAIN`,
`sessions` table) is **disabled**. Those routes return 404. Supabase Auth handles
Google OAuth and email magic-link flows from the client side.

**Google OAuth flows:**

| Flow | Configured via | Scopes | Callback path |
|------|---------------|--------|---------------|
| User login | Supabase Dashboard only | `openid email profile` | Supabase-managed |
| Calendar/Drive integration | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` in `.env` | `calendar drive` | `APP_URL/oauth/google/callback` |

The Calendar/Drive OAuth callback path in `server.py` also signs and verifies a
workspace id into the OAuth `state` parameter using HMAC-SHA256
(`OAUTH_STATE_SECRET` → `SUPABASE_JWT_SECRET` → client secret fallback), so a
token connecting PCO/Google in workspace B cannot land in workspace A.

### Project Visibility Model

All projects are **workspace-visible by default** — `save_project` always
inserts `visibility='workspace'`. There is no private/share toggle. Editing is
gated by ownership, and **hand-off** (`POST /api/projects/{id}/transfer`)
reassigns the sole editor. The `'private'` column default is vestigial.

`storage.list_projects(user_id=...)` returns only projects the requesting user
can see within the caller's workspace. When `workspace_id` is `None`
(admin/migration paths), all projects are returned.

### Ownership and Presence Model

- **Owner-only writes**: `POST /api/projects` returns 403 for non-owners. Frontend shows a toast.
- **Read-only mode**: Non-owners see a banner with a Duplicate button. Autosave is suppressed.
- **Duplicate**: Creates a new project owned by the current user.
- **Hand-off**: `POST /api/projects/{id}/transfer` transfers ownership to another workspace member.
- **Presence**: `POST /api/presence/heartbeat` (30 s), `GET /api/presence`, `DELETE /api/presence`. Best-effort; errors are swallowed.

Conflict detection and `_clientRevision` have been **removed**. No 409 responses are generated.

### Revision History

Every project save appends a row to `project_revisions`:

- `revision` — monotonically incrementing integer
- `summary` — human-readable description of what changed (generated by `revisions.py`)
- `updated_by_email`, `updated_by_user_id` — attribution

### Migration Pipeline (`scripts/`)

`scripts/migrate_to_supabase.py` is the operator entry point for importing
legacy JSON data into the Supabase multi-tenant schema.

**What it migrates:**

| JSON file | Postgres table |
|-----------|---------------|
| `data/projects.json` | `projects` |
| `data/announcements.json` | `announcements` |
| `data/settings.json` | `workspace_settings` |
| `data/song_database.json` | `songs` |
| `data/templates.json` | `templates` |

OAuth tokens (`pcoAccessToken`, `pcoRefreshToken`, `googleAccessToken`,
`googleRefreshToken`) are **excluded** — they are secrets and must be re-issued
after migration.

Font binaries are **not** migrated by this script. After migration, upload fonts
via the app UI; they will be stored in the `workspace-fonts` Storage bucket.

**Commands:**

```bash
set -a && source .env && set +a

# Dry run (no writes):
APP_MODE=server .venv/bin/python scripts/migrate_to_supabase.py \
  --source ./data --dry-run

# Execute:
APP_MODE=server .venv/bin/python scripts/migrate_to_supabase.py \
  --source ./data --execute
```

All importers are idempotent — re-running skips records that already exist in Postgres.

## Guiding Principle

Keep one repository and one core application, but allow mode-specific behavior where the product needs differ.

Do not split the project into separate repos unless the codebases diverge significantly.

## Feature Scoping

Use runtime configuration to gate mode-specific behavior.

Example:

- `APP_MODE=desktop`
- `APP_MODE=server`

Features that should usually be mode-specific:

### Desktop-first

- packaging/installer flow
- release-based update flow
- local file import/export helpers
- single-user assumptions

### Server-first

- multi-user attribution
- stale document detection
- revision/conflict protection
- admin-managed update tools
- future account infrastructure

### Shared Core

- bulletin editing
- PCO import
- Google Calendar integration
- formatting templates
- song database management
- rendering and PDF generation

## Server Mode: Data Directory Layout

The repo's `docker-compose.yml` bind-mounts `./data:/app/data`. In the current
Supabase architecture, this directory holds only migration output:

- `data/backups/` — timestamped pg_dump output from `scripts/backup.sh`

Live application data (projects, songs, fonts, images) is stored entirely in
Supabase Postgres and Supabase Storage — nothing is written to `./data` during
normal operation.

**The Synology NAS production deployment uses a different host path: `./app/data:/app/data`.** The container side (`/app/data`) is identical; only the host side differs because of how the NAS organizes the stack's working directory. Do **not** "fix" the repo's `./data:/app/data` to match the NAS.

## GitHub Organization

Issues are organized with:

### Mode labels

- `mode:desktop`
- `mode:server`
- `mode:both`

### Area labels

- `area:deployment`
- `area:collaboration`
- `area:editor`
- `area:formatting`
- `area:integrations`
- `area:song-db`

### Milestones

- `Desktop MVP`
- `Server MVP`
- `Shared Core`

## Current Planning Rule

When adding a new issue:

1. Decide whether it applies to desktop mode, server mode, or both.
2. Add the most relevant `area:*` label.
3. Assign it to the matching milestone.

If a feature only solves shared multi-user needs, it should usually be `mode:server`.
If a feature only affects packaging or local install/update behavior, it should usually be `mode:desktop`.

