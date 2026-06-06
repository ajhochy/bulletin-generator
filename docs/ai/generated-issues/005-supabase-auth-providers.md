# 005: Configure Supabase Auth providers

**Milestone:** M2  ·  **Plan ref:** issue 9
**Depends on:** none (dashboard configuration, no code dependency; can run in parallel with M1)

## Context

`auth.py` (from `collab-v1`) implements Google-OAuth-only authentication against a single hard-coded domain (`visaliacrc.com`). The plan (D3) replaces it with Supabase Auth: Google OAuth and email magic link, with a per-workspace domain allow-list strategy replacing the hard-coded domain. Before server-side JWT verification (issue 006) or frontend login (issue 007) can be built, the auth providers must be live and issuing tokens in the staging project.

## Acceptance criteria

- [ ] Google OAuth provider is enabled on the staging Supabase project (`dgydekhfzrmeoscpgmvo`) with the correct callback URL (`https://dgydekhfzrmeoscpgmvo.supabase.co/auth/v1/callback`). A test Google account can complete the OAuth flow and receive a Supabase session JWT.
- [ ] Email magic link provider is enabled. A test email address can request and receive a magic link that, when clicked, issues a Supabase session JWT.
- [ ] Custom SMTP is configured (or documented as a required pre-production step with the Supabase built-in mailer as a staging fallback). The MANUAL-STEPS.md notes the rate-limit risk of the built-in mailer for multi-church testing.
- [ ] The leaked-password protection toggle in the Supabase Auth dashboard is enabled (was flagged as disabled in the security advisor; low priority for magic-link-focused flow but must be resolved before production).
- [ ] `MANUAL-STEPS.md` is updated with: (a) exact dashboard steps to enable each provider, (b) the redirect URL to register in the Google Cloud Console OAuth client, (c) SMTP configuration fields, (d) the per-workspace domain allow-list strategy (documented as a manual seed step for v1 — no UI; add user emails to `workspace_members` via seed script).
- [ ] No code changes to `server.py` or `auth.py` in this issue (that is issue 006); this issue is configuration + documentation only.

## Likely files

- `MANUAL-STEPS.md` (modify — add auth provider setup section)
- Supabase dashboard (staging project): Authentication → Providers (Google, Email), Authentication → SMTP settings

## Tests / validation

Manual only (dashboard configuration cannot be automated):

1. Open Supabase dashboard → staging project → Authentication → Providers.
2. Enable Google OAuth: paste client ID + secret from the Google Cloud Console; confirm callback URL matches.
3. Enable Email (magic link); confirm link expiry is set to a reasonable value (e.g. 1 hour).
4. Request a magic link for a test email; confirm delivery and that clicking the link redirects to the configured site URL with a token fragment.
5. Complete a Google OAuth flow with a test account; confirm a session appears in Authentication → Users.
6. Enable leaked-password protection toggle.

No automated tests in this issue. Issue 006 (JWT verification) will have automated tests that require a valid token from a provider configured here.

## Data-safety / out of scope

- Google OAuth client secret must not be committed to the repo; it lives in the Supabase dashboard only.
- Custom SMTP credentials must not be committed; document as environment variable injection for production.
- Out of scope: per-workspace domain allow-list enforcement in code (that is issue 008); this issue only documents the manual seed strategy.
- Out of scope: Electron deep-link redirect handling for OAuth (that is issue 013); this issue covers the provider configuration that both web and Electron auth share.
