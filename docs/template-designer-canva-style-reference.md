# Template Designer Canva-Style Reference

This is a curated reference for issue [#180](https://github.com/ajhochy/bulletin-generator/issues/180), which tracks Canva-style polish for the Template Designer.

The goal is familiarity for users who have worked in Canva, not a complete editor rewrite. Keep the existing Template Designer engine, schema, preview renderer, and save/apply flows intact.

## Source

Design extraction source path on the originating machine:

`/Users/ajhochhalter/design-extract-output`

Files reviewed:

- `canva-link-design-language.md`
- `canva-link-design-tokens.json`
- `canva-link-figma-variables.json`
- `canva-link-preview.html`
- `canva-link-shadcn-theme.css`
- `canva-link-tailwind.config.js`
- `canva-link-theme.js`
- `canva-link-variables.css`
- `canva-link-wordpress-theme.json`

Extraction date shown in the output: April 16, 2026.

Do not commit the full generated extraction folder unless there is a specific reason. Most of it is redundant generated output. This document captures the usable parts.

## Usable Tokens

The extraction was sparse but useful as a designer-chrome token set.

### Colors

| Role | Value | Notes |
| --- | --- | --- |
| Ink / primary | `#0e1318` | Use for designer text and dark UI lines. |
| Black | `#000000` | Use sparingly; prefer `#0e1318` for designer chrome. |
| Muted | `#737373` | Secondary labels, hints, metadata. |
| White | `#ffffff` | Panels, template cards, page/workspace base. |
| Accent | `#8b3dff` | Canva-like purple for selection, active states, snap guides. |

### Typography

| Token | Value | Use |
| --- | --- | --- |
| Sans | `Open Sans` | Designer UI/chrome. |
| Editorial | `Times` | Modern template content/body/editorial contrast. |
| Fallback | `Arial` | Utility fallback. |
| Heading | `21.6px / 700 / 30.24px` | Panel headings or strong section labels. |
| Body | `14.4px / 400 / 20.16px` | Panel body, zone rows, toolbar labels. |
| Input | `13.3333px / 400` | Inputs, selects, compact controls. |

### Layout

| Token | Value | Use |
| --- | --- | --- |
| Base gap | `14px` | Designer chrome spacing rhythm. |
| Radius | `8px` | Designer panels, cards, popovers, controls. |
| Motion | `opacity/transform`, extracted as `0.8s` | Use shorter `0.18s` for editor responsiveness. |

## Plug-In Snippets

These snippets are adapted from the extraction and are intended to be easy to plug into the current app.

### Designer UI Tokens

Extracted from `canva-link-variables.css`:

```css
:root {
  --color-primary: #0e1318;
  --color-secondary: #8b3dff;
  --color-neutral-100: #737373;
  --color-bg: #ffffff;
  --font-sans: 'Open Sans', sans-serif;
  --font-body: 'Times', sans-serif;
  --font-size-21.6: 21.6px;
  --font-size-14.4: 14.4px;
  --font-size-13.3333: 13.3333px;
  --spacing-14: 14px;
  --radius-md: 8px;
}
```

Suggested app-specific adaptation:

```css
:root {
  --td-bg: #ffffff;
  --td-ink: #0e1318;
  --td-muted: #737373;
  --td-accent: #8b3dff;
  --td-border: rgba(14, 19, 24, 0.14);
  --td-radius: 8px;
  --td-gap: 14px;
  --td-font: 'Open Sans', system-ui, sans-serif;
}
```

Important: `--td-*` variables should style Template Designer chrome only. Do not force these tokens into bulletin output unless the active template explicitly chooses them.

### Interaction States

Extracted from `canva-link-theme.js`:

```js
states: {
  hover: { opacity: 0.08 },
  focus: { opacity: 0.12 },
  active: { opacity: 0.16 },
  disabled: { opacity: 0.38 }
}
```

Suggested CSS adaptation:

```css
.tpl-designer-action:hover {
  background: color-mix(in srgb, var(--td-accent) 8%, transparent);
}

.tpl-designer-action:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--td-accent) 70%, white);
  outline-offset: 2px;
}

.tpl-designer-action:active {
  background: color-mix(in srgb, var(--td-accent) 16%, transparent);
}

.tpl-designer-action:disabled {
  opacity: 0.38;
}
```

If `color-mix()` compatibility becomes a concern, replace these with static rgba values.

### Type Scale For Designer Chrome

Extracted from `canva-link-design-language.md`:

```css
h2 { font-size: 21.6px; font-weight: 700; line-height: 30.24px; }
body { font-size: 14.4px; font-weight: 400; line-height: 20.16px; }
input { font-size: 13.3333px; }
```

Suggested adaptation:

```css
#tpl-designer-overlay {
  font-family: var(--td-font);
  color: var(--td-ink);
}

.tpl-panel-title {
  font-size: 21.6px;
  font-weight: 700;
  line-height: 30.24px;
}

.tpl-panel-body,
.tpl-zone-row,
.tpl-toolbar-control {
  font-size: 14.4px;
  line-height: 20.16px;
}

#tpl-designer-overlay input,
#tpl-designer-overlay select,
#tpl-designer-overlay button {
  font-size: 13.3333px;
}
```

### Template Gallery Swatch Pattern

Extracted from `canva-link-preview.html`:

```css
.swatch {
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-card);
  border: 1px solid var(--border);
  cursor: pointer;
  position: relative;
}

.swatch-color { height: 80px; position: relative; }
.swatch-info { padding: 10px 12px; font-size: 13px; }
.swatch-hex { font-weight: 600; font-family: monospace; }
```

Suggested adaptation for template cards:

```css
.tpl-template-card {
  border-radius: var(--td-radius);
  border: 1px solid var(--td-border);
  background: #fff;
  overflow: hidden;
}

.tpl-template-swatches {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  height: 32px;
}

.tpl-template-card-meta {
  padding: 10px 12px;
  font-size: 13px;
}
```

Use the template's own `cssVars` to populate swatches:

- `cssVars.primary`
- `cssVars.muted`
- `cssVars.accent`
- `cssVars.border`

### Subtle Motion

Extracted pattern:

```css
transition: opacity 0.8s ease-in-out, transform 0.8s ease-in-out;
```

Suggested shorter editor adaptation:

```css
.tpl-panel,
.tpl-floating-label,
.tpl-selection-handle,
#tpl-snap-guide {
  transition: opacity 0.18s ease, transform 0.18s ease, background-color 0.18s ease;
}
```

Use `0.18s`, not `0.8s`, for editor controls so the UI stays responsive.

## Suggested Implementation Areas

### 1. Workspace

- Apply `--td-*` tokens to the Template Designer overlay.
- Make the center canvas feel like a creative workspace:
  - light neutral background
  - clean page shadow
  - stronger selected-page focus
- Add bottom-right zoom controls:
  - `-`
  - `100%`
  - `+`
  - `Fit`
- Keep zoom as a designer-only view setting. It must not affect saved template data or PDF output.

### 2. Selection And Dragging

- Use `#8b3dff` for selected outlines and snap guides.
- Add small corner handles to selected elements.
- Add a small floating label for the selected element, such as:
  - `Song Title`
  - `Copyright`
  - `Announcement Body`
- Keep the existing persisted layout model:
  - free layout stays `layout.position = "free"`
  - inline row layout stays `layout.position = "inline"`

### 3. Toolbar

- Keep existing toolbar behavior.
- Restyle around the extracted tokens.
- Group controls into familiar creative-editor clusters:
  - Font
  - Text
  - Color
  - Layout
- Use compact icon buttons for obvious actions:
  - bold
  - italic
  - underline
  - align left / center / right

### 4. Right Panel

Reorganize the existing right panel into simple tabs:

- `Style`
- `Rules`
- `Layout`

Suggested mapping:

- `Rules`: current binding/type/title match controls.
- `Style`: selected element formatting controls.
- `Layout`: alignment, inline/free layout, spacing controls.

Preserve the current template schema and matching behavior.

### 5. Replace Browser Prompts

These current flows feel like a prototype and should become in-app modals or popovers:

- New template base picker
- Save As name
- Add zone binding
- Add title-match rule
- Match mode exact/contains

This is likely the highest-impact familiarity improvement.

### 6. Template Gallery

- Add real palette swatches to template cards.
- Show font pairing preview, such as `Open Sans / Times`.
- Show badges:
  - `Built-in`
  - `Custom`
  - `Uses uploaded fonts`
- Keep current actions:
  - Apply
  - Design
  - Export

### 7. Modern Preset Alignment

Consider aligning the Modern built-in preset more closely with extracted Canva tokens:

```json
{
  "primary": "#0e1318",
  "muted": "#737373",
  "accent": "#8b3dff",
  "background": "#ffffff",
  "fontFamily": "Open Sans"
}
```

Keep Classic unchanged.

## Non-Goals

- Do not rewrite the template engine.
- Do not change the persisted template schema unless unavoidable.
- Do not turn the bulletin output into a Canva clone.
- Do not add a general-purpose page builder.
- Do not merge Template Designer chrome tokens with bulletin output tokens.
- Do not commit the full generated extraction folder unless future work needs the raw files.

## Files Most Likely To Change

- `src/js/templates.js`
- `src/css/preview.css`
- `index.html`
- `data/templates.example.json` if Modern token alignment is included
- `server.py` only if font/token behavior requires backend support

## Verification

Run the existing checks after any polish pass:

```bash
python3 -m py_compile server.py
node --check src/js/templates.js
node --check src/js/state.js
node --check src/js/projects.js
python3 -m pytest
npm test -- --run
```

Also re-run the live checklist:

`docs/template-designer-live-testing.md`
