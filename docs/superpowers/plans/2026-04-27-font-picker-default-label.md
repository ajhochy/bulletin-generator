# Font Picker Default Label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `(default)` and `system-ui` strings in the template designer's font pickers with values derived from `DEFAULT_TEMPLATE_CSS_VARS` so the UI accurately reflects the font that will actually render.

**Architecture:** Two targeted edits in `src/js/templates.js`. The element-level font picker computes a label from the effective document font at render time. The document-level font picker replaces a hardcoded `'system-ui'` fallback with `DEFAULT_TEMPLATE_CSS_VARS.fontFamily`. No data model changes — saving `''` (no override) remains unchanged.

**Tech Stack:** Vanilla JS, no bundler. `DEFAULT_TEMPLATE_CSS_VARS` is a global defined in `src/js/state.js`, available to `templates.js` at runtime. Tests run with `npm test` (Vitest).

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `src/js/templates.js` | Modify line 1497 | `|| 'system-ui'` → `|| DEFAULT_TEMPLATE_CSS_VARS.fontFamily` |
| `src/js/templates.js` | Modify line 1533 | Hardcoded `'(default)'` label → dynamic `(default: Arial)` label |

No new files. No new modules. Both changes are in the same rendering pass of the template designer toolbar.

---

## Task 1: Fix the document-level font picker fallback

The document-level font picker (shown in the template toolbar when no element is selected) currently falls back to the hardcoded string `'system-ui'` when the template has no `cssVars.fontFamily`. It should fall back to `DEFAULT_TEMPLATE_CSS_VARS.fontFamily` to stay in sync with the actual default.

**Files:**
- Modify: `src/js/templates.js:1497`

- [ ] **Step 1: Open `src/js/templates.js` and find line 1497**

The current code looks like this:

```js
    // Font cluster
    const fontPicker = makeFontSelect(designerFontOptions(), _editingTemplate.cssVars?.fontFamily || 'system-ui', val => {
      _editingTemplate.cssVars = _editingTemplate.cssVars || {};
      _editingTemplate.cssVars.fontFamily = val;
      markDesignerDirty();
    });
```

- [ ] **Step 2: Replace `|| 'system-ui'` with `|| DEFAULT_TEMPLATE_CSS_VARS.fontFamily`**

```js
    // Font cluster
    const fontPicker = makeFontSelect(designerFontOptions(), _editingTemplate.cssVars?.fontFamily || DEFAULT_TEMPLATE_CSS_VARS.fontFamily, val => {
      _editingTemplate.cssVars = _editingTemplate.cssVars || {};
      _editingTemplate.cssVars.fontFamily = val;
      markDesignerDirty();
    });
```

- [ ] **Step 3: Run the test suite to confirm no regressions**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 4: Manually verify in the browser**

```bash
python3 server.py
```

Open `http://localhost:8080`, go to the Template Designer, and open or create any template. With no font explicitly set, the document-level font picker in the top toolbar should now show `Arial` (not `system-ui`).

- [ ] **Step 5: Commit**

```bash
git add src/js/templates.js
git commit -m "fix: use DEFAULT_TEMPLATE_CSS_VARS fallback in document-level font picker"
```

---

## Task 2: Fix the element-level font picker label

The element-level font picker (shown when an element like "Label Items / body" is selected) hardcodes `'(default)'` as the label for the no-override option. It should read the effective document font and show `(default: Arial)` — or whatever the template font is if one is set.

**Files:**
- Modify: `src/js/templates.js:1533`

- [ ] **Step 1: Open `src/js/templates.js` and find line 1533**

The current code looks like this:

```js
  // Font cluster
  const fontPicker = makeFontSelect([{ value: '', label: '(default)' }].concat(designerFontOptions()), fmt.fontFamily || '', val => updateSelectedFmt('fontFamily', val));
  const sizePicker = makeSizePicker(fmt.size || '', val => updateSelectedFmt('size', val));
  toolbar.appendChild(toolbarCluster('Font', [fontPicker, sizePicker]));
```

- [ ] **Step 2: Compute the effective document font name and use it in the label**

```js
  // Font cluster
  const docFont = (_editingTemplate.cssVars?.fontFamily || DEFAULT_TEMPLATE_CSS_VARS.fontFamily).split(',')[0].trim();
  const fontPicker = makeFontSelect([{ value: '', label: `(default: ${docFont})` }].concat(designerFontOptions()), fmt.fontFamily || '', val => updateSelectedFmt('fontFamily', val));
  const sizePicker = makeSizePicker(fmt.size || '', val => updateSelectedFmt('size', val));
  toolbar.appendChild(toolbarCluster('Font', [fontPicker, sizePicker]));
```

`_editingTemplate` is the template currently open in the designer. `DEFAULT_TEMPLATE_CSS_VARS` is the global from `state.js`. `.split(',')[0].trim()` extracts the first font name — `Arial` from `Arial, Helvetica, sans-serif`, or `Open Sans` from a Google Font value.

- [ ] **Step 3: Run the test suite**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 4: Manually verify in the browser**

Open `http://localhost:8080`, go to the Template Designer. Click any element (e.g. "Label Items / body"). The FONT picker should now show `(default: Arial)` when no font override is set.

Then set a custom template font (e.g. Open Sans) via the document-level font picker in the toolbar. Click an element that has no font override. The FONT picker should now show `(default: Open Sans)`.

- [ ] **Step 5: Commit**

```bash
git add src/js/templates.js
git commit -m "fix: show effective default font name in element-level font picker label"
```
