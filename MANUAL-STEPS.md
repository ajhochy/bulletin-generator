# Bulletin Generator — Manual Steps Required

This file collects every human-operator action that cannot be automated.
Complete these before or during smoke-testing the current migration branch.

---

## Supabase Auth Provider Setup (staging project)

Applies to staging project `dgydekhfzrmeoscpgmvo` (`https://dgydekhfzrmeoscpgmvo.supabase.co`).
This replaces the old app-login `AUTH_GOOGLE_*` flow when issues 006/007 wire
Supabase JWT verification and frontend token handling. Do not commit provider
secrets or SMTP credentials.

### 1. Configure Supabase Auth URL settings

In Supabase Dashboard → `bulletin-generator` → Authentication → URL Configuration:

- Set Site URL for the current web smoke target. For local staging before the
  Electron deep-link work, use the localhost URL that will host the app during
  issue 007 manual smoke, for example `http://localhost:8766`.
- Add Redirect URLs for every smoke target that will be passed as
  `redirectTo` / `emailRedirectTo`:
  - `http://localhost:8766`
  - `http://localhost:8766/auth/callback` if issue 007 adds a browser callback route
  - `bulletingen://auth-callback` only after issue 013 implements the Electron protocol handler
- Keep production URLs out until the production host is known.

### 2. Enable Google OAuth in Supabase Auth

In Google Cloud Console → APIs & Services → Credentials:

- Create or select an OAuth 2.0 Client ID of type `Web application`.
- Authorized JavaScript origins:
  - `https://dgydekhfzrmeoscpgmvo.supabase.co`
  - the current local smoke origin, for example `http://localhost:8766`
- Authorized redirect URI:
  - `https://dgydekhfzrmeoscpgmvo.supabase.co/auth/v1/callback`
- Save the Client ID and Client Secret.

In Supabase Dashboard → Authentication → Providers → Google:

- Enable Google.
- Paste the Google Client ID and Client Secret.
- Save.

Manual validation:

- Start a Google OAuth sign-in from the app or Supabase auth test page.
- Complete the flow with a test Google account.
- Confirm a session is issued and the user appears in Authentication → Users.

### 3. Enable email magic links

In Supabase Dashboard → Authentication → Providers → Email:

- Keep Email provider enabled.
- Use magic-link/passwordless sign-in for this migration phase.
- Keep the default one-hour OTP expiry unless product requirements change.
- Confirm the Magic Link email template uses the Supabase confirmation URL while
  issue 007 uses the implicit browser flow. If issue 007 adopts PKCE, update the
  template to send a token hash to the app callback route and exchange it there.

Manual validation:

- Request a magic link for a test email address.
- Click the email link.
- Confirm a Supabase session is issued and the user appears in Authentication → Users.

### 4. Configure custom SMTP or record staging fallback

Supabase's built-in mailer is a staging fallback only. Without custom SMTP,
delivery is restricted to project team addresses and rate-limited; this is not
usable for multi-church testing.

Before broader testing, choose an SMTP provider such as Resend, AWS SES, Postmark,
SendGrid, ZeptoMail, or Brevo. In Supabase Dashboard → Authentication → SMTP
Settings, configure:

- SMTP host
- SMTP port, usually `587`
- SMTP username
- SMTP password
- Sender email, for example `no-reply@auth.<domain>`
- Sender name, for example `Bulletin Generator`

Operational notes:

- Store SMTP credentials only in the Supabase dashboard or secret manager.
- Configure SPF, DKIM, and DMARC for the sending domain.
- Use a dedicated auth-mail domain/address, separate from marketing email.
- If custom SMTP is not ready, document that staging can test only with project
  team email addresses and is subject to Supabase built-in-mailer rate limits.

### 5. Enable leaked-password protection

In Supabase Dashboard → Authentication → Security / Password Security:

- Enable leaked-password protection if the project plan supports it.
- If unavailable on the current Supabase plan, record this as a production
  blocker before enabling password-based login. Google OAuth and magic links are
  still the intended v1 login methods, but the security advisor already flagged
  this toggle.

### 6. Workspace membership strategy for v1

No self-serve workspace UI is planned for v1. Workspace access is seeded manually:

- Existing Visalia CRC users are inserted into `public.workspace_members` for
  the Visalia workspace by the workspace seed/migration script.
- New church testers are inserted into their own workspace by the same seed path.
- Domain allow-list enforcement is deferred to issue 008. The allow-list source
  should be either a dedicated invite/allow-list table or a documented key in
  `workspace_settings`; decide before coding issue 008.
- Never put authorization decisions in user-editable Supabase `user_metadata`.
  Membership must come from database rows or trusted app metadata.

Issue 005 is complete only after the dashboard validation above succeeds for
both Google OAuth and email magic links.

---

## Legacy Collab-v1 Google OAuth Setup (pre-Supabase Auth)

This section documents the old `auth.py` app-login flow. It remains useful for
understanding the branch history, but it is superseded by the Supabase Auth setup
above for the current migration.

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
