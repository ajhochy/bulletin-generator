# Fix Plan: `fix/tailwind-ui` Branch

**Branch:** `fix/tailwind-ui` (commit `4da06f8`)  
**Good baseline:** commit `5378919`  
**Problem:** The Tailwind CSS + DaisyUI 4 migration (PR #156) deleted ~1,400 lines of CSS without fully replacing all of them, breaking the app's layout, page switching, and preview rendering.

---

## Context

The migration replaced `base.css`, `editor.css`, and `pages.css` with a compiled `tw-output.css` and inline Tailwind utility classes on HTML elements. `preview.css` and `print.css` were kept unchanged. Several structural CSS rules and all CSS custom properties were deleted without replacement.

The correct fix approach is **not** to restore the old CSS files wholesale. Instead, create a small `src/css/compat.css` that adds back only the rules that Tailwind cannot replace (structural rules and CSS variables), then link it in `index.html`.

---

## Confirmed Breaks

### 1. All pages display simultaneously (CRITICAL)

**Root cause:** `.app-page { display: none }` and `.app-page.active { display: flex }` were in `base.css`, which was deleted. Tailwind never generates component rules like these because they depend on JS-toggled `.active` class state.

**Fix:** Add to `src/css/compat.css`:
```css
.app-page { display: none; flex: 1; overflow: hidden; }
.app-page.active { display: flex; }
```

No changes needed to `index.html` or any JS file.

---

### 2. Preview pane renders unstyled / wrong dimensions (CRITICAL)

**Root cause:** `preview.css` (unchanged, still loaded) references ~25 CSS custom properties defined in `base.css` which was deleted. DaisyUI defines its own variables (`--p`, `--base-100`, etc.) but NOT the app's custom ones.

Variables used in `preview.css` that are now undefined:
- `--font-serif` → `'Georgia', 'Times New Roman', serif`
- `--font-sans` → `system-ui, -apple-system, sans-serif`
- `--doc-page-w` → `5.5in`
- `--doc-page-h` → `8.5in`
- `--border` → `#d6cfc4`
- `--radius` → `5px`
- `--text` → `#2a2318`
- `--muted` → `#7a6e62`
- `--accent` → `#4a3728`
- `--accent-light` → `#7a5c45`
- `--surface` → `#ffffff`

**Fix:** Add to `src/css/compat.css`:
```css
:root {
  --bg: #f4f1ec;
  --surface: #ffffff;
  --border: #d6cfc4;
  --text: #2a2318;
  --muted: #7a6e62;
  --accent: #4a3728;
  --accent-light: #7a5c45;
  --danger: #8b2020;
  --danger-light: #f5e5e5;
  --radius: 5px;
  --font-serif: 'Georgia', 'Times New Roman', serif;
  --font-sans: system-ui, -apple-system, sans-serif;
  --doc-page-w: 5.5in;
  --doc-page-h: 8.5in;
}
```

---

### 3. App layout broken — no sidebar/preview split (CRITICAL)

**Root cause:** `base.css` contained the structural rules for `html`, `body`, and `main`. Without them the app has no flex column structure and the 3-column editor grid (sidebar | resize handle | preview) doesn't exist.

The `<main>` tag in the current `index.html` has no Tailwind classes or inline styles providing grid layout.

**Fix:** Add to `src/css/compat.css`:
```css
html {
  font-size: 19px;
  height: 100%;
  overflow: hidden;
}
body {
  font-family: var(--font-sans);
  background: var(--bg);
  color: var(--text);
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
main {
  flex: 1;
  display: grid;
  grid-template-columns: var(--editor-w, 690px) 4px 1fr;
  overflow: hidden;
}
#editor-resize-handle {
  width: 4px;
  cursor: col-resize;
  background: var(--border);
  transition: background 0.15s;
  flex-shrink: 0;
  z-index: 10;
}
#editor-resize-handle:hover,
#editor-resize-handle.dragging { background: var(--accent-light); }
```

---

### 4. Format tab — type-format cards stack in single column (MODERATE)

**Root cause:** `.fmt-types-grid` responsive grid was defined in `editor.css` (deleted) and was never replaced with Tailwind classes on the HTML element.

Check `index.html` for the `fmt-types-grid` element — it likely has no grid classes.

**Fix:** Add to `src/css/compat.css`:
```css
.fmt-types-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 0.85rem;
}
```

---

## Atomic Implementation Steps

Work through these in order. Each step is independently verifiable before moving to the next.

---

### Step 1 — Confirm you are on the right branch

```bash
cd "/Users/ajhochhalter/Documents/Bulletin Generator - Most Recent Release"
git branch --show-current
# must output: fix/tailwind-ui
git log --oneline -2
# top commit must be: 4da06f8 feat: migrate UI to Tailwind CSS + DaisyUI 4 (#146–#155) (#156)
```

If not on `fix/tailwind-ui`, run: `git checkout fix/tailwind-ui`

---

### Step 2 — Confirm `src/css/compat.css` does not already exist

```bash
ls src/css/
# should NOT list compat.css
```

If it exists already, read it before proceeding — someone may have partially applied this fix.

---

### Step 3 — Create `src/css/compat.css`

Create the file `src/css/compat.css` with exactly this content (order matters — variables must come before rules that use them):

```css
/* ─── CSS Custom Properties ─────────────────────────────────────────────────
   preview.css and print.css reference these variables and were not updated
   during the Tailwind migration. Do not remove without also updating those files.
   ────────────────────────────────────────────────────────────────────────── */
:root {
  --bg: #f4f1ec;
  --surface: #ffffff;
  --border: #d6cfc4;
  --text: #2a2318;
  --muted: #7a6e62;
  --accent: #4a3728;
  --accent-light: #7a5c45;
  --danger: #8b2020;
  --danger-light: #f5e5e5;
  --radius: 5px;
  --font-serif: 'Georgia', 'Times New Roman', serif;
  --font-sans: system-ui, -apple-system, sans-serif;
  --doc-page-w: 5.5in;
  --doc-page-h: 8.5in;
}

/* ─── Top-level Layout ───────────────────────────────────────────────────────
   Tailwind's base reset does not set height:100% or overflow:hidden on html/body.
   These are required for the app's full-viewport, no-scroll layout.
   ────────────────────────────────────────────────────────────────────────── */
html {
  font-size: 19px;
  height: 100%;
  overflow: hidden;
}
body {
  font-family: var(--font-sans);
  background: var(--bg);
  color: var(--text);
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ─── Editor 3-Column Grid ───────────────────────────────────────────────────
   <main> contains: aside (sidebar) | #editor-resize-handle | #preview-panel.
   No Tailwind classes were added to the <main> tag during migration.
   ────────────────────────────────────────────────────────────────────────── */
main {
  flex: 1;
  display: grid;
  grid-template-columns: var(--editor-w, 690px) 4px 1fr;
  overflow: hidden;
}
#editor-resize-handle {
  width: 4px;
  cursor: col-resize;
  background: var(--border);
  transition: background 0.15s;
  flex-shrink: 0;
  z-index: 10;
}
#editor-resize-handle:hover,
#editor-resize-handle.dragging { background: var(--accent-light); }

/* ─── Page Tab Visibility ────────────────────────────────────────────────────
   JS in app.js toggles .active on .app-page elements to switch tabs.
   Tailwind cannot generate these rules — they depend on runtime class toggling.
   ────────────────────────────────────────────────────────────────────────── */
.app-page { display: none; flex: 1; overflow: hidden; }
.app-page.active { display: flex; }

/* ─── Format Tab Grid ────────────────────────────────────────────────────────
   .fmt-types-grid was in editor.css (deleted). The HTML element has no
   Tailwind grid classes added during migration.
   ────────────────────────────────────────────────────────────────────────── */
.fmt-types-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 0.85rem;
}
```

---

### Step 4 — Add `compat.css` to `index.html`

Open `index.html`. Find this block in `<head>` (it will be near the top of the file, around line 6–9):

```html
  <link rel="stylesheet" href="src/css/preview.css" />
  <link rel="stylesheet" href="src/css/print.css" />
  <link rel="stylesheet" href="src/css/tw-output.css" />
```

Add one line **after** `tw-output.css` (after = compat.css wins over any conflicting Tailwind resets):

```html
  <link rel="stylesheet" href="src/css/preview.css" />
  <link rel="stylesheet" href="src/css/print.css" />
  <link rel="stylesheet" href="src/css/tw-output.css" />
  <link rel="stylesheet" href="src/css/compat.css" />
```

Save the file.

---

### Step 5 — Start the app and verify tab switching

```bash
python3 server.py
# open http://localhost:8080 in a browser
```

Check:
- [ ] On load, only the **Booklet Editor** tab content is visible. The Projects, Song Database, Format, and Settings pages are hidden.
- [ ] Clicking each tab in the nav bar switches to that page — no double content, no stacking.
- [ ] Clicking back to Booklet Editor works.

If all tabs still show at once: `compat.css` is not loading. Open browser DevTools → Network tab, reload, confirm `compat.css` returns 200. If it returns 404, the file path is wrong.

---

### Step 6 — Verify the editor layout

Still on the Booklet Editor tab:
- [ ] The left sidebar (panels: Import from PCO, File, Service Details, etc.) is visible and has a fixed width (~690px).
- [ ] A thin drag handle is visible between the sidebar and the right pane.
- [ ] The right pane shows the live preview area.
- [ ] Dragging the resize handle adjusts the sidebar width.

If the layout is a single column: the `main` grid rule isn't applying. Open DevTools → Elements, inspect the `<main>` tag, confirm `display: grid` appears in Styles from `compat.css`.

---

### Step 7 — Verify the preview pane renders correctly

Import a plan from PCO (or load an existing project), then check the preview pane:
- [ ] Bulletin pages render at approximately 5.5in wide (not full-width or zero-width).
- [ ] Text uses serif font (Georgia) for bulletin content.
- [ ] Section headings have a bottom border rule.
- [ ] Cover page accent bar renders in dark brown (`#4a3728`), not transparent.

If dimensions are wrong: the `:root` variables aren't loading. In DevTools → Elements → `<html>`, check Computed styles for `--doc-page-w`. It should read `5.5in`.

---

### Step 8 — Verify the Format tab grid

Click the **Format** tab:
- [ ] The type-format cards (Section, Song, Label, etc.) display in a **multi-column responsive grid**, not a single vertical stack.
- [ ] Cards reflow when the window is resized.

If cards are stacked: inspect `.fmt-types-grid` in DevTools, confirm `display: grid` is applied from `compat.css`.

---

### Step 9 — Spot-check the Settings and Song Database tabs

Click **Settings**:
- [ ] Page renders with readable layout — settings groups are visible, inputs are styled.

Click **Song Database**:
- [ ] Song list is visible and scrollable.

These pages rely on DaisyUI classes that were added to the HTML during migration. If they look reasonable, they're fine. Only flag if something is completely broken or invisible.

---

### Step 10 — Commit the fix

Once all checklist items pass:

```bash
git add src/css/compat.css index.html
git commit -m "fix: add compat.css to restore structural CSS lost in Tailwind migration

Adds back CSS custom properties, html/body layout, main grid, .app-page
visibility toggle, and .fmt-types-grid — all of which were in base.css or
editor.css and were not replaced by Tailwind utility classes during PR #156."
```

Do **not** push to `origin/main`. This branch is a local fix branch. Open a PR against `main` when ready, or ask the user how they want to merge.

---

## Changes That Were Done Correctly (Do NOT revert)

These were intentional breaking changes in the migration that the JS was updated to match — leave them alone:

- **Modals** — converted from `style.display='flex'/'none'` to native HTML5 `<dialog>` `.showModal()/.close()`. Changes are consistent across `pco.js`, `propresenter.js`, and the HTML.
- **Progress bar** — changed from `<div id="update-progress-fill">` (styled with `.style.width`) to `<progress>` element (using `.value`). `update.js` was updated to match.
- **Toast notifications** — class names changed from `toast`/`toast-success`/`toast-error` to DaisyUI `alert`/`alert-success`/`alert-error`. `utils.js` was updated to match.

---

## Files to Touch

| File | Action |
|------|--------|
| `src/css/compat.css` | **Create** (new file) |
| `index.html` | **Edit** — add `<link>` for `compat.css` in `<head>` |

No JS files need changes. No other CSS files need changes.
