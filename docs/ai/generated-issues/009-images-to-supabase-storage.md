# 009: Move cover/logo images to Supabase Storage

**Milestone:** M3  ·  **Plan ref:** issue 13
**Depends on:** 004

## Context

Project state currently embeds cover and logo images as base64 strings in JSONB, contributing ~8.6 MB per project and inflating the stale-poll and RSS. Decision D5 moves these binaries to Supabase Storage (buckets), storing only the Storage URL in the project `state` JSONB. `collab-v1` did not do this step; this is the one piece of "Migration A" that remains. The existing `src/js/editor.js` handles image upload and preview; `storage.py` handles project persistence.

## Acceptance criteria

- [ ] A Supabase Storage bucket `project-assets` (or `covers`) exists on the staging project with RLS: authenticated users can read/write objects whose path starts with `<workspace_id>/` (workspace-scoped); anon is denied.
- [ ] `storage.py` (or a new `asset_storage.py`) exposes `upload_image(workspace_id, project_id, image_type, data_url) -> str` that: decodes the base64 data URL, uploads to Storage at path `<workspace_id>/<project_id>/<image_type>.<ext>`, returns the public or signed URL.
- [ ] `server.py`'s image-handling routes (cover/logo upload) call `upload_image()` and store the returned URL in `project.state` instead of the raw base64.
- [ ] `src/js/editor.js` (and `src/js/preview.js`) continue to work with both URL strings and legacy base64 strings — the rendering path must handle both so that projects migrated in issue 015 (which may have base64 until migrated) still render correctly.
- [ ] A one-time migration helper function `migrate_base64_images_for_project(project_id)` extracts existing base64 fields from a project's `state`, uploads them to Storage, and updates the project `state` in-place with URLs. This is used by issue 015's data-migration tool.
- [ ] `npm test` (vitest) — existing 123 tests pass; `pytest` — existing passing tests pass.
- [ ] Manual: upload a cover image in the app, save, reload — image renders correctly from the Storage URL. PDF export still includes the image.

## Likely files

- `storage.py` or new `asset_storage.py` (modify/new — `upload_image()`, `migrate_base64_images_for_project()`)
- `server.py` (modify — cover/logo upload routes store URL, not base64)
- `src/js/editor.js` (modify — accept both URL and base64 in image preview)
- `src/js/preview.js` (verify/modify — rendering handles URL strings)
- `src/js/projects.js` (verify — `collectCurrentProjectState` still captures image ref correctly)
- `.env.example` (modify — document `SUPABASE_URL` if not already; Storage uses the same project URL)

## Tests / validation

```bash
python3 -c "import storage"
node --check src/js/editor.js
node --check src/js/preview.js
npm run build
npm test
pytest -v
```

Manual smoke (server mode):
1. Upload a cover image → confirm Storage bucket has the file at the expected path.
2. Save and reload the project → image renders (URL path, not base64).
3. Export PDF → cover image appears correctly.
4. Open an old project with base64 cover → still renders (backwards-compatible path).

## Data-safety / out of scope

- Storage bucket RLS must prevent workspace B from reading workspace A's images (path prefix `<workspace_id>/` enforces this).
- The Supabase Storage service key must not be used for normal uploads; use the authenticated user's session or a signed upload URL.
- Never delete the base64 from existing projects until issue 015's migration tool has been run and verified — the migration is additive.
- Out of scope: font files (issue 010); cover/logo only in this issue.
- Out of scope: Storage URL signing / expiry policies — use public bucket or long-lived signed URLs for v1.
