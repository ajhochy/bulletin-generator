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
  - `bulletingen://auth-callback` (issue 013 — Electron deep-link handler is now implemented;
    add this URL to the allow-list before running Electron auth smoke tests)
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

No self-serve workspace UI is planned for v1. Workspace access is seeded manually
or auto-provisioned via the domain allow-list (see section 7 below):

- Existing Visalia CRC users are inserted into `public.workspace_members` for
  the Visalia workspace by the workspace seed/migration script.
- New church testers are inserted into their own workspace by the same seed path.
- Auto-provisioning: if a new user's verified email domain appears in a
  workspace's `allowed_domains` list, they are automatically added as `editor`
  on first login (issue 008). See section 7 for how to manage that list.
- Never put authorization decisions in user-editable Supabase `user_metadata`.
  Membership must come from database rows or trusted app metadata.

Issue 005 is complete only after the dashboard validation above succeeds for
both Google OAuth and email magic links.

### 7. Managing the domain allow-list (issue 008)

After issue 008 lands, new users whose email domain is on the allow-list are
automatically provisioned as `editor` in the matching workspace on first login.

**Adding a domain to the allow-list**

Run as `service_role` (bypasses RLS) using psql or the Supabase SQL Editor
(Dashboard → SQL Editor → New query):

```sql
-- Replace <workspace-id> with the target workspace UUID and
-- <domain> with the lowercase domain string, e.g. 'visaliacrc.com'.
UPDATE public.workspace_settings
SET settings = jsonb_set(
    settings,
    '{allowed_domains}',
    COALESCE(settings->'allowed_domains', '[]'::jsonb) || to_jsonb('<domain>'::text)
)
WHERE workspace_id = '<workspace-id>'::uuid;
```

If no `workspace_settings` row exists yet for the workspace, insert one:

```sql
INSERT INTO public.workspace_settings (workspace_id, settings)
VALUES ('<workspace-id>'::uuid, '{"allowed_domains": ["<domain>"]}'::jsonb)
ON CONFLICT (workspace_id) DO UPDATE
SET settings = jsonb_set(
    workspace_settings.settings,
    '{allowed_domains}',
    COALESCE(workspace_settings.settings->'allowed_domains', '[]'::jsonb)
    || to_jsonb('<domain>'::text)
);
```

**Removing a domain from the allow-list**

```sql
UPDATE public.workspace_settings
SET settings = jsonb_set(
    settings,
    '{allowed_domains}',
    (
        SELECT jsonb_agg(d)
        FROM jsonb_array_elements_text(settings->'allowed_domains') AS d
        WHERE lower(d) != '<domain>'
    )
)
WHERE workspace_id = '<workspace-id>'::uuid;
```

**Verifying the current allow-list**

```sql
SELECT workspace_id, settings->'allowed_domains' AS allowed_domains
FROM public.workspace_settings
WHERE settings ? 'allowed_domains';
```

**Security notes**

- Domain matching is performed on the **verified JWT email claim** from Supabase
  Auth, not from user-editable `user_metadata`. The server derives the domain
  after the token signature is verified.
- `ON CONFLICT … DO NOTHING` in the provisioning INSERT means a race between two
  simultaneous first-logins from the same user is safe — the second insert is a
  no-op and the subsequent SELECT returns the already-inserted row.
- Auto-provisioned users receive the `editor` role. To grant `owner` or `viewer`,
  update the row manually after provisioning.

---

## Electron Auth Deep-Link Setup (Issue 013)

Issue 013 registers `bulletingen` as a custom URL protocol in the Electron
main process so OAuth and magic-link redirects can complete inside the app.
These manual steps must be done before running Electron auth smoke tests.

### 1. Add bulletingen://auth-callback to Supabase redirect allow-list

In Supabase Dashboard → `bulletin-generator` → Authentication → URL Configuration
→ Redirect URLs, add:

```
bulletingen://auth-callback
```

Without this entry Supabase will refuse to redirect to the custom protocol and
Google OAuth / magic-link flows will silently fail.

### 2. Smoke test: Google OAuth flow in Electron

1. `npm run start:electron` (dev mode, requires Python 3 + server.py deps in PATH).
2. On the login screen, click **Sign in with Google**.
3. The OS default browser should open the Google OAuth consent page.
4. Complete consent with a valid test Google account.
5. The OS routes the `bulletingen://auth-callback#...` redirect back to Electron.
6. The app window should come to the front and show the authenticated user in the
   nav bar (avatar + name + "Sign out" button).

### 3. Smoke test: magic-link flow in Electron

1. On the login screen, enter a test email address and click **Send magic link**.
2. A message "Check your email for a sign-in link." should appear.
3. Open the email in the OS default mail client and click the link.
4. The OS routes the `bulletingen://auth-callback#...` redirect back to Electron.
5. The app window should come to the front and show the authenticated user.

### 4. Smoke test: single-instance behaviour (Windows)

On Windows, open the app, then click a `bulletingen://` link from the browser.
The already-running app window should focus and the auth flow should complete.
A second Electron instance should not open.

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

## 🗂️ Supabase Data Migration (Issue 015)

Migrates the live Visalia CRC JSON data into the Supabase multi-tenant schema.

**Target workspace:** Visalia CRC (`614505d2-0f12-4c00-afb1-9077a0dc94fe`)
**Source data:** `/Volumes/docker/bulletingenerator/` (Synology NAS) or `./data/`
**Script:** `scripts/migrate_to_supabase.py`

### Prerequisites

1. The Supabase schema migrations must already be applied to the staging project:
   - `20260602000001_tenancy_foundation.sql`
   - `20260602000002_data_tables.sql`
2. `.env` must contain `SUPABASE_SERVICE_ROLE_URL` and `APP_MODE=server`.

### Step 1 — Verify source data counts

```bash
# Quick pre-flight: count records in source JSON files (no DB)
set -a && source .env && set +a
.venv/bin/python scripts/migrate_to_supabase.py \
  --source /Volumes/docker/bulletingenerator \
  --dry-run
```

Expected output shows row counts per table. Errors mean malformed JSON.

### Step 2 — Execute migration

When the dry-run output looks correct:

```bash
set -a && source .env && set +a
.venv/bin/python scripts/migrate_to_supabase.py \
  --source /Volumes/docker/bulletingenerator \
  --execute
```

The script is **idempotent** — re-running will not duplicate rows.
`ON CONFLICT DO NOTHING` on `projects`, `announcements`, and `songs`; merge on `workspace_settings`.

### Step 3 — Verify in Supabase Dashboard

1. Open Supabase Dashboard → `bulletin-generator` → Table Editor.
2. Confirm row counts in `projects`, `announcements`, `songs`, `workspace_settings`.
3. Check `workspace_settings` for the correct `workspace_id` and `settings` JSONB.

### Re-running is safe

The script uses `ON CONFLICT DO NOTHING` (or merge) for every table.
Running it again after a partial failure or a data re-upload will not create duplicates.

### Data-safety notes

- OAuth tokens (`pcoAccessToken`, `pcoRefreshToken`, `googleAccessToken`, `googleRefreshToken`)
  are **excluded** from the migration. They are secrets and must be re-issued for
  the multi-tenant deployment.
- The `SUPABASE_SERVICE_ROLE_URL` is never logged by the script.
- Source JSON files are never modified.

---

## 🚀 First-Run Server Setup

```bash
# 1. Start services
docker compose up -d

# 2. Check DB health
curl http://localhost:8080/api/health

# 3. Run Supabase data migration (see section above)
set -a && source .env && set +a
python scripts/migrate_to_supabase.py --source ./data --dry-run
python scripts/migrate_to_supabase.py --source ./data --execute

# 4. Verify migration
curl http://localhost:8080/api/health
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

---

## Electron Packaging + Auto-Update Setup (Issue 014)

The `release-electron.yml` workflow builds signed + notarized macOS DMG and
Windows NSIS installers via electron-builder when a version tag is pushed.
The following GitHub Secrets must be present in the repository before the
workflow runs.

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `CSC_LINK` | Base64-encoded Developer ID Application certificate (.p12) |
| `CSC_KEY_PASSWORD` | Password for the .p12 certificate |
| `APPLE_ID` | Apple ID email used for notarization (e.g. `you@example.com`) |
| `APPLE_ID_PASSWORD` | App-specific password for that Apple ID (generate at appleid.apple.com → App-Specific Passwords) |
| `APPLE_TEAM_ID` | Apple Developer Team ID (10-character string, e.g. `AB12CD34EF`) |
| `PCO_CLIENT_ID` | Planning Center OAuth client ID (same as used in the legacy .app build) |
| `PCO_CLIENT_SECRET` | Planning Center OAuth client secret |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |

`GITHUB_TOKEN` is provided automatically by GitHub Actions (no setup needed).

### How to export and encode the Developer ID certificate

1. Open **Keychain Access** on your Mac.
2. Find your **Developer ID Application** certificate (issued by Apple).
3. Right-click → **Export** → choose **.p12** format.
4. Set a strong export password — this becomes `CSC_KEY_PASSWORD`.
5. Base64-encode the .p12 file:
   ```bash
   base64 -i ~/Desktop/DeveloperID.p12 | pbcopy
   ```
6. Paste the clipboard contents as the `CSC_LINK` secret in GitHub:
   Settings → Secrets and variables → Actions → New repository secret.
7. Delete the .p12 file from your Desktop once the secret is saved.

### How to find your Apple Team ID

- Log in to [developer.apple.com](https://developer.apple.com/account) →
  Membership → Team ID (10-character alphanumeric).
- Alternatively: `xcrun altool --list-providers -u "$APPLE_ID" -p "$APPLE_ID_PASSWORD"`

### How to create an app-specific password (APPLE_ID_PASSWORD)

1. Go to [appleid.apple.com](https://appleid.apple.com) → Sign-In and Security
   → App-Specific Passwords → Generate.
2. Label it "bulletin-generator-ci" (or similar).
3. Add the generated password as the `APPLE_ID_PASSWORD` secret.

### Triggering a release

```bash
git tag v1.13.0
git push origin v1.13.0
```

Both `release.yml` (Docker + legacy PyInstaller .app) and `release-electron.yml`
(Electron DMG + Windows NSIS) run in parallel. GitHub Releases artifacts will
include both the legacy zip and the new DMG/.exe installers until the legacy
workflow is retired.

### Windows code signing (TODO)

The Windows job currently skips code signing (`signingHashAlgorithms: null` in
`package.json`). Windows SmartScreen will show an "Unknown publisher" warning
until a Windows code-signing certificate (EV or OV) is added. When a certificate
is obtained:

1. Add `CSC_LINK_WIN` and `CSC_KEY_PASSWORD_WIN` secrets (or reuse `CSC_LINK` if
   the certificate covers both platforms, which is uncommon).
2. Remove `"signingHashAlgorithms": null` from the `win` section in `package.json`.
3. Add the certificate env vars to the `electron-windows` job in
   `.github/workflows/release-electron.yml`.

### Note on launcher.py deprecation

`launcher.py` is now deprecated for desktop distribution. It is retained because:
- Docker server-mode does not use it but it lives in the repo root.
- Some developer tooling may reference it.

Do not delete `launcher.py` until all desktop users have migrated to the Electron
build and no tooling depends on it. See the deprecation comment at the top of
`launcher.py` for details.
