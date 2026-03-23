// ─── Project persistence ─────────────────────────────────────────────────────
function cloneItems(list) {
  return list.map(item => {
    const cloned = {
      type:   migrateItemType(item.type || 'label'),
      title:  item.title  || '',
      detail: item.detail || '',
    };
    if (item._noBreakBefore) cloned._noBreakBefore = true;
    if (Array.isArray(item._noBreakBeforeStanzas) && item._noBreakBeforeStanzas.length > 0)
      cloned._noBreakBeforeStanzas = [...item._noBreakBeforeStanzas];
    if (item._collapsed) cloned._collapsed = true;
    if (item._fmt && typeof item._fmt === 'object') cloned._fmt = Object.assign({}, item._fmt);
    return cloned;
  });
}

function collectCurrentProjectState() {
  syncAllItems();
  return {
    svcTitle: svcTitle.value,
    svcDate: svcDate.value,
    svcChurch: svcChurch.value,
    optCover: !!optCover.checked,
    optFooter: !!optFooter.checked,
    optCal: !!optCal.checked,
    optBookletSize: optBookletSize.value,
    optAnnouncements: !!optAnnouncements.checked,
    optVolunteers:    !!optVolunteers.checked,
    optStaff:         !!optStaff.checked,
    welcomeItems: welcomeItems.slice(),
    announcements: annData.map(a => ({ title: a.title || '', body: a.body || '', url: a.url || '', _breakBefore: !!a._breakBefore, _noBreakBefore: !!a._noBreakBefore })),
    items: cloneItems(items),
    coverImageUrl: coverImageUrl || null,
    staffLogoUrl: staffLogoUrl || null,
    giveOnlineUrl: giveOnlineUrl || '',
    servingSchedule: servingSchedule || null,
    calEvents: Array.isArray(calEvents) ? calEvents.map(e => Object.assign({}, e, { start: Object.assign({}, e.start), end: e.end ? Object.assign({}, e.end) : null })) : null,
  };
}

function applyProjectState(state) {
  const safe = state || {};
  applyingProjectState = true;
  svcTitle.value = safe.svcTitle || '';
  svcDate.value = safe.svcDate || '';
  svcChurch.value = safe.svcChurch || '';
  welcomeItems = Array.isArray(safe.welcomeItems) ? safe.welcomeItems.slice() : [...WELCOME_ITEMS];
  welcomeRender();
  if (Array.isArray(safe.announcements)) {
    annData = safe.announcements.map(a => ({ title: a.title || '', body: a.body || '', url: a.url || '', _breakBefore: !!a._breakBefore, _noBreakBefore: !!a._noBreakBefore }));
    saveAnnGlobal();
  }
  annRender();
  optCover.checked = safe.optCover !== false;
  optFooter.checked = safe.optFooter === true;
  optCal.checked = safe.optCal !== false;
  optBookletSize.value = safe.optBookletSize || 'auto';
  optAnnouncements.checked = safe.optAnnouncements !== false;
  optVolunteers.checked    = safe.optVolunteers !== false;
  optStaff.checked         = safe.optStaff !== false;
  items = Array.isArray(safe.items) ? cloneItems(safe.items) : [];
  renderItemList();
  applyCoverImage(safe.coverImageUrl || null, '(saved image)');
  // Logo is a global setting — only apply from project if it has one;
  // never wipe the global logo just because this project was saved without one.
  if (safe.staffLogoUrl) {
    applyStaffLogo(safe.staffLogoUrl, '(saved logo)');
  } else if (!staffLogoUrl) {
    restoreDefaultStaffLogo();
  }
  giveOnlineUrl = safe.giveOnlineUrl || '';
  giveOnlineUrlInput.value = giveOnlineUrl;
  // Backward compat: convert old thisWeek/nextWeek format to weeks array
  if (safe.servingSchedule && !safe.servingSchedule.weeks && safe.servingSchedule.thisWeek) {
    const weeks = [safe.servingSchedule.thisWeek];
    if (safe.servingSchedule.nextWeek) weeks.push(safe.servingSchedule.nextWeek);
    servingSchedule = { weeks };
  } else {
    servingSchedule = safe.servingSchedule || null;
  }
  volRender();
  calEvents = Array.isArray(safe.calEvents) ? safe.calEvents : null;
  calLastFetch = Array.isArray(safe.calEvents) ? Date.now() : 0;
  renderCalEventEditor();
  updateDocTitle();
  applyingProjectState = false;
  renderPreview();
}

async function saveProjectToServer(project) {
  if (isServerMode() && _editorDisplayName) {
    project.updatedBy = _editorDisplayName;
  }
  if (isServerMode() && _loadedRevision !== null) {
    project._clientRevision = _loadedRevision;
  }
  try {
    const result = await apiFetch('/api/projects', 'POST', project);
    // Server returns canonical revision — update local tracking
    if (isServerMode() && result && typeof result.revision === 'number') {
      _loadedRevision = result.revision;
      const stored = projectById(project.id);
      if (stored) stored.revision = result.revision;
    }
    document.getElementById('conflict-banner').style.display = 'none';
  } catch (err) {
    if (err.message && err.message.includes('409')) {
      const banner = document.getElementById('conflict-banner');
      banner.textContent = 'This bulletin was updated by someone else.';
      banner.style.display = '';
      const reloadLink = document.createElement('a');
      reloadLink.href = '#';
      reloadLink.textContent = ' Reload latest';
      reloadLink.style.marginLeft = '0.4rem';
      reloadLink.addEventListener('click', e => { e.preventDefault(); loadProjectById(project.id); });
      banner.appendChild(reloadLink);
    } else {
      setStatus(isDesktopMode() ? 'Could not save project.' : 'Could not save project to server.', 'error');
    }
  }
}

function deleteProjectFromServer(projectId) {
  apiFetch('/api/projects/' + projectId, 'DELETE')
    .catch(() => {});
}

function projectById(id) {
  return projects.find(p => p.id === id) || null;
}

function updateProjectMeta() {
  if (activeProjectId) {
    const project = projectById(activeProjectId);
    if (project) {
      let meta = `Last saved: ${shortTimestamp(project.updatedAt) || 'just now'}`;
      if (isServerMode() && project.updatedBy) meta += ` by ${project.updatedBy}`;
      projectMeta.textContent = meta;
      bulletinTitleInput.value = project.name;
      updateSectionPreviews();
      return;
    }
  }
  projectMeta.textContent = 'Unsaved draft — click Save to create a project.';
  if (!bulletinTitleInput.value) {
    bulletinTitleInput.value = suggestedProjectName();
  }
}

function renderProjectSelect() {
  const previous = projectSelect.value;
  projectSelect.innerHTML = '';
  const draftOpt = document.createElement('option');
  draftOpt.value = DRAFT_OPTION_VALUE;
  draftOpt.textContent = 'Unsaved Draft';
  projectSelect.appendChild(draftOpt);

  projects
    .slice()
    .sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''))
    .forEach(project => {
      const opt = document.createElement('option');
      opt.value = project.id;
      const byStr = isServerMode() && project.updatedBy ? ` · ${project.updatedBy}` : '';
      opt.textContent = `${project.name} \u2022 ${shortTimestamp(project.updatedAt) || 'saved'}${byStr}`;
      projectSelect.appendChild(opt);
    });

  projectSelect.value = activeProjectId || DRAFT_OPTION_VALUE;
  if (projectSelect.value !== (activeProjectId || DRAFT_OPTION_VALUE)) {
    projectSelect.value = previous || DRAFT_OPTION_VALUE;
  }
  updateProjectMeta();
  renderFilesList(); // keep Files page in sync
}

function storeActiveProjectId() {
  try {
    if (activeProjectId) localStorage.setItem(ACTIVE_PROJECT_STORAGE_KEY, activeProjectId);
    else localStorage.removeItem(ACTIVE_PROJECT_STORAGE_KEY);
  } catch (e) {}
}

function storeDraftState(state) {
  try {
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ updatedAt: nowIso(), state }));
  } catch (e) {}
}

function autosaveProjectState() {
  if (applyingProjectState) return;
  const state = collectCurrentProjectState();
  storeDraftState(state);

  if (!activeProjectId) return;
  const project = projectById(activeProjectId);
  if (!project) return;
  project.state = state;
  project.updatedAt = nowIso();
  saveProjectToServer(project);
  renderProjectSelect();
}

function scheduleProjectPersist() {
  clearTimeout(persistTimer);
  persistTimer = setTimeout(autosaveProjectState, 350);
}

function suggestedProjectName() {
  const title = svcTitle.value.trim();
  const date = svcDate.value.trim();
  if (title && date) return `${date} - ${title}`;
  if (date) return `${date} Bulletin`;
  if (title) return title;
  return 'New Project';
}

function saveCurrentProject(saveAs = false) {
  const state = collectCurrentProjectState();
  const ts = nowIso();
  let project = activeProjectId && !saveAs ? projectById(activeProjectId) : null;

  // Get the name from the Bulletin Title field; fall back to suggested name
  const typedName = bulletinTitleInput.value.trim();
  const nameToUse = typedName || suggestedProjectName();

  if (!project) {
    project = {
      id: generateProjectId(),
      name: nameToUse,
      createdAt: ts,
      updatedAt: ts,
      createdBy: isServerMode() ? (_editorDisplayName || '') : undefined,
      state,
    };
    _loadedRevision = null;
    projects.unshift(project);
    activeProjectId = project.id;
  } else {
    // Allow renaming by editing the Bulletin Title field
    if (typedName && typedName !== project.name) project.name = typedName;
    project.state = state;
    project.updatedAt = ts;
  }

  bulletinTitleInput.value = project.name;
  storeDraftState(state);
  saveProjectToServer(project);
  storeActiveProjectId();
  renderProjectSelect();
  setStatus(`Saved "${project.name}".`, 'success');
}

// Silently saves a snapshot of the current state before a PCO import.
// Creates a new project named "<current name> — pre-import" without changing
// the active project, so the user can revert from the Browse projects list.
// If a backup with that name already exists it is updated in-place.
function savePreImportBackup() {
  if (!items.length) return; // nothing worth backing up
  const state = collectCurrentProjectState();
  const ts = nowIso();
  const currentName = (activeProjectId && projectById(activeProjectId)?.name)
                    || bulletinTitleInput.value.trim()
                    || suggestedProjectName();
  const backupName = currentName + ' — pre-import';

  // Update existing backup rather than accumulating duplicates
  const existing = projects.find(p => p.name === backupName);
  if (existing) {
    existing.state = state;
    existing.updatedAt = ts;
    saveProjectToServer(existing);
  } else {
    const project = { id: generateProjectId(), name: backupName, createdAt: ts, updatedAt: ts, state };
    projects.push(project); // append to end so it doesn't displace the active project
    saveProjectToServer(project);
  }
  renderProjectSelect();
}

function saveNewVersion() {
  const state = collectCurrentProjectState();
  const ts = nowIso();

  // Determine base name — prefer active project name, fall back to title field
  const currentName = (activeProjectId && projectById(activeProjectId)?.name)
                    || bulletinTitleInput.value.trim()
                    || suggestedProjectName();

  // Strip any trailing " vN" to get the canonical base name
  const baseName = currentName.replace(/\s+v(\d+)$/i, '').trim();

  // Find the highest version number already used for this base name
  const versionPattern = new RegExp(`^${baseName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:\\s+v(\\d+))?$`, 'i');
  let maxVersion = 1;
  projects.forEach(p => {
    const m = p.name.match(versionPattern);
    if (m) maxVersion = Math.max(maxVersion, m[1] ? parseInt(m[1], 10) : 1);
  });

  const newName = `${baseName} v${maxVersion + 1}`;
  const project = {
    id: generateProjectId(),
    name: newName,
    createdAt: ts,
    updatedAt: ts,
    state,
  };
  projects.unshift(project);
  activeProjectId = project.id;
  bulletinTitleInput.value = newName;
  storeDraftState(state);
  saveProjectToServer(project);
  storeActiveProjectId();
  renderProjectSelect();
  setStatus(`Saved new version "${newName}".`, 'success');
}

function loadDraftState() {
  try {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (!parsed || !parsed.state) return false;
    activeProjectId = '';
    applyProjectState(parsed.state);
    storeActiveProjectId();
    renderProjectSelect();
    return true;
  } catch (e) {
    return false;
  }
}

function loadProjectById(id) {
  const project = projectById(id);
  if (!project) {
    setStatus('Project not found.', 'error');
    return;
  }
  activeProjectId = project.id;
  _loadedRevision = typeof project.revision === 'number' ? project.revision : null;
  document.getElementById('stale-banner').style.display = 'none';
  document.getElementById('conflict-banner').style.display = 'none';
  applyProjectState(project.state || {});
  bulletinTitleInput.value = project.name;
  updateSectionPreviews();
  storeDraftState(collectCurrentProjectState());
  storeActiveProjectId();
  renderProjectSelect();
  setStatus(`Loaded "${project.name}".`, 'success');
  startStaleCheck();
}

function startStaleCheck() {
  if (!isServerMode()) return;
  clearInterval(_staleCheckTimer);
  _staleCheckTimer = setInterval(async () => {
    if (!activeProjectId) return;
    try {
      const data = await apiFetch('/api/projects');
      const serverProject = (data.projects || []).find(p => p.id === activeProjectId);
      if (!serverProject) return;
      // Update local copy with latest metadata
      const local = projectById(activeProjectId);
      if (local) {
        local.updatedAt = serverProject.updatedAt;
        local.updatedBy = serverProject.updatedBy;
        local.revision  = serverProject.revision;
      }
      const serverRev = serverProject.revision;
      if (typeof serverRev === 'number' && _loadedRevision !== null && serverRev > _loadedRevision) {
        const banner = document.getElementById('stale-banner');
        const by = serverProject.updatedBy ? ` by ${serverProject.updatedBy}` : '';
        const when = shortTimestamp(serverProject.updatedAt) || '';
        banner.innerHTML = `This bulletin was updated${by}${when ? ' at ' + when : ''}. <a href="#" style="color:inherit">Reload latest</a>`;
        banner.querySelector('a').addEventListener('click', e => {
          e.preventDefault();
          apiFetch('/api/projects').then(d => {
            const fresh = (d.projects || []).find(p => p.id === activeProjectId);
            if (fresh) { projects = projects.map(p => p.id === fresh.id ? fresh : p); loadProjectById(fresh.id); }
          }).catch(() => {});
        });
        banner.style.display = '';
      }
    } catch (e) { /* ignore poll errors */ }
  }, 30000);
}

function clearEditorForNewProject() {
  activeProjectId = '';
  svcTitle.value = '';
  svcDate.value = '';
  svcChurch.value = _serverSettings.churchName || ''; // inherit org-level default
  servingSchedule = null;
  volRender();
  optCover.checked = true;
  optFooter.checked = false;
  optCal.checked = true;
  optBookletSize.value = 'auto';
  optAnnouncements.checked = true;
  optVolunteers.checked    = true;
  optStaff.checked         = true;
  // Seed announcements and welcome items from the most recently dated saved project
  const datedProjects = projects
    .filter(p => p.state?.announcements && p.state?.svcDate)
    .sort((a, b) => {
      const da = new Date(a.state.svcDate), db = new Date(b.state.svcDate);
      if (!isNaN(da) && !isNaN(db)) return db - da;
      return (b.updatedAt || '').localeCompare(a.updatedAt || '');
    });
  if (datedProjects.length > 0) {
    annData = datedProjects[0].state.announcements.map(a => ({ title: a.title || '', body: a.body || '', url: a.url || '', _breakBefore: !!a._breakBefore, _noBreakBefore: !!a._noBreakBefore }));
    welcomeItems = Array.isArray(datedProjects[0].state.welcomeItems) ? datedProjects[0].state.welcomeItems.slice() : [...WELCOME_ITEMS];
    saveAnnGlobal();
    annRender();
  } else {
    welcomeItems = [...WELCOME_ITEMS];
  }
  welcomeRender();
  items = [];
  renderItemList();
  applyCoverImage(null, '');
  // Logo & Give Online URL are global settings — not cleared on new project
  updateDocTitle();
  bulletinTitleInput.value = '';
  updateSectionPreviews();
  storeActiveProjectId();
  scheduleProjectPersist();
  renderProjectSelect();
  setStatus('Started a new project draft.', 'success');
}

function deleteActiveProject() {
  if (!activeProjectId) {
    setStatus('Select a saved project to delete.', 'error');
    return;
  }
  const project = projectById(activeProjectId);
  if (!project) return;
  if (!confirm(`Delete project "${project.name}"? This cannot be undone.`)) return;
  const deletedId = activeProjectId;
  projects = projects.filter(p => p.id !== activeProjectId);
  deleteProjectFromServer(deletedId);
  clearEditorForNewProject();
  setStatus(`Deleted project "${project.name}".`, 'success');
}

async function restoreOnStartup() {
  await loadAllFromServer();
  renderSongDb();

  // Always restore global logo from server settings first
  restoreDefaultStaffLogo();
  restoreChurchName();
  restoreGiveOnlineUrl();
  restoreEditorIdentity();

  let restored = false;

  // 1. Try the project that was last active (stored in localStorage by this browser)
  const rememberedActive = localStorage.getItem(ACTIVE_PROJECT_STORAGE_KEY);
  if (rememberedActive) {
    const activeProject = projectById(rememberedActive);
    if (activeProject) {
      activeProjectId = activeProject.id;
      _loadedRevision = typeof activeProject.revision === 'number' ? activeProject.revision : null;
      applyProjectState(activeProject.state || {});
      restored = true;
      setStatus(`Loaded "${activeProject.name}".`, 'success');
      startStaleCheck();
    }
  }

  // 2. If no remembered project (fresh browser / different machine), auto-load
  //    the most recently updated server project so work is never invisible.
  if (!restored && projects.length > 0) {
    const newest = projects
      .slice()
      .sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''))[0];
    activeProjectId = newest.id;
    _loadedRevision = typeof newest.revision === 'number' ? newest.revision : null;
    applyProjectState(newest.state || {});
    restored = true;
    setStatus(`Loaded "${newest.name}".`, 'success');
    startStaleCheck();
  }

  // 3. Fall back to unsaved local draft
  if (!restored) {
    restored = loadDraftState();
    if (restored) setStatus('Restored unsaved draft.', 'success');
  }

  if (!restored) {
    welcomeRender();
    annRender();
    renderItemList();
    renderPreview();
  }

  renderProjectSelect();
}

projectSaveBtn.addEventListener('click', () => saveCurrentProject(false));
projectSaveAsBtn.addEventListener('click', saveNewVersion);
projectNewBtn.addEventListener('click', clearEditorForNewProject);
projectDeleteBtn.addEventListener('click', deleteActiveProject);
projectSelect.addEventListener('change', () => {
  if (projectSelect.value === DRAFT_OPTION_VALUE) {
    if (!loadDraftState()) {
      clearEditorForNewProject();
      setStatus('No unsaved draft found. Started a new draft.', 'success');
    } else {
      setStatus('Loaded unsaved draft.', 'success');
    }
    return;
  }
  loadProjectById(projectSelect.value);
});


// ─── Files page ───────────────────────────────────────────────────────────────
function updateBulkBar() {
  const bar      = document.getElementById('bulk-bar');
  const countEl  = document.getElementById('bulk-count');
  const selAllBtn = document.getElementById('bulk-select-all');
  if (!bar) return;
  const n = selectedProjectIds.size;
  bar.classList.toggle('visible', n > 0);
  countEl.textContent = `${n} selected`;
  if (selAllBtn) selAllBtn.textContent = (n === projects.length && projects.length > 0) ? 'Deselect All' : 'Select All';
}

function renderFilesList() {
  const list    = document.getElementById('files-list');
  const countEl = document.getElementById('files-count');
  if (!list) return;

  const sorted = projects.slice().sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''));

  if (countEl) {
    countEl.textContent = sorted.length === 0
      ? 'No saved projects yet'
      : `${sorted.length} saved project${sorted.length === 1 ? '' : 's'}`;
  }

  if (sorted.length === 0) {
    list.innerHTML = `
      <div class="files-empty">
        <div class="files-empty-title">No saved projects yet.</div>
        <div class="files-empty-sub">Use the Booklet Editor to build a bulletin, then save it as a project.</div>
        <button class="btn-sm btn-sm-primary files-empty-goto">→ Go to Booklet Editor</button>
      </div>`;
    list.querySelector('.files-empty-goto').addEventListener('click', () => {
      document.querySelector('.tab-btn[data-tab="page-editor"]').click();
    });
    return;
  }

  list.innerHTML = '';
  sorted.forEach(project => {
    const state    = project.state || {};
    const isActive = project.id === activeProjectId;
    const date     = state.svcDate  || '';
    const title    = state.svcTitle || '';
    const count    = Array.isArray(state.items) ? state.items.length : 0;
    const metaParts = [
      date && title ? `${date} · ${title}` : (date || title || null),
      `${count} item${count === 1 ? '' : 's'}`,
      `updated ${shortTimestamp(project.updatedAt) || '—'}`,
    ].filter(Boolean);

    const isSel = selectedProjectIds.has(project.id);
    const card = document.createElement('div');
    card.className = 'file-card' + (isActive ? ' file-card-active' : '') + (isSel ? ' bulk-selected' : '');
    card.innerHTML = `
      <div class="file-card-icon">☰</div>
      <div class="file-card-info">
        <div class="file-card-name">
          ${esc(project.name)}
          ${isActive ? '<span class="file-active-badge">active</span>' : ''}
        </div>
        <div class="file-card-meta">${esc(metaParts.join(' · '))}</div>
      </div>
      <div class="file-card-actions">
        <button class="btn-sm btn-sm-primary" data-fm="load"        data-id="${escAttr(project.id)}">Load</button>
        <button class="btn-sm"               data-fm="download-pdf" data-id="${escAttr(project.id)}">↓ PDF</button>
        <button class="btn-sm"               data-fm="download-json" data-id="${escAttr(project.id)}">↓ JSON</button>
        <button class="btn-sm"               data-fm="rename"       data-id="${escAttr(project.id)}">Rename</button>
        <button class="btn-sm btn-sm-danger" data-fm="delete"       data-id="${escAttr(project.id)}">Delete</button>
      </div>`;

    // Prepend checkbox for bulk selection
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'file-card-cb';
    cb.checked = isSel;
    cb.addEventListener('change', e => {
      e.stopPropagation();
      if (cb.checked) selectedProjectIds.add(project.id);
      else selectedProjectIds.delete(project.id);
      card.classList.toggle('bulk-selected', cb.checked);
      updateBulkBar();
    });
    card.prepend(cb);
    list.appendChild(card);
  });
}

function downloadProjectJson(id) {
  const project = projectById(id);
  if (!project) return;
  const blob = new Blob([JSON.stringify(project, null, 2)], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `${project.name.replace(/[^a-z0-9\-_.() ]/gi, '_')}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Server-side PDF helpers ────────────────────────────────────────────────────

async function buildPrintDocHtml(pagesHtml, title) {
  // Collect CSS from all <link rel="stylesheet"> files (the 1.07 modular structure)
  // plus any inline <style> blocks. Falls back gracefully if a fetch fails.
  const linkEls   = [...document.querySelectorAll('link[rel="stylesheet"]')];
  const fetched   = await Promise.allSettled(
    linkEls.map(el => fetch(el.href).then(r => r.ok ? r.text() : '').catch(() => ''))
  );
  const linkedCss = fetched.map(r => r.status === 'fulfilled' ? r.value : '').join('\n');
  const inlineCss = [...document.querySelectorAll('style')].map(s => s.textContent).join('\n');
  const css       = linkedCss + '\n' + inlineCss;

  const safeTitle = escAttr(title || 'Bulletin');
  const { w, h } = getPageDims();
  return `<!DOCTYPE html>
<html lang="en" style="--doc-page-w:${w}in;--doc-page-h:${h}in;"><head>
<meta charset="UTF-8">
<title>${safeTitle}</title>
<style>
${css}
/* Headless PDF overrides — placed after embedded CSS so page-size variables win */
:root { --doc-page-w: ${w}in; --doc-page-h: ${h}in; }
@page { size: ${w}in ${h}in; margin: 0; }
body { margin: 0; padding: 0; background: white !important; display: block !important; }
header, aside, .tab-bar, .pg-break-ctrl,
.preview-page-num, .item-insert-zone { display: none !important; }
.booklet-page {
  margin: 0 !important; box-shadow: none !important;
  /* Lock each booklet-page to exactly one PDF page.
     box-sizing: border-box makes height 8.5in include the padding,
     overflow: hidden prevents minor headless font-metric differences
     from spilling content onto a new auto-generated PDF page. */
  height: var(--doc-page-h) !important; box-sizing: border-box !important;
  overflow: hidden !important;
  break-after: page; page-break-after: always;
}
.booklet-page:last-child { break-after: avoid; page-break-after: avoid; }
</style>
</head>
<body>
${pagesHtml}
</body></html>`;
}

async function inlineExternalImages(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  const imgs = [...doc.querySelectorAll('img')].filter(img =>
    img.src && (img.src.startsWith('http://') || img.src.startsWith('https://'))
  );
  await Promise.allSettled(imgs.map(async img => {
    try {
      const resp = await fetch(img.src);
      if (!resp.ok) return;
      const blob = await resp.blob();
      const dataUrl = await new Promise((res, rej) => {
        const reader = new FileReader();
        reader.onload  = () => res(reader.result);
        reader.onerror = rej;
        reader.readAsDataURL(blob);
      });
      img.src = dataUrl;
    } catch (e) { /* keep original src if fetch fails */ }
  }));
  return doc.documentElement.outerHTML;
}

async function generateAndDownloadPdf(pagesHtml, filename) {
  setStatus('Generating PDF…', 'info');
  let html = await buildPrintDocHtml(pagesHtml, filename.replace(/\.pdf$/i, ''));
  try { html = await inlineExternalImages(html); } catch (e) { /* proceed anyway */ }

  let resp;
  try {
    resp = await fetch('/api/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ html, filename, pageWidth: getPageDims().w, pageHeight: getPageDims().h }),
    });
  } catch (e) {
    setStatus('PDF generation failed — network error.', 'error');
    return;
  }

  if (!resp.ok) {
    let msg = 'PDF generation failed.';
    try { const err = await resp.json(); msg = err.error || msg; } catch (e) {}
    setStatus(msg, 'error');
    return;
  }

  const blob = await resp.blob();
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  setStatus('PDF downloaded!', 'success');
}

async function downloadProjectAsPdf(id) {
  const project = projectById(id);
  if (!project) return;
  const state = project.state || {};

  // ── Snapshot current editor globals ────────────────────────────────────────
  const prevTitle       = svcTitle.value;
  const prevDate        = svcDate.value;
  const prevChurch      = svcChurch.value;
  const prevCover         = optCover.checked;
  const prevFooter        = optFooter.checked;
  const prevCal           = optCal.checked;
  const prevBookletSize   = optBookletSize.value;
  const prevAnnouncements = optAnnouncements.checked;
  const prevVolunteers    = optVolunteers.checked;
  const prevStaff         = optStaff.checked;
  const prevItems       = items.slice();
  const prevAnnData     = annData.map(a => ({...a}));

  // Suppress autosave during the swap
  applyingProjectState = true;

  // ── Apply target project state to the variables renderPreview() reads ──────
  svcTitle.value       = state.svcTitle  || '';
  svcDate.value        = state.svcDate   || '';
  svcChurch.value      = state.svcChurch || '';
  optCover.checked         = !!state.optCover;
  optFooter.checked        = !!state.optFooter;
  optCal.checked           = !!state.optCal;
  optBookletSize.value     = state.optBookletSize || 'auto';
  optAnnouncements.checked = state.optAnnouncements !== false;
  optVolunteers.checked    = state.optVolunteers !== false;
  optStaff.checked         = state.optStaff !== false;
  items = Array.isArray(state.items) ? cloneItems(state.items) : [];
  annData = Array.isArray(state.announcements)
    ? state.announcements.map(a => ({ title: a.title || '', body: a.body || '', url: a.url || '', _breakBefore: !!a._breakBefore, _noBreakBefore: !!a._noBreakBefore }))
    : annData;

  // Render into previewPane (fully synchronous)
  renderPreview();
  const pageEls   = [...previewPane.querySelectorAll('.booklet-page')];
  const pagesHtml = pageEls.map(el => el.outerHTML).join('\n');

  // ── Restore original editor state ──────────────────────────────────────────
  svcTitle.value       = prevTitle;
  svcDate.value        = prevDate;
  svcChurch.value      = prevChurch;
  optCover.checked         = prevCover;
  optFooter.checked        = prevFooter;
  optCal.checked           = prevCal;
  optBookletSize.value     = prevBookletSize;
  optAnnouncements.checked = prevAnnouncements;
  optVolunteers.checked    = prevVolunteers;
  optStaff.checked         = prevStaff;
  items = prevItems;
  annData = prevAnnData;
  renderPreview();
  applyingProjectState = false;

  if (!pagesHtml) {
    setStatus('Nothing to print for this project.', 'error');
    return;
  }

  const sizeTag  = (activeDocTemplate.pageSize || '5.5x8.5').replace('x', 'x');
  const filename = (project.name || 'Bulletin') + ' - ' + sizeTag + '.pdf';
  await generateAndDownloadPdf(pagesHtml, filename);
}

document.getElementById('files-list').addEventListener('click', e => {
  const btn = e.target.closest('[data-fm]');
  if (!btn) return;
  const action = btn.dataset.fm;
  const id     = btn.dataset.id;

  if (action === 'load') {
    loadProjectById(id);
    document.querySelector('.tab-btn[data-tab="page-editor"]').click();
  } else if (action === 'download-pdf') {
    downloadProjectAsPdf(id);
  } else if (action === 'download-json') {
    downloadProjectJson(id);
  } else if (action === 'rename') {
    const proj = projectById(id);
    if (!proj) return;
    const newName = prompt('Rename project:', proj.name);
    if (!newName || !newName.trim()) return;
    proj.name      = newName.trim();
    proj.updatedAt = nowIso();
    saveProjectToServer(proj);
    renderProjectSelect();
    setStatus(`Renamed to "${proj.name}".`, 'success');
  } else if (action === 'delete') {
    const proj = projectById(id);
    if (!proj) return;
    if (!confirm(`Delete "${proj.name}"? This cannot be undone.`)) return;
    const projName = proj.name;
    projects = projects.filter(p => p.id !== id);
    deleteProjectFromServer(id);
    if (activeProjectId === id) {
      activeProjectId = '';
      storeActiveProjectId();
      clearEditorForNewProject();
    }
    renderProjectSelect();
    setStatus(`Deleted "${projName}".`, 'success');
  }
});

// ─── Bulk action bar handlers ─────────────────────────────────────────────────
document.getElementById('bulk-select-all').addEventListener('click', () => {
  if (selectedProjectIds.size === projects.length && projects.length > 0) {
    selectedProjectIds.clear();
  } else {
    projects.forEach(p => selectedProjectIds.add(p.id));
  }
  renderFilesList();
  updateBulkBar();
});

document.getElementById('bulk-download-json').addEventListener('click', () => {
  const ids = [...selectedProjectIds];
  ids.forEach((id, i) => setTimeout(() => downloadProjectJson(id), i * 150));
  setStatus(`Downloading ${ids.length} project${ids.length !== 1 ? 's' : ''}…`, 'info');
});

document.getElementById('bulk-download-pdf').addEventListener('click', async function() {
  const ids = [...selectedProjectIds];
  const btn = this;
  btn.disabled = true;
  btn.textContent = `↓ 0 / ${ids.length}`;
  for (let i = 0; i < ids.length; i++) {
    btn.textContent = `↓ ${i + 1} / ${ids.length}`;
    await downloadProjectAsPdf(ids[i]);
  }
  btn.disabled = false;
  btn.textContent = '↓ Download PDFs';
  setStatus(`Downloaded ${ids.length} PDF${ids.length !== 1 ? 's' : ''}.`, 'success');
});

document.getElementById('bulk-delete').addEventListener('click', () => {
  const ids = [...selectedProjectIds];
  const names = ids.map(id => projectById(id)?.name).filter(Boolean);
  if (!confirm(`Delete ${ids.length} project${ids.length !== 1 ? 's' : ''}?\n\n${names.join('\n')}\n\nThis cannot be undone.`)) return;
  let activeCleared = false;
  ids.forEach(id => {
    projects = projects.filter(p => p.id !== id);
    deleteProjectFromServer(id);
    if (activeProjectId === id) activeCleared = true;
  });
  selectedProjectIds.clear();
  if (activeCleared) {
    activeProjectId = '';
    storeActiveProjectId();
    clearEditorForNewProject();
  }
  renderProjectSelect();
  setStatus(`Deleted ${ids.length} project${ids.length !== 1 ? 's' : ''}.`, 'success');
});

document.getElementById('bulk-clear').addEventListener('click', () => {
  selectedProjectIds.clear();
  renderFilesList();
  updateBulkBar();
});

document.getElementById('files-new-btn').addEventListener('click', () => {
  clearEditorForNewProject();
  document.querySelector('.tab-btn[data-tab="page-editor"]').click();
});

document.getElementById('files-import-input').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    try {
      const data    = JSON.parse(ev.target.result);
      const imports = Array.isArray(data) ? data : [data];
      let count = 0;
      imports.forEach(proj => {
        if (!proj.id || !proj.name || !proj.state) return;
        const idx = projects.findIndex(p => p.id === proj.id);
        if (idx >= 0) projects[idx] = proj; else projects.unshift(proj);
        saveProjectToServer(proj);
        count++;
      });
      if (count > 0) {
        renderProjectSelect();
        setStatus(`Imported ${count} project${count === 1 ? '' : 's'}.`, 'success');
      } else {
        setStatus('No valid projects found in file.', 'error');
      }
    } catch (_) {
      setStatus('Could not parse JSON file.', 'error');
    }
  };
  reader.readAsText(file);
  e.target.value = '';
});

document.getElementById('project-browse-btn').addEventListener('click', () => {
  document.querySelector('.tab-btn[data-tab="page-files"]').click();
});

