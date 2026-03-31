# Design: PCO Ignore List + Full Resync Diff Dialogue

**Issue:** #81
**Date:** 2026-03-30
**Branch:** feature/issue-81-pco-ignore-resync

---

## Overview

Two related features that improve the PCO sync experience:

1. **Per-project PCO item ignore list** — users can name PCO items to permanently skip during import and resync.
2. **Full resync diff dialogue** — the "Refresh from PCO" flow surfaces all inconsistencies between the live PCO plan and the current project, not just note conflicts.

---

## Feature 1: Per-project PCO Item Ignore List

### Data Model

Add `pcoIgnore: string[]` to the project state object, stored inside `project.state` alongside `items`, `announcements`, etc.

```js
// collectCurrentProjectState() returns:
{
  ...existing fields,
  pcoIgnore: pcoIgnore,   // array of exact PCO item name strings (case-insensitive match)
}

// applyProjectState(state):
pcoIgnore = Array.isArray(safe.pcoIgnore) ? safe.pcoIgnore.slice() : [];
```

`pcoIgnore` is a module-level variable (like `items`, `annData`). Missing field on load defaults to `[]`. The ignore list is per-project and travels with the saved project JSON.

### Filtering Logic

In `applyPcoData()` in `pco.js`, after the PCO items array is sorted and mapped but before `pcoDeduplicateItems()`:

```js
// Filter ignored items
const ignoredNorms = new Set(pcoIgnore.map(n => normTitle(n)));
const filteredItems = sorted.filter(item => {
  const title = (item.attributes.title || '').trim();
  return !ignoredNorms.has(normTitle(title));
});
// use filteredItems instead of sorted for the rest of applyPcoData
```

This applies on both initial import and all resyncs (same code path).

### UI

Below the "↺ Refresh from PCO" button inside `#pco-last-import-wrap`, add:

```html
<div id="pco-ignore-wrap" style="margin-top:0.5rem; padding-top:0.5rem; border-top:1px solid var(--border);">
  <div style="font-size:0.67rem; font-weight:700; text-transform:uppercase; letter-spacing:0.07em; color:var(--muted); margin-bottom:0.35rem;">Ignore Items Named</div>
  <div id="pco-ignore-chips" style="display:flex;flex-wrap:wrap;gap:0.25rem;margin-bottom:0.35rem;"></div>
  <div style="display:flex;gap:0.3rem;">
    <input type="text" id="pco-ignore-input" placeholder="Item name…" style="flex:1;font-size:0.8rem;" />
    <button class="btn-sm" id="pco-ignore-add-btn">Add</button>
  </div>
  <div style="font-size:0.7rem;color:var(--muted);margin-top:0.2rem;">Items with these names are skipped on import and refresh.</div>
</div>
```

**Chip rendering:** Each chip in `#pco-ignore-chips` is a `<span>` with an `×` button. Clicking × removes the item from `pcoIgnore`, re-renders chips, and calls `scheduleProjectPersist()`.

**Adding:** Enter key or "Add" button trims the input, pushes to `pcoIgnore`, re-renders chips, clears input, calls `scheduleProjectPersist()`. Duplicate names (case-insensitive) are silently skipped.

**Rendering:** `renderPcoIgnoreChips()` is called by `applyProjectState()` and whenever the list changes. The whole `#pco-ignore-wrap` is only shown when `#pco-last-import-wrap` is visible (i.e., after a PCO import has been done).

---

## Feature 2: Full Resync Diff Dialogue

### Trigger

Only shown on resync (the "↺ Refresh from PCO" button). Initial import uses the existing `applyPcoData()` flow unchanged (no diff dialogue for first import — only song review/conflict dialogs).

A `isResync` boolean parameter is added to `applyPcoData(planResp, itemsResp, notesResp, isResync = false)`.

### Tracking Last-Imported PCO Items

To distinguish "new in PCO" from "removed from your bulletin," add `pcoLastImportedTitles: string[]` to the project state. This is set to the raw (pre-ignore-filter) PCO item titles at the end of every successful import or resync.

```js
// Added to collectCurrentProjectState():
pcoLastImportedTitles: pcoLastImportedTitles.slice(),

// Added to applyProjectState():
pcoLastImportedTitles = Array.isArray(safe.pcoLastImportedTitles)
  ? safe.pcoLastImportedTitles.slice() : [];
```

### Diff Categories

After the new PCO plan items are fetched (build `rawPcoTitles[]` = all PCO item titles before ignore filtering, and `newItems[]` = after filtering), compute diffs against `prevItems[]` and `pcoLastImportedTitles`:

| Category | Detection | Per-item or section? |
|---|---|---|
| **New in PCO** | normalized title in `newItems` but not in `prevItems`, AND not in `pcoLastImportedTitles` (genuinely added to PCO) | Per-item |
| **Removed from project** | normalized title in `newItems` but not in `prevItems`, AND was in `pcoLastImportedTitles` (user deleted it from bulletin) | Per-item |
| **Ignored items** | normalized title in `rawPcoTitles` that matches `pcoIgnore` | Per-item |
| **Title/type changes** | matched item (same normalized title) has different display title or type in PCO | Per-item |
| **Note/detail conflicts** | matched item, both sides have detail, they differ | Per-item (existing behavior) |
| **Order changes** | relative order of matched items in PCO differs from their order in `prevItems` | Section-level single choice |
| **Volunteer changes** | serving schedule will be re-fetched; shown as a single apply checkbox | Single yes/no line |

**Volunteer diff:** Since serving data is fetched async after `applyPcoData`, the volunteer section is a simple "Volunteer schedule will be updated from PCO — apply?" checkbox, pre-checked. The existing `pcoFetchAndApplyServing` runs regardless; this checkbox only controls whether `volRender()` / `scheduleProjectPersist()` are called after the fetch.

### Dialogue Structure

Reuses `import-review-modal` and `irm-*` pattern. New sections rendered before the existing note-conflict section:

```
[irm-section-label] New items in PCO plan
  [irm-song-card per item]  "Add to bulletin" (default) | "Ignore (add to ignore list)"

[irm-section-label] Items removed from your bulletin (still in PCO)
  [irm-song-card per item]  "Keep removed" (default) | "Re-add to bulletin"

[irm-section-label] Ignored items (in PCO, skipped by ignore list)
  [irm-song-card per item — greyed]  "Keep ignoring" (default) | "Un-ignore and add"

[irm-section-label] Title or type changes
  [irm-song-card per item]  "Keep my version" (default) | "Use PCO title/type"

[irm-section-label] Items with Updated Content (existing note-conflict section)
  [existing conflict cards]

[irm-section-label] Order Changes
  [single card]  PCO order vs current order summary. "Apply PCO order" | "Keep my order" (default)

[irm-section-label] Volunteer Schedule
  [single checkbox]  "Apply updated volunteer schedule from PCO" (default: checked)
```

Sections with no entries are omitted entirely.

### Apply Logic (on "Apply & Continue")

1. **Added items:** For each "Add to bulletin" selection, insert the new item at its PCO sequence position in `items[]`. For "Ignore," add name to `pcoIgnore` and re-render chips.
2. **Removed items (re-add):** For "Re-add," insert the item at its PCO sequence position.
3. **Ignored items (un-ignore):** Remove from `pcoIgnore`, add item to `items[]` at PCO position.
4. **Title/type changes:** For "Use PCO," update `items[i].title` and `items[i].type`.
5. **Note conflicts:** Existing behavior unchanged.
6. **Order changes:** If "Apply PCO order," re-sort `items[]` to match PCO sequence (by matching normalized titles).
7. **Volunteer schedule:** If checked, allow `pcoFetchAndApplyServing` result to take effect normally; if unchecked, suppress the `servingSchedule` assignment.

After applying, call `renderItemList()`, `renderPreview()`, `scheduleProjectPersist()`, `closeImportReviewDialog()`.

### When No Changes Detected

If no diff categories produce any entries (plan is identical to current project), skip the dialogue entirely and show a toast: "Plan is up to date — no changes detected."

---

## New State Variables

```js
// state.js — new module-level variables
let pcoIgnore = [];              // string[] of item names to suppress on PCO import/resync
let pcoLastImportedTitles = [];  // string[] of raw PCO item titles from the last import/resync
```

---

## Files Changed

| File | Change |
|---|---|
| `src/js/state.js` | Add `let pcoIgnore = []` and `let pcoLastImportedTitles = []` |
| `src/js/projects.js` | `collectCurrentProjectState` + `applyProjectState` include `pcoIgnore` |
| `src/js/pco.js` | Ignore filtering in `applyPcoData`; `isResync` param; full diff logic; chip add/remove handlers |
| `index.html` | Add `#pco-ignore-wrap` HTML inside `#pco-last-import-wrap` |

No new files. No changes to `server.py` (the ignore list travels inside `project.state` which is an opaque JSON blob from the server's perspective).

---

## Edge Cases

- **Empty ignore list:** `pcoIgnore = []` → no filtering applied. Default state.
- **Ignore list on initial import:** The ignore filter runs on initial import too (same `applyPcoData` path). Items named in the list are skipped even on first import.
- **Item renamed in PCO:** Would appear as "item removed" + "new item added" (same as today — no stable ID). This is acceptable given no stable PCO item IDs are persisted.
- **Ignore list and re-add:** If a user un-ignores an item from the diff dialogue, the name is removed from `pcoIgnore` and the item is added. On next resync, it will be treated as a normal item.
- **Multiple items with same normalized title:** Matching uses `normTitle()` for comparison (existing pattern). Ambiguous matches follow first-match-wins (existing behavior).
- **Volunteer diff on initial import:** Not shown. `isResync = false` → no diff dialogue, no volunteer section.
