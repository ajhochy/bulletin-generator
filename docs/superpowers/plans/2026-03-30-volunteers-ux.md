# Volunteers Editor UX Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two-level collapsible sections (weeks + service times) to the volunteer editor panel, and enable precise click-to-editor navigation from the preview pane at the team and service-time level.

**Architecture:** All changes are in `src/js/calendar.js` (editor rendering + new scroll functions), `src/js/preview.js` (click handler), and `src/css/pages.css` (collapsible styles). No changes to the data model, server, or preview output HTML. Collapse state is stored in `localStorage` under key `vol-collapse` as a flat object — never sent to the server.

**Tech Stack:** Vanilla JS (ES2017), no bundler, no framework. All JS files are plain globals loaded via `<script>` tags. `editor.js` loads before `calendar.js`, so `scrollEditorToSection`, `scrollElementIntoContainer`, `previewPane`, and `linkedPreviewTimer` are all accessible in `calendar.js`.

---

## File map

| File | What changes |
|------|-------------|
| `src/css/pages.css` | Add 7 new CSS rules for collapse layout |
| `src/js/calendar.js` | Replace `volRender()` entirely; update `renderServingTeam()` and `renderServingWeek()` signatures; add `getVolCollapseState()`, `saveVolCollapseState()`, `scrollEditorToVolTeam()`, `scrollEditorToVolServiceTime()` |
| `src/js/preview.js` | Insert two vol-specific checks in the preview click handler |

---

## Task 1: CSS additions

**Files:**
- Modify: `src/css/pages.css` (after the existing `/* ─── Volunteer editor ──── */` block, around line 755)

- [ ] **Step 1: Add new CSS rules**

Open `src/css/pages.css`. Find the line:
```css
    .vol-page-break-row span {
```
Insert the following block immediately **after** the closing brace of `.vol-page-break-row span { ... }` (after line ~753):

```css
    .vol-week-header {
      display: flex; align-items: center; gap: 0.2rem;
      margin: 0.6rem 0 0.3rem; padding-bottom: 0.2rem;
      border-bottom: 1px solid var(--border);
    }
    .vol-week-header:first-child { margin-top: 0; }
    .vol-week-header-text {
      flex: 1;
      font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.07em; color: var(--muted);
    }
    .vol-st-header {
      display: flex; align-items: center; gap: 0.2rem;
      margin-top: 0.4rem; margin-bottom: 0.15rem;
    }
    .vol-st-header-text {
      flex: 1; font-size: 0.65rem; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.07em;
      color: var(--accent-light);
    }
    .vol-week-body.collapsed { display: none; }
    .vol-st-body.collapsed   { display: none; }
    .vol-collapse-toggle {
      background: none; border: none; cursor: pointer;
      font-size: 0.55rem; color: var(--muted);
      padding: 0; flex-shrink: 0; line-height: 1;
    }
    .vol-collapse-toggle:hover { color: var(--text); }
```

- [ ] **Step 2: Verify the page loads without console errors**

```bash
cd "/Users/ajhochhalter/Documents/Bulletin Generator - Most Recent Release"
python3 server.py
# open http://localhost:8080 in browser, check console for CSS errors
```

Expected: no errors, app loads normally.

- [ ] **Step 3: Commit**

```bash
git add src/css/pages.css
git commit -m "feat(#84): add CSS for collapsible volunteer editor sections"
```

---

## Task 2: Collapse state helpers in calendar.js

**Files:**
- Modify: `src/js/calendar.js` (add two functions just before `function volRender()` at line 24)

- [ ] **Step 1: Add helpers before volRender()**

In `src/js/calendar.js`, find the line:
```javascript
function volRender() {
```

Insert these two functions immediately above it:

```javascript
function getVolCollapseState() {
  try { return JSON.parse(localStorage.getItem('vol-collapse') || '{}'); }
  catch { return {}; }
}

function saveVolCollapseState(state) {
  localStorage.setItem('vol-collapse', JSON.stringify(state));
}
```

- [ ] **Step 2: Manual verify in browser console**

```javascript
// In browser devtools console:
getVolCollapseState()   // should return {} on first run
saveVolCollapseState({ w0: true, 'w0:st:9:00am': true })
getVolCollapseState()   // should return { w0: true, 'w0:st:9:00am': true }
localStorage.removeItem('vol-collapse') // clean up
```

Expected: functions work and localStorage key persists.

- [ ] **Step 3: Commit**

```bash
git add src/js/calendar.js
git commit -m "feat(#84): add vol-collapse localStorage helpers"
```

---

## Task 3: Replace volRender() with collapsible structure

**Files:**
- Modify: `src/js/calendar.js` — replace the entire `volRender()` function (lines 24–258)

This task replaces `volRender()` in full. The new version:
- Wraps each week's teams in a `div.vol-week-body` (collapsible)
- Adds a `div.vol-week-header` with a `▶`/`▼` toggle button
- Groups teams under service times using `div.vol-st-body` + `div.vol-st-header` (collapsible)
- Loads collapse state from localStorage on render; writes it on each toggle click
- Adds `data-vol-week-idx` / `data-vol-team-idx` on team name rows (for editor-side navigation in Task 5)
- Adds `data-vol-week-idx` / `data-vol-st` on service time header elements (for editor-side navigation)
- All existing editing controls (delete, add-role, add-break, add-team) are preserved and unchanged

- [ ] **Step 1: Replace volRender()**

In `src/js/calendar.js`, replace everything from `function volRender() {` through its closing `}` (lines 24–258) with the following:

```javascript
function volRender() {
  const editor   = document.getElementById('vol-editor');
  const emptyMsg = document.getElementById('vol-empty');
  editor.innerHTML = '';

  if (!servingSchedule) {
    emptyMsg.style.display = '';
    return;
  }
  emptyMsg.style.display = 'none';

  const weeks    = servingSchedule.weeks || [];
  const colState = getVolCollapseState();

  // Initialise collapse state on first load: default all weeks collapsed.
  let stateChanged = false;
  weeks.forEach((_, wi) => {
    if (!((`w${wi}`) in colState)) {
      colState[`w${wi}`] = true;
      stateChanged = true;
    }
  });
  if (stateChanged) saveVolCollapseState(colState);

  weeks.forEach((data, wi) => {
    const label = wi === 0
      ? 'This Week'
      : (weeks.length === 2 ? 'Next Week' : data.date || `Week ${wi + 1}`);
    const weekEl = document.createElement('div');

    // ── Page-break before week (always visible, only wi > 0) ─────────────────
    if (wi > 0) {
      if (data._breakBefore) {
        const pbRow = document.createElement('div');
        pbRow.className = 'vol-page-break-row';
        const lbl = document.createElement('span');
        lbl.textContent = '— Page Break —';
        const removeBtn = document.createElement('button');
        removeBtn.className = 'vol-remove-btn';
        removeBtn.title = 'Remove page break';
        removeBtn.textContent = '✕';
        removeBtn.addEventListener('click', () => {
          delete servingSchedule.weeks[wi]._breakBefore;
          volRender(); schedulePreviewUpdate(); scheduleProjectPersist();
        });
        pbRow.appendChild(lbl);
        pbRow.appendChild(removeBtn);
        weekEl.appendChild(pbRow);
      } else {
        const wBreakBtn = document.createElement('button');
        wBreakBtn.className = 'vol-add-link';
        wBreakBtn.style.cssText = 'color:var(--muted); display:block; margin-bottom:0.15rem;';
        wBreakBtn.textContent = '⊞ Add page break before ' + label;
        wBreakBtn.addEventListener('click', () => {
          servingSchedule.weeks[wi]._breakBefore = true;
          volRender(); schedulePreviewUpdate(); scheduleProjectPersist();
        });
        weekEl.appendChild(wBreakBtn);
      }
    }

    // ── Week header: toggle button + label ────────────────────────────────────
    const weekCollapseKey = `w${wi}`;
    const weekCollapsed   = colState[weekCollapseKey] !== false;

    const weekHeader = document.createElement('div');
    weekHeader.className = 'vol-week-header';

    const weekToggle = document.createElement('button');
    weekToggle.className = 'vol-collapse-toggle';
    weekToggle.textContent = weekCollapsed ? '▶' : '▼';

    const weekLabelEl = document.createElement('span');
    weekLabelEl.className = 'vol-week-header-text';
    weekLabelEl.textContent = label
      + (wi === 0 && data.date ? ' — ' + data.date
        : (wi > 0 && label !== data.date && data.date ? ' — ' + data.date : ''));

    weekHeader.appendChild(weekToggle);
    weekHeader.appendChild(weekLabelEl);
    weekEl.appendChild(weekHeader);

    // ── Week body (collapsible) ───────────────────────────────────────────────
    const weekBody = document.createElement('div');
    weekBody.className = 'vol-week-body';
    if (weekCollapsed) weekBody.classList.add('collapsed');

    weekToggle.addEventListener('click', () => {
      const s = getVolCollapseState();
      const nowCollapsed = !weekBody.classList.contains('collapsed');
      if (nowCollapsed) { s[weekCollapseKey] = true; } else { delete s[weekCollapseKey]; }
      saveVolCollapseState(s);
      weekBody.classList.toggle('collapsed');
      weekToggle.textContent = weekBody.classList.contains('collapsed') ? '▶' : '▼';
    });

    let lastServiceTime = undefined;
    let currentContainer = weekBody; // where team content gets appended

    const hasServiceTimes = (data.teams || []).some(
      t => t.type !== 'page-break' && t.serviceTime
    );
    const lastRealTeamIdx = hasServiceTimes ? -1 : (data.teams || []).reduce(
      (last, t, i) => (t.type !== 'page-break' && servingTeamFilter[t.name] !== false) ? i : last,
      -1
    );

    (data.teams || []).forEach((team, ti) => {
      // Page-break marker between teams
      if (team.type === 'page-break') {
        const pbRow = document.createElement('div');
        pbRow.className = 'vol-page-break-row';
        const lbl = document.createElement('span');
        lbl.textContent = '— Page Break —';
        const removeBtn = document.createElement('button');
        removeBtn.className = 'vol-remove-btn';
        removeBtn.title = 'Remove page break';
        removeBtn.textContent = '✕';
        removeBtn.addEventListener('click', () => {
          servingSchedule.weeks[wi].teams.splice(ti, 1);
          volRender(); schedulePreviewUpdate(); scheduleProjectPersist();
        });
        pbRow.appendChild(lbl);
        pbRow.appendChild(removeBtn);
        weekBody.appendChild(pbRow);
        return;
      }

      if (servingTeamFilter[team.name] === false) return;

      // ── Service time group transition ───────────────────────────────────────
      if (team.serviceTime !== lastServiceTime) {
        lastServiceTime = team.serviceTime;
        if (team.serviceTime) {
          if (ti > 0) {
            const stBreakBtn = document.createElement('button');
            stBreakBtn.className = 'vol-add-link';
            stBreakBtn.style.cssText = 'color:var(--muted); display:block; margin-bottom:0.15rem;';
            stBreakBtn.textContent = '⊞ Add page break before ' + team.serviceTime;
            stBreakBtn.title = 'Insert a page break before this service time';
            stBreakBtn.addEventListener('click', () => {
              servingSchedule.weeks[wi].teams.splice(ti, 0, { type: 'page-break' });
              volRender(); schedulePreviewUpdate(); scheduleProjectPersist();
            });
            weekBody.appendChild(stBreakBtn);
          }

          const stCollapseKey = `w${wi}:st:${team.serviceTime}`;
          const stCollapsed   = colState[stCollapseKey] !== false;

          // Service time header: toggle + label
          const stHeaderEl = document.createElement('div');
          stHeaderEl.className = 'vol-st-header';
          stHeaderEl.dataset.volWeekIdx = wi;
          stHeaderEl.dataset.volSt      = team.serviceTime;

          const stToggle = document.createElement('button');
          stToggle.className = 'vol-collapse-toggle';
          stToggle.textContent = stCollapsed ? '▶' : '▼';

          const stLabelEl = document.createElement('span');
          stLabelEl.className = 'vol-st-header-text';
          stLabelEl.textContent = team.serviceTime;

          stHeaderEl.appendChild(stToggle);
          stHeaderEl.appendChild(stLabelEl);
          weekBody.appendChild(stHeaderEl);

          const stBody = document.createElement('div');
          stBody.className = 'vol-st-body';
          if (stCollapsed) stBody.classList.add('collapsed');

          stToggle.addEventListener('click', () => {
            const s = getVolCollapseState();
            const nowC = !stBody.classList.contains('collapsed');
            if (nowC) { s[stCollapseKey] = true; } else { delete s[stCollapseKey]; }
            saveVolCollapseState(s);
            stBody.classList.toggle('collapsed');
            stToggle.textContent = stBody.classList.contains('collapsed') ? '▶' : '▼';
          });

          weekBody.appendChild(stBody);
          currentContainer = stBody;
        } else {
          currentContainer = weekBody;
        }
      }

      // ── Team name row ───────────────────────────────────────────────────────
      const teamNameRow = document.createElement('div');
      teamNameRow.style.cssText =
        'display:flex; align-items:center; justify-content:space-between; margin-bottom:0;';
      teamNameRow.dataset.volWeekIdx = wi;
      teamNameRow.dataset.volTeamIdx = ti;

      const teamNameEl = document.createElement('div');
      teamNameEl.className   = 'vol-team-name';
      teamNameEl.style.marginBottom = '0';
      teamNameEl.textContent = team.name;
      teamNameRow.appendChild(teamNameEl);

      const delTeamBtn = document.createElement('button');
      delTeamBtn.className = 'vol-remove-btn';
      delTeamBtn.title     = 'Remove this team';
      delTeamBtn.textContent = '✕';
      delTeamBtn.addEventListener('click', () => {
        if (!confirm(`Remove team "${team.name}"?`)) return;
        servingSchedule.weeks[wi].teams.splice(ti, 1);
        volRender(); schedulePreviewUpdate(); scheduleProjectPersist();
      });
      teamNameRow.appendChild(delTeamBtn);
      currentContainer.appendChild(teamNameRow);

      // ── Position rows ───────────────────────────────────────────────────────
      team.positions.forEach((pos, pi) => {
        const row = document.createElement('div');
        row.className = 'vol-pos-row';

        const roleLabel = document.createElement('span');
        roleLabel.className   = 'vol-role-label';
        roleLabel.textContent = pos.role;

        const namesInput = document.createElement('input');
        namesInput.type        = 'text';
        namesInput.className   = 'vol-names-input';
        namesInput.value       = (pos.names || []).join(', ');
        namesInput.placeholder = 'Names, comma-separated';
        namesInput.addEventListener('input', () => {
          servingSchedule.weeks[wi].teams[ti].positions[pi].names =
            namesInput.value.split(',').map(n => n.trim()).filter(Boolean);
          schedulePreviewUpdate();
          updateSectionPreviews();
          scheduleProjectPersist();
        });

        const removeBtn = document.createElement('button');
        removeBtn.className   = 'vol-remove-btn';
        removeBtn.title       = 'Remove this role';
        removeBtn.textContent = '✕';
        removeBtn.addEventListener('click', () => {
          servingSchedule.weeks[wi].teams[ti].positions.splice(pi, 1);
          volRender(); schedulePreviewUpdate(); scheduleProjectPersist();
        });

        row.appendChild(roleLabel);
        row.appendChild(namesInput);
        row.appendChild(removeBtn);
        currentContainer.appendChild(row);
      });

      // ── Add role button ─────────────────────────────────────────────────────
      const addRoleBtn = document.createElement('button');
      addRoleBtn.className   = 'vol-add-link';
      addRoleBtn.textContent = '+ Add role';
      addRoleBtn.addEventListener('click', () => {
        const role = prompt('Role name (e.g. GREETER):');
        if (!role || !role.trim()) return;
        servingSchedule.weeks[wi].teams[ti].positions.push({
          role: role.trim().toUpperCase(), names: []
        });
        volRender(); schedulePreviewUpdate(); scheduleProjectPersist();
      });
      currentContainer.appendChild(addRoleBtn);

      // ── Add page break after team (non-service-time data, not the last team) ─
      if (!hasServiceTimes && ti < lastRealTeamIdx) {
        const addBreakBtn = document.createElement('button');
        addBreakBtn.className   = 'vol-add-link';
        addBreakBtn.style.cssText = 'color:var(--muted); margin-left:0.6rem;';
        addBreakBtn.textContent = '⊞ Add page break';
        addBreakBtn.title       = 'Insert a page break after this team group';
        addBreakBtn.addEventListener('click', () => {
          servingSchedule.weeks[wi].teams.splice(ti + 1, 0, { type: 'page-break' });
          volRender(); schedulePreviewUpdate(); scheduleProjectPersist();
        });
        currentContainer.appendChild(addBreakBtn);
      }
    });

    // ── Add team button ───────────────────────────────────────────────────────
    const footer = document.createElement('div');
    footer.className = 'vol-week-footer';
    const addTeamBtn = document.createElement('button');
    addTeamBtn.className   = 'btn-sm';
    addTeamBtn.style.cssText = 'width:100%; font-size:0.7rem;';
    addTeamBtn.textContent = '+ Add Team';
    addTeamBtn.addEventListener('click', () => {
      const name = prompt('Team name (e.g. Greeter):');
      if (!name || !name.trim()) return;
      servingSchedule.weeks[wi].teams.push({ name: name.trim(), positions: [] });
      volRender(); schedulePreviewUpdate(); scheduleProjectPersist();
    });
    footer.appendChild(addTeamBtn);
    weekBody.appendChild(footer);

    weekEl.appendChild(weekBody);
    editor.appendChild(weekEl);
  });
}
```

- [ ] **Step 2: Manual verify**

Start the server and import a plan from PCO (or load an existing project that has a serving schedule). Check:
- Volunteers panel shows weeks with `▶` toggle buttons (collapsed by default)
- Clicking `▶` expands the week to show teams (button becomes `▼`)
- If service times are present, each service time shows a `▶`/`▼` toggle
- Collapsing and reloading the page preserves the state
- All existing edit operations (delete team, add role, edit names) still work

- [ ] **Step 3: Commit**

```bash
git add src/js/calendar.js
git commit -m "feat(#84): collapsible week and service-time sections in volunteer editor"
```

---

## Task 4: Add preview data attributes to renderServingTeam and renderServingWeek

**Files:**
- Modify: `src/js/calendar.js` — update `renderServingTeam()` and `renderServingWeek()` signatures and bodies
- Modify: `src/js/preview.js` — update the one call site for `renderServingWeek`

Goal: make individual serving rows and service-time subheadings in the preview carry coordinates so the click handler can navigate to the right editor element.

- [ ] **Step 1: Update renderServingTeam() signature and body**

In `src/js/calendar.js`, replace:

```javascript
function renderServingTeam(container, team) {
  // Team name subheading removed — only position rows are shown
  team.positions.forEach(pos => {
    const row = document.createElement('div');
    row.className = 'serving-row';
    const roleSpan = document.createElement('span');
    roleSpan.className = 'serving-role';
    roleSpan.textContent = pos.role + ': ';
    row.appendChild(roleSpan);
    row.appendChild(document.createTextNode(formatNameList(pos.names)));
    container.appendChild(row);
  });
}
```

With:

```javascript
function renderServingTeam(container, team, weekIdx, teamIdx) {
  // Team name subheading removed — only position rows are shown
  team.positions.forEach(pos => {
    const row = document.createElement('div');
    row.className = 'serving-row preview-linkable';
    row.dataset.previewVolWeekIdx = weekIdx;
    row.dataset.previewVolTeamIdx = teamIdx;
    const roleSpan = document.createElement('span');
    roleSpan.className = 'serving-role';
    roleSpan.textContent = pos.role + ': ';
    row.appendChild(roleSpan);
    row.appendChild(document.createTextNode(formatNameList(pos.names)));
    container.appendChild(row);
  });
}
```

- [ ] **Step 2: Update renderServingWeek() signature and body**

In `src/js/calendar.js`, replace:

```javascript
function renderServingWeek(container, weekData, labelText) {
  const wLabel = document.createElement('div');
  wLabel.className = 'serving-week-label';
  wLabel.textContent = labelText;
  container.appendChild(wLabel);

  // Filter out page-break markers and hidden teams
  const visibleTeams = (weekData.teams || []).filter(t => t.type !== 'page-break' && servingTeamFilter[t.name] !== false);

  if (visibleTeams.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'serving-empty';
    empty.textContent = 'No schedule available.';
    container.appendChild(empty);
    return;
  }

  // Check whether any teams carry service-time info (from PCO import)
  const hasServiceTimes = visibleTeams.some(t => t.serviceTime);

  if (!hasServiceTimes) {
    // Legacy / manually-entered data — render flat list as before
    visibleTeams.forEach(team => renderServingTeam(container, team));
    return;
  }

  // Group teams by service time, preserving the order they first appear
  const timeGroups = {};
  const timeOrder  = [];
  visibleTeams.forEach(team => {
    const key = team.serviceTime || '';
    if (!timeGroups[key]) { timeGroups[key] = []; timeOrder.push(key); }
    timeGroups[key].push(team);
  });

  timeOrder.forEach(svcTime => {
    if (svcTime) {
      const stLabel = document.createElement('div');
      stLabel.className = 'serving-service-time';
      stLabel.textContent = svcTime;
      container.appendChild(stLabel);
    }
    timeGroups[svcTime].forEach(team => renderServingTeam(container, team));
  });
}
```

With:

```javascript
function renderServingWeek(container, weekData, labelText, weekIdx) {
  const wLabel = document.createElement('div');
  wLabel.className = 'serving-week-label';
  wLabel.textContent = labelText;
  container.appendChild(wLabel);

  // Filter out page-break markers and hidden teams
  const visibleTeams = (weekData.teams || []).filter(
    t => t.type !== 'page-break' && servingTeamFilter[t.name] !== false
  );

  if (visibleTeams.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'serving-empty';
    empty.textContent = 'No schedule available.';
    container.appendChild(empty);
    return;
  }

  // Check whether any teams carry service-time info (from PCO import)
  const hasServiceTimes = visibleTeams.some(t => t.serviceTime);

  if (!hasServiceTimes) {
    // Legacy / manually-entered data — render flat list
    // teamIdx is the original index in weekData.teams (needed for editor navigation)
    visibleTeams.forEach(team => {
      const teamIdx = (weekData.teams || []).indexOf(team);
      renderServingTeam(container, team, weekIdx, teamIdx);
    });
    return;
  }

  // Group teams by service time, preserving the order they first appear
  const timeGroups = {};
  const timeOrder  = [];
  visibleTeams.forEach(team => {
    const key = team.serviceTime || '';
    if (!timeGroups[key]) { timeGroups[key] = []; timeOrder.push(key); }
    timeGroups[key].push(team);
  });

  timeOrder.forEach(svcTime => {
    if (svcTime) {
      const stLabel = document.createElement('div');
      stLabel.className = 'serving-service-time preview-linkable';
      stLabel.dataset.previewVolWeekIdx = weekIdx;
      stLabel.dataset.previewVolSt      = svcTime;
      stLabel.textContent = svcTime;
      container.appendChild(stLabel);
    }
    timeGroups[svcTime].forEach(team => {
      const teamIdx = (weekData.teams || []).indexOf(team);
      renderServingTeam(container, team, weekIdx, teamIdx);
    });
  });
}
```

- [ ] **Step 3: Update the call site in preview.js**

In `src/js/preview.js`, find (around line 730):

```javascript
        renderServingWeek(servingContent, { ...week, teams: segTeams }, label);
```

Replace with:

```javascript
        renderServingWeek(servingContent, { ...week, teams: segTeams }, label, pi === 0 ? 0 : pi);
```

Wait — `label` and page index are separate concepts. The `weekIdx` needed here is the index of the original week in `servingSchedule.weeks`, not the page index. Look at how pages are built in preview.js around line 700–730 to find the week index variable.

The pages loop is:
```javascript
pages.forEach((pageItems, pi) => {
  pageItems.forEach(({ week, segTeams, label }) => {
    renderServingWeek(servingContent, { ...week, teams: segTeams }, label);
  });
});
```

The `week` object comes from `servingSchedule.weeks`. The correct weekIdx is the index of `week` in `servingSchedule.weeks`. Replace the call with:

```javascript
        const weekIdx = (servingSchedule.weeks || []).indexOf(week);
        renderServingWeek(servingContent, { ...week, teams: segTeams }, label, weekIdx);
```

- [ ] **Step 4: Manual verify**

Open browser devtools. In the preview pane, inspect a serving row element. It should have:
```html
<div class="serving-row preview-linkable"
     data-preview-vol-week-idx="0"
     data-preview-vol-team-idx="2">
```

Service time labels should have:
```html
<div class="serving-service-time preview-linkable"
     data-preview-vol-week-idx="0"
     data-preview-vol-st="9:00am">
```

- [ ] **Step 5: Commit**

```bash
git add src/js/calendar.js src/js/preview.js
git commit -m "feat(#84): add preview data attrs to serving rows and service-time labels"
```

---

## Task 5: Add scroll navigation functions in calendar.js

**Files:**
- Modify: `src/js/calendar.js` — add two functions after `saveVolCollapseState()`

These functions are called from the preview click handler (Task 6). They expand the relevant editor sections and scroll to the target element.

`scrollEditorToSection` and `scrollElementIntoContainer` are defined in `editor.js` (loaded before `calendar.js`) so they are globally available here.

- [ ] **Step 1: Add scrollEditorToVolTeam and scrollEditorToVolServiceTime**

In `src/js/calendar.js`, insert the following two functions immediately after `saveVolCollapseState(state) { ... }` and before `function volRender()`:

```javascript
// Expand the volunteers section + the week and service-time containers that
// contain the target team, then scroll to its editor row and flash it.
function scrollEditorToVolTeam(weekIdx, teamIdx) {
  // 1. Expand the volunteers panel section
  scrollEditorToSection('panel-section-volunteers');

  // 2. Expand the week body for weekIdx
  const volEditor = document.getElementById('vol-editor');
  if (!volEditor) return;
  const weekBodies = volEditor.querySelectorAll('.vol-week-body');
  // weekBodies[weekIdx] corresponds to week wi = weekIdx
  // The week bodies are rendered in order, one per week.
  const weekBody = weekBodies[weekIdx];
  if (weekBody && weekBody.classList.contains('collapsed')) {
    weekBody.classList.remove('collapsed');
    // Update the toggle arrow for this week
    const s = getVolCollapseState();
    delete s[`w${weekIdx}`];
    saveVolCollapseState(s);
    const weekHeader = weekBody.previousElementSibling;
    if (weekHeader && weekHeader.classList.contains('vol-week-header')) {
      const toggle = weekHeader.querySelector('.vol-collapse-toggle');
      if (toggle) toggle.textContent = '▼';
    }
  }

  // 3. Find the target team row and expand its service-time body if needed
  const teamRow = volEditor.querySelector(
    `[data-vol-week-idx="${weekIdx}"][data-vol-team-idx="${teamIdx}"]`
  );
  if (!teamRow) return;

  // Walk up to see if teamRow is inside a vol-st-body
  const stBody = teamRow.closest('.vol-st-body');
  if (stBody && stBody.classList.contains('collapsed')) {
    stBody.classList.remove('collapsed');
    const stHeader = stBody.previousElementSibling;
    if (stHeader && stHeader.classList.contains('vol-st-header')) {
      const toggle = stHeader.querySelector('.vol-collapse-toggle');
      const st = stHeader.dataset.volSt;
      if (toggle) toggle.textContent = '▼';
      const s = getVolCollapseState();
      delete s[`w${weekIdx}:st:${st}`];
      saveVolCollapseState(s);
    }
  }

  // 4. Scroll to team row and flash is-linked
  const aside = document.querySelector('aside');
  scrollElementIntoContainer(aside, teamRow, 'smooth');
  teamRow.classList.add('is-linked');
  setTimeout(() => teamRow.classList.remove('is-linked'), 1600);
}

// Expand the volunteers section + the week, then scroll to the service-time
// subheading and flash it.
function scrollEditorToVolServiceTime(weekIdx, st) {
  scrollEditorToSection('panel-section-volunteers');

  const volEditor = document.getElementById('vol-editor');
  if (!volEditor) return;

  // Expand the week body
  const weekBodies = volEditor.querySelectorAll('.vol-week-body');
  const weekBody   = weekBodies[weekIdx];
  if (weekBody && weekBody.classList.contains('collapsed')) {
    weekBody.classList.remove('collapsed');
    const s = getVolCollapseState();
    delete s[`w${weekIdx}`];
    saveVolCollapseState(s);
    const weekHeader = weekBody.previousElementSibling;
    if (weekHeader && weekHeader.classList.contains('vol-week-header')) {
      const toggle = weekHeader.querySelector('.vol-collapse-toggle');
      if (toggle) toggle.textContent = '▼';
    }
  }

  // Find and expand the service-time header
  const stHeader = volEditor.querySelector(
    `[data-vol-week-idx="${weekIdx}"][data-vol-st="${st}"]`
  );
  if (!stHeader) return;

  const stBody = stHeader.nextElementSibling;
  if (stBody && stBody.classList.contains('vol-st-body') && stBody.classList.contains('collapsed')) {
    stBody.classList.remove('collapsed');
    const toggle = stHeader.querySelector('.vol-collapse-toggle');
    if (toggle) toggle.textContent = '▼';
    const s = getVolCollapseState();
    delete s[`w${weekIdx}:st:${st}`];
    saveVolCollapseState(s);
  }

  const aside = document.querySelector('aside');
  scrollElementIntoContainer(aside, stHeader, 'smooth');
  stHeader.classList.add('is-linked');
  setTimeout(() => stHeader.classList.remove('is-linked'), 1600);
}
```

- [ ] **Step 2: Manual verify**

In browser devtools console, with a serving schedule loaded:

```javascript
// Should expand week 0, scroll to team at teamIdx 0, flash highlight
scrollEditorToVolTeam(0, 0)

// Should expand week 0 and scroll to the "9:00am" service-time header
scrollEditorToVolServiceTime(0, '9:00am')
```

Expected: volunteers panel expands, correct section expands, element scrolls into view and briefly highlights.

- [ ] **Step 3: Commit**

```bash
git add src/js/calendar.js
git commit -m "feat(#84): add scrollEditorToVolTeam and scrollEditorToVolServiceTime"
```

---

## Task 6: Update preview click handler

**Files:**
- Modify: `src/js/preview.js` — insert two checks in the click handler before the `[data-preview-section]` check

- [ ] **Step 1: Insert vol-specific checks in the click handler**

In `src/js/preview.js`, find this comment and the two lines after it (around line 1115):

```javascript
  // ── Click on a section-linked preview element → scroll editor to panel section
  const sectionLinked = targetEl.closest('[data-preview-section]');
  if (sectionLinked) {
    scrollEditorToSection('panel-section-' + sectionLinked.dataset.previewSection);
    return;
  }
```

Replace with:

```javascript
  // ── Click on a volunteer serving row → navigate to that team in the editor
  const volTeamEl = targetEl.closest('[data-preview-vol-team-idx]');
  if (volTeamEl) {
    const wi = parseInt(volTeamEl.dataset.previewVolWeekIdx, 10);
    const ti = parseInt(volTeamEl.dataset.previewVolTeamIdx, 10);
    if (Number.isInteger(wi) && Number.isInteger(ti)) {
      scrollEditorToVolTeam(wi, ti);
      return;
    }
  }

  // ── Click on a volunteer service-time label → navigate to that service time
  const volStEl = targetEl.closest('[data-preview-vol-st]');
  if (volStEl) {
    const wi = parseInt(volStEl.dataset.previewVolWeekIdx, 10);
    const st = volStEl.dataset.previewVolSt;
    if (Number.isInteger(wi) && st) {
      scrollEditorToVolServiceTime(wi, st);
      return;
    }
  }

  // ── Click on a section-linked preview element → scroll editor to panel section
  const sectionLinked = targetEl.closest('[data-preview-section]');
  if (sectionLinked) {
    scrollEditorToSection('panel-section-' + sectionLinked.dataset.previewSection);
    return;
  }
```

- [ ] **Step 2: Manual verify**

With a serving schedule visible in the preview:
- Click a serving row (e.g. "DOOR GREETER: John Smith") → volunteers panel should expand, correct week and service time should expand, and the team's row in the editor should scroll into view with a brief highlight
- Click a service time label (e.g. "9:00am") → service time subheading in editor scrolls into view with highlight
- Click the week label or whitespace → falls through to section-level nav (Volunteers panel header highlights)

- [ ] **Step 3: Commit**

```bash
git add src/js/preview.js
git commit -m "feat(#84): precise click-to-editor navigation for volunteer preview"
```

---

## Task 7: Push branch

- [ ] **Step 1: Push to remote**

```bash
git push -u origin feature/issue-84-volunteers-ux
```

Expected: branch is pushed to remote. Do NOT open a PR.

---

## Self-review checklist

- [x] **Spec: collapsible weeks** — Task 3 covers week-level collapse with toggle + body wrapper
- [x] **Spec: collapsible service times** — Task 3 covers service-time-level collapse
- [x] **Spec: default collapsed** — Task 3 initialises `colState[w${wi}] = true` for any key not yet in localStorage
- [x] **Spec: remember collapse state** — `getVolCollapseState` / `saveVolCollapseState` in Task 2/3
- [x] **Spec: data attrs for editor navigation** — Task 3 adds `data-vol-week-idx` / `data-vol-team-idx` / `data-vol-st` to editor elements
- [x] **Spec: data attrs for preview navigation** — Task 4 adds `data-preview-vol-week-idx` / `data-preview-vol-team-idx` / `data-preview-vol-st` to preview elements
- [x] **Spec: click serving row → scroll to team** — Task 5 + Task 6
- [x] **Spec: click service time → scroll to service time** — Task 5 + Task 6
- [x] **Spec: fallback to section nav on whitespace click** — Task 6 preserves the existing `[data-preview-section]` check as the fallback
- [x] **renderServingTeam signature** — Tasks 4 and 5 both use `(container, team, weekIdx, teamIdx)` consistently
- [x] **renderServingWeek signature** — Tasks 4 and 5 both use `(container, weekData, labelText, weekIdx)` consistently
- [x] **preview.js call site** — Task 4 Step 3 updates the one call site in preview.js
- [x] **No placeholders** — all steps contain complete code
