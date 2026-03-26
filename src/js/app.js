// ─── Page size selector ───────────────────────────────────────────────────────
document.getElementById('doc-page-size-sel').addEventListener('change', e => {
  activeDocTemplate = Object.assign({}, activeDocTemplate, { pageSize: e.target.value });
  applyDocTemplate();
  apiFetch('/api/settings', 'POST', { docTemplate: activeDocTemplate }).catch(() => {});
  schedulePreviewUpdate();
});

// ─── Format filter input ──────────────────────────────────────────────────────
document.getElementById('fmt-filter').addEventListener('input', e => {
  applyFmtFilter(e.target.value);
});

// ─── Settings anchor nav ──────────────────────────────────────────────────────
document.querySelector('.stg-anchor-nav').addEventListener('click', e => {
  const link = e.target.closest('.stg-anchor-link');
  if (!link) return;
  e.preventDefault();
  const target = document.getElementById(link.dataset.target);
  if (target) target.scrollIntoView({ behavior: 'smooth' });
});

// ─── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.app-page').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'page-format') {
      renderFormatPage();
    } else {
      // Clear format filter when leaving the Format tab
      const flt = document.getElementById('fmt-filter');
      if (flt) flt.value = '';
    }
  });
});



// Seed welcome items now that staff.js (WELCOME_ITEMS) has loaded
welcomeItems = [...WELCOME_ITEMS];

restoreOnStartup().then(() => {
  initPco();
  initGoogle();
  renderServingTeamSettings();
  initUpdateSection();
});

// ─── Update section button wiring ─────────────────────────────────────────────
document.getElementById('update-check-btn').addEventListener('click', checkForUpdate);
document.getElementById('update-apply-btn').addEventListener('click', applyUpdate);

// ─── Calendar button listeners ────────────────────────────────────────────────
document.getElementById('cal-refresh-btn').addEventListener('click', () => calFetchAll(true));

document.getElementById('cal-settings-save-btn').addEventListener('click', () => {
  const urlsRaw = document.getElementById('cal-urls-input').value.trim();
  const urls = urlsRaw.split('\n').map(s => s.trim()).filter(Boolean);
  _calUrls = urls;
  apiFetch('/api/settings', 'POST', { calUrls: _calUrls }).catch(() => {});
  calEvents = null;
  calLastFetch = 0;
  calFetchAll(true);
  setStatus('Calendar settings saved. Re-fetching…', 'success');
});

document.getElementById('cal-excl-save-btn').addEventListener('click', () => {
  const exclRaw = document.getElementById('cal-excl-input').value.trim();
  const excl = exclRaw.split('\n').map(s => s.trim()).filter(Boolean);
  _calExclude = excl;
  apiFetch('/api/settings', 'POST', { calExclude: _calExclude }).catch(() => {});
  calEvents = null;
  calLastFetch = 0;
  calFetchAll(true);
  setStatus('Exclude list saved. Re-fetching…', 'success');
});

document.getElementById('cal-settings-reset-btn').addEventListener('click', () => {
  _calUrls = null;
  _calExclude = null;
  apiFetch('/api/settings', 'POST', { calUrls: null, calExclude: null }).catch(() => {});
  calInitSettings();
  document.getElementById('cal-excl-input').value = calGetExclude().join('\n');
  calEvents = null;
  calLastFetch = 0;
  calFetchAll(true);
  setStatus('Calendar settings reset to defaults.', 'success');
});

calInitSettings();
// Kick off initial calendar fetch in background
calFetchAll(false);

// ─── Add Event button ─────────────────────────────────────────────────────────
document.getElementById('cal-add-event-btn').addEventListener('click', () => {
  // Toggle: if form already open, close it
  const existing = document.getElementById('cal-add-form');
  if (existing) { existing.remove(); return; }

  const form = document.createElement('div');
  form.id = 'cal-add-form';
  form.className = 'cal-add-form';

  // Date + all-day row
  const dateRow = document.createElement('div');
  dateRow.className = 'cal-add-form-row';

  const dateIn = document.createElement('input');
  dateIn.type = 'date';
  dateIn.style.flex = '1';
  dateIn.value = new Date().toISOString().slice(0, 10);

  const allDayLabel = document.createElement('label');
  allDayLabel.style.cssText = 'font-size:0.74rem; display:flex; align-items:center; gap:0.25rem; white-space:nowrap; cursor:pointer;';
  const allDayCheck = document.createElement('input');
  allDayCheck.type = 'checkbox';
  allDayCheck.checked = false;
  allDayLabel.appendChild(allDayCheck);
  allDayLabel.appendChild(document.createTextNode(' All day'));
  dateRow.appendChild(dateIn);
  dateRow.appendChild(allDayLabel);
  form.appendChild(dateRow);

  // Time row (visible by default since all-day is unchecked)
  const timeRow = document.createElement('div');
  timeRow.className = 'cal-add-form-row';
  timeRow.style.display = 'flex';
  const timeLabel = document.createElement('span');
  timeLabel.textContent = 'Time:';
  timeLabel.style.cssText = 'font-size:0.74rem; white-space:nowrap; flex-shrink:0;';
  const timeIn = document.createElement('input');
  timeIn.type = 'time';
  timeIn.value = '09:00';
  timeIn.style.flex = '1';
  timeRow.appendChild(timeLabel);
  timeRow.appendChild(timeIn);
  form.appendChild(timeRow);

  allDayCheck.addEventListener('change', () => {
    timeRow.style.display = allDayCheck.checked ? 'none' : 'flex';
  });

  // Title
  const titleIn = document.createElement('input');
  titleIn.type = 'text';
  titleIn.placeholder = 'Event title *';
  form.appendChild(titleIn);

  // Location
  const locIn = document.createElement('input');
  locIn.type = 'text';
  locIn.placeholder = 'Location (optional)';
  form.appendChild(locIn);

  // Buttons
  const btnRow = document.createElement('div');
  btnRow.style.cssText = 'display:flex; gap:0.4rem; margin-bottom:0;';

  const confirmBtn = document.createElement('button');
  confirmBtn.className = 'btn-sm btn-sm-primary';
  confirmBtn.textContent = 'Add Event';
  confirmBtn.style.flex = '1';
  confirmBtn.addEventListener('click', () => {
    const title = titleIn.value.trim();
    if (!title) { titleIn.style.borderColor = 'var(--danger)'; titleIn.focus(); return; }
    const dateVal = dateIn.value;
    if (!dateVal) { dateIn.style.borderColor = 'var(--danger)'; dateIn.focus(); return; }

    const isAllDay = allDayCheck.checked;
    const isoStr  = isAllDay ? dateVal : `${dateVal}T${timeIn.value || '00:00'}:00`;

    if (!Array.isArray(calEvents)) calEvents = [];
    calEvents.push({
      title,
      start:       { iso: isoStr, allDay: isAllDay },
      end:         null,
      location:    locIn.value.trim(),
      description: '',
    });
    form.remove();
    renderCalEventEditor();
    renderPreview();
  });
  btnRow.appendChild(confirmBtn);

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn-sm';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.style.flex = '1';
  cancelBtn.addEventListener('click', () => form.remove());
  btnRow.appendChild(cancelBtn);
  form.appendChild(btnRow);

  // Insert the form after the Add Event button
  const addBtnEl = document.getElementById('cal-add-event-btn');
  addBtnEl.parentNode.insertBefore(form, addBtnEl.nextSibling);
  titleIn.focus();
});

// ─── Editor / Preview resizable split ────────────────────────────────────────
(function () {
  const STORAGE_KEY = 'editorPanelWidth';
  const MIN_W = 320;
  const MAX_W = 900;
  const handle = document.getElementById('editor-resize-handle');
  if (!handle) return;

  // Restore saved width
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) document.documentElement.style.setProperty('--editor-w', saved + 'px');

  let dragging = false;
  let startX = 0;
  let startW = 0;

  handle.addEventListener('mousedown', e => {
    e.preventDefault();
    dragging = true;
    startX = e.clientX;
    startW = parseInt(getComputedStyle(document.documentElement)
      .getPropertyValue('--editor-w')) || 690;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const delta = e.clientX - startX;
    const newW = Math.min(MAX_W, Math.max(MIN_W, startW + delta));
    document.documentElement.style.setProperty('--editor-w', newW + 'px');
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    const w = parseInt(getComputedStyle(document.documentElement)
      .getPropertyValue('--editor-w')) || 690;
    localStorage.setItem(STORAGE_KEY, w);
  });
})();
