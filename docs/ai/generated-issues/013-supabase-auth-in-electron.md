# 013: Supabase Auth inside Electron (deep-link + PKCE)

**Milestone:** M4  ·  **Plan ref:** issue 17
**Depends on:** 007, 011

## Context

The browser login flow (issue 007) uses standard OAuth redirects to `https://<supabase-project>.supabase.co/auth/v1/callback`. Inside Electron, the app is a desktop window at `http://localhost:<port>` — the standard OAuth redirect will not reach it. The plan (D4, Prior Art) calls for: (a) a registered custom-protocol deep link (e.g. `bulletingen://auth-callback`) that the OS hands back to the Electron app after OAuth completes, or (b) a loopback `http://127.0.0.1` redirect; PKCE flow to avoid the implicit token in the URL; and `@supabase/supabase-js` session persistence to localStorage (or Electron's `safeStorage`).

## Acceptance criteria

- [ ] A custom protocol `bulletingen:` is registered in `electron/main.js` (macOS: `app.setAsDefaultProtocolClient('bulletingen')`; Windows: same call or registry entry via `electron-builder` config).
- [ ] `electron/main.js` handles the `open-url` event (macOS) and `second-instance` argv parsing (Windows) to extract the auth callback URL when the OS redirects back; forwards the URL to the renderer via IPC so `@supabase/supabase-js` can call `supabase.auth.exchangeCodeForSession(url)` (PKCE).
- [ ] `src/js/auth-ui.js`'s `signInWithGoogle()` and `signInWithMagicLink()` detect Electron (`window.electronAPI?.isElectron`): in Electron, pass `redirectTo: 'bulletingen://auth-callback'`; in browser, pass the normal HTTP callback URL.
- [ ] After PKCE exchange, the Supabase session is stored in `localStorage` (accessible to the renderer); `getSession()` returns the active session.
- [ ] Magic links open in the system browser (not inside the Electron window) — `electron/main.js` uses `shell.openExternal(url)` for the magic-link URL.
- [ ] Session persistence: closing and reopening the Electron app restores the session from localStorage without requiring re-login (until the Supabase token expires).
- [ ] `electron/preload.js` exposes `window.electronAPI.isElectron = true` so `auth-ui.js` can detect the Electron environment.
- [ ] Manual smoke: Google OAuth and magic-link login both complete inside the Electron app and yield an active Supabase session.

## Likely files

- `electron/main.js` (modify — custom protocol registration, open-url / second-instance handling, IPC bridge for auth callback)
- `electron/preload.js` (modify — expose `isElectron`, auth callback IPC)
- `src/js/auth-ui.js` (modify — Electron-aware redirectTo, PKCE exchange)
- `package.json` / `electron-builder.yml` (modify — protocol registration in packaged build)

## Tests / validation

Manual only (OAuth flows cannot be meaningfully automated without browser automation):

1. `npm run electron` — Electron app opens, login screen appears.
2. Click "Sign in with Google" — system browser opens Google OAuth; after consent, OS hands URL to Electron; app loads with active session.
3. Click "Sign in with magic link", enter test email — system browser opens the magic-link URL; after click, OS hands URL to Electron; app loads with active session.
4. Close and reopen the Electron app — session is restored, login screen does not appear.
5. Session expiry / sign-out: after `signOut()`, session is cleared; login screen reappears on next open.
6. DevTools console clean throughout.

Note: PKCE flow is security-critical — confirm `state` and `code_verifier` are never logged or exposed to the renderer beyond the exchange call.

## Data-safety / out of scope

- `code_verifier` must be generated in the main process or a trusted context, not in the renderer, to prevent a compromised renderer from forging the exchange.
- The Supabase session (JWT + refresh token) stored in localStorage is accessible to any renderer JS; this is acceptable for a trusted desktop app but must not be exposed via `contextBridge` as a raw string to untrusted web content.
- Out of scope: Windows registry protocol registration testing in CI — manual on a Windows machine (or CI Windows runner in issue 014).
- Out of scope: biometric/keychain session storage — localStorage is sufficient for v1.
