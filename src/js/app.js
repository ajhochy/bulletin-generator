let _appInitialized = false;

function handlePageSizeChange(e) {
  setActiveDocTemplate(Object.assign({}, activeDocTemplate, { pageSize: e.target.value }));
  applyDocTemplate();
  apiFetch('/api/settings', 'POST', { docTemplate: activeDocTemplate }).catch(err => setStatus('Page size save failed: ' + (err.message || err), 'error'));
  schedulePreviewUpdate();
}

function handleFmtFilterInput(e) {
  applyFmtFilter(e.target.value);
}

function handleSettingsAnchorClick(e) {
  const link = e.target.closest('.stg-anchor-link');
  if (!link) return;
  e.preventDefault();
  const target = document.getElementById(link.dataset.target);
  if (target) target.scrollIntoView({ behavior: 'smooth' });
}

function handleTabClick(btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.app-page').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(btn.dataset.tab).classList.add('active');
  if (btn.dataset.tab === 'page-format') {
    renderFormatPage();
  } else if (btn.dataset.tab === 'page-templates') {
    renderTemplateGallery();
  } else {
    const flt = document.getElementById('fmt-filter');
    if (flt) flt.value = '';
  }
}

function openTabById(tabId) {
  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  if (btn) handleTabClick(btn);
}

function handleCalSettingsSave() {
  const urlsRaw = document.getElementById('cal-urls-input').value.trim();
  const urls = urlsRaw.split('\n').map(s => s.trim()).filter(Boolean);
  setCalendarSettings(urls, _calExclude);
  calEvents = null;
  calLastFetch = 0;
  apiFetch('/api/settings', 'POST', { calUrls: _calUrls }).catch(err => setStatus('Calendar URL save failed: ' + (err.message || err), 'error'));
  calFetchAll(true);
  setStatus('Calendar settings saved. Re-fetching…', 'success');
}

function handleCalExcludeSave() {
  const exclRaw = document.getElementById('cal-excl-input').value.trim();
  const excl = exclRaw.split('\n').map(s => s.trim()).filter(Boolean);
  setCalendarSettings(_calUrls, excl);
  calEvents = null;
  calLastFetch = 0;
  apiFetch('/api/settings', 'POST', { calExclude: _calExclude }).catch(err => setStatus('Exclude list save failed: ' + (err.message || err), 'error'));
  calFetchAll(true);
  setStatus('Exclude list saved. Re-fetching…', 'success');
}

function handleCalSettingsReset() {
  setCalendarSettings(null, null);
  calEvents = null;
  calLastFetch = 0;
  apiFetch('/api/settings', 'POST', { calUrls: null, calExclude: null }).catch(err => setStatus('Calendar reset failed: ' + (err.message || err), 'error'));
  calInitSettings();
  document.getElementById('cal-excl-input').value = calGetExclude().join('\n');
  calFetchAll(true);
  setStatus('Calendar settings reset to defaults.', 'success');
}

function openCalendarAddForm() {
  const existing = document.getElementById('cal-add-form');
  if (existing) { existing.remove(); return; }

  const form = document.createElement('div');
  form.id = 'cal-add-form';
  form.className = 'cal-add-form';

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

  const titleIn = document.createElement('input');
  titleIn.type = 'text';
  titleIn.placeholder = 'Event title *';
  form.appendChild(titleIn);

  const locIn = document.createElement('input');
  locIn.type = 'text';
  locIn.placeholder = 'Location (optional)';
  form.appendChild(locIn);

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
    const isoStr = isAllDay ? dateVal : `${dateVal}T${timeIn.value || '00:00'}:00`;

    if (!Array.isArray(calEvents)) calEvents = [];
    calEvents.push({
      title,
      start: { iso: isoStr, allDay: isAllDay },
      end: null,
      location: locIn.value.trim(),
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

  const addBtnEl = document.getElementById('cal-add-event-btn');
  addBtnEl.parentNode.insertBefore(form, addBtnEl.nextSibling);
  titleIn.focus();
}

function initResizableEditorSplit() {
  const STORAGE_KEY = 'editorPanelWidth';
  const MIN_W = 320;
  const MAX_W = 900;
  const handle = document.getElementById('editor-resize-handle');
  if (!handle) return;

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
}

function initAppShell() {
  if (_appInitialized) return;
  _appInitialized = true;

  document.getElementById('doc-page-size-sel').addEventListener('change', handlePageSizeChange);
  document.getElementById('fmt-filter').addEventListener('input', handleFmtFilterInput);
  document.querySelector('.stg-anchor-nav').addEventListener('click', handleSettingsAnchorClick);
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => handleTabClick(btn));
  });

  document.getElementById('cal-refresh-btn').addEventListener('click', () => calFetchAll(true));
  document.getElementById('cal-settings-save-btn').addEventListener('click', handleCalSettingsSave);
  document.getElementById('cal-excl-save-btn').addEventListener('click', handleCalExcludeSave);
  document.getElementById('cal-settings-reset-btn').addEventListener('click', handleCalSettingsReset);
  document.getElementById('cal-add-event-btn').addEventListener('click', openCalendarAddForm);

  initResizableEditorSplit();
}

async function startApp() {
  initAppShell();
  initFormattingControls();
  initStaffEditor();
  initEditor();
  initProjects();
  initUpdateControls();

  welcomeItems = [...WELCOME_ITEMS];

  const startupParams = new URLSearchParams(window.location.search);
  const requestedTab = startupParams.get('tab');
  if (requestedTab) openTabById(requestedTab);

  await restoreOnStartup();
  initPco();
  initGoogle();
  renderServingTeamSettings();
  initUpdateSection();
  calInitSettings();
  calFetchAll(false);
}

startApp().catch(err => {
  setStatus('Startup failed: ' + (err.message || err), 'error');
});
