---
date: 2026-06-09
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# Cutover re-sync: Synology JSON → Supabase, Synology wins (new upsert script)

**Context.** The secretary's live data lives on the Synology JSON-mode Docker server (`/Volumes/docker/bulletingenerator/app/data/`, 37 projects). Supabase (`dgydekhfzrmeoscpgmvo`, workspace `614505d2-…`) was seeded from it earlier (issue 018) and had drifted: 40 projects = 36 `uuid5` seed rows + 4 app-created `proj_*` rows; songs/announcements diverged. Goal: make Supabase authoritative with current Synology data before moving the secretary to the Supabase/Electron app. Requirement: **Synology wins; nothing the secretary did is lost.**

**Why a new script (`scripts/resync_synology_to_supabase.py`), not `migrate_to_supabase.py`.** The original migrator is insert-only (`ON CONFLICT DO NOTHING`) and keys projects by `uuid5(proj_id)`. The live Electron app inserts projects under their **raw `proj_*` text id**, so the same bulletin can exist twice in Supabase (one seed `uuid5`, one app `proj_*`). An upsert keyed the old way would update the wrong row and leave duplicates. The new script keys projects by **raw `proj_*` id** (matches the app), so re-imports land on the right row and stay consistent going forward.

**Reconciliation rules (operator-approved 2026-06-09).**
- **projects** — replace: delete (existing − Synology − keep-list), then upsert the 37 Synology projects (raw id, `state` = whole wrapper object — verified to match the app's stored shape, which nests the editable content under `state.state`). Keep-list = the 3 `Lake Service - June 7` projects created in the Electron app (operator chose to keep). Result 40.
- **songs / announcements / templates** — union/upsert (Synology wins on conflict; Supabase-only rows preserved). Nothing lost.
- **workspace_settings** — REPLACE the blob with Synology's (staff, volunteerRoles, churchName, etc.); OAuth tokens excluded.
- **owner** — imported projects owned by AJ (`74b48104-…`); transfer to `info@visaliacrc.com` after she first signs in (her `auth.users` row doesn't exist yet). The seed's `owner_user_id = NULL` left projects uneditable under the single-owner RLS UPDATE policy; this run fixes that (post-run: 0 null owners).

**Safety.** Dry-run default; `--execute` takes a fresh Supabase backup (`/Volumes/docker/bulletingenerator/backups/supabase-precutover-<ts>/`, full `json_agg` per table) then writes in one `admin_transaction()` (all-or-nothing). Synology source files never modified.

**Latent bug found + fixed.** `cutover-plan.md` pointed `--source` at `/Volumes/docker/bulletingenerator` (repo root), whose `*.json` are empty stubs — running it as documented would migrate zero records. Corrected to `/app/data`.

**Verified PASS (2026-06-09).** Post-execute: projects 40 (37 + 3 kept), 0 null owners, secretary's `06.14.26` present (23 items) replacing the stale `June 14 — pre-import` placeholder, songs 213 / announcements 13 (union), staff 14 / volunteerRoles 2 in settings.

