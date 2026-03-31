# Volunteers Editor UX Overhaul — Design Spec
**Issue:** #84
**Branch:** `feature/issue-84-volunteers-ux`
**Date:** 2026-03-30

---

## Problem Summary

Two distinct UX problems in the volunteers/serving-schedule section:

1. **Editor panel is too cluttered.** All weeks, service times, teams, and roles render as one unbroken flat list. Large serving schedules are hard to scan.
2. **Preview click navigation is imprecise.** Clicking anywhere on the volunteers preview page navigates only to the section header — not to the specific team, service time, or role that was clicked.

---

## Problem 1: Collapsible Editor

### Hierarchy

```
Week (collapsible)
└── Service Time (collapsible, only when serviceTime field is present)
    └── Team
        └── Roles / Names (always visible when team is visible)
```

### Toggle controls

- Each week label row gets a `▶`/`▼` toggle button on its left.
- Each service time subheading gets a `▶`/`▼` toggle on its left.
- Clicking the toggle flips a `collapsed` CSS class on the content container immediately below it.

### DOM structure

```
div.vol-week-el
  [page-break row or add-page-break button — always visible]
  div.vol-week-header        ← toggle + label text
  div.vol-week-body          ← .collapsed { display:none }
    div.vol-st-header        ← toggle + service time text (when applicable)
    div.vol-st-body          ← .collapsed { display:none }
      [teams, positions, add-role, add-break, add-team footer]
```

Page-break add buttons and the week/service-time labels are outside the body containers so they remain visible when collapsed.

### Collapse state

- **Storage:** `localStorage` key `vol-collapse`, JSON object.
- **Key format:**
  - Week: `"w{weekIdx}"` — e.g. `"w0"`, `"w1"`
  - Service time within week: `"w{weekIdx}:st:{serviceTime}"` — e.g. `"w0:st:9:00am"`
- **Value:** `true` = collapsed, absent/`false` = expanded.
- **Default:** all weeks collapsed on first load (write `true` for each week when no existing state found).
- **Persistence:** loaded once at the top of `volRender()`, written on each toggle click.

### CSS additions (pages.css)

```css
.vol-week-body.collapsed  { display: none; }
.vol-st-body.collapsed    { display: none; }
.vol-collapse-toggle {
  background: none; border: none; cursor: pointer;
  font-size: 0.6rem; color: var(--muted);
  padding: 0; margin-right: 0.3rem; flex-shrink: 0;
}
.vol-collapse-toggle:hover { color: var(--text); }
```

### Files changed

| File | Change |
|------|--------|
| `src/js/calendar.js` | `volRender()` — add toggle buttons, wrap content in body containers, load/persist state |
| `src/css/pages.css` | Add `.vol-week-body.collapsed`, `.vol-st-body.collapsed`, `.vol-collapse-toggle` |

---

## Problem 2: Precise Click Navigation

### Preview data attributes

Added by `renderServingWeek(container, week, label, weekIdx)` and `renderServingTeam(container, team, weekIdx, teamIdx)` in `calendar.js`:

| Element | Added attributes |
|---------|-----------------|
| Each `serving-row` div | `data-preview-vol-week-idx`, `data-preview-vol-team-idx`, class `preview-linkable` |
| Service time subheading | `data-preview-vol-week-idx`, `data-preview-vol-st` (service time string), class `preview-linkable` |
| Outer volunteers container | `data-preview-section="volunteers"` (already present — fallback for whitespace clicks) |

### Editor data attributes

Added by `volRender()` in `calendar.js`:

| Element | Added attributes |
|---------|-----------------|
| Team name row (`div` wrapping `vol-team-name`) | `data-vol-week-idx`, `data-vol-team-idx` |
| Service time subheading (`div.vol-st-header`) | `data-vol-week-idx`, `data-vol-st` |

### Click handler (preview.js)

Two checks inserted **before** the existing `[data-preview-section]` check:

```javascript
// 1. Click on a serving row → navigate to that team
const volTeamEl = targetEl.closest('[data-preview-vol-team-idx]');
if (volTeamEl) {
  const wi = parseInt(volTeamEl.dataset.previewVolWeekIdx, 10);
  const ti = parseInt(volTeamEl.dataset.previewVolTeamIdx, 10);
  scrollEditorToVolTeam(wi, ti);
  return;
}

// 2. Click on a service time subheading → navigate to that service time block
const volStEl = targetEl.closest('[data-preview-vol-st]');
if (volStEl) {
  const wi = parseInt(volStEl.dataset.previewVolWeekIdx, 10);
  const st = volStEl.dataset.previewVolSt;
  scrollEditorToVolServiceTime(wi, st);
  return;
}
```

### Navigation functions (calendar.js)

**`scrollEditorToVolTeam(weekIdx, teamIdx)`**
1. Expand the `panel-section-volunteers` panel section (using existing `scrollEditorToSection` pattern).
2. Expand `vol-week-body` for `weekIdx` — remove `collapsed`, update toggle arrow, persist state.
3. If a `vol-st-body` contains the target team, expand it too.
4. Find editor element: `#vol-editor [data-vol-week-idx="${weekIdx}"][data-vol-team-idx="${teamIdx}"]`.
5. Scroll it into the aside using `scrollElementIntoContainer`.
6. Add `is-linked` briefly (1600 ms), then remove.

**`scrollEditorToVolServiceTime(weekIdx, st)`**
1–2. Same expand steps as above.
3. Find editor element: `#vol-editor [data-vol-week-idx="${weekIdx}"][data-vol-st="${st}"]`.
4. Scroll and highlight.

### Click granularity

| User clicks on | Navigates to |
|----------------|-------------|
| Name text or role label in a serving row | Team containing that row |
| Team heading in preview (if added) | That team |
| Service time subheading in preview | That service time block in editor |
| Week label or whitespace in volunteers section | Volunteers section header (existing behavior) |

### Files changed

| File | Change |
|------|--------|
| `src/js/calendar.js` | `renderServingTeam()` — add `weekIdx`/`teamIdx` params + data attrs + `preview-linkable`; `renderServingWeek()` — add `weekIdx` param + data attrs on service time subheading; add `scrollEditorToVolTeam()` and `scrollEditorToVolServiceTime()` |
| `src/js/preview.js` | Click handler — add two vol-specific checks before section check |

---

## Implementation Scope

- No changes to the serving schedule data structure.
- No changes to the preview rendering output (only data attributes added to existing elements).
- No changes to server.py.
- Collapse state is UI-only (localStorage), not persisted to the project.
