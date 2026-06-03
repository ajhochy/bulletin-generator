# 010: Move font files to Supabase Storage

**Milestone:** M3  ·  **Plan ref:** issue 14
**Depends on:** 004, 009

## Context

User-uploaded fonts are currently stored as binary files on the server's local filesystem (or as base64 in `settings.json` / the `fonts` table). Decision D5 moves them to Supabase Storage. The `fonts` table (created in issue 001) will store metadata and Storage URLs; the actual font binary lives in a Storage bucket `fonts` or `workspace-fonts`. The server's `/api/fonts` routes need to upload to Storage on write and return Storage URLs on read. The font-rendering path (CSS `@font-face` in preview/print HTML) must use the Storage URL.

## Acceptance criteria

- [ ] A Supabase Storage bucket `workspace-fonts` exists with RLS: `<workspace_id>/` path prefix, same authenticated-only pattern as `project-assets` (issue 009). Anon denied.
- [ ] `server.py`'s font upload route: accepts the font binary, uploads to Storage at `<workspace_id>/<font_id>.<ext>`, inserts a row into the `fonts` table with `storage_path` = the Storage path and `name` = the display name, returns the Storage URL to the client.
- [ ] `server.py`'s font list/fetch routes: query the `fonts` table (scoped to `workspace_id` via `storage.py`), return Storage URLs (not binary blobs) to the client.
- [ ] `src/js/` font rendering: `@font-face` CSS in preview/print HTML uses the Storage URL. Legacy local-path font references continue to work for any fonts not yet migrated.
- [ ] `tests/test_import_fonts.py` (existing from collab-v1): passes or is updated to match the new storage_path column shape.
- [ ] A `migrate_local_fonts_for_workspace(workspace_id)` helper function (used by issue 015): reads font binaries from the old location, uploads to Storage, updates the `fonts` table rows.
- [ ] `python3 -c "import server"` succeeds.
- [ ] Manual: upload a custom font, use it in a bulletin, export PDF — font renders correctly.

## Likely files

- `server.py` (modify — font upload/list/fetch routes)
- `storage.py` (modify — fonts table queries scoped to workspace_id)
- `src/js/` (identify font-rendering path — likely `server.py` generates the CSS, or `src/js/preview.js` constructs `@font-face`)
- `tests/test_import_fonts.py` (modify if needed)

## Tests / validation

```bash
python3 -c "import server"
npm run build
pytest tests/test_import_fonts.py -v
pytest -v
```

Manual smoke:
1. Upload a custom font (e.g. a `.woff2` file) → confirm it appears in Storage bucket under the correct workspace path.
2. Apply the font to a bulletin item, render preview → font appears correctly.
3. Export PDF → custom font renders in PDF.
4. A user in workspace B cannot download workspace A's font (confirm via Storage RLS or a direct URL attempt).

## Data-safety / out of scope

- Font binaries must not be stored in JSONB or committed to the repo.
- The Storage upload must use the authenticated user's session or a service-role signed URL — never expose a service_role key to the frontend.
- Out of scope: font subsetting or caching optimization — Storage URL delivery is sufficient for v1.
- Out of scope: ProPresenter font import (that is `src/js/propresenter.js` — an unrelated flow).
