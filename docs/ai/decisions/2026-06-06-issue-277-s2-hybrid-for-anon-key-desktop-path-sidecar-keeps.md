---
date: 2026-06-06
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# Issue #277: S2 hybrid for anon-key desktop path; sidecar keeps OAuth callbacks + PCO/Cal/PDF

**Context.** Issue #277 requires removing DATABASE_URL from the Electron desktop build. Two candidate shapes: S1 (sidecar calls PostgREST via anon key) and S2 (renderer does CRUD directly via supabase-js). Planning investigation confirmed all data tables have correct RLS policies for the `authenticated` role. Security advisor shows no RLS gaps. The only structural blocker is `transfer_project_owner`, which uses `admin_transaction()` because the `projects_update` WITH CHECK requires `owner_user_id = auth.uid()` on the NEW row — impossible when the caller transfers ownership to a different user.

**Decision.** Use **S2 hybrid**:
- Renderer (`supabase-data.js`) handles all routine CRUD: projects, announcements, songs, workspace_settings, project_revisions, workspace_presences, templates, fonts metadata, workspace_members.
- The `transfer_project_owner` operation is implemented as a **SECURITY DEFINER RPC** in a new migration (`transfer_project_owner_rpc.sql`). The renderer calls `supabase.rpc('transfer_project_owner', {...})`. The function validates caller = current owner + target is workspace member, then UPDATEs. No DATABASE_URL needed.
- The sidecar keeps: static serving, PCO proxy, Google Calendar fetch, PDF generation, OAuth callbacks (PCO/Google — unauthenticated redirects that cannot use a user JWT at the callback moment; sidecar writes tokens via owner-role which is acceptable since that path runs only on the server anyway and is not bundled in the Electron binary).
- `APP_MODE=electron` is treated as desktop-equivalent in `_validate_server_config()` (no DATABASE_URL required at boot). Sidecar endpoints that touch psycopg return 501/no-op in electron mode.

**S1 rejected.** Rewriting psycopg queries to HTTP REST in Python gains nothing architecturally — the sidecar still needs DATABASE_URL and the renderer still can't bypass the sidecar.

**Consequences.**
- New file: `src/js/supabase-data.js`.
- New migration: `supabase/migrations/20260606000001_transfer_owner_rpc.sql`.
- `server.py` `_validate_server_config()`: add `IS_ELECTRON` bypass.
- `release-electron.yml`: remove `DATABASE_URL` from the `.env` step (after all sub-issues land).
- Server (Docker) mode is entirely unaffected — psycopg + DATABASE_URL kept.
- Old draft prereleases (v0.0.1/2/3) carry DATABASE_URL in bundled .env — delete them after the new build lands and DB password is rotated.
