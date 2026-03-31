# PCO Ignore List + Full Resync Diff Dialogue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-project PCO item ignore list and a full resync diff dialogue that surfaces all inconsistencies between the live PCO plan and the current project.

**Architecture:** Two new module-level arrays (`pcoIgnore`, `pcoLastImportedTitles`) are added to `state.js` and persisted inside `project.state`. The ignore filter runs inside `applyPcoData()` (in `pco.js`) on every import and resync. On resync, `buildResyncDiff()` computes all change categories; `showResyncDiffDialog()` renders them in the existing `import-review-modal` and handles apply logic.

**Tech Stack:** Vanilla JS (no bundler, no framework), Python stdlib HTTP server. No test runner — verification is manual browser testing. All files are loaded as `<script>` globals; functions are hoisted so declaration order within a file doesn't matter.

---

## File Map

| File | Change |
|---|---|
| `src/js/state.js` | Add `let pcoIgnore = []` and `let pcoLastImportedTitles = []` |
| `src/js/projects.js` | `collectCurrentProjectState`, `applyProjectState`, `clearEditorForNewProject` |
| `index.html` | Add `#pco-ignore-wrap` HTML inside `#pco-last-import-wrap` |
| `src/js/pco.js` | Ignore filter in `applyPcoData`; new `isResync`/`servingParams` params; `buildResyncDiff`; `showResyncDiffDialog`; chip UI; event handlers |

No new files. No changes to `server.py`.

---

## Task 1: Add state variables

**Files:**
- Modify: `src/js/state.js` (after line 2, after `let items = [];`)

- [ ] **Step 1: Add two new module-level variables to `state.js`**

Open `src/js/state.js`. After the line `let items = [];` (line 2), add:

```js
let pcoIgnore = [];              // string[] — PCO item names to skip on import/resync
let pcoLastImportedTitles = [];  // string[] — raw PCO item titles from last import/resync
```

- [ ] **Step 2: Verify the file**

Open `src/js/state.js` and confirm both variables appear near the top alongside `items`, `annData`, etc.

- [ ] **Step 3: Commit**

```bash
cd "/Users/ajhochhalter/Documents/Bulletin Generator - Most Recent Release"
git add src/js/state.js
git commit -m "feat(#81): add pcoIgnore and pcoLastImportedTitles state variables"
```

---

## Task 2: Persist state in project save/load/clear

**Files:**
- Modify: `src/js/projects.js` — `collectCurrentProjectState` (line 46), `applyProjectState` (line 71), `clearEditorForNewProject` (line 439)

- [ ] **Step 1: Add to `collectCurrentProjectState` return object**

In `src/js/projects.js`, find `collectCurrentProjectState()`. The return object ends with `calEvents: ...`. Add these two fields before the closing `}`:

```js
    pcoIgnore: pcoIgnore.slice(),
    pcoLastImportedTitles: pcoLastImportedTitles.slice(),
```

The tail of the function should look like:

```js
    calEvents: Array.isArray(calEvents) ? calEvents.map(e => Object.assign({}, e, { start: Object.assign({}, e.start), end: e.end ? Object.assign({}, e.end) : null })) : null,
    pcoIgnore: pcoIgnore.slice(),
    pcoLastImportedTitles: pcoLastImportedTitles.slice(),
  };
}
```

- [ ] **Step 2: Add to `applyProjectState`**

In `src/js/projects.js`, inside `applyProjectState(state)`, find the line `calEvents = ...` (near the end, around line 114). After it, add:

```js
  pcoIgnore = Array.isArray(safe.pcoIgnore) ? safe.pcoIgnore.slice() : [];
  pcoLastImportedTitles = Array.isArray(safe.pcoLastImportedTitles) ? safe.pcoLastImportedTitles.slice() : [];
  if (typeof renderPcoIgnoreChips === 'function') renderPcoIgnoreChips();
```

- [ ] **Step 3: Reset in `clearEditorForNewProject`**

In `src/js/projects.js`, inside `clearEditorForNewProject()`, find the line `items = [];` (around line 473). Just before it, add:

```js
  pcoIgnore = [];
  pcoLastImportedTitles = [];
  if (typeof renderPcoIgnoreChips === 'function') renderPcoIgnoreChips();
```

- [ ] **Step 4: Start the server and verify in browser console**

```bash
python3 server.py
```

Open http://localhost:8080. In the browser console run:

```js
collectCurrentProjectState().pcoIgnore     // should be []
collectCurrentProjectState().pcoLastImportedTitles  // should be []
```

Both should return `[]` with no errors.

- [ ] **Step 5: Commit**

```bash
git add src/js/projects.js
git commit -m "feat(#81): persist pcoIgnore and pcoLastImportedTitles in project state"
```

---

## Task 3: Add ignore list HTML to index.html

**Files:**
- Modify: `index.html` — inside `#pco-last-import-wrap`

- [ ] **Step 1: Add the ignore list markup**

In `index.html`, find `<div id="pco-refresh-msg" class="pco-msg"></div>` (line 77). Insert the following block immediately after it (still inside `#pco-last-import-wrap`):

```html
          <div id="pco-ignore-wrap" style="margin-top:0.5rem; padding-top:0.5rem; border-top:1px solid var(--border);">
            <div style="font-size:0.67rem; font-weight:700; text-transform:uppercase; letter-spacing:0.07em; color:var(--muted); margin-bottom:0.35rem;">Ignore Items Named</div>
            <div id="pco-ignore-chips" style="display:flex;flex-wrap:wrap;gap:0.25rem;margin-bottom:0.35rem;min-height:0.5rem;"></div>
            <div style="display:flex;gap:0.3rem;">
              <input type="text" id="pco-ignore-input" placeholder="Item name…" style="flex:1;font-size:0.8rem;" />
              <button class="btn-sm" id="pco-ignore-add-btn">Add</button>
            </div>
            <div style="font-size:0.7rem;color:var(--muted);margin-top:0.2rem;">Items with these names are skipped on import and refresh.</div>
          </div>
```

- [ ] **Step 2: Verify structure**

The resulting `#pco-last-import-wrap` section should contain (in order):
1. "Last Imported" label div
2. `#pco-last-plan-label`
3. `#pco-refresh-btn`
4. `#pco-refresh-msg`
5. `#pco-ignore-wrap` ← new

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(#81): add PCO ignore list UI inside last-import section"
```

---

## Task 4: Implement chip rendering and event handlers in pco.js

**Files:**
- Modify: `src/js/pco.js` — add `renderPcoIgnoreChips()` function and two event listeners

This task adds the chip UI logic. `renderPcoIgnoreChips` is called by `applyProjectState` (already added in Task 2) and from the add/remove handlers.

- [ ] **Step 1: Add `renderPcoIgnoreChips` function**

In `src/js/pco.js`, find the `closeImportReviewDialog` function (around line 482). Add `renderPcoIgnoreChips` just before it:

```js
function renderPcoIgnoreChips() {
  const container = document.getElementById('pco-ignore-chips');
  if (!container) return;
  container.innerHTML = '';
  pcoIgnore.forEach((name, i) => {
    const chip = document.createElement('span');
    chip.style.cssText = 'display:inline-flex;align-items:center;gap:0.25rem;background:var(--border);border-radius:3px;padding:0.1rem 0.4rem;font-size:0.75rem;';
    chip.appendChild(document.createTextNode(name));
    const x = document.createElement('button');
    x.textContent = '×';
    x.title = 'Remove';
    x.style.cssText = 'background:none;border:none;cursor:pointer;padding:0 0 0 0.1rem;font-size:0.9rem;line-height:1;color:var(--muted);';
    x.addEventListener('click', () => {
      pcoIgnore.splice(i, 1);
      renderPcoIgnoreChips();
      scheduleProjectPersist();
    });
    chip.appendChild(x);
    container.appendChild(chip);
  });
}
```

- [ ] **Step 2: Add event listeners for Add button and Enter key**

At the bottom of `src/js/pco.js` (after all existing event listeners), add:

```js
// ─── PCO ignore list handlers ─────────────────────────────────────────────────
document.getElementById('pco-ignore-add-btn').addEventListener('click', () => {
  const input = document.getElementById('pco-ignore-input');
  const name = (input.value || '').trim();
  if (!name) return;
  const normName = normTitle(name);
  if (!pcoIgnore.some(n => normTitle(n) === normName)) {
    pcoIgnore.push(name);
    renderPcoIgnoreChips();
    scheduleProjectPersist();
  }
  input.value = '';
  input.focus();
});

document.getElementById('pco-ignore-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('pco-ignore-add-btn').click();
});
```

- [ ] **Step 3: Verify in browser**

Reload http://localhost:8080. Connect to PCO (or use existing credentials). Import a plan so `#pco-last-import-wrap` becomes visible. You should see the "Ignore Items Named" section. Type a name, press Enter — a chip should appear. Click × on the chip — it should disappear. The project should autosave (check network tab for POST to `/api/projects`).

- [ ] **Step 4: Commit**

```bash
git add src/js/pco.js
git commit -m "feat(#81): add renderPcoIgnoreChips and ignore list event handlers"
```

---

## Task 5: Apply ignore filter and track last-imported titles in applyPcoData

**Files:**
- Modify: `src/js/pco.js` — `applyPcoData` function, refresh button handler

This task makes the ignore list actually work during import/resync. It also adds `isResync` and `servingParams` parameters to `applyPcoData` for use in Task 7.

- [ ] **Step 1: Update `applyPcoData` signature and item-build logic**

In `src/js/pco.js`, find `function applyPcoData(planResp, itemsResp, notesResp) {` (line 128).

Replace the entire signature line and the `items = sorted.map(...).filter(...)` block. The current code looks like:

```js
function applyPcoData(planResp, itemsResp, notesResp) {
  const planAttrs = planResp.data.attributes;

  // Snapshot current items so user edits can be preserved on re-sync
  const prevItems = items.slice();
```

Change to:

```js
function applyPcoData(planResp, itemsResp, notesResp, isResync = false, servingParams = null) {
  const planAttrs = planResp.data.attributes;

  // Snapshot current items so user edits can be preserved on re-sync
  const prevItems = items.slice();
```

- [ ] **Step 2: Replace `items = sorted.map(...).filter(item => item.title)` with ignore-filtered version**

Find the block that currently reads:

```js
  items = sorted.map(item => {
    const a    = item.attributes;
    const type = pcoMapItemType(a);
    let title  = (a.title || '').trim();
    let detail = '';

    // For songs, always prefer the canonical Song record title over the item title.
    // PCO item titles often contain hymnal/arranger prefixes like
    // "Bread - Gray Hymnal 297 - O Come My Soul Sing Praise to God",
    // while the linked Song record holds the clean song name.
    if (a.item_type === 'song') {
      const songRel = item.relationships && item.relationships.song && item.relationships.song.data;
      if (songRel && incSongs[songRel.id] && incSongs[songRel.id].title) {
        title = incSongs[songRel.id].title;
      }
    }

    // Strip HTML from description and use as detail
    if (a.description) {
      const tmp = document.createElement('div');
      tmp.innerHTML = a.description;
      const stripped = (tmp.textContent || tmp.innerText || '')
        .replace(/\[[^\]]*\]/g, '')   // strip [bracket notes]
        .replace(/\s{2,}/g, ' ')
        .trim();
      if (stripped) detail = stripped;
    }

    // Section headers are rendered uppercase in the booklet
    if (type === 'section') title = title.toUpperCase();

    return { type, title, detail };
  }).filter(item => item.title);

  items = pcoDeduplicateItems(items);
```

Replace with:

```js
  // Map all PCO items (including those that will be ignored) so we can
  // track them for the resync diff and for pcoLastImportedTitles.
  const allPcoMapped = pcoDeduplicateItems(sorted.map(item => {
    const a    = item.attributes;
    const type = pcoMapItemType(a);
    let title  = (a.title || '').trim();
    let detail = '';

    // For songs, always prefer the canonical Song record title over the item title.
    if (a.item_type === 'song') {
      const songRel = item.relationships && item.relationships.song && item.relationships.song.data;
      if (songRel && incSongs[songRel.id] && incSongs[songRel.id].title) {
        title = incSongs[songRel.id].title;
      }
    }

    // Strip HTML from description and use as detail
    if (a.description) {
      const tmp = document.createElement('div');
      tmp.innerHTML = a.description;
      const stripped = (tmp.textContent || tmp.innerText || '')
        .replace(/\[[^\]]*\]/g, '')   // strip [bracket notes]
        .replace(/\s{2,}/g, ' ')
        .trim();
      if (stripped) detail = stripped;
    }

    // Section headers are rendered uppercase in the booklet
    if (type === 'section') title = title.toUpperCase();

    return { type, title, detail };
  }).filter(item => item.title));

  // Apply per-project ignore filter
  const ignoredNorms    = new Set(pcoIgnore.map(n => normTitle(n)));
  const pcoIgnoredMapped = allPcoMapped.filter(item => ignoredNorms.has(normTitle(item.title)));
  items = allPcoMapped.filter(item => !ignoredNorms.has(normTitle(item.title)));
```

- [ ] **Step 3: Store pcoLastImportedTitles at the end of applyPcoData**

In `applyPcoData`, find the lines at the bottom that compute `pendingUnmatched` and eventually call `showRefreshConflictsDialog` or `showImportReviewDialog`. Just before the line `if (refreshConflicts.length > 0) {`, add:

```js
  // Track all PCO item titles from this import for future resync diff detection
  pcoLastImportedTitles = allPcoMapped.map(i => i.title);
```

- [ ] **Step 4: Update the refresh button call site**

Find the `pco-refresh-btn` click handler (around line 798). It currently calls:

```js
    applyPcoData(planResp, itemsResp, notesResp);
    pcoSetMsg('pco-refresh-msg', `Updated — ${items.length} items refreshed.`, 'success');
    setStatus(`Refreshed from Planning Center (${items.length} items).`, 'success');
    document.querySelector('.tab-btn[data-tab="page-editor"]').click();
    // Fetch serving schedule in background (non-blocking)
    pcoFetchAndApplyServing(last.serviceTypeId, last.planId,
      planResp.data.attributes.sort_date, planResp.data.attributes.dates);
```

Replace with:

```js
    const _servingParams = {
      stId:     last.serviceTypeId,
      planId:   last.planId,
      sortDate: planResp.data.attributes.sort_date,
      date:     planResp.data.attributes.dates,
    };
    applyPcoData(planResp, itemsResp, notesResp, true, _servingParams);
    pcoSetMsg('pco-refresh-msg', `Updated — ${items.length} items refreshed.`, 'success');
    setStatus(`Refreshed from Planning Center (${items.length} items).`, 'success');
    document.querySelector('.tab-btn[data-tab="page-editor"]').click();
    // NOTE: pcoFetchAndApplyServing is now called from inside applyPcoData's resync path
    // (either directly for the no-changes case, or from showResyncDiffDialog's Apply button).
```

- [ ] **Step 5: Verify ignore filter works**

In the browser, import a PCO plan. Type "Sermon" in the Ignore Items Named input and press Enter. Click "↺ Refresh from PCO". The "Sermon" item should no longer appear in the item list after refresh. Check browser console for errors.

- [ ] **Step 6: Commit**

```bash
git add src/js/pco.js
git commit -m "feat(#81): apply pcoIgnore filter in applyPcoData, track pcoLastImportedTitles"
```

---

## Task 6: Add resync diff helpers in pco.js

**Files:**
- Modify: `src/js/pco.js` — add `buildResyncDiff`, `findInsertPosition`, `applyCPcoOrder`

These are pure computation helpers. Add them near the top of pco.js (after the `pcoMapItemType` function, around line 514).

- [ ] **Step 1: Add `buildResyncDiff`**

```js
// Computes all diff categories between prevItems (current project) and newItems (PCO, post-filter).
// pcoIgnoredMapped: items that were filtered out by pcoIgnore (for display in diff modal).
// allPcoMapped: all PCO items including ignored, used for insert-position calculation.
function buildResyncDiff(prevItems, newItems, pcoIgnoredMapped, allPcoMapped) {
  const prevNorms = new Set(prevItems.map(i => normTitle(i.title)));
  const newNorms  = new Set(newItems.map(i => normTitle(i.title)));
  const lastNorms = new Set(pcoLastImportedTitles.map(t => normTitle(t)));

  // New in PCO: in newItems, not in prevItems, and not in last import
  // (genuinely added to the PCO plan since last import)
  const newInPco = newItems.filter(item => {
    const n = normTitle(item.title);
    return !prevNorms.has(n) && !lastNorms.has(n);
  });

  // Removed from project: in newItems, not in prevItems, but WAS in last import
  // (user deleted it from their bulletin since last import; still exists in PCO)
  const removedFromProject = newItems.filter(item => {
    const n = normTitle(item.title);
    return !prevNorms.has(n) && lastNorms.has(n);
  });

  // Title or type changes: matched items (same normalized title) where PCO differs
  const titleTypeChanges = [];
  newItems.forEach(newItem => {
    const match = prevItems.find(p => normTitle(p.title) === normTitle(newItem.title));
    if (match && (match.title !== newItem.title || match.type !== newItem.type)) {
      titleTypeChanges.push({
        normKey:   normTitle(newItem.title),
        prevTitle: match.title,
        newTitle:  newItem.title,
        prevType:  match.type,
        newType:   newItem.type,
      });
    }
  });

  // Order changes: compare relative sequence of items present in both
  const prevMatchedNorms = prevItems.map(i => normTitle(i.title)).filter(n => newNorms.has(n));
  const newMatchedNorms  = newItems.map(i => normTitle(i.title)).filter(n => prevNorms.has(n));
  const orderChanged = prevMatchedNorms.length > 1 &&
                       prevMatchedNorms.join('|') !== newMatchedNorms.join('|');

  return {
    newInPco, removedFromProject, pcoIgnoredMapped, titleTypeChanges,
    orderChanged, prevMatchedNorms, newMatchedNorms, allPcoMapped,
  };
}
```

- [ ] **Step 2: Add `findInsertPosition`**

```js
// Returns the index in items[] where a new item should be inserted to match PCO order.
// Looks backwards through allPcoMapped for the closest preceding item already in items[].
function findInsertPosition(targetItem, allPcoMapped) {
  const targetNorm = normTitle(targetItem.title);
  const pcoIdx = allPcoMapped.findIndex(i => normTitle(i.title) === targetNorm);
  if (pcoIdx <= 0) return 0;
  for (let i = pcoIdx - 1; i >= 0; i--) {
    const precedingNorm = normTitle(allPcoMapped[i].title);
    const localIdx = items.findIndex(li => normTitle(li.title) === precedingNorm);
    if (localIdx >= 0) return localIdx + 1;
  }
  return 0;
}
```

- [ ] **Step 3: Add `applyCPcoOrder`**

```js
// Re-sorts items[] to match the PCO order given by pcoNormsOrdered.
// Items not present in the PCO order (e.g. page-breaks, manual items) move to the end.
function applyCPcoOrder(pcoNormsOrdered) {
  const pcoRank = new Map(pcoNormsOrdered.map((n, i) => [n, i]));
  items.sort((a, b) => {
    const ra = pcoRank.has(normTitle(a.title)) ? pcoRank.get(normTitle(a.title)) : Infinity;
    const rb = pcoRank.has(normTitle(b.title)) ? pcoRank.get(normTitle(b.title)) : Infinity;
    return ra - rb;
  });
}
```

- [ ] **Step 4: Commit**

```bash
git add src/js/pco.js
git commit -m "feat(#81): add buildResyncDiff, findInsertPosition, applyCPcoOrder helpers"
```

---

## Task 7: Add irmAddSection helper and showResyncDiffDialog, wire into applyPcoData

**Files:**
- Modify: `src/js/pco.js` — add `irmAddSection`, `showResyncDiffDialog`, update `applyPcoData` tail

This is the largest task. `showResyncDiffDialog` replaces both `showRefreshConflictsDialog` and `showImportReviewDialog` for the resync flow. The initial import flow is unchanged.

- [ ] **Step 1: Add `irmAddSection` helper near existing irm* helpers**

In `src/js/pco.js`, find `function irmRadioRow(...)` (around line 486). Add `irmAddSection` just before it:

```js
function irmAddSection(body, labelText) {
  const el = document.createElement('div');
  el.className = 'irm-section-label';
  el.textContent = labelText;
  body.appendChild(el);
}
```

- [ ] **Step 2: Add `showResyncDiffDialog` function**

Add this function after `showRefreshConflictsDialog` (i.e., after line ~1047). The complete function:

```js
function showResyncDiffDialog(diff, refreshConflicts, pendingWithNotes, pendingUnmatched, serveCallback) {
  const body = document.getElementById('irm-body');
  body.innerHTML = '';

  // Track selections per category
  const newInPcoSels   = new Map(); // normTitle → 'add' | 'ignore'
  const removedSels    = new Map(); // normTitle → 'keep' | 'readd'
  const ignoredSels    = new Map(); // normTitle → 'keep' | 'unignore'
  const titleTypeSels  = new Map(); // normKey   → 'mine' | 'pco'
  const conflictSels   = new Map(); // idx       → 'mine' | 'pco'
  let   orderApplyPco  = false;
  let   applyServing   = true;

  // ── New items in PCO ──────────────────────────────────────────────────────
  if (diff.newInPco.length) {
    irmAddSection(body, 'New Items in PCO Plan');
    diff.newInPco.forEach(item => {
      const key = normTitle(item.title);
      newInPcoSels.set(key, 'add');
      const card = document.createElement('div');
      card.className = 'irm-song-card';
      const titleEl = document.createElement('div');
      titleEl.className = 'irm-song-title';
      titleEl.textContent = item.title;
      card.appendChild(titleEl);
      const gn = 'irm-new-' + Math.random().toString(36).slice(2);
      const { row: r1 } = irmRadioRow(gn, 'Add to bulletin', true,
        () => newInPcoSels.set(key, 'add'));
      const { row: r2 } = irmRadioRow(gn, 'Ignore (add to ignore list)', false,
        () => newInPcoSels.set(key, 'ignore'));
      card.appendChild(r1);
      card.appendChild(r2);
      body.appendChild(card);
    });
  }

  // ── Items removed from bulletin (still in PCO) ───────────────────────────
  if (diff.removedFromProject.length) {
    irmAddSection(body, 'Removed from Your Bulletin (still in PCO)');
    diff.removedFromProject.forEach(item => {
      const key = normTitle(item.title);
      removedSels.set(key, 'keep');
      const card = document.createElement('div');
      card.className = 'irm-song-card';
      const titleEl = document.createElement('div');
      titleEl.className = 'irm-song-title';
      titleEl.textContent = item.title;
      card.appendChild(titleEl);
      const gn = 'irm-rem-' + Math.random().toString(36).slice(2);
      const { row: r1 } = irmRadioRow(gn, 'Keep removed', true,
        () => removedSels.set(key, 'keep'));
      const { row: r2 } = irmRadioRow(gn, 'Re-add to bulletin', false,
        () => removedSels.set(key, 'readd'));
      card.appendChild(r1);
      card.appendChild(r2);
      body.appendChild(card);
    });
  }

  // ── Ignored items ─────────────────────────────────────────────────────────
  if (diff.pcoIgnoredMapped.length) {
    irmAddSection(body, 'Ignored Items (in PCO, skipped by your ignore list)');
    diff.pcoIgnoredMapped.forEach(item => {
      const key = normTitle(item.title);
      ignoredSels.set(key, 'keep');
      const card = document.createElement('div');
      card.className = 'irm-song-card';
      card.style.opacity = '0.65';
      const titleEl = document.createElement('div');
      titleEl.className = 'irm-song-title';
      titleEl.textContent = item.title + ' (ignored)';
      card.appendChild(titleEl);
      const gn = 'irm-ign-' + Math.random().toString(36).slice(2);
      const { row: r1 } = irmRadioRow(gn, 'Keep ignoring', true, () => {
        ignoredSels.set(key, 'keep');
        card.style.opacity = '0.65';
      });
      const { row: r2 } = irmRadioRow(gn, 'Un-ignore and add to bulletin', false, () => {
        ignoredSels.set(key, 'unignore');
        card.style.opacity = '1';
      });
      card.appendChild(r1);
      card.appendChild(r2);
      body.appendChild(card);
    });
  }

  // ── Title / type changes ──────────────────────────────────────────────────
  if (diff.titleTypeChanges.length) {
    irmAddSection(body, 'Title or Type Changes in PCO');
    diff.titleTypeChanges.forEach(({ normKey, prevTitle, newTitle, prevType, newType }) => {
      titleTypeSels.set(normKey, 'mine');
      const card = document.createElement('div');
      card.className = 'irm-song-card';
      const titleEl = document.createElement('div');
      titleEl.className = 'irm-song-title';
      titleEl.textContent = prevTitle;
      card.appendChild(titleEl);
      const gn = 'irm-ttc-' + Math.random().toString(36).slice(2);
      const { row: r1 } = irmRadioRow(gn,
        'Keep mine: "' + prevTitle + '" (' + prevType + ')', true,
        () => titleTypeSels.set(normKey, 'mine'));
      const { row: r2 } = irmRadioRow(gn,
        'Use PCO: "' + newTitle + '" (' + newType + ')', false,
        () => titleTypeSels.set(normKey, 'pco'));
      card.appendChild(r1);
      card.appendChild(r2);
      body.appendChild(card);
    });
  }

  // ── Note / detail conflicts (existing behaviour) ──────────────────────────
  if (refreshConflicts.length) {
    irmAddSection(body, 'Items with Updated Content from Planning Center');
    const desc = document.createElement('p');
    desc.className = 'irm-desc';
    desc.textContent = 'Planning Center has different content for the items below. Your edits have been kept by default — choose "Use PCO" for any item you want to override.';
    body.appendChild(desc);
    refreshConflicts.forEach(({ idx, title, prevDetail, pcoDetail }) => {
      conflictSels.set(idx, 'mine');
      const card = document.createElement('div');
      card.className = 'irm-song-card';
      const titleEl = document.createElement('div');
      titleEl.className = 'irm-song-title';
      titleEl.textContent = title;
      card.appendChild(titleEl);
      const gn = 'irm-rc-' + Math.random().toString(36).slice(2);
      const { row: r1 } = irmRadioRow(gn, 'Keep my current edit', true,
        () => conflictSels.set(idx, 'mine'));
      card.appendChild(r1);
      const prevFirst = prevDetail.split('\n').map(l => l.trim()).find(l => l) || '';
      if (prevFirst) {
        const pv = document.createElement('div');
        pv.className = 'irm-preview-text';
        pv.textContent = '"' + prevFirst.slice(0, 90) + (prevFirst.length > 90 ? '…' : '') + '"';
        card.appendChild(pv);
      }
      const { row: r2 } = irmRadioRow(gn, 'Use Planning Center data', false,
        () => conflictSels.set(idx, 'pco'));
      card.appendChild(r2);
      const pcoFirst = pcoDetail.split('\n').map(l => l.trim()).find(l => l) || '';
      if (pcoFirst) {
        const pv2 = document.createElement('div');
        pv2.className = 'irm-preview-text';
        pv2.textContent = '"' + pcoFirst.slice(0, 90) + (pcoFirst.length > 90 ? '…' : '') + '"';
        card.appendChild(pv2);
      }
      body.appendChild(card);
    });
  }

  // ── Order changes ─────────────────────────────────────────────────────────
  if (diff.orderChanged) {
    irmAddSection(body, 'Order Changes');
    const card = document.createElement('div');
    card.className = 'irm-song-card';
    const desc = document.createElement('div');
    desc.style.cssText = 'font-size:0.82rem;margin-bottom:0.4rem;';
    desc.textContent = 'The sequence of items in PCO differs from your bulletin order.';
    card.appendChild(desc);
    const gn = 'irm-ord-' + Math.random().toString(36).slice(2);
    const { row: r1 } = irmRadioRow(gn, 'Keep my order', true,  () => { orderApplyPco = false; });
    const { row: r2 } = irmRadioRow(gn, 'Apply PCO order', false, () => { orderApplyPco = true; });
    card.appendChild(r1);
    card.appendChild(r2);
    body.appendChild(card);
  }

  // ── Volunteer schedule ────────────────────────────────────────────────────
  {
    irmAddSection(body, 'Volunteer Schedule');
    const card = document.createElement('div');
    card.className = 'irm-song-card';
    const label = document.createElement('label');
    label.className = 'opt-row';
    label.style.cssText = 'font-size:0.82rem;margin:0.1rem 0;';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.addEventListener('change', () => { applyServing = cb.checked; });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(' Apply updated volunteer schedule from PCO'));
    card.appendChild(label);
    body.appendChild(card);
  }

  // ── Song review sections (existing) ──────────────────────────────────────
  const withNotesSels  = irmBuildWithNotesSection(body, pendingWithNotes);
  const unmatchedSels  = irmBuildUnmatchedSection(body, pendingUnmatched);

  // ── Wire buttons ──────────────────────────────────────────────────────────
  document.getElementById('irm-apply-btn').onclick = () => {
    // New in PCO: add or push to ignore list
    diff.newInPco.forEach(item => {
      const key = normTitle(item.title);
      if (newInPcoSels.get(key) === 'add') {
        items.splice(findInsertPosition(item, diff.allPcoMapped), 0, item);
      } else {
        if (!pcoIgnore.some(n => normTitle(n) === key)) {
          pcoIgnore.push(item.title);
          renderPcoIgnoreChips();
        }
      }
    });

    // Removed from project: optionally re-add
    diff.removedFromProject.forEach(item => {
      if (removedSels.get(normTitle(item.title)) === 'readd') {
        items.splice(findInsertPosition(item, diff.allPcoMapped), 0, item);
      }
    });

    // Ignored items: optionally un-ignore and add
    diff.pcoIgnoredMapped.forEach(item => {
      const key = normTitle(item.title);
      if (ignoredSels.get(key) === 'unignore') {
        pcoIgnore = pcoIgnore.filter(n => normTitle(n) !== key);
        renderPcoIgnoreChips();
        items.splice(findInsertPosition(item, diff.allPcoMapped), 0, item);
      }
    });

    // Title / type changes
    diff.titleTypeChanges.forEach(({ normKey, newTitle, newType }) => {
      if (titleTypeSels.get(normKey) === 'pco') {
        const live = items.find(i => normTitle(i.title) === normKey);
        if (live) { live.title = newTitle; live.type = newType; }
      }
    });

    // Note / detail conflicts
    refreshConflicts.forEach(({ idx, pcoDetail }) => {
      if (conflictSels.get(idx) === 'pco' && items[idx]) {
        items[idx].detail = pcoDetail;
      }
    });

    // Order
    if (orderApplyPco && diff.orderChanged) {
      applyCPcoOrder(diff.newMatchedNorms);
    }

    // Volunteer schedule
    if (applyServing && serveCallback) serveCallback();

    // Song review (existing)
    irmApplyWithNotes(pendingWithNotes, withNotesSels);
    irmApplyUnmatched(pendingUnmatched, unmatchedSels);

    renderItemList();
    renderPreview();
    scheduleProjectPersist();
    closeImportReviewDialog();
  };

  document.getElementById('irm-cancel-btn').onclick = closeImportReviewDialog;
  document.getElementById('irm-close-btn').onclick  = closeImportReviewDialog;

  document.getElementById('irm-title').textContent = 'Review Plan Changes';
  document.getElementById('import-review-modal').style.display = 'flex';
}
```

- [ ] **Step 3: Update the tail of `applyPcoData` to use `showResyncDiffDialog`**

At the end of `applyPcoData`, find the block that starts:

```js
  // Surface a per-item review dialog when PCO data differs from user edits.
  // Pass pending song reviews so they can be chained after conflict resolution.
  if (refreshConflicts.length > 0) {
    showRefreshConflictsDialog(refreshConflicts, pendingWithNotes, pendingUnmatched);
    return;
  }

  // No conflicts — go straight to import review if there are new songs to handle.
  if (pendingWithNotes.length || pendingUnmatched.length) {
    showImportReviewDialog(pendingWithNotes, pendingUnmatched);
  }
```

Replace with:

```js
  // ── Resync path: full diff dialogue ─────────────────────────────────────
  if (isResync && prevItems.length > 0) {
    const diff = buildResyncDiff(prevItems, items, pcoIgnoredMapped, allPcoMapped);
    const hasChanges =
      diff.newInPco.length || diff.removedFromProject.length ||
      diff.pcoIgnoredMapped.length || diff.titleTypeChanges.length ||
      diff.orderChanged || refreshConflicts.length ||
      pendingWithNotes.length || pendingUnmatched.length;

    if (!hasChanges) {
      setStatus('Plan is up to date — no changes detected.', 'success');
      if (servingParams) {
        pcoFetchAndApplyServing(
          servingParams.stId, servingParams.planId,
          servingParams.sortDate, servingParams.date
        );
      }
      return;
    }

    const serveCallback = servingParams
      ? () => pcoFetchAndApplyServing(
          servingParams.stId, servingParams.planId,
          servingParams.sortDate, servingParams.date
        )
      : null;

    showResyncDiffDialog(diff, refreshConflicts, pendingWithNotes, pendingUnmatched, serveCallback);
    return;
  }

  // ── Initial import path (unchanged) ─────────────────────────────────────
  // Surface a per-item review dialog when PCO data differs from user edits.
  if (refreshConflicts.length > 0) {
    showRefreshConflictsDialog(refreshConflicts, pendingWithNotes, pendingUnmatched);
    return;
  }

  // No conflicts — go straight to import review if there are new songs to handle.
  if (pendingWithNotes.length || pendingUnmatched.length) {
    showImportReviewDialog(pendingWithNotes, pendingUnmatched);
  }
```

- [ ] **Step 4: Verify resync diff in browser**

With PCO connected and a plan imported:

1. Reload the page. Add a PCO item name to the ignore list.
2. Click "↺ Refresh from PCO".
3. The "Review Plan Changes" modal should appear.
4. Verify the "Ignored Items" section shows the item you ignored (greyed, "Keep ignoring" default).
5. Select "Un-ignore and add" on one item → click "Apply & Continue" → that item should appear in the item list and be removed from the ignore chips.

6. Manually delete an item from the item list, then refresh from PCO.
7. That item should appear in the "Removed from Your Bulletin" section.
8. Select "Re-add" → click Apply → item reappears.

9. If PCO plan truly has no changes vs project, the modal should NOT appear; instead a toast "Plan is up to date — no changes detected." should show.

- [ ] **Step 5: Commit**

```bash
git add src/js/pco.js
git commit -m "feat(#81): add showResyncDiffDialog with full diff categories and apply logic"
```

---

## Task 8: Push branch and final verification

- [ ] **Step 1: Run a full end-to-end flow**

Start the server fresh:

```bash
python3 server.py
```

Open http://localhost:8080 and verify:

a. **Ignore list persists:** Add "Sermon" to the ignore list, save the project, reload page, load the same project → "Sermon" chip should still be present.

b. **Initial import unaffected:** Import a PCO plan → no resync diff modal appears (only existing song review dialog, if any).

c. **Resync with ignored item:** After import, type an item's actual PCO title in the ignore list. Refresh from PCO → that item should disappear from the item list. The resync diff modal should show it in the "Ignored Items" section.

d. **New project clears ignore list:** Click "New" to create a new project → ignore chips should be empty.

e. **pcoLastImportedTitles serialised:** Open browser console, run `collectCurrentProjectState().pcoLastImportedTitles` → should show the PCO item title array (non-empty after import).

- [ ] **Step 2: Check for console errors**

Open browser DevTools Console. Perform a full import + resync cycle. There should be no uncaught errors.

- [ ] **Step 3: Push branch**

```bash
cd "/Users/ajhochhalter/Documents/Bulletin Generator - Most Recent Release"
git push -u origin feature/issue-81-pco-ignore-resync
```

Expected output should include `Branch 'feature/issue-81-pco-ignore-resync' set up to track remote branch`.
