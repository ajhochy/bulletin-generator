# UI Overhaul Design — Tailwind CSS + DaisyUI 4 Migration

**Date:** 2026-04-15  
**Issues:** #146–#155 (milestone: DaisyUI + VCRC Theme Migration)

## Scope and Constraint

Migrate the app's custom hand-rolled CSS to Tailwind CSS + DaisyUI 4 with a VCRC custom theme. **Aesthetic changes only** — no changes to business logic, data flow, API calls, or non-CSS JS behavior. Functional class names referenced by JS (e.g. `.item-card`, `.item-detail-input`) must be preserved.

## Tech Stack

- **Tailwind CSS v3** via Tailwind CLI (no bundler — app uses Python `http.server` in dev)
- **DaisyUI 4** component classes
- **VCRC custom theme**: primary navy `#172429`, grays as defined in issue #146
- Generated output: `src/css/tw-output.css` (committed for Docker compatibility)
- npm scripts: `css:watch` (dev) and `css:build` (prod/CI)

## Migration Sequence

Each issue is a self-contained PR. They must be merged in order since each depends on #146.

| Issue | Area | Key files |
|-------|------|-----------|
| #146 | Tailwind + DaisyUI install, VCRC theme config | `tailwind.config.js`, `src/css/tw-input.css`, `index.html` |
| #147 | App shell — navbar, tab bar, toast | `index.html`, `app.js`, `utils.js`, `base.css` |
| #148 | Editor sidebar — panels, inputs, buttons | `index.html`, `app.js`, `editor.css`, `base.css`, `pages.css` |
| #149 | Order of Worship item cards (JS-rendered) | `editor.js`, `editor.css` |
| #150 | Projects page | `index.html`, `projects.js`, `pages.css` |
| #151 | Settings page | `index.html`, `update.js`, `pages.css` |
| #152 | Song Database page | `index.html`, `songs.js`, `pages.css` |
| #153 | Format page | `index.html`, `formatting.js`, `editor.css` |
| #154 | Modals and dialogs | `index.html`, `songs.js`, `pco.js`, `pages.css` |
| #155 | Delete old CSS files, finalize | `base.css`, `editor.css`, `pages.css`, `Dockerfile`, spec file |

## Rules

1. **No logic changes.** Only class names, HTML structure for styling, and CSS files change.
2. **Preserve JS hooks.** Any class name read or written by JS stays — add Tailwind classes alongside, don't replace.
3. **Keep `preview.css` and `print.css` untouched** — these control the bulletin output, not the app UI.
4. **Commit built `tw-output.css`** so Docker builds don't require a Node build step.
5. **Each issue = one PR** — don't batch multiple migration areas in a single commit.
