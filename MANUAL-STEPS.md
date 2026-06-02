# Collab v1 — Manual Steps Required

This file collects every human-operator action that cannot be automated.
Complete these before or during smoke-testing the collab-v1 branch (PR #250).

---

## 🔐 Google OAuth Setup (required before any server-mode login works)

These must be done in [Google Cloud Console](https://console.cloud.google.com/apis/credentials):

### 1. App Login OAuth Client (AUTH_GOOGLE_*)
- Create a new **OAuth 2.0 Client ID** (type: Web application)
- Set authorized redirect URI: `https://<your-domain>/auth/google/callback`
  - For local testing: `http://localhost:8080/auth/google/callback`
- Copy **Client ID** → set as `AUTH_GOOGLE_CLIENT_ID` in `.env`
- Copy **Client Secret** → set as `AUTH_GOOGLE_CLIENT_SECRET` in `.env`
- Set `AUTH_GOOGLE_REDIRECT_URI=https://<your-domain>/auth/google/callback` in `.env`

### 2. Calendar & Drive Integration OAuth Client (GOOGLE_CLIENT_ID)
- This is the **existing** Google OAuth client for calendar/drive integration
- Add authorized redirect URI: `https://<your-domain>/oauth/google/callback`
  - For local testing: `http://localhost:8080/oauth/google/callback`
- Ensure `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env` match this client

### 3. Set Workspace Domain Restriction
In `.env`, set:
```
GOOGLE_WORKSPACE_DOMAIN=visaliacrc.com
```
This restricts app login to `@visaliacrc.com` accounts only. Only users from this domain can sign in.

---

## 🔗 PCO OAuth Setup

In [Planning Center Developer Portal](https://api.planningcenteronline.com/oauth/applications):
- Add redirect URI: `https://<your-domain>/oauth/pco/callback`
  - For local testing: `http://localhost:8080/oauth/pco/callback`

---

## 🔑 Set Secrets in .env

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

Required for server mode:
```
# Postgres
POSTGRES_PASSWORD=<strong-random-password>
POSTGRES_USER=bulletin
POSTGRES_DB=bulletindb
DATABASE_URL=postgresql://bulletin:<POSTGRES_PASSWORD>@postgres:5432/bulletindb

# App Login (NEW — see step 1 above)
AUTH_GOOGLE_CLIENT_ID=<from-google-cloud-console>
AUTH_GOOGLE_CLIENT_SECRET=<from-google-cloud-console>
AUTH_GOOGLE_REDIRECT_URI=https://<your-domain>/auth/google/callback
GOOGLE_WORKSPACE_DOMAIN=visaliacrc.com

# Calendar & Drive (existing)
GOOGLE_CLIENT_ID=<existing-client-id>
GOOGLE_CLIENT_SECRET=<existing-client-secret>
GOOGLE_REDIRECT_URI=https://<your-domain>/oauth/google/callback

# Session security
SESSION_SECRET=<64-char-random-hex>   # generate: python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 🚀 First-Run Server Setup

```bash
# 1. Start services
docker compose up -d

# 2. Check DB health
curl http://localhost:8080/api/health

# 3. Dry-run migration (verify counts before writing)
docker compose exec app python -m migrations.run_all_migrations --dry-run

# 4. Run migration (imports all legacy JSON data)
docker compose exec app python -m migrations.run_all_migrations

# 5. Verify migration backup was created
ls data/backups/
```

---

## 🗄️ Database Backup

After migration and periodically during operation:

```bash
# Bare server
export DATABASE_URL='postgresql://bulletin:<password>@localhost:5432/bulletindb'
./scripts/backup.sh

# Docker Compose
export DATABASE_URL='postgresql://bulletin:<password>@postgres:5432/bulletindb'
./scripts/backup-compose.sh
```

Backups go to `data/backups/YYYYMMDD_HHMMSS/` and include:
- `db.dump` — full Postgres dump (restorable with `pg_restore`)
- `fonts/` — user-uploaded and cached font files

**Prerequisite:** `postgresql-client` must be installed on the host (`pg_dump`/`pg_restore` tools).

---

## 🌐 Browser Manual Testing (QA Checklist — Issue #226)

Perform these tests with **two different `@visaliacrc.com` Google accounts** in separate browser profiles.

### Auth & Login
- [ ] Sign in with a `@visaliacrc.com` account → lands in the app with name shown in navbar
- [ ] Sign in with a non-`@visaliacrc.com` account → sees "Access denied" page, no cookie set
- [ ] Sign out → login screen reappears, app content hidden
- [ ] Unauthenticated `GET /api/projects` → 401 JSON response (verify in devtools)

### Desktop Mode
- [ ] Start with `APP_MODE=desktop` (no `APP_MODE=server`) → login screen does NOT appear, app loads normally

### Project Isolation (two-user)
- [ ] **User A** creates a new project → it appears in "My Projects" as private (lock badge)
- [ ] **User B** cannot see User A's private project in the Files list
- [ ] **User A** shares project to Workspace → it moves to "Workspace" tab
- [ ] **User B** can now see and edit the shared project

### Startup Restore
- [ ] **Fresh browser (incognito)** in server mode → lands on blank draft, not someone else's project
- [ ] Reload after working on a project → same project restores
- [ ] Delete the remembered project in another session → reload shows "Previous project not available" info, not an error

### Conflict UX (two tabs, same workspace project)
- [ ] Tab A edits and saves. Tab B edits (without reloading). Tab B saves → conflict dialog appears
- [ ] "Review latest" shows a summary of the server version inline
- [ ] "Save as my copy" creates a new private project with Tab B's work
- [ ] "Replace with latest" reloads the server version after confirmation

### Stale Banner (two users, same workspace project)
- [ ] User B saves a workspace project. Within 30 seconds User A sees "Updated by <B email> · Xm ago" banner
- [ ] "Reload latest" reloads and clears the banner
- [ ] "Dismiss" hides the banner without reloading

### Revision History
- [ ] After multiple saves, `GET /api/projects/{id}/history` returns revision list with summaries
- [ ] Restoring an old revision creates a new revision on top (history not deleted)

### Migrated Data
- [ ] Announcements editor loads the same content after migration
- [ ] Song database UI shows migrated songs
- [ ] Built-in templates (Classic, Modern) are available and cannot be deleted
- [ ] Custom templates from legacy data are available
- [ ] Uploaded fonts still render in the preview

### Health Endpoint
- [ ] `GET /api/health` returns `{status: "healthy", mode: "server", database: {connected: true}}`
- [ ] `GET /api/health` in desktop mode returns `{status: "healthy", mode: "desktop"}` (no DB fields)

---

## 🔄 Rollback Plan (if migration fails)

```bash
# 1. Stop the app
docker compose down

# 2. Restore JSON files from backup
cp data/backups/<TIMESTAMP>/projects.json data/projects.json
cp data/backups/<TIMESTAMP>/settings.json data/settings.json
# ... repeat for announcements, songs, templates

# 3. Restore Postgres from dump
export DATABASE_URL='postgresql://bulletin:<password>@localhost:5432/bulletindb'
./scripts/restore.sh data/backups/<TIMESTAMP>

# 4. Restart
docker compose up -d
```

---

## ℹ️ Notes on What's Not Automated

- **Issue #226** (two-user end-to-end QA) is entirely manual — see the Browser Manual Testing section above.
- **Integration tests** against a live Postgres instance require `DATABASE_URL` set and the schema migrated. Run with:
  ```bash
  DATABASE_URL=postgresql://... APP_MODE=server pytest tests/ -m integration
  ```
- **Font binaries** remain on disk (not in Postgres). Postgres only stores font metadata.
- **OAuth tokens** (PCO, Google Calendar) are temporarily stored in `org_settings` under key `oauth_tokens`. A dedicated secrets store migration is planned for a future release.
- **Session secret** (`SESSION_SECRET`) should be rotated if the server is compromised — this invalidates all active sessions.
