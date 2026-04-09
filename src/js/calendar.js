// ─── Serving schedule helpers ─────────────────────────────────────────────────

// Split a teams array at {type:'page-break'} entries, returning an array of segments.
// Each segment is an array of normal team objects. Always returns at least one segment.
function volSegments(teams) {
  const segs = [];
  let cur = [];
  for (const t of (teams || [])) {
    if (t.type === 'page-break') { segs.push(cur); cur = []; }
    else cur.push(t);
  }
  segs.push(cur);
  return segs;
}

/**
 * buildServingChunks(schedule, teamFilter, volFilter) → chunk[]
 * Adapter that converts servingSchedule into the shared chunk contract.
 * Each serving week-segment becomes one chunk with section:'serving'.
 *
 *   chunk.forceBreak      — resolved from _breakBefore flag and volSegments() si > 0
 *   chunk.servingWeekIdx  — index into schedule.weeks[]
 *   chunk.servingLabel    — display label ('Serving Today', 'Serving Next Week', etc.)
 *   chunk.servingWeek     — the full week object from schedule.weeks[]
 *   chunk.servingSegTeams — filtered teams for this segment (no page-break entries)
 *   chunk.els             — empty; filled by renderServingWeek() at placement time
 *
 * Note: makeChunk() is defined in preview.js which loads after calendar.js, but
 * buildServingChunks() is only ever called at render time (from renderPreview()),
 * at which point preview.js is already loaded and makeChunk() is available.
 *
 * Called by: src/js/preview.js serving rendering block (Task 3 / #136).
 */
function buildServingChunks(schedule, teamFilter, volFilter) {
  const sWeeks = schedule.weeks || [];
  const chunks = [];

  sWeeks.forEach((week, wi) => {
    const allHidden = (week.teams || [])
      .filter(t => t.type !== 'page-break')
      .every(t => teamFilter[t.name] === false ||
                  volFilter['w' + wi + ':' + (t.serviceTime || '') + ':' + t.name] === false);
    if (allHidden) return;

    const baseLabel = wi === 0 ? 'Serving Today'
      : (sWeeks.length === 2 ? 'Serving Next Week' : week.date || `Week ${wi + 1}`);

    volSegments(week.teams).forEach((segTeams, si) => {
      if (si > 0 && segTeams.length === 0) return;
      const label = si === 0 ? baseLabel : baseLabel + ' (cont.)';
      // forceBreak: week _breakBefore (first seg of a non-first week) OR intra-week continuation
      const forceBreak = (si === 0 && wi > 0 && !!week._breakBefore) || si > 0;

      // For intra-week breaks (si > 0), find the index of the si-th page-break in teams[].
      // This is needed by the "Remove page break" handler to splice it out.
      let teamBreakIdx = null;
      if (si > 0) {
        let breakCount = 0;
        for (let ti = 0; ti < (week.teams || []).length; ti++) {
          if (week.teams[ti]?.type === 'page-break') {
            breakCount++;
            if (breakCount === si) { teamBreakIdx = ti; break; }
          }
        }
      }

      chunks.push(makeChunk({
        section:              'serving',
        sourceId:             wi,
        forceBreak,
        servingWeekIdx:       wi,
        servingLabel:         label,
        servingWeek:          week,
        servingSegTeams:      segTeams,
        servingTeamBreakIdx:  teamBreakIdx,
        els:                  [],
      }));
    });
  });

  return chunks;
}

function formatNameList(names) {
  if (!names || names.length === 0) return '—';
  if (names.length === 1) return names[0];
  if (names.length === 2) return names[0] + ' & ' + names[1];
  return names.slice(0, -1).join(', ') + ' & ' + names[names.length - 1];
}

// ─── Volunteer editor (sidebar) ───────────────────────────────────────────────

function getVolCollapseState() {
  try { return JSON.parse(localStorage.getItem('vol-collapse') || '{}'); }
  catch { return {}; }
}

function saveVolCollapseState(state) {
  localStorage.setItem('vol-collapse', JSON.stringify(state));
}

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
    s[`w${weekIdx}`] = false;
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
      s[`w${weekIdx}:st:${st}`] = false;
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
      s[weekCollapseKey] = nowCollapsed ? true : false;
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
      (last, t, i) => (t.type !== 'page-break' && servingTeamFilter[t.name] !== false && volTeamFilter['w'+wi+':'+(t.serviceTime||'')+':'+t.name] !== false) ? i : last,
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
      const volKey = 'w'+wi+':'+(team.serviceTime||'')+':'+team.name;
      const teamHidden = volTeamFilter[volKey] === false;

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

          // Determine if all teams in this service time are hidden
          const stTeams = (data.teams || []).filter(t => t.type !== 'page-break' && t.serviceTime === team.serviceTime);
          const allStHidden = stTeams.length > 0 && stTeams.every(t => volTeamFilter['w'+wi+':'+t.serviceTime+':'+t.name] === false);

          // Service time header: toggle + label + hide-all button
          const stHeaderEl = document.createElement('div');
          stHeaderEl.className = 'vol-st-header';
          stHeaderEl.dataset.volWeekIdx = wi;
          stHeaderEl.dataset.volSt      = team.serviceTime;

          const stToggle = document.createElement('button');
          stToggle.className = 'vol-collapse-toggle';
          stToggle.textContent = stCollapsed ? '▶' : '▼';

          const stLabelEl = document.createElement('span');
          stLabelEl.className = 'vol-st-header-text';
          stLabelEl.textContent = team.serviceTime + (allStHidden ? ' (hidden)' : '');
          if (allStHidden) stLabelEl.style.opacity = '0.45';

          const stVisBtn = document.createElement('button');
          stVisBtn.className = 'vol-vis-btn';
          stVisBtn.style.cssText = 'margin-left:auto;font-size:0.75rem;';
          stVisBtn.textContent = allStHidden ? 'Show all' : 'Hide all';
          stVisBtn.addEventListener('click', () => {
            const hide = !allStHidden;
            stTeams.forEach(t => {
              volTeamFilter['w'+wi+':'+t.serviceTime+':'+t.name] = hide ? false : true;
            });
            volRender(); schedulePreviewUpdate(); autosaveProjectState();
          });

          stHeaderEl.appendChild(stToggle);
          stHeaderEl.appendChild(stLabelEl);
          stHeaderEl.appendChild(stVisBtn);
          weekBody.appendChild(stHeaderEl);

          const stBody = document.createElement('div');
          stBody.className = 'vol-st-body';
          if (stCollapsed) stBody.classList.add('collapsed');

          stToggle.addEventListener('click', () => {
            const s = getVolCollapseState();
            const nowC = !stBody.classList.contains('collapsed');
            s[stCollapseKey] = nowC ? true : false;
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
        'display:flex; align-items:center; justify-content:space-between; margin-bottom:0;' +
        (teamHidden ? 'opacity:0.45;' : '');
      teamNameRow.dataset.volWeekIdx = wi;
      teamNameRow.dataset.volTeamIdx = ti;

      const teamNameEl = document.createElement('div');
      teamNameEl.className   = 'vol-team-name';
      teamNameEl.style.marginBottom = '0';
      teamNameEl.textContent = team.name + (teamHidden ? ' (hidden)' : '');
      teamNameRow.appendChild(teamNameEl);

      const visBtn = document.createElement('button');
      visBtn.className = 'vol-vis-btn';
      visBtn.title = 'Toggle visibility in bulletin';
      visBtn.textContent = teamHidden ? 'Show' : 'Hide';
      visBtn.addEventListener('click', () => {
        volTeamFilter[volKey] = volTeamFilter[volKey] === false ? true : false;
        volRender(); schedulePreviewUpdate(); autosaveProjectState();
      });
      teamNameRow.appendChild(visBtn);

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

      // ── Position rows (skipped for hidden teams) ────────────────────────────
      if (teamHidden) return;
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

// ─── Calendar helpers ─────────────────────────────────────────────────────────

function calGetUrls() {
  const defaults = Array.isArray(_publicConfig.calendarDefaults?.urls)
    ? _publicConfig.calendarDefaults.urls : [];
  return _calUrls || defaults.slice();
}

function calGetExclude() {
  const defaults = Array.isArray(_publicConfig.calendarDefaults?.exclude) && _publicConfig.calendarDefaults.exclude.length
    ? _publicConfig.calendarDefaults.exclude : CAL_DEFAULT_EXCL;
  return _calExclude || defaults.slice();
}

function calInitSettings() {
  const urlsInput = document.getElementById('cal-urls-input');
  const exclInput = document.getElementById('cal-excl-input');
  if (urlsInput) urlsInput.value = calGetUrls().join('\n');
  if (exclInput) exclInput.value = calGetExclude().join('\n');
}

function calSetStatus(msg, isError) {
  const el = document.getElementById('cal-status-text');
  if (el) {
    el.textContent = msg;
    el.style.color = isError ? '#c44' : 'var(--muted)';
  }
}

async function calFetchAll(force) {
  const now = Date.now();
  if (!force && calEvents !== null && calEvents !== false && (now - calLastFetch) < CAL_CACHE_MS) {
    return; // still fresh
  }

  const btn = document.getElementById('cal-refresh-btn');
  if (btn) { btn.disabled = true; btn.textContent = '↻ Fetching…'; }
  calSetStatus('Fetching calendar…', false);

  const urls = calGetUrls();
  const excl = calGetExclude();

  const params = new URLSearchParams({
    urls: JSON.stringify(urls),
    exclude: JSON.stringify(excl),
  });

  try {
    // When force=true (user clicked Refresh), bypass the browser HTTP cache so
    // a previously-cached failure doesn't block recovery after a token refresh.
    const fetchOpts = force ? { cache: 'no-store' } : {};
    const resp = await fetch(`/cal?${params}`, fetchOpts);
    if (!resp.ok) {
      throw new Error(`Server returned HTTP ${resp.status}`);
    }
    const data = await resp.json();
    if (data.ok) {
      // Merge fresh events with any user edits (title/location changes made in the editor).
      // Each event gets a _srcTitle tag (the original server title) so future merges
      // can still match even if the user renamed the event.
      const oldEvents = Array.isArray(calEvents) ? calEvents : [];
      calEvents = data.events.map(freshEv => {
        const match = oldEvents.find(old =>
          old.start.iso === freshEv.start.iso &&
          (old._srcTitle || old.title).toLowerCase() === freshEv.title.toLowerCase()
        );
        if (match) {
          // Preserve user-edited title and location; update everything else from server
          return { ...freshEv, title: match.title, location: match.location, _srcTitle: freshEv.title };
        }
        return { ...freshEv, _srcTitle: freshEv.title };
      });
      calLastFetch = Date.now();
      const count = calEvents.length;
      calSetStatus(`${count} event${count === 1 ? '' : 's'} loaded`, false);
    } else {
      calEvents = false;
      calSetStatus('Calendar unavailable', true);
    }
  } catch (e) {
    calEvents = false;
    const msg = e && e.message ? e.message : String(e);
    calSetStatus(`Fetch failed: ${msg}`, true);
    console.error('[cal] fetch error:', e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '↺ Refresh Calendar'; }
  }

  renderCalEventEditor();
  renderPreview();
}

function formatCalTime(isoStr, allDay) {
  if (allDay || !isoStr) return '';
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  } catch (e) {
    return '';
  }
}

function calDayLabel(isoStr) {
  try {
    const d = new Date(isoStr + (isoStr.length === 10 ? 'T12:00:00' : ''));
    return d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
  } catch (e) {
    return isoStr;
  }
}

function renderCalEventEditor() {
  const container = document.getElementById('cal-event-editor');
  const addBtn    = document.getElementById('cal-add-event-btn');
  if (!container) return;
  container.innerHTML = '';

  // "Start calendar on new page" toggle
  const calForceBreakBtn = document.createElement('button');
  calForceBreakBtn.className = 'vol-add-link';
  calForceBreakBtn.style.cssText = 'color:var(--muted); display:block; margin:0.3rem 0 0.5rem;';
  calForceBreakBtn.textContent = breakBeforeCalendar
    ? '\u2193 Calendar on same page as previous'
    : '\u2191 Start calendar on new page';
  calForceBreakBtn.addEventListener('click', () => {
    breakBeforeCalendar = !breakBeforeCalendar;
    renderCalEventEditor();
    schedulePreviewUpdate();
    scheduleProjectPersist();
  });
  container.appendChild(calForceBreakBtn);

  // Show/hide add button depending on whether we have a fetched (or manual) array
  const ready = Array.isArray(calEvents);
  if (addBtn) addBtn.style.display = ready ? '' : 'none';
  if (!ready || calEvents.length === 0) return;

  // Sort events by start ISO before grouping
  calEvents.sort((a, b) => a.start.iso.localeCompare(b.start.iso));

  // Group indices by calendar date
  const byDay = new Map();
  calEvents.forEach((ev, idx) => {
    const key = ev.start.iso.slice(0, 10);
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(idx);
  });

  let editorDayIndex = 0;
  byDay.forEach((indices, dayKey) => {
    // Per-day-group break button (for days after the first)
    if (editorDayIndex > 0) {
      const hasBreak = calBreakBeforeDates.includes(dayKey);
      const breakBtn = document.createElement('button');
      breakBtn.className = 'vol-add-link';
      breakBtn.style.cssText = 'color:var(--muted); margin-left:0.6rem; display:block; margin-top:0.2rem;';
      breakBtn.textContent = hasBreak
        ? '\u2715 Remove break before ' + calDayLabel(dayKey)
        : '\u229e Add break before ' + calDayLabel(dayKey);
      breakBtn.addEventListener('click', () => {
        if (hasBreak) {
          calBreakBeforeDates = calBreakBeforeDates.filter(d => d !== dayKey);
        } else {
          if (!calBreakBeforeDates.includes(dayKey)) calBreakBeforeDates.push(dayKey);
        }
        renderCalEventEditor();
        schedulePreviewUpdate();
        scheduleProjectPersist();
      });
      container.appendChild(breakBtn);
    }
    editorDayIndex++;

    const dayH = document.createElement('div');
    dayH.className = 'cal-edit-daygroup';
    dayH.textContent = calDayLabel(dayKey);
    container.appendChild(dayH);

    indices.forEach(idx => {
      const ev  = calEvents[idx];
      const row = document.createElement('div');
      row.className = 'cal-edit-row';

      // ── Row header: time badge · title input · delete ──
      const hdr = document.createElement('div');
      hdr.className = 'cal-edit-row-hdr';

      const timeBadge = document.createElement('div');
      timeBadge.className = 'cal-edit-time-badge';
      timeBadge.textContent = ev.start.allDay ? 'All day' : (formatCalTime(ev.start.iso, false) || '—');
      hdr.appendChild(timeBadge);

      const titleInput = document.createElement('input');
      titleInput.type = 'text';
      titleInput.className = 'cal-edit-title';
      titleInput.value = ev.title;
      titleInput.placeholder = 'Event title';
      titleInput.addEventListener('input', () => {
        ev.title = titleInput.value;
        renderPreview();
      });
      hdr.appendChild(titleInput);

      const delBtn = document.createElement('button');
      delBtn.className = 'cal-edit-del';
      delBtn.title = 'Remove this event from the bulletin';
      delBtn.textContent = '✕';
      delBtn.addEventListener('click', () => {
        calEvents.splice(calEvents.indexOf(ev), 1);
        renderCalEventEditor();
        renderPreview();
      });
      hdr.appendChild(delBtn);
      row.appendChild(hdr);

      // ── Location sub-row ──
      const locInput = document.createElement('input');
      locInput.type = 'text';
      locInput.className = 'cal-edit-loc';
      locInput.placeholder = 'Location (optional)';
      locInput.value = ev.location || '';
      locInput.addEventListener('input', () => {
        ev.location = locInput.value;
        renderPreview();
      });
      row.appendChild(locInput);

      container.appendChild(row);
    });
  });
}

function buildCalEventRow(ev) {
  const row = document.createElement('div');
  row.className = 'cal-event-row';
  const timeEl = document.createElement('div');
  timeEl.className = 'cal-event-time';
  timeEl.textContent = formatCalTime(ev.start.iso, ev.start.allDay);
  row.appendChild(timeEl);
  const info = document.createElement('div');
  info.className = 'cal-event-info';
  const titleSpan = document.createElement('div');
  titleSpan.className = 'cal-event-title';
  titleSpan.textContent = ev.title;
  info.appendChild(titleSpan);
  const isAtChurch = /1030\s*s\.?\s*linwood/i.test(ev.location);
  if (ev.location && !isAtChurch) {
    const locSpan = document.createElement('div');
    locSpan.className = 'cal-event-loc';
    locSpan.textContent = ev.location;
    info.appendChild(locSpan);
  }
  row.appendChild(info);
  return row;
}

function buildCalendarSegments(church) {
  // Returns [{date: string|null, el: HTMLElement}]
  // First segment has date: null (title + first day group, or loading/error msg).
  // Subsequent segments have date: 'YYYY-MM-DD' (one per additional day group).
  const titleEl = document.createElement('div');
  titleEl.className = 'cal-page-title';
  titleEl.textContent = church ? `This Week at ${church}` : 'This Week';

  function singleSegment(msgClass, msgText) {
    const container = document.createElement('div');
    container.appendChild(titleEl);
    const msg = document.createElement('div');
    msg.className = msgClass;
    msg.textContent = msgText;
    container.appendChild(msg);
    return [{ date: null, el: container }];
  }

  if (calEvents === null) {
    calFetchAll(false);
    return singleSegment('cal-empty', 'Loading calendar\u2026');
  }
  if (calEvents === false || !Array.isArray(calEvents)) {
    return singleSegment('cal-unavailable', 'Calendar unavailable \u2014 please add events manually.');
  }
  if (calEvents.length === 0) {
    return singleSegment('cal-empty', 'No events scheduled this week.');
  }

  const byDay = new Map();
  for (const ev of calEvents) {
    const dayKey = ev.start.iso.slice(0, 10);
    if (!byDay.has(dayKey)) byDay.set(dayKey, []);
    byDay.get(dayKey).push(ev);
  }

  const segments = [];
  let isFirst = true;
  byDay.forEach((evs, dayKey) => {
    const container = document.createElement('div');
    if (isFirst) {
      container.appendChild(titleEl);
      isFirst = false;
    }
    const dayH = document.createElement('div');
    dayH.className = 'cal-day-heading';
    dayH.textContent = calDayLabel(dayKey);
    container.appendChild(dayH);
    evs.forEach(ev => container.appendChild(buildCalEventRow(ev)));
    segments.push({ date: dayKey, el: container });
  });
  return segments;
}

/**
 * buildCalendarChunks(church) → chunk[]
 * Adapter that wraps buildCalendarSegments() output into the shared chunk contract.
 * Each calendar day group becomes one chunk with section:'calendar'.
 *
 *   chunk.sourceId = seg.date || null  (null for first/title segment)
 *   chunk.calDate  = seg.date || ''    (ISO date string or '' — used by break controls)
 *   chunk.els      = [seg.el]
 *
 * forceBreak is NOT resolved here — the preview rendering loop determines it from
 * breakBeforeCalendar and calBreakBeforeDates at render time and stamps it then.
 *
 * Note: makeChunk() is defined in preview.js which loads after calendar.js, but
 * buildCalendarChunks() is only ever called at render time (from renderPreview()),
 * at which point preview.js is already loaded and makeChunk() is available.
 *
 * Called by: src/js/preview.js calendar rendering block (Task 3 / #132).
 */
function buildCalendarChunks(church) {
  return buildCalendarSegments(church).map(seg => makeChunk({
    section:  'calendar',
    sourceId: seg.date || null,
    calDate:  seg.date || '',
    els:      [seg.el],
  }));
}

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

function renderServingWeek(container, weekData, labelText, weekIdx) {
  // Filter out page-break markers and hidden teams
  const visibleTeams = (weekData.teams || []).filter(
    t => t.type !== 'page-break' && servingTeamFilter[t.name] !== false && volTeamFilter['w'+weekIdx+':'+(t.serviceTime||'')+':'+t.name] !== false
  );

  if (visibleTeams.length === 0) return; // hide header too when all teams are filtered

  const wLabel = document.createElement('div');
  wLabel.className = 'serving-week-label';
  wLabel.textContent = labelText;
  container.appendChild(wLabel);

  // Check whether any teams carry service-time info (from PCO import)
  const hasServiceTimes = visibleTeams.some(t => t.serviceTime);

  if (!hasServiceTimes) {
    // Legacy / manually-entered data — render flat list
    // teamIdx is the original index in weekData.teams (needed for editor navigation)
    visibleTeams.forEach((team, vi) => {
      if (vi > 0) {
        const teamIdx = (weekData.teams || []).indexOf(team);
        container.appendChild(makeSplitCtrlEl(makeBreakSrc('serving-split', {
          weekIdx, boundary: 'team', insertBeforeIdx: teamIdx,
        })));
      }
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

  timeOrder.forEach((svcTime, groupIdx) => {
    if (groupIdx > 0) {
      const firstTeam = timeGroups[svcTime][0];
      const insertBeforeIdx = (weekData.teams || []).indexOf(firstTeam);
      container.appendChild(makeSplitCtrlEl(makeBreakSrc('serving-split', {
        weekIdx, boundary: 'team', insertBeforeIdx,
      })));
    }
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

// ── Google Drive settings ──────────────────────────────────────────────────────

function initDriveSettings() {
  const card = document.getElementById('google-drive-card');
  if (!card) return;

  const googleConnected = _publicConfig && _publicConfig.googleConfigured;
  if (!googleConnected) { card.style.display = 'none'; return; }
  card.style.display = '';

  const driveConfigured = _publicConfig && _publicConfig.driveConfigured;
  const scopeWarn  = document.getElementById('google-drive-scope-warn');
  const folderRow  = document.getElementById('google-drive-folder-row');

  if (!driveConfigured) {
    if (scopeWarn) scopeWarn.style.display = '';
    if (folderRow) folderRow.style.display = 'none';
    return;
  }

  if (scopeWarn) scopeWarn.style.display = 'none';
  if (folderRow) folderRow.style.display = '';

  // Populate saved folder ID
  apiFetch('/api/settings').then(data => {
    const folderInput = document.getElementById('google-drive-folder-id');
    if (folderInput && data.googleDriveFolderId) {
      folderInput.value = data.googleDriveFolderId;
    }
  }).catch(() => {}); // non-critical prefetch — folder ID simply stays blank if unavailable

  // Wire save button (guard against double-wiring on re-init)
  const saveBtn = document.getElementById('google-drive-save-btn');
  if (saveBtn && !saveBtn._driveWired) {
    saveBtn._driveWired = true;
    saveBtn.addEventListener('click', saveDriveFolderId);
  }
}

async function saveDriveFolderId() {
  const input    = document.getElementById('google-drive-folder-id');
  const msg      = document.getElementById('google-drive-msg');
  const folderId = input ? input.value.trim() : '';

  if (msg) { msg.textContent = 'Saving…'; msg.className = 'pco-msg'; }

  try {
    const settings = await apiFetch('/api/settings');
    settings.googleDriveFolderId = folderId || null;
    await apiFetch('/api/settings', 'POST', settings);
    if (msg) {
      msg.textContent = folderId
        ? 'Folder saved.'
        : 'Cleared — files will save to My Drive root.';
      msg.className = 'pco-msg success';
    }
  } catch (e) {
    if (msg) { msg.textContent = `Save failed: ${e.message || e}`; msg.className = 'pco-msg error'; }
  }
}
