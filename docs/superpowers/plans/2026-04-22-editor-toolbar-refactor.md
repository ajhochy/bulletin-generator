# Editor Toolbar Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move document/system controls (File, Sync, Service Details, Options) out of the Booklet Editor left panel and into a horizontal dropdown toolbar that only appears in the Booklet Editor tab, leaving the left panel as a pure content editor.

**Architecture:** The toolbar is placed inside `#page-editor` before `<main>`, so it automatically appears/disappears with the tab — no JS tab-switch wiring needed. Each toolbar item is a DaisyUI `<details class="dropdown">` with a `<div class="dropdown-content">` panel (not `<ul class="menu">` since panels contain form fields, not just menu items). All DOM IDs stay unchanged — only the surrounding HTML structure moves.

**Tech Stack:** Plain HTML, DaisyUI (already used in project), CSS in `src/css/compat.css`. No JS logic changes — just moving elements to new DOM parents.

---

> **Note on TDD:** This is a pure HTML/CSS restructuring with no logic changes. All unit-testable behavior (save, import, options) remains in the same JS functions referencing the same DOM IDs. The "test" for each task is a server start + browser smoke check confirming the moved controls still work.

---

### Task 1: Add Editor Toolbar Skeleton (HTML + CSS)

**Files:**
- Modify: `index.html` (between line 37 and `<main>`)
- Modify: `src/css/compat.css` (after the `.tab-bar` block, ~line 143)

- [ ] **Step 1: Add the toolbar HTML inside `#page-editor`, before `<main>`**

Open `index.html`. Find line 37:
```html
<div class="app-page active" id="page-editor" style="flex-direction:column; height:calc(100vh - 88px);">
<main>
```

Replace with:
```html
<div class="app-page active" id="page-editor" style="flex-direction:column; height:calc(100vh - 88px);">

<!-- ═══ Editor Toolbar ══════════════════════════════════════════════════════ -->
<div id="editor-toolbar" class="flex items-center gap-1 px-2 border-b border-base-300 bg-base-100 flex-shrink-0" style="min-height:38px;">

  <!-- File dropdown -->
  <details class="dropdown" id="editor-toolbar-file">
    <summary class="btn btn-ghost btn-sm gap-1 font-medium">
      <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M2 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v13.5a.5.5 0 0 1-.777.416L8 13.101l-5.223 2.815A.5.5 0 0 1 2 15.5V2zm2-1a1 1 0 0 0-1 1v12.566l4.723-2.482a.5.5 0 0 1 .554 0L13 14.566V2a1 1 0 0 0-1-1H4z"/></svg>
      File
      <span id="editor-file-dirty-dot" class="w-1.5 h-1.5 rounded-full bg-warning" style="display:none;" title="Unsaved changes or conflict"></span>
    </summary>
    <div id="editor-file-panel" class="dropdown-content z-50 bg-base-100 border border-base-300 rounded-lg shadow-lg mt-1 p-3 w-80">
      <!-- File panel content moves here in Task 2 -->
    </div>
  </details>

  <!-- Sync dropdown -->
  <details class="dropdown" id="editor-toolbar-sync">
    <summary class="btn btn-ghost btn-sm gap-1 font-medium">
      <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z"/><path d="M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z"/></svg>
      Sync
    </summary>
    <div id="editor-sync-panel" class="dropdown-content z-50 bg-base-100 border border-base-300 rounded-lg shadow-lg mt-1 p-3 w-80 max-h-[520px] overflow-y-auto">
      <!-- Sync panel content moves here in Task 3 -->
    </div>
  </details>

  <!-- Document dropdown -->
  <details class="dropdown" id="editor-toolbar-document">
    <summary class="btn btn-ghost btn-sm gap-1 font-medium">
      <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M4 0h5.293A1 1 0 0 1 10 .293L13.707 4a1 1 0 0 1 .293.707V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2zm5.5 1.5v2a1 1 0 0 0 1 1h2L9.5 1.5z"/></svg>
      Document
    </summary>
    <div id="editor-document-panel" class="dropdown-content z-50 bg-base-100 border border-base-300 rounded-lg shadow-lg mt-1 p-3 w-80 max-h-[580px] overflow-y-auto">
      <!-- Document panel content moves here in Task 4 -->
    </div>
  </details>

  <div class="flex-1"></div>
</div>
<!-- ════════════════════════════════════════════════════════════════════════ -->

<main>
```

- [ ] **Step 2: Add toolbar CSS to `src/css/compat.css`**

Find the `.tab-bar-right` block (~line 133). After it, add:

```css
/* ─── Editor Toolbar ─────────────────────────────────────────────────────────
   Horizontal dropdown toolbar that appears only inside the Booklet Editor tab.
   Placed before <main> inside #page-editor so it shows/hides with the tab.
   ────────────────────────────────────────────────────────────────────────── */
#editor-toolbar .dropdown-content {
  /* Ensure panels appear above the aside sidebar and preview pane */
  z-index: 50;
}
#editor-toolbar details > summary {
  list-style: none;
}
#editor-toolbar details > summary::-webkit-details-marker {
  display: none;
}
```

- [ ] **Step 3: Start the dev server and verify the toolbar renders**

```bash
cd "/Users/ajhochhalter/Documents/Bulletin Generator - Most Recent Release"
python3 server.py
```

Open `http://localhost:8080` in a browser. Expected:
- Booklet Editor tab shows a slim toolbar bar with "File", "Sync", "Document" buttons below the main tabs
- Clicking each button opens an empty dropdown panel
- Switching to Projects/Settings tab hides the toolbar completely

- [ ] **Step 4: Commit**

```bash
git add index.html src/css/compat.css
git commit -m "feat: add editor toolbar skeleton with File/Sync/Document dropdowns"
```

---

### Task 2: File Dropdown — Move File Panel

**Files:**
- Modify: `index.html` (move File panel content from `<aside>` to `#editor-file-panel`)

**Context:** The File panel currently occupies `index.html` lines 95–116. It contains: Bulletin Title input, Save/Save New Version/New/Delete buttons, `#project-meta`, `#stale-banner`, `#conflict-banner`, "Browse & manage projects" button, and a hidden `#project-select`. All these DOM IDs are referenced by `src/js/projects.js` — moving them to the dropdown doesn't require any JS changes.

A `#editor-file-dirty-dot` orange dot on the File button will show when either banner has content, so users know to open File even when the dropdown is closed. A small JS addition to `src/js/projects.js` (or `src/js/app.js`) will drive this dot.

**Files:**
- Modify: `index.html`
- Modify: `src/js/projects.js` (add dirty-dot update logic, ~4 lines)

- [ ] **Step 1: Move File panel HTML into `#editor-file-panel`**

In `index.html`, find and **remove** this entire block (lines 95–116):
```html
    <!-- File (project management) -->
    <div class="panel-section rounded-lg border border-base-300 bg-base-100 mb-2 p-3">
      <div class="section-label text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">File</div>
      <div class="field-row form-control mb-1">
        <label class="label py-0.5" for="bulletin-title"><span class="label-text text-xs">Bulletin Title</span></label>
        <input type="text" class="input input-bordered input-sm w-full" id="bulletin-title" placeholder="e.g. March 22, 2026 Bulletin" />
      </div>
      <div class="projects-actions flex flex-wrap gap-1 mt-2">
        <button class="btn btn-sm btn-primary" id="project-save-btn" type="button">Save</button>
        <button class="btn btn-sm btn-ghost" id="project-save-as-btn" type="button">Save New Version</button>
        <button class="btn btn-sm btn-ghost" id="project-new-btn" type="button">New</button>
        <button class="btn btn-sm btn-error" id="project-delete-btn" type="button">Delete</button>
      </div>
      <div class="project-meta text-xs text-base-content/50 mt-1" id="project-meta">Unsaved draft autosaves in this browser.</div>
      <div id="stale-banner" style="display:none;color:#7a5c45;" class="text-xs mt-1"></div>
      <div id="conflict-banner" style="display:none;" class="text-xs mt-1 text-error"></div>
      <button class="btn btn-ghost btn-xs files-browse-btn mt-1" id="project-browse-btn" type="button">Browse &amp; manage projects →</button>
      <!-- Hidden select kept for internal JS state tracking -->
      <select id="project-select" style="display:none;">
        <option value="__draft__">Unsaved Draft</option>
      </select>
    </div>
```

Replace the placeholder comment inside `#editor-file-panel` (added in Task 1) with:
```html
      <div class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">File</div>
      <div class="field-row form-control mb-1">
        <label class="label py-0.5" for="bulletin-title"><span class="label-text text-xs">Bulletin Title</span></label>
        <input type="text" class="input input-bordered input-sm w-full" id="bulletin-title" placeholder="e.g. March 22, 2026 Bulletin" />
      </div>
      <div class="projects-actions flex flex-wrap gap-1 mt-2">
        <button class="btn btn-sm btn-primary" id="project-save-btn" type="button">Save</button>
        <button class="btn btn-sm btn-ghost" id="project-save-as-btn" type="button">Save New Version</button>
        <button class="btn btn-sm btn-ghost" id="project-new-btn" type="button">New</button>
        <button class="btn btn-sm btn-error" id="project-delete-btn" type="button">Delete</button>
      </div>
      <div class="project-meta text-xs text-base-content/50 mt-1" id="project-meta">Unsaved draft autosaves in this browser.</div>
      <div id="stale-banner" style="display:none;color:#7a5c45;" class="text-xs mt-1"></div>
      <div id="conflict-banner" style="display:none;" class="text-xs mt-1 text-error"></div>
      <button class="btn btn-ghost btn-xs files-browse-btn mt-1" id="project-browse-btn" type="button">Browse &amp; manage projects →</button>
      <!-- Hidden select kept for internal JS state tracking -->
      <select id="project-select" style="display:none;">
        <option value="__draft__">Unsaved Draft</option>
      </select>
```

- [ ] **Step 2: Add dirty-dot update helper**

In `src/js/projects.js`, find the function `updateProjectMeta` (or wherever `project-meta`, `stale-banner`, `conflict-banner` are written to). Search for assignments to `#stale-banner` and `#conflict-banner`.

After any line that sets `staleBanner.style.display` or `conflictBanner.style.display`, add a call to `_updateFileDirtyDot()`.

Add this helper function near the top of `projects.js` (after the existing `const` declarations):

```javascript
function _updateFileDirtyDot() {
  const dot = document.getElementById('editor-file-dirty-dot');
  if (!dot) return;
  const stale = document.getElementById('stale-banner');
  const conflict = document.getElementById('conflict-banner');
  const active = (stale && stale.style.display !== 'none' && stale.textContent.trim()) ||
                 (conflict && conflict.style.display !== 'none' && conflict.textContent.trim());
  dot.style.display = active ? 'inline-block' : 'none';
}
```

Search for all places in `projects.js` where `stale-banner` or `conflict-banner` visibility is set. There will be 2–4 such sites. After each, add:
```javascript
_updateFileDirtyDot();
```

Run:
```bash
grep -n "stale-banner\|conflict-banner" "src/js/projects.js"
```
Expected: 4–8 lines referencing these IDs. Add the call after each `.style.display` assignment in that list.

- [ ] **Step 3: Verify File dropdown works**

```bash
python3 server.py
```

Open `http://localhost:8080`. In Booklet Editor:
- Click "File" in toolbar — panel opens with Bulletin Title field and Save/New/Delete buttons
- Type a title — autosave should still trigger normally
- Click "Save" — `#project-meta` text updates inside the panel
- Simulate a stale revision (open in two tabs, save in one) — orange dot should appear on "File" button

- [ ] **Step 4: Commit**

```bash
git add index.html src/js/projects.js
git commit -m "feat: move File panel into editor toolbar File dropdown"
```

---

### Task 3: Sync Dropdown — Move PCO Section

**Files:**
- Modify: `index.html`

**Context:** The Planning Center section (`#pco-section`, lines 41–93) is a self-contained block. All event handlers in `src/js/pco.js` reference its child elements by DOM ID (`pco-connect-btn`, `pco-service-type-sel`, etc.) — no handler changes needed after the move.

- [ ] **Step 1: Move PCO section HTML into `#editor-sync-panel`**

In `index.html`, find and **remove** this entire block (lines 41–93):
```html
    <!-- Import from Planning Center -->
    <div class="panel-section rounded-lg border border-base-300 bg-base-100 mb-2 p-3" id="pco-section">
      <div class="section-label text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">Import from Planning Center</div>

      <!-- Credentials view -->
      <div id="pco-creds-view">
        <p class="section-hint text-xs text-base-content/60 mb-1" id="pco-creds-hint"></p>
        <button class="btn btn-primary btn-sm w-full mt-1" id="pco-connect-btn">Connect Planning Center</button>
        <div id="pco-creds-msg" class="pco-msg"></div>
      </div>

      <!-- Connected / import view -->
      <div id="pco-import-view" style="display:none;">
        <div class="bg-base-200 border border-base-300 rounded-lg p-3 mt-2">
          <div class="pco-status-row flex items-center justify-between mb-2">
            <div class="flex items-center gap-1">
              <span class="text-success text-sm leading-none">●</span>
              <span class="pco-connected-badge text-sm font-medium" id="pco-connected-badge">Connected</span>
            </div>
            <button class="btn btn-ghost btn-xs" id="pco-disconnect-btn" style="display:none;">Disconnect</button>
          </div>
          <div class="field-row form-control mb-1">
            <label class="label py-0.5" for="pco-service-type-sel"><span class="label-text text-xs">Service Type</span></label>
            <select class="select select-bordered select-sm w-full" id="pco-service-type-sel"><option value="">Loading…</option></select>
          </div>
          <div class="field-row form-control mb-1" id="pco-plan-field" style="display:none;">
            <label class="label py-0.5" for="pco-plan-sel"><span class="label-text text-xs">Plan</span></label>
            <select class="select select-bordered select-sm w-full" id="pco-plan-sel"><option value="">— Select plan —</option></select>
            <label class="opt-row flex items-center gap-1.5 mt-1 text-xs cursor-pointer">
              <input type="checkbox" class="checkbox checkbox-xs" id="pco-show-past" />
              Show previous plans
            </label>
          </div>
          <button class="btn btn-primary btn-sm w-full mt-2" id="pco-import-btn" disabled>Import Plan</button>
          <div id="pco-import-msg" class="pco-msg"></div>
          <div id="pco-last-import-wrap" style="display:none;" class="mt-3 pt-3 border-t border-base-300">
            <div class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-1">Last Imported</div>
            <div id="pco-last-plan-label" class="text-xs mb-2"></div>
            <button class="btn btn-ghost btn-sm w-full" id="pco-refresh-btn">↺ Refresh from PCO</button>
            <div id="pco-refresh-msg" class="pco-msg"></div>
            <div id="pco-ignore-wrap" class="mt-2 pt-2 border-t border-base-300">
              <div class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-1">Ignore Items Named</div>
              <div id="pco-ignore-chips" class="flex flex-wrap gap-1 mb-1 min-h-2"></div>
              <div class="flex gap-1">
                <input type="text" class="input input-bordered input-xs flex-1" id="pco-ignore-input" placeholder="Item name…" />
                <button class="btn btn-ghost btn-xs" id="pco-ignore-add-btn">Add</button>
              </div>
              <div class="text-xs text-base-content/50 mt-1">Items with these names are skipped on import and refresh.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
```

Replace the placeholder comment inside `#editor-sync-panel` with:
```html
      <div class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">Planning Center Sync</div>

      <!-- Credentials view -->
      <div id="pco-creds-view">
        <p class="section-hint text-xs text-base-content/60 mb-1" id="pco-creds-hint"></p>
        <button class="btn btn-primary btn-sm w-full mt-1" id="pco-connect-btn">Connect Planning Center</button>
        <div id="pco-creds-msg" class="pco-msg"></div>
      </div>

      <!-- Connected / import view -->
      <div id="pco-import-view" style="display:none;">
        <div class="bg-base-200 border border-base-300 rounded-lg p-3 mt-2">
          <div class="pco-status-row flex items-center justify-between mb-2">
            <div class="flex items-center gap-1">
              <span class="text-success text-sm leading-none">●</span>
              <span class="pco-connected-badge text-sm font-medium" id="pco-connected-badge">Connected</span>
            </div>
            <button class="btn btn-ghost btn-xs" id="pco-disconnect-btn" style="display:none;">Disconnect</button>
          </div>
          <div class="field-row form-control mb-1">
            <label class="label py-0.5" for="pco-service-type-sel"><span class="label-text text-xs">Service Type</span></label>
            <select class="select select-bordered select-sm w-full" id="pco-service-type-sel"><option value="">Loading…</option></select>
          </div>
          <div class="field-row form-control mb-1" id="pco-plan-field" style="display:none;">
            <label class="label py-0.5" for="pco-plan-sel"><span class="label-text text-xs">Plan</span></label>
            <select class="select select-bordered select-sm w-full" id="pco-plan-sel"><option value="">— Select plan —</option></select>
            <label class="opt-row flex items-center gap-1.5 mt-1 text-xs cursor-pointer">
              <input type="checkbox" class="checkbox checkbox-xs" id="pco-show-past" />
              Show previous plans
            </label>
          </div>
          <button class="btn btn-primary btn-sm w-full mt-2" id="pco-import-btn" disabled>Import Plan</button>
          <div id="pco-import-msg" class="pco-msg"></div>
          <div id="pco-last-import-wrap" style="display:none;" class="mt-3 pt-3 border-t border-base-300">
            <div class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-1">Last Imported</div>
            <div id="pco-last-plan-label" class="text-xs mb-2"></div>
            <button class="btn btn-ghost btn-sm w-full" id="pco-refresh-btn">↺ Refresh from PCO</button>
            <div id="pco-refresh-msg" class="pco-msg"></div>
            <div id="pco-ignore-wrap" class="mt-2 pt-2 border-t border-base-300">
              <div class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-1">Ignore Items Named</div>
              <div id="pco-ignore-chips" class="flex flex-wrap gap-1 mb-1 min-h-2"></div>
              <div class="flex gap-1">
                <input type="text" class="input input-bordered input-xs flex-1" id="pco-ignore-input" placeholder="Item name…" />
                <button class="btn btn-ghost btn-xs" id="pco-ignore-add-btn">Add</button>
              </div>
              <div class="text-xs text-base-content/50 mt-1">Items with these names are skipped on import and refresh.</div>
            </div>
          </div>
        </div>
      </div>
```

Note: the outer `<div id="pco-section" class="panel-section ...">` wrapper is **dropped** — the `#editor-sync-panel` div serves as the container now. `#pco-section` as an ID is only referenced in `src/js/pco.js` as a positional marker — verify this before removing:

```bash
grep -rn "pco-section" src/js/
```

Expected output: 0 lines (the ID is not referenced in JS — it was only a CSS anchor). If you see JS references, adjust accordingly before proceeding.

- [ ] **Step 2: Verify Sync dropdown works**

```bash
python3 server.py
```

Open `http://localhost:8080`, Booklet Editor tab. Click "Sync":
- Unconnected state: shows "Connect Planning Center" button
- If PCO was previously connected: shows Connected badge + service type dropdown
- "Import Plan" button works and populates Order of Worship items

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat: move Planning Center import section into Sync dropdown"
```

---

### Task 4: Document Dropdown — Move Service Details, Cover Image, Options

**Files:**
- Modify: `index.html`

**Context:** Three sections move into `#editor-document-panel`: Service Details (lines 118–129, contains `#svc-title` and `#svc-date`), Cover Image (lines 131–144, contains `#cover-img-zone` and related), and Options (lines 146–163, contains all `opt-*` checkboxes and `#opt-booklet-size`). All DOM IDs are referenced by `src/js/editor.js` and `src/js/state.js` — no changes needed to those files.

- [ ] **Step 1: Move Service Details section**

In `index.html`, find and **remove** this block (lines 118–129):
```html
    <!-- Service Details -->
    <div class="panel-section rounded-lg border border-base-300 bg-base-100 mb-2 p-3">
      <div class="section-label text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">Service Details</div>
      <div class="field-row form-control mb-1">
        <label class="label py-0.5" for="svc-title"><span class="label-text text-xs">Service Title</span></label>
        <input type="text" class="input input-bordered input-sm w-full" id="svc-title" placeholder="e.g. Morning Worship" />
      </div>
      <div class="field-row form-control mb-1">
        <label class="label py-0.5" for="svc-date"><span class="label-text text-xs">Date</span></label>
        <input type="text" class="input input-bordered input-sm w-full" id="svc-date" placeholder="e.g. January 5, 2025" />
      </div>
    </div>
```

Replace the placeholder comment inside `#editor-document-panel` with:
```html
      <!-- Service Details -->
      <div class="mb-3 pb-3 border-b border-base-300">
        <div class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">Service Details</div>
        <div class="field-row form-control mb-1">
          <label class="label py-0.5" for="svc-title"><span class="label-text text-xs">Service Title</span></label>
          <input type="text" class="input input-bordered input-sm w-full" id="svc-title" placeholder="e.g. Morning Worship" />
        </div>
        <div class="field-row form-control mb-1">
          <label class="label py-0.5" for="svc-date"><span class="label-text text-xs">Date</span></label>
          <input type="text" class="input input-bordered input-sm w-full" id="svc-date" placeholder="e.g. January 5, 2025" />
        </div>
      </div>

      <!-- Cover Image (placeholder — filled in Step 2) -->
```

- [ ] **Step 2: Move Cover Image section**

In `index.html`, find and **remove** this block (lines 131–144):
```html
    <!-- Cover Image -->
    <div class="panel-section rounded-lg border border-base-300 bg-base-100 mb-2 p-3">
      <div class="section-label text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">Cover Image</div>
      <p class="section-hint text-xs text-base-content/60 mb-2">Displayed on the cover page in place of the cross symbol.</p>
      <div class="img-zone" id="cover-img-zone" role="button" tabindex="0">
        <input type="file" id="cover-img-input" accept="image/*" />
        <div id="cover-img-label">Click to select an image</div>
      </div>
      <div class="img-preview-wrap" id="cover-img-preview-wrap" style="display:none;">
        <img class="img-preview-thumb" id="cover-img-thumb" src="" alt="" />
        <span class="img-preview-name" id="cover-img-name"></span>
        <button class="img-clear-btn btn btn-ghost btn-xs" id="cover-img-clear">Remove</button>
      </div>
    </div>
```

Replace the `<!-- Cover Image (placeholder — filled in Step 2) -->` comment with:
```html
      <!-- Cover Image -->
      <div class="mb-3 pb-3 border-b border-base-300">
        <div class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">Cover Image</div>
        <p class="section-hint text-xs text-base-content/60 mb-2">Displayed on the cover page in place of the cross symbol.</p>
        <div class="img-zone" id="cover-img-zone" role="button" tabindex="0">
          <input type="file" id="cover-img-input" accept="image/*" />
          <div id="cover-img-label">Click to select an image</div>
        </div>
        <div class="img-preview-wrap" id="cover-img-preview-wrap" style="display:none;">
          <img class="img-preview-thumb" id="cover-img-thumb" src="" alt="" />
          <span class="img-preview-name" id="cover-img-name"></span>
          <button class="img-clear-btn btn btn-ghost btn-xs" id="cover-img-clear">Remove</button>
        </div>
      </div>

      <!-- Options (placeholder — filled in Step 3) -->
```

- [ ] **Step 3: Move Options section**

In `index.html`, find and **remove** this block (lines 146–163):
```html
    <!-- Options -->
    <div class="panel-section rounded-lg border border-base-300 bg-base-100 mb-2 p-3">
      <div class="section-label text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">Options</div>
      <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-cover" checked /> Include cover page</label>
      <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-footer" /> Include page footer</label>
      <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-announcements" checked /> Include announcements</label>
      <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-cal" checked /> Include "This Week" calendar page</label>
      <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-volunteers" checked /> Include volunteers / serving schedule</label>
      <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-staff" checked /> Include staff &amp; contact page</label>
      <div class="form-control mt-2">
        <label class="label py-0.5"><span class="label-text text-xs">Booklet size target</span></label>
        <select class="select select-bordered select-sm w-full" id="opt-booklet-size">
          <option value="auto">Auto (no target)</option>
          <option value="8">8 pages</option>
          <option value="12">12 pages</option>
        </select>
      </div>
    </div>
```

Replace `<!-- Options (placeholder — filled in Step 3) -->` with:
```html
      <!-- Options -->
      <div>
        <div class="text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">Options</div>
        <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-cover" checked /> Include cover page</label>
        <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-footer" /> Include page footer</label>
        <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-announcements" checked /> Include announcements</label>
        <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-cal" checked /> Include "This Week" calendar page</label>
        <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-volunteers" checked /> Include volunteers / serving schedule</label>
        <label class="opt-row flex items-center gap-1.5 text-sm mb-1 cursor-pointer"><input type="checkbox" class="checkbox checkbox-xs checkbox-primary" id="opt-staff" checked /> Include staff &amp; contact page</label>
        <div class="form-control mt-2">
          <label class="label py-0.5"><span class="label-text text-xs">Booklet size target</span></label>
          <select class="select select-bordered select-sm w-full" id="opt-booklet-size">
            <option value="auto">Auto (no target)</option>
            <option value="8">8 pages</option>
            <option value="12">12 pages</option>
          </select>
        </div>
      </div>
```

- [ ] **Step 4: Verify Document dropdown works**

```bash
python3 server.py
```

Open `http://localhost:8080`, Booklet Editor tab. Click "Document":
- Panel shows "Service Details" (title + date inputs), "Cover Image" (upload zone), and "Options" (checkboxes + booklet size)
- Typing in Service Title → live preview updates
- Toggling "Include cover page" checkbox → live preview updates
- Uploading a cover image → preview updates

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: move Service Details, Cover Image, and Options into Document dropdown"
```

---

### Task 5: Verify Aside Is Content-Only

**Files:**
- Verify: `index.html` `<aside>` — should only contain Welcome, Announcements, Order of Worship, Calendar, Volunteers, Church Staff & Contact
- Verify: `src/js/editor.js` — `aside .panel-section` collapse logic applies to all remaining sections

- [ ] **Step 1: Confirm aside contains exactly 6 sections**

```bash
grep -c 'class="panel-section' index.html
```

Expected: `6` (Welcome, Announcements, Order of Worship, Calendar, Volunteers, Church Staff & Contact).

If the count is higher, a section was not removed from the aside. Find the stray section:
```bash
grep -n 'class="panel-section' index.html
```

Expected lines: approximately 166, 175, 183, 193, 205, 216 (the 6 content sections).

- [ ] **Step 2: Confirm no duplicate DOM IDs were introduced**

```bash
grep -oE 'id="[^"]+"' index.html | sort | uniq -d
```

Expected: no output. Any output indicates a duplicate ID — fix by ensuring each ID only appears once (the moved sections should no longer be in the aside).

- [ ] **Step 3: Full smoke test**

```bash
python3 server.py
```

Open `http://localhost:8080`. Walk through this checklist:

**Toolbar appearance:**
- [ ] Booklet Editor tab: toolbar with File, Sync, Document buttons is visible
- [ ] Projects tab: toolbar is NOT visible
- [ ] Settings tab: toolbar is NOT visible

**File dropdown:**
- [ ] Opens and shows Bulletin Title, Save, Save New Version, New, Delete
- [ ] Save updates `#project-meta` text inside the panel
- [ ] "Browse & manage projects →" link switches to Projects tab

**Sync dropdown:**
- [ ] Shows Connect/Connected state correctly
- [ ] Service type dropdown populates (if PCO connected)
- [ ] Import Plan populates Order of Worship in aside

**Document dropdown:**
- [ ] Service Title + Date inputs trigger live preview update on change
- [ ] Checkboxes toggle sections in live preview
- [ ] Cover image upload reflects in preview
- [ ] Booklet size dropdown changes page target

**Aside (content-only panel):**
- [ ] Collapse/expand (+ / −) toggles work on all 6 remaining sections
- [ ] Welcome, Announcements, Order of Worship, Calendar, Volunteers, Staff sections are present

**Download PDF:**
- [ ] Button in top-right of tab bar still works (was already outside aside — no change needed)

- [ ] **Step 4: Final commit**

```bash
git add index.html src/js/projects.js src/css/compat.css
git commit -m "feat: complete editor toolbar refactor — closes #181"
```

---

## Self-Review Against Spec

**Acceptance criteria check:**

| Criteria | Covered in |
|----------|-----------|
| Booklet Editor shows top dropdown toolbar | Task 1 |
| Toolbar only appears in Booklet Editor tab | Task 1 (placed inside `#page-editor`) |
| PCO controls moved to Sync dropdown | Task 3 |
| File controls moved to File dropdown | Task 2 |
| Service Details + Options moved to Document dropdown | Task 4 |
| Welcome, Announcements, Order of Worship, Calendar, Volunteers, Staff stay in aside | Task 4 / Task 5 |
| Download PDF separated from sidebar | Already true (lives in `.tab-bar-right`) — no change needed |
| No existing functionality lost | DOM IDs preserved throughout; only HTML structure relocated |

**Church Name field:** The issue spec lists "Church Name" under Document, but in this codebase it already lives in the Settings tab (`index.html` line 406, `id="svc-church"`). It is not in the editor sidebar. No action needed — the spec was written before inspecting the actual HTML.

**Placeholder scan:** No TODOs or TBDs. All code blocks are complete.
