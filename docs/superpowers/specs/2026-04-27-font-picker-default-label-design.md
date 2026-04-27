# Design: Font Picker "default" Label Shows Actual Font Name

**Date:** 2026-04-27
**Status:** Approved

---

## Problem

The template designer's element-level font picker shows `(default)` when no font override is set for an element. After the locked default template was changed to use `Arial, Helvetica, sans-serif` instead of `system-ui`, the label still says `(default)` — giving users no indication of what font will actually render.

Additionally, the document-level font picker (the template-wide font selector in the toolbar) falls back to the hardcoded string `'system-ui'` when no template font is configured, rather than reading from `DEFAULT_TEMPLATE_CSS_VARS`. This means it can drift out of sync if the default ever changes again.

---

## Solution

### 1. Element-level font picker — dynamic label

In `src/js/templates.js` (around line 1533), replace the hardcoded `'(default)'` label with one computed from the effective document font at render time:

```js
const docFont = (_editingTemplate.cssVars?.fontFamily || DEFAULT_TEMPLATE_CSS_VARS.fontFamily)
  .split(',')[0].trim();
const fontPicker = makeFontSelect(
  [{ value: '', label: `(default: ${docFont})` }].concat(designerFontOptions()),
  fmt.fontFamily || '',
  val => updateSelectedFmt('fontFamily', val)
);
```

- Shows `(default: Arial)` when no template font is set
- Shows `(default: Open Sans)` when the template uses a custom Google Font
- Selecting `(default: Arial)` still saves `''` (no override) — no data model change

### 2. Document-level font picker — remove hardcoded `'system-ui'` fallback

In `src/js/templates.js` (around line 1497), replace `|| 'system-ui'` with `|| DEFAULT_TEMPLATE_CSS_VARS.fontFamily`:

```js
const fontPicker = makeFontSelect(
  designerFontOptions(),
  _editingTemplate.cssVars?.fontFamily || DEFAULT_TEMPLATE_CSS_VARS.fontFamily,
  val => {
    _editingTemplate.cssVars = _editingTemplate.cssVars || {};
    _editingTemplate.cssVars.fontFamily = val;
    markDesignerDirty();
  }
);
```

---

## Scope

### Files changed

| File | Change |
|------|--------|
| `src/js/templates.js` | Two targeted edits — element-level picker label (line ~1533) and document-level picker fallback (line ~1497) |

### No changes to

- Template data model — `''` (no override) continues to mean "inherit from document"
- `makeFontSelect` function — label generation logic is unchanged
- `DEFAULT_TEMPLATE_CSS_VARS` — already updated in the previous fix
- Any server-side code

---

## Behavior after the change

| Scenario | Before | After |
|----------|--------|-------|
| Element picker, no template font set | `(default)` | `(default: Arial)` |
| Element picker, template font = Open Sans | `(default)` | `(default: Open Sans)` |
| Document picker, no template font set | selects `system-ui` | selects `Arial` |
| Saving element with no override | saves `''` | saves `''` (unchanged) |
