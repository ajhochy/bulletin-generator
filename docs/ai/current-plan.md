# Current Plan

_Last updated: 2026-05-19_

## User request

Stabilize the Volunteer Roles feature (PRs #251, #252, #253). Most-recent in-flight item: fix Template Designer so volunteer-role elements are selectable / formattable like every other zone.

## Goal

Every previewable section type — including Volunteer Roles — must be fully wired in the Template Designer canvas: clickable, selectable, labeled, and formattable via per-element overrides.

## Non-goals

- Re-architecting the Template Designer.
- Unifying the editor-card DOM and the preview DOM.
- Adding new volunteer-role features (drag reorder in canvas, etc.). File separately.

## Constraints

- No JS bundler — files must remain directly loadable via `<script>` tags.
- No new dependencies.
- Backwards-compatible with existing project JSON; no migration required for this fix.

## Phases / issues

1. **#253 (in flight, branch `fix/template-editor-volunteer-roles-not-selectable`)** — add `.vr-entry-title` / `.vr-entry-body` / `.vr-entry-url` to `inferCanvasElement()` selector + branches, add to `TPL_SELECTABLE_SELECTOR`, add `nearestVolunteerRoleTitle()` helper.
2. **Follow-up (not filed)** — audit other zones for the same gap and add a contributor checklist to `CLAUDE.md` "Common Gotchas": "When adding a new previewable section, update both `inferCanvasElement()` and `TPL_SELECTABLE_SELECTOR`."

## Validation plan

- Automated browser smoke via preview server (script in this PR's verification).
- Manual click-through of every zone in Template Designer (see `testing-guide.md`).
- PDF export still produces the expected output.
