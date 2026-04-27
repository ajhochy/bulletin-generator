# Explicit Default Font Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `system-ui, -apple-system, sans-serif` as the default template font with `Arial, Helvetica, sans-serif` so the locked default template renders consistently across macOS and Linux/Docker headless Chrome.

**Architecture:** `DEFAULT_TEMPLATE_CSS_VARS` in `src/js/state.js` is the single source of truth for the locked default template's CSS. Both `applyDocTemplate()` (live preview) and `buildPrintDocHtml()` (PDF) read from it, so changing the `fontFamily` value propagates to both automatically with no additional plumbing needed.

**Tech Stack:** Vanilla JS, no bundler. Changes to `src/js/state.js` and `src/js/projects.js` take effect immediately on page reload (served with `Cache-Control: no-store`). Vitest for JS unit tests (run with `npm test`).

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `src/js/state.js` | Modify | `fontFamily` in `DEFAULT_TEMPLATE_CSS_VARS`: `system-ui, -apple-system, sans-serif` → `Arial, Helvetica, sans-serif` |
| `src/js/projects.js` | Modify | Add clarifying comment to the Arial fallback suffix in `buildPrintDocHtml` |

No new files. No new modules. No test file needed — `DEFAULT_TEMPLATE_CSS_VARS` is a plain object literal in a non-module browser script; verifying it is a constant value assertion with no behaviour to test. Correctness is verified by manual render check in Task 2.

---

## Task 1: Change the default font constant and clean up the comment

**Files:**
- Modify: `src/js/state.js` (line ~102)
- Modify: `src/js/projects.js` (line ~831)

- [ ] **Step 1: Open `src/js/state.js` and find `DEFAULT_TEMPLATE_CSS_VARS`**

It looks like this (around line 101):

```js
const DEFAULT_TEMPLATE_CSS_VARS = {
  fontFamily: 'system-ui, -apple-system, sans-serif',
  primary: '#111827',
  muted: '#6b7280',
  accent: '#172429',
  border: '#e5e7eb',
};
```

- [ ] **Step 2: Change `fontFamily` to `Arial, Helvetica, sans-serif`**

```js
const DEFAULT_TEMPLATE_CSS_VARS = {
  fontFamily: 'Arial, Helvetica, sans-serif',
  primary: '#111827',
  muted: '#6b7280',
  accent: '#172429',
  border: '#e5e7eb',
};
```

- [ ] **Step 3: Open `src/js/projects.js` and find the PDF font stack line in `buildPrintDocHtml`**

It looks like this (around line 830):

```js
const templateFont = cssVars.fontFamily || DEFAULT_TEMPLATE_CSS_VARS.fontFamily;
const pdfFontSans  = `${templateFont}, Arial, Helvetica, sans-serif`;
```

- [ ] **Step 4: Add a comment so the redundancy is intentional-looking when no custom font is set**

```js
const templateFont = cssVars.fontFamily || DEFAULT_TEMPLATE_CSS_VARS.fontFamily;
// Append Arial fallback so custom Google Fonts have a reliable cross-platform fallback.
// When no custom font is set, templateFont is already 'Arial, Helvetica, sans-serif',
// making this redundant but harmless.
const pdfFontSans  = `${templateFont}, Arial, Helvetica, sans-serif`;
```

- [ ] **Step 5: Run the JS test suite to confirm nothing is broken**

```bash
npm test
```

Expected: all tests pass. (No tests cover this constant directly — this confirms no regressions in related modules.)

- [ ] **Step 6: Commit**

```bash
git add src/js/state.js src/js/projects.js
git commit -m "fix: use Arial as explicit default template font instead of system-ui"
```

---

## Task 2: Manual verification

**Goal:** Confirm the preview and PDF both render with Arial for the affected sections (copyright, calendar, serving today, staff & contact) when no custom template is active.

- [ ] **Step 1: Start the local server**

```bash
python3 server.py
```

Open `http://localhost:8080` in your browser.

- [ ] **Step 2: Confirm the font picker shows "Arial" for the default template**

Open the Template Editor. With no custom template active (the locked default), the font picker for sans-serif sections should now show "Arial" rather than "Default" or blank. `Arial` is already in `SYSTEM_TEMPLATE_FONTS` so it will be recognised by name.

- [ ] **Step 3: Load a project that has calendar events, a serving schedule, and staff data**

Use an existing project on the Synology server or a local project with all sections populated. If testing locally, ensure at least one song (copyright), calendar events, a serving schedule, and staff entries are present.

- [ ] **Step 4: Visually inspect the preview**

The affected sections (copyright line under songs, calendar page, serving today page, staff & contact page) should render in Arial. The OOW body text continues to use Georgia (unchanged).

- [ ] **Step 5: Export a PDF and compare it to the preview**

Click **Export PDF**. Open the PDF. Verify:
- Copyright lines under songs: Arial ✓
- Calendar page: Arial ✓
- Serving today page: Arial ✓
- Staff & contact page: Arial ✓
- OOW body text: Georgia (unchanged) ✓

If the PDF fonts match the preview, the fix is complete.

- [ ] **Step 6: If you have Synology access, trigger a Watchtower update and verify there**

After pushing to GitHub and the release workflow builds the new Docker image:

```bash
# On the Synology, trigger Watchtower via its HTTP API (Watchtower listens on port 8080
# inside its own container; trigger from the host via docker exec or the app's update UI)
curl -H "Authorization: Bearer bulletin-updater" \
  http://localhost:<watchtower-port>/v1/update
```

Or use the in-app **Check for Updates** button if that's how updates are normally triggered on Synology.

Then repeat Steps 3–5 against the Synology server to confirm the fix holds on Linux/Docker headless Chrome.
