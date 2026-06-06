# E2E Suite — Phases 2–5 Implementation Plan (Full Coverage)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Each slice is verified by RUNNING the lane (`npm run test:e2e` / `:live`) against the real app + Supabase, not just typecheck. Steps use `- [ ]`.

**Goal:** Grow the verified Phase-1 harness into exhaustive coverage of every tab, control, field, route, render path, export, and persistence flow — the "test everything, forever" target from the spec.

**Approach — verified vertical slices.** Rather than build all Page Objects, then all specs, we deliver one **feature area at a time**: its Page Object **plus** its exhaustive spec, run green against the live app before moving on. This makes every increment independently reviewable and proven, and folds the spec's Phase 2 (page objects) and Phase 4 (exhaustive matrix) into per-area units. Phase 3 (golden flows) is a capstone; Phase 5 (record/replay + live PCO/Google specs + fixture refresh) is infra.

**Reference:** design spec `docs/superpowers/specs/2026-06-05-e2e-playwright-suite-design.md`; Phase 1 plan `2026-06-05-e2e-playwright-foundation.md`.

---

## Runtime patterns learned in Phase 1 (apply in every slice)

- **App readiness:** `AppShell.goto()` already waits for `[data-tab=page-editor]` aria-selected — the app wires UI after `load`. Reuse it; never interact before it.
- **No fake clock:** `page.clock.install()` stalls the app's timer-driven legacy-script loader. Wait on real network (`waitForResponse`) or UI state instead.
- **Autosave gating:** edits only persist once a project is active (`projects.js:345`). A fresh user must Save first (File menu → `#bulletin-title` → `#project-save-btn`).
- **Collapsed `<details>` menus:** File `#editor-toolbar-file`, Sync `#editor-toolbar-sync`, Document `#editor-toolbar-document` — click the `summary` to open before touching fields inside.
- **Editor sidebar sections** (Welcome, Announcements, Order of Worship, Calendar, Volunteers, Volunteer Roles, Staff) render as collapsible cards; expanding is required before their inner controls are visible (slice 1 establishes the helper).
- **Dynamic rows** carry `data-testid="<area>-row"` + `data-index` (Phase 1 seam).
- **Writes hit the live project** → every spec must create only disposable data within the run's ephemeral workspace (core lane) and clean up project rows via teardown (already destroys the whole ephemeral workspace).

---

## Shared infrastructure (slice 0)

**Files:** `tests/e2e/pages/BasePanel.ts` (or helpers) — utilities used across POs:
- `openToolbarMenu(name)` — open File/Sync/Document `<details>` by clicking its summary; assert panel visible.
- `expandSection(label)` — expand an editor sidebar section card by its heading; assert inner controls visible.
- `createAndSaveProject(name)` — the canonical "make a persistable project" flow (File → title → Save → await POST). Most specs need an active project first.
- `row(area, index)` — locator helper for `[data-testid="<area>-row"][data-index="N"]`.

Verify slice 0 by refactoring the existing smoke to use these helpers and re-running core lane green.

---

## Per-area slices (each = Page Object + exhaustive spec, run green)

Each slice: (1) inspect that area's real DOM/interaction in index.html + its JS module; (2) write `pages/<Area>Page.ts`; (3) write `features/<area>.spec.ts` covering every control/field/route from the coverage matrix (spec §6); (4) run the lane until green; (5) commit.

1. **Editor / Order of Worship** (`editor.js`): add item, every item type (song/liturgy/label/section/note/media via `.item-type-sel`), title + detail edit, per-item format override, collapse, move up/down, drag-reorder, delete, add page break. Assert preview reflects changes.
2. **Projects / Files** (`projects.js`): new, save, save-new-version, rename, delete, open from list, import JSON, bulk select/all/clear, bulk download JSON/PDF/ProPresenter, delete-selected. Server-mode subtabs.
3. **Song Database** (`songs.js`): add manually, edit, delete, search, all sorts, source filter, paste-from-clipboard (+ fallback dialog), export/import JSON, clear-all. ProPresenter import dialogs (disclaimer→import→preview) — file upload fixtures.
4. **Format** (`formatting.js`): page-size select, per-type cards for every type, filter, save, reset, override-precedence assertion (computed style on rendered preview element — see memory feedback_test_contract_not_surface).
5. **Templates** (`templates`/designer): apply built-in (dialog confirm/cancel), designer open/edit-element/name/save/save-as/export/back, import, new, fonts upload/list/delete.
6. **Settings** (`staff.js`/`calendar.js`/branding/update): identity display name, church name, give URL, logo upload/clear, calendar (iCal URLs save/reset, exclude save), serving-team filter, song-db export/import/clear, updates (check, banner). Calendar manual add/edit/delete event lives in the editor Calendar section.
7. **Editor sub-sections:** Welcome, Announcements (title/body/url/page-break), Volunteer Roles, Staff (name/role/email, move, remove). Each add/edit/remove + preview assertion.
8. **Auth & server-mode behaviors:** login screen states; ownership/read-only (second ephemeral user views a workspace project → banner + disabled saves + Duplicate); 409 conflict dialog (two contexts editing → all three resolution buttons); stale-revision poll; presence badge. Needs multi-context tests.

## Phase 3 — Golden flows (`flows/`)
- Build-from-scratch → all sections populated → save → export PDF (page-count + preview snapshot).
- Bulk export (JSON + PDF + ProPresenter) of multiple projects.
- (live lane) PCO import → edit → save → export, read-only.

## Phase 5 — Live integrations + fixture refresh
- `helpers/record-replay.ts` (`routeFromHAR`): live lane records PCO/Google; core lane replays so PCO/calendar specs run deterministically in the gate (ephemeral users have no connected tokens).
- Live-lane PCO + Google Calendar read-only specs (service types/plans/items load; calendar events render).
- Fixture auto-refresh: live lane re-records HARs and opens a PR on diff.
- Optional: thin Electron boot-smoke (deferred from v1).

---

## Definition of done (per the spec's coverage matrix §6)
Every matrix row maps to a passing test tagged `@core` or `@live`. Track completion area-by-area. `npm test` (vitest) stays green throughout. Core lane remains the PR gate; live lane stays soft.
