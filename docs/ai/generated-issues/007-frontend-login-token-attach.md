# 007: Frontend login/logout via supabase-js + Bearer token attach

**Milestone:** M2  ·  **Plan ref:** issue 11
**Depends on:** 006

## Context

The existing vanilla-JS frontend has no login screen — it relies on `auth.py`'s server-side session cookie. This issue adds a minimal login/logout flow using `@supabase/supabase-js` in the browser: a login screen (Google + magic-link), session persistence in `localStorage`, and `apiFetch` attaching the Supabase Bearer token on every request. The existing app UI stays unchanged; auth just gates it. No React rewrite (D4).

## Acceptance criteria

- [ ] `@supabase/supabase-js` is added to `package.json` and bundled/imported. The Supabase anon key (`SUPABASE_ANON_KEY`) and project URL (`SUPABASE_URL`) are injected as JS constants (via a generated `src/js/supabase-config.js` written by server.py's bootstrap or a build step — not hardcoded in source).
- [ ] `src/js/auth-ui.js` (new) exports: `initAuth()` (checks for existing session; shows login screen if none), `signInWithGoogle()`, `signInWithMagicLink(email)`, `signOut()`, `getSession()` returning the current Supabase session (or null).
- [ ] `src/js/api.js`'s `apiFetch()` is updated to: call `getSession()`, and if a session exists, attach `Authorization: Bearer <access_token>` header on every request.
- [ ] `index.html` shows a login screen (minimal: Google button + email input + "Send magic link" button) when `initAuth()` finds no session; hides the login screen and shows the existing app UI when a session is established.
- [ ] `src/js/app.js` calls `initAuth()` at startup before the existing initialization flow runs.
- [ ] After `signOut()`, the app UI is hidden and the login screen is shown; the Supabase session is cleared from localStorage.
- [ ] `node --check src/js/auth-ui.js`, `node --check src/js/api.js`, `node --check src/js/app.js` all pass.
- [ ] `npm run build` (vite) produces no new errors.
- [ ] `npm test` (vitest) — existing 123 tests continue to pass; new tests in `tests/auth-ui.spec.js` cover `initAuth` (no-session path shows login, has-session path shows app) — minimum 2 tests.

## Likely files

- `src/js/auth-ui.js` (new)
- `src/js/api.js` (modify — Bearer token attach in `apiFetch`)
- `src/js/app.js` (modify — call `initAuth()` at startup)
- `index.html` (modify — add login screen HTML, hidden by default)
- `package.json` (modify — add `@supabase/supabase-js`)
- `tests/auth-ui.spec.js` (new)
- `server.py` (possibly modify — inject `SUPABASE_URL` + `SUPABASE_ANON_KEY` into the bootstrap response or a config endpoint)
- `.env.example` (modify — document `SUPABASE_URL`, `SUPABASE_ANON_KEY`)

## Tests / validation

```bash
node --check src/js/auth-ui.js
node --check src/js/api.js
node --check src/js/app.js
npm run build
npm test
```

Manual smoke (server mode with issue 006 deployed):
1. Open the app at `http://localhost:8080` — login screen must appear (no existing session).
2. Click "Sign in with Google" — Google OAuth completes, app UI loads, DevTools console clean.
3. Request a magic link for a test email — click link in email, app UI loads.
4. Click "Sign out" — login screen reappears, session cleared from localStorage.
5. `GET /api/projects` without a session → 401 in Network tab.
6. `GET /api/projects` with an active session → 200, projects list.

## Data-safety / out of scope

- The Supabase anon key is safe to ship to the browser (it is the "publishable" key); the JWT secret and service_role key must never appear in frontend JS.
- The login screen must not expose any user data before authentication — the existing app state must not load until `initAuth()` resolves with a valid session.
- Out of scope: Electron deep-link OAuth redirect (issue 013); this issue covers browser-mode only (the `@supabase/supabase-js` browser flow uses the standard redirect URL).
- Out of scope: per-workspace domain enforcement (issue 008); this issue gates on "any valid Supabase session" — the membership check happens server-side (issue 006).
