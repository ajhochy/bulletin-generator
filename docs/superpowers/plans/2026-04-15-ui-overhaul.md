# UI Overhaul — Tailwind CSS + DaisyUI 4 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the app's custom hand-rolled CSS to Tailwind CSS + DaisyUI 4 with a VCRC navy theme, touching only aesthetics — no logic changes.

**Architecture:** Sequential migration across 10 issues (#146–#155). Tailwind CLI generates `src/css/tw-output.css` (committed for Docker). All old CSS files coexist until the final cleanup task. Functional JS class names (e.g. `.item-card`, `.file-card`) are preserved alongside new Tailwind classes.

**Tech Stack:** Tailwind CSS v3, DaisyUI v4, npm Tailwind CLI, Python stdlib HTTP server (no bundler in dev).

**Constraint:** Aesthetic only. Do not change business logic, data flow, or API calls. Do not change `src/css/preview.css` or `src/css/print.css`.

---

## Task 1: Issue #146 — Install Tailwind CSS + DaisyUI 4, configure VCRC theme

**Files:**
- Create: `tailwind.config.js`
- Create: `src/css/tw-input.css`
- Create: `src/css/tw-output.css` (generated, committed)
- Modify: `package.json`
- Modify: `index.html`

- [ ] **Step 1: Install packages**

```bash
npm install --save-dev tailwindcss@3 autoprefixer daisyui@4
```

Expected: `package.json` gains `tailwindcss`, `autoprefixer`, `daisyui` under `devDependencies`.

- [ ] **Step 2: Create `tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './index.html',
    './src/**/*.{js,ts}',
  ],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {},
  },
  plugins: [require('daisyui')],
  daisyui: {
    themes: [
      {
        vcrc: {
          "primary":         "#172429",
          "primary-content": "#ffffff",
          "secondary":       "#4b5563",
          "accent":          "#3b82f6",
          "neutral":         "#374151",
          "base-100":        "#ffffff",
          "base-200":        "#f9fafb",
          "base-300":        "#e5e7eb",
          "base-content":    "#111827",
          "info":            "#3b82f6",
          "success":         "#22c55e",
          "warning":         "#f59e0b",
          "error":           "#ef4444",
        },
      },
    ],
    logs: false,
  },
};
```

- [ ] **Step 3: Create `src/css/tw-input.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: Add npm scripts to `package.json`**

Add these two entries to the `"scripts"` block:

```json
"css:watch": "tailwindcss -i src/css/tw-input.css -o src/css/tw-output.css --watch",
"css:build": "tailwindcss -i src/css/tw-input.css -o src/css/tw-output.css --minify"
```

- [ ] **Step 5: Add Tailwind output link and theme to `index.html`**

Change line 2 from:
```html
<html lang="en">
```
to:
```html
<html lang="en" data-theme="vcrc">
```

Add after line 11 (after the existing CSS links):
```html
  <link rel="stylesheet" href="src/css/tw-output.css" />
```

- [ ] **Step 6: Build initial `tw-output.css`**

```bash
npm run css:build
```

Expected: `src/css/tw-output.css` is created (~50–200KB).

- [ ] **Step 7: Run tests**

```bash
npm test
```

Expected: all tests pass (this task touches no app logic).

- [ ] **Step 8: Commit**

```bash
git add tailwind.config.js src/css/tw-input.css src/css/tw-output.css package.json package-lock.json index.html
git commit -m "chore(#146): install Tailwind CSS v3 + DaisyUI 4, configure VCRC theme"
```

---

## Task 2: Issue #147 — App shell — navbar, tab bar, toast system

**Files:**
- Modify: `index.html` (lines 16–31 header + tab bar; line 663 toast container)
- Modify: `src/js/utils.js` (setStatus function)
- Modify: `src/css/tw-input.css` (add tab active-state layer)

- [ ] **Step 1: Replace `<header>` with DaisyUI navbar in `index.html`**

Replace lines 16–19:
```html
<header>
  <h1>Bulletin Generator</h1>
  <p>Import from PCO &mdash; edit items &mdash; download PDF</p>
</header>
```
with:
```html
<div class="navbar bg-primary text-primary-content px-4 shadow-sm" style="min-height:52px;">
  <div class="flex-1 flex flex-col gap-0 leading-tight">
    <span class="font-bold text-base">Bulletin Generator</span>
    <span class="text-xs opacity-60">Import from PCO &mdash; edit items &mdash; download PDF</span>
  </div>
</div>
```

- [ ] **Step 2: Restyle tab bar in `index.html`**

Replace lines 21–31:
```html
<div class="tab-bar">
  <button class="tab-btn active" data-tab="page-editor"><svg ...>Booklet Editor</button>
  <button class="tab-btn" data-tab="page-files"><svg ...>Projects</button>
  <button class="tab-btn" data-tab="page-songdb"><svg ...>Song Database</button>
  <button class="tab-btn" data-tab="page-format"><svg ...>Format</button>
  <button class="tab-btn" data-tab="page-settings"><svg ...>Settings</button>
  <div class="tab-bar-right">
    <div id="page-count-display"></div>
    <button class="btn btn-primary" id="btn-print" disabled>Download PDF</button>
  </div>
</div>
```
with (preserve all SVGs and `data-tab` attributes exactly, only update wrapper and button classes):
```html
<div class="tab-bar flex items-stretch border-b border-base-300 bg-base-100 px-1" style="min-height:40px;">
  <button class="tab-btn active flex items-center gap-1.5 px-3 text-sm font-medium border-b-2 border-transparent -mb-px hover:text-base-content" data-tab="page-editor"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" style="margin-right:5px;vertical-align:middle"><path d="M12.854 0.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5l1.647-1.646a.5.5 0 0 0 0-.708l-3-3zM9.793 2.5L2 10.293V14h3.707L13.5 6.207 9.793 2.5zM1 11.707V15h3.293L1 11.707z"/></svg>Booklet Editor</button>
  <button class="tab-btn flex items-center gap-1.5 px-3 text-sm font-medium border-b-2 border-transparent -mb-px hover:text-base-content" data-tab="page-files"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" style="margin-right:5px;vertical-align:middle"><path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h2.764c.958 0 1.76.56 2.311 1.184C7.985 3.648 8.48 4 9 4h4.5A1.5 1.5 0 0 1 15 5.5v7a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5v-9z"/></svg>Projects</button>
  <button class="tab-btn flex items-center gap-1.5 px-3 text-sm font-medium border-b-2 border-transparent -mb-px hover:text-base-content" data-tab="page-songdb"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" style="margin-right:5px;vertical-align:middle"><path d="M9 3a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H10a1 1 0 0 1-1-1V3zm-5 0a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3zm2 10.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0zm5 0a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/></svg>Song Database</button>
  <button class="tab-btn flex items-center gap-1.5 px-3 text-sm font-medium border-b-2 border-transparent -mb-px hover:text-base-content" data-tab="page-format"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" style="margin-right:5px;vertical-align:middle"><path d="M8 5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zm4 3a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM5 6.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0zm.5 6.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z"/><path d="M16 8c0 3.15-1.866 2.585-3.567 2.07C11.42 9.763 10.465 9.5 10 9.5c-.944 0-1.98.37-2.80.956C6.354 11.1 5.556 11.5 5 11.5c-2.207 0-4-1.794-4-4 0-4.418 3.582-8 8-8s8 3.582 8 8z"/></svg>Format</button>
  <button class="tab-btn flex items-center gap-1.5 px-3 text-sm font-medium border-b-2 border-transparent -mb-px hover:text-base-content" data-tab="page-settings"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" style="margin-right:5px;vertical-align:middle"><path d="M8 4.754a3.246 3.246 0 1 0 0 6.492 3.246 3.246 0 0 0 0-6.492zM5.754 8a2.246 2.246 0 1 1 4.492 0 2.246 2.246 0 0 1-4.492 0z"/><path d="M9.796 1.343c-.527-1.79-3.065-1.79-3.592 0l-.094.319a.873.873 0 0 1-1.255.52l-.292-.16c-1.64-.892-3.433.902-2.54 2.541l.159.292a.873.873 0 0 1-.52 1.255l-.319.094c-1.79.527-1.79 3.065 0 3.592l.319.094a.873.873 0 0 1 .52 1.255l-.16.292c-.892 1.64.901 3.434 2.541 2.54l.292-.159a.873.873 0 0 1 1.255.52l.094.319c.527 1.79 3.065 1.79 3.592 0l.094-.319a.873.873 0 0 1 1.255-.52l.292.16c1.64.893 3.434-.902 2.54-2.541l-.159-.292a.873.873 0 0 1 .52-1.255l.319-.094c1.79-.527 1.79-3.065 0-3.592l-.319-.094a.873.873 0 0 1-.52-1.255l.16-.292c.893-1.64-.902-3.433-2.541-2.54l-.292.159a.873.873 0 0 1-1.255-.52l-.094-.319zm-2.633.283c.246-.835 1.428-.835 1.674 0l.094.319a1.873 1.873 0 0 0 2.693 1.115l.291-.16c.764-.415 1.6.42 1.184 1.185l-.159.292a1.873 1.873 0 0 0 1.116 2.692l.318.094c.835.246.835 1.428 0 1.674l-.319.094a1.873 1.873 0 0 0-1.115 2.693l.16.291c.415.764-.42 1.6-1.185 1.184l-.291-.159a1.873 1.873 0 0 0-2.693 1.116l-.094.318c-.246.835-1.428.835-1.674 0l-.094-.319a1.873 1.873 0 0 0-2.692-1.115l-.292.16c-.764.415-1.6-.42-1.184-1.185l.159-.291A1.873 1.873 0 0 0 1.945 8.93l-.319-.094c-.835-.246-.835-1.428 0-1.674l.319-.094A1.873 1.873 0 0 0 3.06 4.474l-.16-.292c-.415-.764.42-1.6 1.185-1.184l.292.159a1.873 1.873 0 0 0 2.692-1.115l.094-.319z"/></svg>Settings</button>
  <div class="tab-bar-right ml-auto flex items-center gap-2 px-2">
    <div id="page-count-display" class="text-xs text-base-content/50"></div>
    <button class="btn btn-primary btn-sm" id="btn-print" disabled>Download PDF</button>
  </div>
</div>
```

- [ ] **Step 3: Add active tab styles to `src/css/tw-input.css`**

Append to `src/css/tw-input.css`:
```css
@layer components {
  .tab-btn.active {
    @apply border-primary text-primary;
  }
  .tab-btn:not(.active) {
    @apply text-base-content/60;
  }
}
```

- [ ] **Step 4: Update `#toast-container` in `index.html`**

Replace line 663:
```html
<div id="toast-container"></div>
```
with:
```html
<div id="toast-container" class="toast toast-top toast-end z-50"></div>
```

- [ ] **Step 5: Update `setStatus()` in `src/js/utils.js`**

Replace the existing `setStatus` function (lines 2–31) with:
```javascript
function setStatus(msg, type = '') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const alertClass = type === 'success' ? 'alert-success'
                   : type === 'error'   ? 'alert-error'
                   : type === 'info'    ? 'alert-info'
                   : '';

  const toast = document.createElement('div');
  toast.className = 'alert shadow-md text-sm py-2 px-4' + (alertClass ? ' ' + alertClass : '');

  const msgEl = document.createElement('span');
  msgEl.textContent = msg;
  toast.appendChild(msgEl);

  if (type === 'error') {
    const closeBtn = document.createElement('button');
    closeBtn.className = 'btn btn-ghost btn-xs ml-2';
    closeBtn.textContent = '✕';
    closeBtn.addEventListener('click', () => dismissToast(toast));
    toast.appendChild(closeBtn);
  } else {
    setTimeout(() => dismissToast(toast), 3000);
  }

  container.appendChild(toast);
}
```

- [ ] **Step 6: Rebuild Tailwind output**

```bash
npm run css:build
```

- [ ] **Step 7: Run tests**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add index.html src/js/utils.js src/css/tw-input.css src/css/tw-output.css
git commit -m "feat(#147): migrate app shell — navbar, tab bar, toast to DaisyUI"
```

---

## Task 3: Issue #148 — Editor sidebar — panels, inputs, buttons

**Files:**
- Modify: `index.html` (lines 36–223, the `<aside>` block)

Rules: preserve all `id=` attributes, `data-*` attributes, and functional class names. Only add/replace styling classes.

- [ ] **Step 1: Read the current `<aside>` block**

Read `index.html` lines 36–223 to get the full current HTML before editing.

- [ ] **Step 2: Replace `.panel-section` panel wrappers with DaisyUI card styling**

For each `.panel-section` div in the aside, change the wrapper from:
```html
<div class="panel-section">
  <div class="section-label">Panel Title</div>
  ...
</div>
```
to:
```html
<div class="panel-section card card-compact bg-base-100 border border-base-300 rounded-lg mb-2 p-3">
  <div class="section-label text-xs font-bold uppercase tracking-widest text-base-content/50 mb-2">Panel Title</div>
  ...
</div>
```

Apply this pattern to all 9 panel sections:
- `#pco-section` (Import from Planning Center)
- File panel (starts `<div class="panel-section">` after `#pco-section`)
- Service Details
- Cover Image
- Options
- `#panel-section-welcome` (Welcome)
- `#panel-section-announcements` (Announcements)
- Order of Worship
- `#panel-section-calendar` (Calendar)
- `#panel-section-volunteers` (Volunteers)
- `#panel-section-staff` (Church Staff & Contact)

- [ ] **Step 3: Replace button classes throughout the aside**

In the `<aside>` block only, apply these replacements (use replace_all=false, context-match each one):

| Old class | New class |
|-----------|-----------|
| `btn btn-primary btn-full` | `btn btn-primary btn-sm w-full` |
| `btn btn-full` | `btn btn-sm w-full` |
| `btn-sm btn-sm-primary` | `btn btn-sm btn-primary` |
| `btn-sm btn-sm-danger` | `btn btn-sm btn-error` |
| `btn-sm` (standalone, not already DaisyUI) | `btn btn-sm btn-ghost` |
| `btn btn-full` | `btn btn-sm w-full` |

- [ ] **Step 4: Replace form input classes in the aside**

In the `<aside>` block, for all `<input type="text">`, `<input type="url">`, `<select>`, and `<textarea>` elements that do not already have Tailwind classes, add DaisyUI input classes:

```html
<!-- text/url inputs: add class="input input-bordered input-sm w-full" -->
<!-- selects: add class="select select-bordered select-sm w-full" -->
<!-- textareas: add class="textarea textarea-bordered textarea-sm w-full" -->
```

Preserve any existing `id=`, `placeholder=`, `style=` attributes. The goal is adding the DaisyUI class, not replacing inline styles.

- [ ] **Step 5: Replace `.field-row` label + input pairs**

Change `.field-row` divs from:
```html
<div class="field-row">
  <label for="x">Label</label>
  <input ... />
</div>
```
to:
```html
<div class="field-row form-control mb-1">
  <label class="label py-0.5" for="x"><span class="label-text text-xs">Label</span></label>
  <input class="input input-bordered input-sm w-full" ... />
</div>
```

- [ ] **Step 6: Rebuild Tailwind output**

```bash
npm run css:build
```

- [ ] **Step 7: Run tests**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add index.html src/css/tw-output.css
git commit -m "feat(#148): migrate editor sidebar panels, inputs, and buttons to DaisyUI"
```

---

## Task 4: Issue #149 — Order of Worship item cards (JS-rendered)

**Files:**
- Modify: `src/js/editor.js` (renderItemList function, around lines 89–200)

Rules: preserve `.item-card`, `.item-detail-input`, `.item-card-header`, `.item-title-input`, `.item-type-sel` and any other class names queried or set in JS elsewhere. Add Tailwind classes alongside them.

- [ ] **Step 1: Read the full `renderItemList` function**

Read `src/js/editor.js` lines 89–250 to get the exact HTML template strings being generated.

- [ ] **Step 2: Update item card HTML template in `renderItemList`**

Find where `.item-card` HTML is constructed. Wherever you see:
```javascript
card.className = 'item-card'
// or
`<div class="item-card"`
```
Change to add Tailwind styling while keeping the functional class:
```javascript
card.className = 'item-card card card-compact border border-base-300 rounded-lg mb-1'
```

For section-type items, the card typically gets a different background. Wherever sections get a special class:
```javascript
// old: card.classList.add('item-card-section')
// new: keep item-card-section, add Tailwind
card.classList.add('item-card-section', 'bg-base-200')
```

For page-break items (dashed divider), wherever they are rendered:
```javascript
// old: card.className = 'item-card item-card-break'
// new:
card.className = 'item-card item-card-break border-dashed border-2 border-base-300 rounded-lg my-1 flex items-center justify-center py-1'
```

- [ ] **Step 3: Update action button classes in item card templates**

In the generated item card HTML, find the up/down/delete buttons and add btn classes:
```javascript
// Old: `<button class="item-up-btn">↑</button>`
// New: `<button class="item-up-btn btn btn-ghost btn-xs">↑</button>`
// Same for item-dn-btn and item-del-btn
```

- [ ] **Step 4: Update insert-break zone styling**

Find where insert-break divs are created (the zones between items). Add Tailwind classes to them:
```javascript
// Add: class="insert-break-zone h-1 hover:h-3 transition-all cursor-pointer opacity-0 hover:opacity-100"
```

- [ ] **Step 5: Rebuild Tailwind output**

```bash
npm run css:build
```

- [ ] **Step 6: Run tests**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/js/editor.js src/css/tw-output.css
git commit -m "feat(#149): migrate Order of Worship item cards to DaisyUI"
```

---

## Task 5: Issue #150 — Projects page

**Files:**
- Modify: `index.html` (lines 239–266, `#page-files`)
- Modify: `src/js/projects.js` (renderFilesList / renderProjectList function)

- [ ] **Step 1: Read the current projects page HTML and renderFilesList function**

Read `index.html` lines 239–266 and search for `renderFilesList` in `src/js/projects.js`.

- [ ] **Step 2: Restyle `#page-files` page wrapper in `index.html`**

Change:
```html
<div class="app-page" id="page-files" style="height:calc(100vh - 88px);">
  <div class="files-inner">
    <div class="files-hdr">
      <div>
        <h2 class="files-title">Saved Projects</h2>
        <p id="files-count" class="files-subtitle">Loading…</p>
      </div>
      <div class="files-toolbar">
        <button class="btn-sm btn-sm-primary" id="files-new-btn" type="button">+ New Project</button>
        <label class="btn-sm" for="files-import-input" style="cursor:pointer;">↑ Import JSON</label>
        <input type="file" id="files-import-input" accept=".json" style="display:none;">
      </div>
    </div>
```
to:
```html
<div class="app-page" id="page-files" style="height:calc(100vh - 88px); overflow-y:auto;">
  <div class="files-inner max-w-4xl mx-auto px-4 py-4">
    <div class="files-hdr flex items-center justify-between mb-4">
      <div>
        <h2 class="files-title text-xl font-bold">Saved Projects</h2>
        <p id="files-count" class="files-subtitle text-sm text-base-content/60">Loading…</p>
      </div>
      <div class="files-toolbar flex gap-2">
        <button class="btn btn-sm btn-primary" id="files-new-btn" type="button">+ New Project</button>
        <label class="btn btn-sm btn-ghost" for="files-import-input" style="cursor:pointer;">↑ Import JSON</label>
        <input type="file" id="files-import-input" accept=".json" style="display:none;">
      </div>
    </div>
```

- [ ] **Step 3: Restyle bulk action bar in `index.html`**

Change:
```html
    <div id="bulk-bar" class="bulk-bar">
      <span class="bulk-bar-count" id="bulk-count">0 selected</span>
      <button class="bulk-bar-btn" id="bulk-select-all">Select All</button>
      <button class="bulk-bar-btn" id="bulk-export-pp">Export ProPresenter</button>
      <button class="bulk-bar-btn" id="bulk-download-json">↓ Download JSON</button>
      <button class="bulk-bar-btn" id="bulk-download-pdf">↓ Download PDFs</button>
      <button class="bulk-bar-btn" id="bulk-drive-json" style="display:none;">Save JSON to Drive</button>
      <button class="bulk-bar-btn" id="bulk-drive-pdf" style="display:none;">Save PDF to Drive</button>
      <button class="bulk-bar-btn bulk-danger" id="bulk-delete">Delete Selected</button>
      <button class="bulk-bar-clear" id="bulk-clear">✕ Clear</button>
    </div>
```
to:
```html
    <div id="bulk-bar" class="bulk-bar hidden flex items-center gap-2 bg-primary text-primary-content px-4 py-2 rounded-lg mb-3 flex-wrap">
      <span class="bulk-bar-count font-semibold text-sm" id="bulk-count">0 selected</span>
      <button class="bulk-bar-btn btn btn-sm btn-ghost text-primary-content" id="bulk-select-all">Select All</button>
      <button class="bulk-bar-btn btn btn-sm btn-ghost text-primary-content" id="bulk-export-pp">Export ProPresenter</button>
      <button class="bulk-bar-btn btn btn-sm btn-ghost text-primary-content" id="bulk-download-json">↓ Download JSON</button>
      <button class="bulk-bar-btn btn btn-sm btn-ghost text-primary-content" id="bulk-download-pdf">↓ Download PDFs</button>
      <button class="bulk-bar-btn btn btn-sm btn-ghost text-primary-content" id="bulk-drive-json" style="display:none;">Save JSON to Drive</button>
      <button class="bulk-bar-btn btn btn-sm btn-ghost text-primary-content" id="bulk-drive-pdf" style="display:none;">Save PDF to Drive</button>
      <button class="bulk-bar-btn btn btn-sm btn-error" id="bulk-delete">Delete Selected</button>
      <button class="bulk-bar-clear btn btn-sm btn-ghost text-primary-content ml-auto" id="bulk-clear">✕ Clear</button>
    </div>
```

Note: the bulk bar visibility is controlled by JS adding/removing the `.visible` class. Check how JS shows/hides it — if it uses `.style.display`, keep `style="display:none"` on the element instead of `hidden`. If it uses `.classList.toggle('visible')` or `.classList.toggle('hidden')`, update the initial state accordingly.

- [ ] **Step 4: Update project card rendering in `projects.js`**

Find `renderFilesList` (or the function that creates `.file-card` elements). Update the generated card HTML to add Tailwind classes while preserving functional ones:

```javascript
// Add to file-card: 'card card-compact border border-base-300 rounded-lg mb-2 p-3 flex items-center gap-3 cursor-pointer hover:bg-base-200'
// Add to active card: also add 'ring-2 ring-primary'
// Add to checkbox: 'checkbox checkbox-sm checkbox-primary'
// Add to load button: 'btn btn-sm btn-primary'
// Add to other action buttons: 'btn btn-sm btn-ghost'
```

- [ ] **Step 5: Rebuild Tailwind output**

```bash
npm run css:build
```

- [ ] **Step 6: Run tests**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add index.html src/js/projects.js src/css/tw-output.css
git commit -m "feat(#150): migrate Projects page to DaisyUI"
```

---

## Task 6: Issue #151 — Settings page

**Files:**
- Modify: `index.html` (lines 355–556, `#page-settings`)
- Modify: `src/js/update.js` (progress bar update logic)

- [ ] **Step 1: Restyle settings page sections in `index.html`**

For the settings page, apply these class changes:

Change `<div class="stg-inner">` to:
```html
<div class="stg-inner max-w-2xl mx-auto px-4 py-6 overflow-y-auto" style="height:100%;">
```

Change each `<div class="stg-group">` to:
```html
<div class="stg-group mb-8">
```

Change each `<div class="stg-group-heading" id="stg-*">Title</div>` to:
```html
<div class="stg-group-heading text-xs font-bold uppercase tracking-widest text-base-content/50 border-b border-base-300 pb-1 mb-3" id="stg-*">Title</div>
```

Change each `<div class="stg-card">` to:
```html
<div class="stg-card card card-compact bg-base-100 border border-base-300 rounded-lg p-4 mb-3">
```

Change each `<div class="stg-card-label">` to:
```html
<div class="stg-card-label font-semibold text-sm mb-1">
```

Change each `<div class="stg-btn-row">` to:
```html
<div class="stg-btn-row flex gap-2 mt-2 flex-wrap">
```

Convert all `<button class="btn-sm btn-sm-primary">` to `<button class="btn btn-sm btn-primary">` and `<button class="btn-sm">` to `<button class="btn btn-sm btn-ghost">` within the settings page.

Convert all `<input type="text">`, `<input type="url">` within the settings page (that have inline `style=` sizing) to use DaisyUI classes. Replace the inline `style=` sizing with:
```html
<input class="input input-bordered input-sm w-full mt-1" .../>
```
(keep the `id=` and `placeholder=`, remove inline `style=` width/padding/font-size).

Convert `<textarea>` elements within settings to:
```html
<textarea class="textarea textarea-bordered textarea-sm w-full" ...>
```

- [ ] **Step 2: Replace progress bar with native `<progress>` in `index.html`**

Find the progress bar block (around line 545):
```html
<div id="update-progress-bar" style="display:none;margin-top:0.6rem;">
  <div style="background:#e0e0e0;border-radius:6px;height:20px;overflow:hidden;position:relative;">
    <div id="update-progress-fill" style="background:var(--primary, #7b5e3c);height:100%;width:0%;transition:width 0.5s ease;border-radius:6px;"></div>
    <span id="update-progress-text" style="position:absolute;top:0;left:0;right:0;text-align:center;line-height:20px;font-size:0.72rem;color:#333;font-weight:600;"></span>
  </div>
</div>
```
Replace with:
```html
<div id="update-progress-bar" style="display:none;" class="mt-3">
  <progress id="update-progress-fill" class="progress progress-primary w-full" value="0" max="100"></progress>
  <p id="update-progress-text" class="text-xs text-center text-base-content/60 mt-1"></p>
</div>
```

- [ ] **Step 3: Update `update.js` to use `<progress>` element API**

In `src/js/update.js`, find the `updateProgress` helper function. It currently sets `barFill.style.width = pct + '%'`. Change it to set the `value` attribute:

Find:
```javascript
barFill.style.width = pct + '%';
```
Replace with:
```javascript
barFill.value = pct;
```

Also, the `barFill` reference must point to `#update-progress-fill` (the `<progress>` element). Verify the query selector still works — `document.getElementById('update-progress-fill')` will now return a `<progress>` element instead of a `<div>`, and setting `.value` works on `<progress>`.

- [ ] **Step 4: Rebuild Tailwind output**

```bash
npm run css:build
```

- [ ] **Step 5: Run tests**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add index.html src/js/update.js src/css/tw-output.css
git commit -m "feat(#151): migrate Settings page to DaisyUI, replace progress bar"
```

---

## Task 7: Issue #152 — Song Database page

**Files:**
- Modify: `index.html` (lines 268–353, `#page-songdb`)
- Modify: `src/js/songs.js` (renderSongList / song entry rendering)

- [ ] **Step 1: Read the current song DB page HTML**

Read `index.html` lines 268–353.

- [ ] **Step 2: Restyle song DB page structure in `index.html`**

Change `<div class="sdb-page-inner">` to:
```html
<div class="sdb-page-inner flex flex-col h-full">
```

Change `<div class="sdb-page-header">` and `.sdb-page-title` to:
```html
<div class="sdb-page-header px-4 pt-4 pb-2">
  <div class="sdb-page-title text-xl font-bold">Song Database</div>
</div>
```

Change `<div class="sdb-page-cols">` to:
```html
<div class="sdb-page-cols flex gap-0 flex-1 min-h-0 divide-x divide-base-300">
```

Change `<div class="sdb-list-col">` to:
```html
<div class="sdb-list-col flex flex-col w-72 shrink-0 overflow-hidden">
```

Change `<div id="sdb-controls-page">` to:
```html
<div id="sdb-controls-page" class="p-3 border-b border-base-300">
```

On `<input type="text" id="song-db-search">`, add:
```html
class="input input-bordered input-sm w-full mb-2"
```

On `<select id="song-db-sort">` and `<select id="song-db-source-filter">`, add:
```html
class="select select-bordered select-xs"
```

Change `<div id="song-db-scroll">` to:
```html
<div id="song-db-scroll" class="flex-1 overflow-y-auto">
```

Change `<div class="sdb-form-col">` to:
```html
<div class="sdb-form-col flex-1 overflow-y-auto p-4">
```

Convert buttons in `<div class="sdb-panel-actions">` from `btn-sm btn-sm-primary` / `btn-sm` to `btn btn-sm btn-primary` / `btn btn-sm btn-ghost`.

In the form, replace inline `style=` inputs with DaisyUI input classes (same approach as Settings task).

Convert `<div class="sdb-panel-divider">` to `<div class="sdb-panel-divider divider my-2">`.

- [ ] **Step 3: Find and update `renderSongList` (or equivalent) in `songs.js`**

Search for the function in `songs.js` that generates song entry HTML (look for `song-db-list`, `sdb-entry`, or similar class names). Read it, then add Tailwind styling to the generated card HTML:

```javascript
// song entry card: add 'cursor-pointer px-3 py-2 border-b border-base-300 hover:bg-base-200'
// selected song: also add 'bg-base-200 ring-inset ring-1 ring-primary'
// title text: add 'font-medium text-sm'
// meta text (author, use count): add 'text-xs text-base-content/60'
```

Preserve whatever functional class names are used for selection state.

- [ ] **Step 4: Rebuild Tailwind output**

```bash
npm run css:build
```

- [ ] **Step 5: Run tests**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add index.html src/js/songs.js src/css/tw-output.css
git commit -m "feat(#152): migrate Song Database page to DaisyUI"
```

---

## Task 8: Issue #153 — Format page

**Files:**
- Modify: `index.html` (lines 558–592, `#page-format`)
- Modify: `src/js/formatting.js` (renderFormatPage function)

- [ ] **Step 1: Read `#page-format` HTML and renderFormatPage function**

Read `index.html` lines 558–592. Search for `renderFormatPage` in `src/js/formatting.js` and read that function.

- [ ] **Step 2: Restyle format page in `index.html`**

Change `<div class="fmt-page-inner">` to:
```html
<div class="fmt-page-inner max-w-4xl mx-auto px-4 py-6 overflow-y-auto" style="height:100%;">
```

Change `<h2 class="fmt-page-title">` headings to:
```html
<h2 class="fmt-page-title text-lg font-bold mb-3">
```

For the page size row, change the inline `style=` select to use DaisyUI:
```html
<select id="doc-page-size-sel" class="select select-bordered select-sm">
```

Change `<div class="fmt-filter-wrap">` to:
```html
<div class="fmt-filter-wrap mb-4">
```

On `<input type="text" id="fmt-filter">`, add:
```html
class="input input-bordered input-sm w-full max-w-xs"
```

Change `<div class="fmt-types-grid" id="fmt-types-grid">` to:
```html
<div class="fmt-types-grid grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" id="fmt-types-grid">
```

Change `<div class="fmt-page-btns">` to:
```html
<div class="fmt-page-btns flex gap-2 mt-6">
```

Change `<button class="btn btn-primary" id="fmt-save-btn">` to `<button class="btn btn-primary btn-sm" id="fmt-save-btn">` and `<button class="btn" id="fmt-reset-btn">` to `<button class="btn btn-ghost btn-sm" id="fmt-reset-btn">`.

- [ ] **Step 3: Update format type card HTML in `renderFormatPage` in `formatting.js`**

Find the card template HTML generated for each format type. Add Tailwind classes to the card container:

```javascript
// format type card: add 'card card-compact bg-base-100 border border-base-300 rounded-lg p-3'
// card title: add 'font-semibold text-sm mb-2'
// label text (Bold, Italic, etc.): add 'text-xs text-base-content/60'
// size inputs: add 'input input-bordered input-xs w-16'
// alignment selects: add 'select select-bordered select-xs'
// bold/italic checkboxes: add 'checkbox checkbox-xs'
// color inputs: add 'w-8 h-6 rounded cursor-pointer border-0'
```

Preserve all functional class names and `id=` attributes used by the formatting JS.

- [ ] **Step 4: Rebuild Tailwind output**

```bash
npm run css:build
```

- [ ] **Step 5: Run tests**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add index.html src/js/formatting.js src/css/tw-output.css
git commit -m "feat(#153): migrate Format page to DaisyUI"
```

---

## Task 9: Issue #154 — Modals and dialogs

**Files:**
- Modify: `index.html` (lines 594–661, the 4 modal blocks)
- Modify: `src/js/pco.js` (modal show/hide call sites)
- Modify: `src/js/songs.js` (modal show/hide call sites)

- [ ] **Step 1: Read all modal show/hide call sites**

Run these to find every call site:
```bash
grep -n "import-review-modal\|pro-disclaimer-modal\|pro-import-modal\|pro-preview-modal" src/js/pco.js src/js/songs.js
```

Record the exact line numbers and the current `.style.display` assignments.

- [ ] **Step 2: Replace `#import-review-modal` in `index.html`**

Replace:
```html
<div id="import-review-modal" class="irm-overlay" style="display:none;" role="dialog" aria-modal="true">
  <div class="irm-box">
    <div class="irm-header">
      <div class="irm-title" id="irm-title">Review Imported Songs</div>
      <button class="irm-close-btn" id="irm-close-btn" title="Close">✕</button>
    </div>
    <div class="irm-body" id="irm-body">
      <!-- populated by JS -->
    </div>
    <div class="irm-footer">
      <button class="btn" id="irm-cancel-btn">Skip All</button>
      <button class="btn btn-primary" id="irm-apply-btn">Apply &amp; Continue</button>
    </div>
  </div>
</div>
```
with:
```html
<dialog id="import-review-modal" class="modal" role="dialog" aria-modal="true">
  <div class="modal-box irm-box max-w-2xl">
    <div class="irm-header flex items-center justify-between mb-4">
      <h3 class="irm-title font-bold text-lg" id="irm-title">Review Imported Songs</h3>
      <button class="irm-close-btn btn btn-ghost btn-sm btn-circle" id="irm-close-btn" title="Close">✕</button>
    </div>
    <div class="irm-body" id="irm-body">
      <!-- populated by JS -->
    </div>
    <div class="irm-footer modal-action">
      <button class="btn btn-ghost" id="irm-cancel-btn">Skip All</button>
      <button class="btn btn-primary" id="irm-apply-btn">Apply &amp; Continue</button>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
```

- [ ] **Step 3: Replace `#pro-disclaimer-modal` in `index.html`**

Replace:
```html
<div id="pro-disclaimer-modal" class="irm-overlay" style="display:none;" role="dialog" aria-modal="true">
  <div class="irm-box" style="max-width:460px;">
    <div class="irm-header">
      <div class="irm-title">ProPresenter Import (Beta)</div>
      <button class="irm-close-btn" id="pro-disclaimer-close-btn" title="Close">✕</button>
    </div>
    <div class="irm-body" style="font-size:0.84rem;line-height:1.5;">
      <p style="margin:0 0 0.6rem;">This feature is still in development. Import results may vary&nbsp;&mdash; some songs may have incomplete lyrics or missing section headings.</p>
      <p style="margin:0;">You will be able to preview a sample of the results before anything is saved.</p>
    </div>
    <div class="irm-footer">
      <button class="btn" id="pro-disclaimer-cancel-btn">Cancel</button>
      <button class="btn btn-primary" id="pro-disclaimer-continue-btn">Continue</button>
    </div>
  </div>
</div>
```
with:
```html
<dialog id="pro-disclaimer-modal" class="modal" role="dialog" aria-modal="true">
  <div class="modal-box irm-box max-w-md">
    <div class="irm-header flex items-center justify-between mb-3">
      <h3 class="irm-title font-bold text-base">ProPresenter Import (Beta)</h3>
      <button class="irm-close-btn btn btn-ghost btn-sm btn-circle" id="pro-disclaimer-close-btn" title="Close">✕</button>
    </div>
    <div class="irm-body text-sm leading-relaxed">
      <p class="mb-2">This feature is still in development. Import results may vary&nbsp;&mdash; some songs may have incomplete lyrics or missing section headings.</p>
      <p>You will be able to preview a sample of the results before anything is saved.</p>
    </div>
    <div class="irm-footer modal-action">
      <button class="btn btn-ghost" id="pro-disclaimer-cancel-btn">Cancel</button>
      <button class="btn btn-primary" id="pro-disclaimer-continue-btn">Continue</button>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
```

- [ ] **Step 4: Replace `#pro-import-modal` in `index.html`**

Replace:
```html
<div id="pro-import-modal" class="irm-overlay" style="display:none;" role="dialog" aria-modal="true">
  <div class="irm-box" style="max-width:580px;">
    <div class="irm-header">
      <div class="irm-title">Import from ProPresenter</div>
      <button class="irm-close-btn" id="pro-import-close-btn" title="Close">✕</button>
    </div>
    <div class="irm-body" id="pro-import-body">
      <!-- populated by JS -->
    </div>
    <div class="irm-footer">
      <button class="btn" id="pro-import-cancel-btn">Cancel</button>
      <button class="btn btn-primary" id="pro-import-confirm-btn">Import Songs</button>
    </div>
  </div>
</div>
```
with:
```html
<dialog id="pro-import-modal" class="modal" role="dialog" aria-modal="true">
  <div class="modal-box irm-box max-w-xl">
    <div class="irm-header flex items-center justify-between mb-4">
      <h3 class="irm-title font-bold text-lg">Import from ProPresenter</h3>
      <button class="irm-close-btn btn btn-ghost btn-sm btn-circle" id="pro-import-close-btn" title="Close">✕</button>
    </div>
    <div class="irm-body" id="pro-import-body">
      <!-- populated by JS -->
    </div>
    <div class="irm-footer modal-action">
      <button class="btn btn-ghost" id="pro-import-cancel-btn">Cancel</button>
      <button class="btn btn-primary" id="pro-import-confirm-btn">Import Songs</button>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
```

- [ ] **Step 5: Replace `#pro-preview-modal` in `index.html`**

Replace:
```html
<div id="pro-preview-modal" class="irm-overlay" style="display:none;" role="dialog" aria-modal="true">
  <div class="irm-box" style="max-width:680px;">
    <div class="irm-header">
      <div class="irm-title">Preview Import Results</div>
      <button class="irm-close-btn" id="pro-preview-close-btn" title="Close">✕</button>
    </div>
    <div class="irm-body" id="pro-preview-body" style="max-height:60vh;overflow-y:auto;">
      <!-- populated by JS -->
    </div>
    <div class="irm-footer" style="justify-content:space-between;align-items:center;">
      <span style="font-size:0.74rem;color:#888;" id="pro-preview-hint">Scroll to review sample imports</span>
      <div style="display:flex;gap:0.5rem;">
        <button class="btn" id="pro-preview-cancel-btn">Cancel Import</button>
        <button class="btn btn-primary" id="pro-preview-continue-btn">Looks Good — Continue</button>
      </div>
    </div>
  </div>
</div>
```
with:
```html
<dialog id="pro-preview-modal" class="modal" role="dialog" aria-modal="true">
  <div class="modal-box irm-box w-11/12 max-w-2xl">
    <div class="irm-header flex items-center justify-between mb-4">
      <h3 class="irm-title font-bold text-lg">Preview Import Results</h3>
      <button class="irm-close-btn btn btn-ghost btn-sm btn-circle" id="pro-preview-close-btn" title="Close">✕</button>
    </div>
    <div class="irm-body overflow-y-auto" id="pro-preview-body" style="max-height:60vh;">
      <!-- populated by JS -->
    </div>
    <div class="irm-footer modal-action justify-between items-center">
      <span class="text-xs text-base-content/50" id="pro-preview-hint">Scroll to review sample imports</span>
      <div class="flex gap-2">
        <button class="btn btn-ghost" id="pro-preview-cancel-btn">Cancel Import</button>
        <button class="btn btn-primary" id="pro-preview-continue-btn">Looks Good — Continue</button>
      </div>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop"><button>close</button></form>
</dialog>
```

- [ ] **Step 6: Update `pco.js` modal show/hide call sites**

For every line that does `document.getElementById('import-review-modal').style.display = 'flex'`, replace with:
```javascript
document.getElementById('import-review-modal').showModal();
```

For every line that does `document.getElementById('import-review-modal').style.display = 'none'`, replace with:
```javascript
document.getElementById('import-review-modal').close();
```

Apply the same pattern to any other modals that `pco.js` shows/hides.

- [ ] **Step 7: Update `songs.js` modal show/hide call sites**

Apply the same `.style.display = 'flex'` → `.showModal()` and `.style.display = 'none'` → `.close()` replacements for all four modals in `songs.js`.

Also update the close buttons: each modal's `irm-close-btn` button click handler currently does `modal.style.display = 'none'`. Change to `modal.close()`.

- [ ] **Step 8: Update close button handlers to use `dialog.close()`**

Search for any `addEventListener` or `onclick` wiring for `irm-close-btn`, `pro-disclaimer-close-btn`, `pro-import-close-btn`, `pro-preview-close-btn` in all JS files. Change:
```javascript
// old
modal.style.display = 'none';
// new
modal.close();
```

- [ ] **Step 9: Rebuild Tailwind output**

```bash
npm run css:build
```

- [ ] **Step 10: Run tests**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 11: Commit**

```bash
git add index.html src/js/pco.js src/js/songs.js src/css/tw-output.css
git commit -m "feat(#154): replace custom overlays with native <dialog> + DaisyUI modal"
```

---

## Task 10: Issue #155 — Remove replaced CSS files, finalize migration

**Files:**
- Delete: `src/css/base.css`
- Delete: `src/css/editor.css`
- Delete: `src/css/pages.css`
- Modify: `index.html` (remove <link> tags for deleted files)
- Modify: `tailwind.config.js` (remove `corePlugins: { preflight: false }`)
- Modify: `Dockerfile` (add `npm run css:build` step)
- Modify: `bulletin-generator.spec` (ensure `tw-output.css` is bundled)

- [ ] **Step 1: Audit remaining CSS class references**

Run these grep commands and verify nothing critical is still relying on old CSS:

```bash
grep -rn "panel-section\|section-label\|btn-sm-primary\|btn-sm-danger\|irm-overlay\|irm-box\|files-inner\|stg-inner\|stg-card\|bulk-bar\|file-card" index.html src/js/ --include="*.js" --include="*.html"
```

For any class still referenced purely for styling (not for JS logic), add the equivalent Tailwind styling. For class names that JS queries or toggles (functional), they can stay even if the CSS rule is gone — the styling comes from Tailwind now.

- [ ] **Step 2: Remove old CSS `<link>` tags from `index.html`**

Remove these lines from `index.html`:
```html
  <link rel="stylesheet" href="src/css/base.css" />
  <link rel="stylesheet" href="src/css/editor.css" />
  <link rel="stylesheet" href="src/css/pages.css" />
```

Keep these lines (do NOT remove):
```html
  <link rel="stylesheet" href="src/css/preview.css" />
  <link rel="stylesheet" href="src/css/print.css" />
  <link rel="stylesheet" href="src/css/tw-output.css" />
```

- [ ] **Step 3: Delete the three CSS files**

```bash
rm src/css/base.css src/css/editor.css src/css/pages.css
```

- [ ] **Step 4: Remove `preflight: false` from `tailwind.config.js`**

In `tailwind.config.js`, remove the `corePlugins` block:
```js
// Remove this:
  corePlugins: {
    preflight: false,
  },
```

- [ ] **Step 5: Rebuild Tailwind output with full preflight enabled**

```bash
npm run css:build
```

After this rebuild, test the app in the browser to check for visual regressions. Tailwind's preflight will now reset base styles. If any heading, paragraph, or list styles broke, add them back in `src/css/tw-input.css` under `@layer base`.

- [ ] **Step 6: Update `Dockerfile`**

Read the `Dockerfile`. Find the build/copy steps and add `npm run css:build` after the npm install step. Example pattern to add:

```dockerfile
RUN npm ci
RUN npm run css:build
```

(Read the actual Dockerfile first before editing — match the existing style.)

- [ ] **Step 7: Update `bulletin-generator.spec`**

Read `bulletin-generator.spec`. Find where CSS files are listed in the `datas` array. Ensure `src/css/tw-output.css` is included. Remove entries for `base.css`, `editor.css`, `pages.css` if they exist.

Pattern to find and remove (if present):
```python
('src/css/base.css', 'src/css'),
('src/css/editor.css', 'src/css'),
('src/css/pages.css', 'src/css'),
```

Pattern to add (if not already present):
```python
('src/css/tw-output.css', 'src/css'),
```

- [ ] **Step 8: Run full test suite**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add index.html tailwind.config.js src/css/tw-output.css src/css/tw-input.css Dockerfile bulletin-generator.spec
git rm src/css/base.css src/css/editor.css src/css/pages.css
git commit -m "chore(#155): remove old CSS files, finalize Tailwind migration"
```

---

## Task 11: Create PR, wait for CI, merge, close issues

**Files:** None — GitHub operations only.

- [ ] **Step 1: Push branch**

```bash
git push -u origin claude/nice-ramanujan
```

- [ ] **Step 2: Create PR**

```bash
gh pr create \
  --title "UI overhaul: migrate to Tailwind CSS + DaisyUI 4 with VCRC theme" \
  --body "$(cat <<'EOF'
## Summary

Migrates the app shell, editor sidebar, all pages, and modals from hand-rolled CSS to Tailwind CSS v3 + DaisyUI 4 with the VCRC custom navy theme (#172429). Aesthetic changes only — no logic, data flow, or API changes.

Closes #146, #147, #148, #149, #150, #151, #152, #153, #154, #155

## Changes

- Install Tailwind CSS v3 + DaisyUI 4, configure VCRC theme (`tailwind.config.js`, `tw-input.css`)
- Navbar: DaisyUI navbar replacing `<header>`, custom underline tab bar
- Toast: DaisyUI alert components, positioned with `.toast.toast-top.toast-end`
- Editor sidebar: DaisyUI card panels, btn/input/select/textarea classes
- OoW item cards: Tailwind styling in `renderItemList()`
- Projects page: DaisyUI card list, navy bulk action bar
- Settings page: DaisyUI card groups, native `<progress>` for update bar
- Song Database: DaisyUI two-column layout
- Format page: DaisyUI grid layout for type cards
- Modals: native `<dialog>` + DaisyUI `.modal` / `.modal-box`, `.showModal()` / `.close()`
- Final: delete `base.css`, `editor.css`, `pages.css`; update Dockerfile and PyInstaller spec

## Test plan

- [ ] `npm test` passes
- [ ] CI checks pass
EOF
)"
```

- [ ] **Step 3: Wait for CI checks to pass**

```bash
gh pr checks --watch
```

Wait until all checks pass. If a check fails, read the output:

```bash
gh pr checks
gh run view --log-failed
```

Fix any failures, push the fix, and re-run checks.

- [ ] **Step 4: Merge PR once all checks pass**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 5: Close issues**

```bash
gh issue close 146 147 148 149 150 151 152 153 154 155 --comment "Completed in #<PR_NUMBER>."
```

(Replace `<PR_NUMBER>` with the actual PR number from Step 2.)

---

## Progress Tracker

Update checkboxes above as work completes. Each task maps to one GitHub issue commit. If an agent session ends mid-task, resume at the first unchecked step.

| Task | Issue | Status |
|------|-------|--------|
| 1 | #146 Install Tailwind + DaisyUI | ⬜ |
| 2 | #147 App shell | ⬜ |
| 3 | #148 Editor sidebar | ⬜ |
| 4 | #149 OoW item cards | ⬜ |
| 5 | #150 Projects page | ⬜ |
| 6 | #151 Settings page | ⬜ |
| 7 | #152 Song Database | ⬜ |
| 8 | #153 Format page | ⬜ |
| 9 | #154 Modals | ⬜ |
| 10 | #155 Final cleanup | ⬜ |
| 11 | PR, CI, merge, close | ⬜ |
