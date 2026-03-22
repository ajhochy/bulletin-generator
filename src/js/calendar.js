// ─── Serving schedule helpers ─────────────────────────────────────────────────
function formatNameList(names) {
  if (!names || names.length === 0) return '—';
  if (names.length === 1) return names[0];
  if (names.length === 2) return names[0] + ' & ' + names[1];
  return names.slice(0, -1).join(', ') + ' & ' + names[names.length - 1];
}

// ─── Volunteer editor (sidebar) ───────────────────────────────────────────────
function volRender() {
  const editor   = document.getElementById('vol-editor');
  const emptyMsg = document.getElementById('vol-empty');
  editor.innerHTML = '';

  if (!servingSchedule) {
    emptyMsg.style.display = '';
    return;
  }
  emptyMsg.style.display = 'none';

  const weeks = servingSchedule.weeks || [];

  weeks.forEach((data, wi) => {
    const label = wi === 0 ? 'This Week' : (weeks.length === 2 ? 'Next Week' : data.date || `Week ${wi + 1}`);
    const weekEl = document.createElement('div');

    const weekLabel = document.createElement('div');
    weekLabel.className = 'vol-week-label';
    weekLabel.textContent = label + (wi === 0 && data.date ? ' — ' + data.date : (wi > 0 && label !== data.date && data.date ? ' — ' + data.date : ''));
    weekEl.appendChild(weekLabel);

    // Track service time headers so we insert them before the first team in each group
    let lastServiceTime = undefined;

    (data.teams || []).forEach((team, ti) => {
      // Skip teams hidden by the serving team filter
      if (servingTeamFilter[team.name] === false) return;

      // Insert a service-time subheading when the group changes
      if (team.serviceTime !== lastServiceTime) {
        lastServiceTime = team.serviceTime;
        if (team.serviceTime) {
          const stHeader = document.createElement('div');
          stHeader.className = 'vol-week-label';
          stHeader.style.cssText = 'font-size:0.65rem; margin-top:0.4rem; margin-bottom:0.15rem; color:var(--accent-light); border-bottom-color:var(--border);';
          stHeader.textContent = team.serviceTime;
          weekEl.appendChild(stHeader);
        }
      }

      const teamNameRow = document.createElement('div');
      teamNameRow.style.cssText = 'display:flex; align-items:center; justify-content:space-between; margin-bottom:0;';
      const teamNameEl = document.createElement('div');
      teamNameEl.className = 'vol-team-name';
      teamNameEl.style.marginBottom = '0';
      teamNameEl.textContent = team.name;
      teamNameRow.appendChild(teamNameEl);
      const delTeamBtn = document.createElement('button');
      delTeamBtn.className = 'vol-remove-btn';
      delTeamBtn.title = 'Remove this team';
      delTeamBtn.textContent = '✕';
      delTeamBtn.addEventListener('click', () => {
        if (!confirm(`Remove team "${team.name}"?`)) return;
        servingSchedule.weeks[wi].teams.splice(ti, 1);
        volRender();
        schedulePreviewUpdate();
        scheduleProjectPersist();
      });
      teamNameRow.appendChild(delTeamBtn);
      weekEl.appendChild(teamNameRow);

      team.positions.forEach((pos, pi) => {
        const row = document.createElement('div');
        row.className = 'vol-pos-row';

        const roleLabel = document.createElement('span');
        roleLabel.className = 'vol-role-label';
        roleLabel.textContent = pos.role;

        const namesInput = document.createElement('input');
        namesInput.type = 'text';
        namesInput.className = 'vol-names-input';
        namesInput.value = (pos.names || []).join(', ');
        namesInput.placeholder = 'Names, comma-separated';
        namesInput.addEventListener('input', () => {
          servingSchedule.weeks[wi].teams[ti].positions[pi].names =
            namesInput.value.split(',').map(n => n.trim()).filter(Boolean);
          schedulePreviewUpdate();
          updateSectionPreviews();
          scheduleProjectPersist();
        });

        const removeBtn = document.createElement('button');
        removeBtn.className = 'vol-remove-btn';
        removeBtn.title = 'Remove this role';
        removeBtn.textContent = '✕';
        removeBtn.addEventListener('click', () => {
          servingSchedule.weeks[wi].teams[ti].positions.splice(pi, 1);
          volRender();
          schedulePreviewUpdate();
          scheduleProjectPersist();
        });

        row.appendChild(roleLabel);
        row.appendChild(namesInput);
        row.appendChild(removeBtn);
        weekEl.appendChild(row);
      });

      // Add role button
      const addRoleBtn = document.createElement('button');
      addRoleBtn.className = 'vol-add-link';
      addRoleBtn.textContent = '+ Add role';
      addRoleBtn.addEventListener('click', () => {
        const role = prompt('Role name (e.g. GREETER):');
        if (!role || !role.trim()) return;
        servingSchedule.weeks[wi].teams[ti].positions.push({
          role: role.trim().toUpperCase(), names: []
        });
        volRender();
        schedulePreviewUpdate();
        scheduleProjectPersist();
      });
      weekEl.appendChild(addRoleBtn);
    });

    // Add team button
    const footer = document.createElement('div');
    footer.className = 'vol-week-footer';
    const addTeamBtn = document.createElement('button');
    addTeamBtn.className = 'btn-sm';
    addTeamBtn.style.cssText = 'width:100%; font-size:0.7rem;';
    addTeamBtn.textContent = '+ Add Team';
    addTeamBtn.addEventListener('click', () => {
      const name = prompt('Team name (e.g. Greeter):');
      if (!name || !name.trim()) return;
      servingSchedule.weeks[wi].teams.push({ name: name.trim(), positions: [] });
      volRender();
      schedulePreviewUpdate();
      scheduleProjectPersist();
    });
    footer.appendChild(addTeamBtn);
    weekEl.appendChild(footer);

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
    const resp = await fetch(`/cal?${params}`);
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

  byDay.forEach((indices, dayKey) => {
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

function renderCalendarPage(container, church, date) {
  const titleEl = document.createElement('div');
  titleEl.className = 'cal-page-title';
  titleEl.textContent = church ? `This Week at ${church}` : 'This Week';
  container.appendChild(titleEl);

  if (calEvents === null) {
    // Not yet fetched — kick off a fetch in background
    calFetchAll(false);
    const msg = document.createElement('div');
    msg.className = 'cal-empty';
    msg.textContent = 'Loading calendar…';
    container.appendChild(msg);
    return;
  }

  if (calEvents === false || !Array.isArray(calEvents)) {
    const msg = document.createElement('div');
    msg.className = 'cal-unavailable';
    msg.textContent = 'Calendar unavailable — please add events manually.';
    container.appendChild(msg);
    return;
  }

  if (calEvents.length === 0) {
    const msg = document.createElement('div');
    msg.className = 'cal-empty';
    msg.textContent = 'No events scheduled this week.';
    container.appendChild(msg);
    return;
  }

  // Group by date
  const byDay = new Map();
  for (const ev of calEvents) {
    const dayKey = ev.start.iso.slice(0, 10);
    if (!byDay.has(dayKey)) byDay.set(dayKey, []);
    byDay.get(dayKey).push(ev);
  }

  byDay.forEach((evs, dayKey) => {
    const dayH = document.createElement('div');
    dayH.className = 'cal-day-heading';
    dayH.textContent = calDayLabel(dayKey);
    container.appendChild(dayH);

    evs.forEach(ev => {
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
      container.appendChild(row);
    });
  });
}

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

function renderServingWeek(container, weekData, labelText) {
  const wLabel = document.createElement('div');
  wLabel.className = 'serving-week-label';
  wLabel.textContent = labelText + (weekData.date ? ` (${weekData.date})` : '');
  container.appendChild(wLabel);

  // Filter out hidden teams
  const visibleTeams = (weekData.teams || []).filter(t => servingTeamFilter[t.name] !== false);

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

