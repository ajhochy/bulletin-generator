---
date: 2026-06-05
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# Carry workspace id through a signed OAuth `state` for the CONNECT path

**Context.** Commit 67bb9ca scoped the OAuth *read* path (proxy/refresh/config) to
the authenticated workspace, but the *connect* (write) path was still un-scoped:
`_handle_pco_oauth_callback` / `_handle_google_oauth_callback` are unauthenticated
browser redirects (no Bearer/session), so they wrote tokens via `_get_settings()`/
`_save_settings()` → `workspace_settings LIMIT 1`. With multiple workspaces, connecting
in workspace B could write tokens into workspace A's row.

**Decision.**
- The SPA passes its Supabase access token to `/oauth/{pco,google}/start` as a `?token=`
  query param (the start endpoint is a top-level navigation with no Authorization header).
  The start handler verifies it via `auth.authenticate_authorization_header`, resolves
  workspace membership, and signs the workspace id into the OAuth `state` with
  HMAC-SHA256 (`_sign_oauth_state`). The provider echoes `state` back to the callback,
  which verifies it (`_verify_oauth_state`, constant-time) and builds workspace-scoped
  storage `get_storage(workspace_id=…, user_claims=None)` for the token write.
- HMAC key precedence: `OAUTH_STATE_SECRET` → `SUPABASE_JWT_SECRET` → concatenated
  OAuth client secrets. This is never empty in a correctly-configured server deployment
  and requires zero new config for existing deployments.
- Missing/invalid/forged `state` in server mode is **refused** (error redirect, no write)
  rather than falling back to an arbitrary workspace.
- Desktop mode is single-workspace: `getSession()` is null → no `?token=` → start emits
  no `state` → callback uses default desktop storage (unchanged behavior).

**Alternatives considered.**
- *Server-minted single-use nonce* instead of the raw access token in the query string —
  avoids exposing the (short-lived) token in URL/history/logs, but adds a server-side
  nonce store and lifecycle. Deferred; the access token is short-lived and the endpoint
  302-redirects immediately. Start handlers must not log the query string.
- *Per-user token rows / proper RLS service path for `workspace_settings` writes* — the
  callback write uses `user_claims=None`, i.e. the owner-role DATABASE_URL connection that
  bypasses RLS for the upsert (the same path the prior un-scoped fallback used). A future
  hardening (issue #277 family) could move OAuth tokens off the owner connection.

**Consequences.**
- Token writes land in the connecting user's workspace; A/B isolation holds for connect.
- New optional env `OAUTH_STATE_SECRET` (documented precedence). No migration required.
- The earlier "members can't use PCO → blame workspace_settings RLS" diagnosis was wrong;
  the real cause was the un-scoped LIMIT 1 *read*, fixed in 67bb9ca. This change fixes the
  symmetric *write* gap.
