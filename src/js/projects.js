// ─── Read-only mode ───────────────────────────────────────────────────────────
// Entered when a non-owner opens a workspace project in server mode.
// Blocks autosave; shows a non-intrusive banner with a "Duplicate" shortcut.

function enterReadOnlyMode(ownerName) {
  _isReadOnly = true;
  const banner = document.getElementById('readonly-banner');
  if (!banner) return;

  const nameLabel = ownerName ? `${esc(ownerName)}'s` : 'this';
  banner.innerHTML =
    `<span>Viewing ${nameLabel} bulletin · changes won't save · </span>` +
    `<button class="btn btn-xs btn-primary btn-sm ml-1" id="readonly-duplicate-btn">Duplicate to edit your own copy</button>`;
  banner.style.display = '';

  const dupBtn = document.getElementById('readonly-duplicate-btn');
  if (dupBtn) {
    dupBtn.addEventListener('click', () => _duplicateProjectForCurrentUser());
  }
}

function exitReadOnlyMode() {
  _isReadOnly = false;
  const banner = document.getElementById('readonly-banner');
  if (banner) banner.style.display = 'none';
}

async function _duplicateProjectForCurrentUser() {
  const project = projectById(activeProjectId);
  if (!project) return;
  const ts = nowIso();
  const copyName = `${project.name || 'Bulletin'} — copy`;
  const copyProject = {
    id: generateProjectId(),
    name: copyName,
    createdAt: ts,
    updatedAt: ts,
    visibility: 'private',
    state: project.state || collectCurrentProjectState(),
  };
  projects.unshift(copyProject);
  activeProjectId = copyProject.id;
  bulletinTitleInput.value = copyName;
  exitReadOnlyMode();
  _stopPresenceHeartbeat();
  storeActiveProjectId();
  saveProjectToServer(copyProject);
  renderProjectSelect();
  setStatus(`Saved as "${copyName}".`, 'success');
}

// ─── Presence heartbeat ───────────────────────────────────────────────────────
// Best-effort — all errors are silently swallowed.
// Desktop mode: no-op.

function _startPresenceHeartbeat(projectId) {
  // Guard: server mode needs heartbeat through /api/presence; Electron mode needs
  // it through sdPostPresenceHeartbeat; desktop (non-server, non-electron) skips.
  const _electronMode = typeof isElectronMode === 'function' && isElectronMode();
  if (!isServerMode() && !_electronMode) return;
  _stopPresenceHeartbeat(); // clear any existing timer

  const _heartbeat = () => {
    if (_electronMode) {
      // Electron path: use supabase-data.js with session-supplied userId/workspaceId
      const currentUser = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
      const session = (typeof getSession === 'function') ? getSession() : null;
      const userId = currentUser?.id || currentUser?.user_id || null;
      // workspace_id: prefer the server-resolved value surfaced by /api/me onto
      // getCurrentUser() (it is NOT in the JWT metadata — workspace membership
      // lives in the DB). Fall back to metadata for safety.
      const workspaceId = currentUser?.workspace_id
        || currentUser?.user_metadata?.workspace_id
        || currentUser?.app_metadata?.workspace_id
        || session?.user?.user_metadata?.workspace_id
        || session?.user?.app_metadata?.workspace_id
        || null;
      sdPostPresenceHeartbeat(projectId, { userId, workspaceId }).catch(() => {}); // best-effort
    } else {
      apiFetch('/api/presence/heartbeat', 'POST', { project_id: projectId })
        .catch(() => {}); // best-effort
    }
  };

  _heartbeat(); // send immediately on project open
  _presenceTimer = setInterval(_heartbeat, 30000);

  // Poll once on project open to check if someone else is actively editing
  const _getPresence = _electronMode
    ? (() => {
        // Electron path: 90-second TTL filter applied client-side (limitation from 277-C)
        const cutoff = new Date(Date.now() - 90000).toISOString();
        return sdGetPresence(projectId).then(rows =>
          (rows || []).filter(p => p.last_seen_at && p.last_seen_at >= cutoff)
        );
      })
    : (() => apiFetch(`/api/presence?project_id=${encodeURIComponent(projectId)}`).then(data =>
        Array.isArray(data) ? data : (data?.presences || [])
      ));

  _getPresence()
    .then(presences => {
      const currentUser = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
      const currentUserId = currentUser?.id || currentUser?.user_id || null;
      const others = presences.filter(p => {
        const uid = p.user_id || p.userId;
        return currentUserId ? String(uid) !== String(currentUserId) : true;
      });
      if (others.length > 0) {
        const who = others[0].display_name || others[0].email || 'Someone';
        _showPresenceBadge(who);
      } else {
        _hidePresenceBadge();
      }
    })
    .catch(() => {}); // best-effort
}

function _stopPresenceHeartbeat() {
  if (_presenceTimer) {
    clearInterval(_presenceTimer);
    _presenceTimer = null;
  }
  const _electronMode = typeof isElectronMode === 'function' && isElectronMode();
  if (_electronMode) {
    // Electron path: delete presence via Supabase with session-supplied userId
    const currentUser = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
    const userId = currentUser?.id || currentUser?.user_id || null;
    sdDeletePresence({ userId }).catch(() => {}); // best-effort
  } else if (isServerMode()) {
    apiFetch('/api/presence', 'DELETE').catch(() => {}); // best-effort
  }
  _hidePresenceBadge();
}

function _showPresenceBadge(userName) {
  const badge = document.getElementById('presence-badge');
  if (!badge) return;
  badge.textContent = `● ${userName} is editing`;
  badge.style.display = '';
}

function _hidePresenceBadge() {
  const badge = document.getElementById('presence-badge');
  if (badge) badge.style.display = 'none';
}

// ─── Project persistence ─────────────────────────────────────────────────────
function cloneItems(list) {
  return cloneItemsDataCore(list);
}

// ── Persisted layout fields (all sections) ────────────────────────────────────
// When adding a new per-section layout flag, update THREE locations in this file:
//   1. collectCurrentProjectState()   — write flag into the saved object
//   2. applyProjectState()            — read it back on project load / project switch
//   3. applyProjectStateForExport()   — read it back before PDF generation
//
// Current persisted layout state:
//   items[i]._noBreakBefore               OOW: suppress auto break before item
//   items[i]._noBreakBeforeStanzas[]      OOW: suppress auto break before specific stanzas
//   items[i]._forceBreakBeforeParagraph[] OOW: explicit break before a paragraph
//   items[i]._noBreakBeforeParagraph[]    OOW: suppress auto break before a paragraph
//   announcements[i]._breakBefore         Ann: explicit "Break before this card"
//   announcements[i]._noBreakBefore       Ann: suppress auto break before this card
//   servingSchedule.weeks[i]._breakBefore Serving: "Start this week on a new page"
//   servingSchedule.weeks[i].teams[j] with type:'page-break'  Serving: intra-week team break
//   breakBeforeCalendar                   Calendar: "Start calendar on a new page"
//   calBreakBeforeDates[]                 Calendar: forced breaks before specific day groups
//   breakBeforeStaff                      Staff: "Start staff page on a new page"
//   bottomMerge.{oow,serving,calendar,staff}  All: merge section onto previous page
// ─────────────────────────────────────────────────────────────────────────────
function collectCurrentProjectState() {
  syncAllItems();
  return {
    svcTitle: svcTitle.value,
    svcDate: svcDate.value,
    svcChurch: svcChurch.value,
    optCover: !!optCover.checked,
    optWelcome: !!optWelcome.checked,
    optFooter: !!optFooter.checked,
    optCal: !!optCal.checked,
    optBookletSize: optBookletSize.value,
    optAnnouncements: !!optAnnouncements.checked,
    optVolunteers:    !!optVolunteers.checked,
    optVolunteerRoles:!!optVolunteerRoles.checked,
    optStaff:         !!optStaff.checked,
    welcomeHeading: welcomeHeading || '',
    welcomeItems: welcomeItems.slice(),
    announcements: annData.map(a => ({ title: a.title || '', body: a.body || '', url: a.url || '', _breakBefore: !!a._breakBefore, _noBreakBefore: !!a._noBreakBefore })),
    items: cloneItems(items),
    coverImageUrl: coverImageUrl || null,
    staffLogoUrl: staffLogoUrl || null,
    giveOnlineUrl: giveOnlineUrl || '',
    servingSchedule: servingSchedule || null,
    calEvents: Array.isArray(calEvents) ? calEvents.map(e => Object.assign({}, e, { start: Object.assign({}, e.start), end: e.end ? Object.assign({}, e.end) : null })) : null,
    pcoIgnore: pcoIgnore.slice(),
    pcoLastImportedTitles: pcoLastImportedTitles.slice(),
    volTeamFilter: Object.assign({}, volTeamFilter),
    breakBeforeCalendar: breakBeforeCalendar,
    breakBeforeStaff:    breakBeforeStaff,
    calBreakBeforeDates: calBreakBeforeDates.slice(),
    bottomMerge: Object.assign({}, bottomMerge),
    activeDocTemplate: JSON.parse(JSON.stringify(activeDocTemplate || { pageSize: '5.5x8.5', cssVars: {}, typeFormats: {}, zones: [] })),
  };
}

function applyProjectState(state) {
  const safe = state || {};
  applyingProjectState = true;
  svcTitle.value = safe.svcTitle || '';
  svcDate.value = safe.svcDate || '';
  svcChurch.value = safe.svcChurch || '';
  welcomeHeading = typeof safe.welcomeHeading === 'string' ? safe.welcomeHeading : '';
  welcomeHeadingInput.value = welcomeHeading;
  welcomeItems = Array.isArray(safe.welcomeItems) ? safe.welcomeItems.slice() : [...WELCOME_ITEMS];
  welcomeRender();
  if (Array.isArray(safe.announcements)) {
    setAnnData(safe.announcements.map(a => ({ title: a.title || '', body: a.body || '', url: a.url || '', _breakBefore: !!a._breakBefore, _noBreakBefore: !!a._noBreakBefore })));
    saveAnnGlobal();
  }
  annRender();
  optCover.checked = safe.optCover !== false;
  optWelcome.checked = safe.optWelcome !== false;
  optFooter.checked = safe.optFooter === true;
  optCal.checked = safe.optCal !== false;
  optBookletSize.value = safe.optBookletSize || 'auto';
  optAnnouncements.checked = safe.optAnnouncements !== false;
  optVolunteers.checked    = safe.optVolunteers !== false;
  optVolunteerRoles.checked= safe.optVolunteerRoles !== false;
  optStaff.checked         = safe.optStaff !== false;
  setItems(Array.isArray(safe.items) ? cloneItems(safe.items) : []);
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
  pcoIgnore = Array.isArray(safe.pcoIgnore) ? safe.pcoIgnore.slice() : [];
  pcoLastImportedTitles = Array.isArray(safe.pcoLastImportedTitles) ? safe.pcoLastImportedTitles.slice() : [];
  volTeamFilter = (typeof safe.volTeamFilter === 'object' && safe.volTeamFilter) ? Object.assign({}, safe.volTeamFilter) : {};
  breakBeforeCalendar = !!safe.breakBeforeCalendar;
  breakBeforeStaff    = !!safe.breakBeforeStaff;
  calBreakBeforeDates = Array.isArray(safe.calBreakBeforeDates) ? safe.calBreakBeforeDates.slice() : [];
  const bm = (safe.bottomMerge && typeof safe.bottomMerge === 'object') ? safe.bottomMerge : {};
  bottomMerge.oow      = !!bm.oow;
  bottomMerge.serving  = !!bm.serving;
  bottomMerge.calendar = !!bm.calendar;
  bottomMerge.staff    = !!bm.staff;
  setActiveDocTemplate(safe.activeDocTemplate || activeDocTemplate);
  applyDocTemplate();
  if (typeof renderPcoIgnoreChips === 'function') renderPcoIgnoreChips();
  updateDocTitle();
  applyingProjectState = false;
  renderPreview();
}

async function saveProjectToServer(project) {
  // Guard against concurrent saves: if a save is already in-flight, queue this
  // one to fire after it completes.
  if (_saveInFlight) {
    _pendingSaveProject = project;
    return;
  }
  _saveInFlight = true;
  try {
    const _electronMode = typeof isElectronMode === 'function' && isElectronMode();
    if (_electronMode) {
      // Electron path: write directly to Supabase via supabase-data.js.
      // TODO(#216): revision snapshot handled by DB trigger (not implemented
      // here — see issue #216 which will add a DB trigger for BOTH server- and
      // renderer-writes).  Until #216 lands, Electron-mode saves do NOT create
      // project_revisions snapshots.
      const currentUser = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
      const session = (typeof getSession === 'function') ? getSession() : null;
      const userId = currentUser?.id || currentUser?.user_id || null;
      const workspaceId = currentUser?.workspace_id
        || currentUser?.user_metadata?.workspace_id
        || currentUser?.app_metadata?.workspace_id
        || session?.user?.user_metadata?.workspace_id
        || session?.user?.app_metadata?.workspace_id
        || null;
      const payload = Object.assign({}, project, {
        owner_user_id: project.owner_user_id || userId,
        workspace_id: project.workspace_id || workspaceId,
      });
      await sdSaveProject(payload);
    } else {
      // Server/browser path: unchanged
      const requestProject = buildProjectSaveRequestCore(project, {
        isServerMode: isServerMode(),
        editorDisplayName: _editorDisplayName,
      });
      await apiFetch('/api/projects', 'POST', requestProject);
    }
  } catch (err) {
    const failure = deriveProjectSaveFailureCore({
      errorStatus: err.status,
      isDesktopMode: isDesktopMode(),
    });
    setStatus(failure.message, 'error');
  } finally {
    _saveInFlight = false;
    // If a save was deferred while this one was in-flight, fire it now with
    // the latest queued full project object.
    if (_pendingSaveProject) {
      const queuedProject = _pendingSaveProject;
      _pendingSaveProject = null;
      saveProjectToServer(queuedProject);
    }
  }
}

function deleteProjectFromServer(projectId) {
  const _electronMode = typeof isElectronMode === 'function' && isElectronMode();
  if (_electronMode) {
    sdDeleteProject(projectId).catch(err => setStatus('Delete failed: ' + (err.message || err), 'error'));
  } else {
    apiFetch('/api/projects/' + projectId, 'DELETE')
      .catch(err => setStatus('Delete failed: ' + (err.message || err), 'error'));
  }
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

  // Non-owners viewing a workspace project must not trigger autosave
  if (_isReadOnly) return;

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

async function loadProjectById(id) {
  const meta = projectById(id);
  if (!meta) {
    setStatus('Project not found.', 'error');
    return;
  }

  // Stop any in-progress presence for the previous project
  _stopPresenceHeartbeat();
  exitReadOnlyMode();

  // Fetch full state on demand — the list only contains metadata now.
  let project = meta;
  if (!project.state) {
    try {
      const _electronMode = typeof isElectronMode === 'function' && isElectronMode();
      if (_electronMode) {
        project = await sdGetProject(id);
        // supabase-data returns rows where state is in the `state` column
        // (same shape as the server's /api/projects/:id response.project)
      } else {
        const res = await apiFetch('/api/projects/' + id);
        project = res.project || meta;
      }
    } catch (e) {
      setStatus('Could not load project.', 'error');
      return;
    }
  }

  activeProjectId = project.id;
  applyProjectState(project.state || {});
  bulletinTitleInput.value = project.name;
  updateSectionPreviews();
  storeDraftState(collectCurrentProjectState());
  storeActiveProjectId();
  renderProjectSelect();
  setStatus(`Loaded "${project.name}".`, 'success');

  // Determine read-only mode: non-owner viewing a workspace project
  // Also applies in Electron mode (same ownership semantics via RLS).
  const _emForReadOnly = typeof isElectronMode === 'function' && isElectronMode();
  if ((isServerMode() || _emForReadOnly) && project.owner_user_id) {
    const currentUser = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
    const currentUserId = currentUser?.id || currentUser?.user_id || null;
    if (currentUserId && String(project.owner_user_id) !== String(currentUserId)) {
      const ownerName = project.owner_display_name || project.owner_email || null;
      enterReadOnlyMode(ownerName);
    }
  }

  // Start presence heartbeat (best-effort, desktop skips)
  _startPresenceHeartbeat(project.id);
}

function clearEditorForNewProject() {
  // Stop presence tracking and read-only mode for the project being left
  _stopPresenceHeartbeat();
  exitReadOnlyMode();

  activeProjectId = '';
  svcTitle.value = '';
  svcDate.value = '';
  svcChurch.value = _serverSettings.churchName || ''; // inherit org-level default
  servingSchedule = null;
  volTeamFilter = {};
  volRender();
  optCover.checked = true;
  optWelcome.checked = true;
  optFooter.checked = false;
  optCal.checked = true;
  optBookletSize.value = 'auto';
  optAnnouncements.checked = true;
  optVolunteers.checked    = true;
  optVolunteerRoles.checked= true;
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
    setAnnData(datedProjects[0].state.announcements.map(a => ({ title: a.title || '', body: a.body || '', url: a.url || '', _breakBefore: !!a._breakBefore, _noBreakBefore: !!a._noBreakBefore })));
    welcomeHeading = typeof datedProjects[0].state.welcomeHeading === 'string' ? datedProjects[0].state.welcomeHeading : '';
    welcomeItems = Array.isArray(datedProjects[0].state.welcomeItems) ? datedProjects[0].state.welcomeItems.slice() : [...WELCOME_ITEMS];
    saveAnnGlobal();
    annRender();
  } else {
    welcomeHeading = '';
    welcomeItems = [...WELCOME_ITEMS];
  }
  welcomeHeadingInput.value = welcomeHeading;
  welcomeRender();
  setItems([]);
  pcoIgnore = [];
  pcoLastImportedTitles = [];
  if (typeof renderPcoIgnoreChips === 'function') renderPcoIgnoreChips();
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
  renderStaffEditor(); // re-render now that staffData is loaded from server
  if (typeof vrRender === 'function') vrRender(); // re-render volunteer-role cards now that vrData is loaded

  // Always restore global logo from server settings first
  restoreDefaultStaffLogo();
  restoreChurchName();
  restoreGiveOnlineUrl();
  restoreEditorIdentity();

  let restored = false;

  const rememberedId = (() => {
    try { return localStorage.getItem(ACTIVE_PROJECT_STORAGE_KEY) || ''; } catch (_) { return ''; }
  })();

  const decision = deriveStartupRestoreCore({ rememberedId, projects, isServerMode: isServerMode() });

  if (decision.action === 'load' || decision.action === 'load-newest') {
    let project = decision.project;
    // Fetch full state on demand — the list only contains metadata now.
    if (!project.state) {
      try {
        const _electronModeStartup = typeof isElectronMode === 'function' && isElectronMode();
        if (_electronModeStartup) {
          project = await sdGetProject(project.id);
        } else {
          const res = await apiFetch('/api/projects/' + project.id);
          project = res.project || project;
        }
      } catch (_) { /* fall through with empty state */ }
    }
    activeProjectId = project.id;
    applyProjectState(project.state || {});
    bulletinTitleInput.value = project.name;
    restored = true;
    setStatus(`Loaded "${project.name}".`, 'success');
    storeActiveProjectId();
    // Determine read-only mode for loaded project (server + Electron share ownership model)
    const _emStartupReadOnly = typeof isElectronMode === 'function' && isElectronMode();
    if ((isServerMode() || _emStartupReadOnly) && project.owner_user_id) {
      const currentUser = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
      const currentUserId = currentUser?.id || currentUser?.user_id || null;
      if (currentUserId && String(project.owner_user_id) !== String(currentUserId)) {
        const ownerName = project.owner_display_name || project.owner_email || null;
        enterReadOnlyMode(ownerName);
      }
    }
    _startPresenceHeartbeat(project.id);
  } else if (decision.action === 'blank' && decision.reason === 'not-found') {
    try { localStorage.removeItem(ACTIVE_PROJECT_STORAGE_KEY); } catch (_) {}
    setStatus(decision.statusMessage, 'info');
  }

  // Fall back to unsaved local draft if no project was restored
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
  // Startup (incl. async server load + project/draft restore) is complete.
  // Exposed so automated tests can wait for a stable state before editing,
  // avoiding a race where the restore re-applies state over fresh edits.
  if (typeof window !== 'undefined') window.__BG_READY__ = true;
}

let _projectsInitialized = false;


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

// ─── Files tab auto-refresh ───────────────────────────────────────────────────
let _filesRefreshTimer = null;

function startFilesAutoRefresh() {
  stopFilesAutoRefresh();
  const _electronMode = typeof isElectronMode === 'function' && isElectronMode();
  if (!isServerMode() && !_electronMode) return;
  _filesRefreshTimer = setInterval(async () => {
    try {
      let freshProjects;
      if (_electronMode) {
        freshProjects = await sdGetProjects();
        if (typeof attachOwnerLabels === 'function') freshProjects = attachOwnerLabels(freshProjects);
      } else {
        const res = await apiFetch('/api/projects');
        freshProjects = res.projects || [];
      }
      const prev = projects.slice();
      setProjects(freshProjects);
      renderProjectSelect();
      renderFilesList();

      // Toast for any project newly handed off to the current user.
      const currentUser = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
      const currentUserId = currentUser?.id || currentUser?.user_id || null;
      if (currentUserId) {
        freshProjects.forEach(p => {
          const updatedMs = p.updatedAt ? new Date(p.updatedAt).getTime() : 0;
          const updatedByMe = !p.updated_by_user_id || String(p.updated_by_user_id) === String(currentUserId);
          const isNewToYou = String(p.owner_user_id) === String(currentUserId)
                             && !updatedByMe
                             && (Date.now() - updatedMs) < 600_000;
          if (isNewToYou) {
            const prevEntry = prev.find(old => old.id === p.id);
            const wasAlreadyMine = prevEntry && String(prevEntry.owner_user_id) === String(currentUserId);
            if (!wasAlreadyMine) {
              setStatus(`"${p.name}" was handed off to you.`, 'success');
            }
          }
        });
      }
    } catch (_) { /* silent */ }
  }, 30_000);
}

function stopFilesAutoRefresh() {
  if (_filesRefreshTimer) { clearInterval(_filesRefreshTimer); _filesRefreshTimer = null; }
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
      <div class="files-empty flex flex-col items-center justify-center py-16 text-center">
        <div class="files-empty-title text-lg font-semibold mb-2">No saved projects yet.</div>
        <div class="files-empty-sub text-sm text-base-content/60 mb-4">Use the Booklet Editor to build a bulletin, then save it as a project.</div>
        <button class="btn btn-sm btn-primary files-empty-goto">→ Go to Booklet Editor</button>
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
    // Owner display: prefer display_name, fall back to first part of email.
    const ownerRaw = project.owner_display_name || project.owner_email || '';
    const ownerLabel = ownerRaw.includes('@') ? ownerRaw.split('@')[0] : ownerRaw;
    const updatedLabel = `updated ${shortTimestamp(project.updatedAt) || '—'}`;
    const metaParts = [
      date && title ? `${date} · ${title}` : (date || title || null),
      ownerLabel ? ownerLabel : null,
      updatedLabel,
    ].filter(Boolean);

    const currentUser = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
    const currentUserId = currentUser?.id || currentUser?.user_id || null;
    const isOwner = !isServerMode() || !project.owner_user_id ||
                    (currentUserId && String(project.owner_user_id) === String(currentUserId));
    // "New to you" badge: I own it, but someone else last modified it
    // (set by the transfer), and it was within the last 10 minutes.
    const updatedMs = project.updatedAt ? new Date(project.updatedAt).getTime() : 0;
    const updatedByMe = !project.updated_by_user_id
                        || String(project.updated_by_user_id) === String(currentUserId);
    const isNewToYou = isOwner && currentUserId
                       && !updatedByMe
                       && (Date.now() - updatedMs) < 600_000;
    const isSel = selectedProjectIds.has(project.id);
    const card = document.createElement('div');
    card.className = 'file-card flex items-center gap-3 border border-base-300 rounded-lg mb-2 px-3 py-2 bg-base-100 hover:bg-base-200 cursor-pointer'
      + (isActive ? ' file-card-active ring-2 ring-primary' : '')
      + (isSel ? ' bulk-selected bg-base-200' : '');
    card.innerHTML = `
      <div class="file-card-icon text-base-content/30 text-lg">☰</div>
      <div class="file-card-info flex-1 min-w-0">
        <div class="file-card-name font-medium text-sm truncate">
          ${esc(project.name)}
          ${isActive ? '<span class="file-active-badge badge badge-sm badge-primary ml-1">active</span>' : ''}
          ${isNewToYou ? '<span class="badge badge-sm badge-warning ml-1">handed off to you ↗</span>' : ''}
        </div>
        <div class="file-card-meta text-xs text-base-content/50 truncate">${esc(metaParts.join(' · '))}</div>
      </div>
      <div class="file-card-actions flex gap-1 shrink-0">
        <button class="btn btn-xs btn-primary" data-fm="load"         data-id="${escAttr(project.id)}">Load</button>
        <button class="btn btn-xs btn-ghost"   data-fm="download-pdf" data-id="${escAttr(project.id)}">↓ PDF</button>
        <button class="btn btn-xs btn-ghost"   data-fm="download-json" data-id="${escAttr(project.id)}">↓ JSON</button>
        <button class="btn btn-xs btn-ghost"   data-fm="rename"       data-id="${escAttr(project.id)}">Rename</button>
        ${isOwner ? `<button class="btn btn-xs btn-ghost" data-fm="handoff" data-id="${escAttr(project.id)}">Hand off →</button>` : ''}
        <button class="btn btn-xs btn-error"   data-fm="delete"       data-id="${escAttr(project.id)}">Delete</button>
      </div>`;

    // Prepend checkbox for bulk selection
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'file-card-cb checkbox checkbox-xs checkbox-primary mr-1';
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

function bytesToB64(bytes) {
  const CHUNK = 8192;
  let bin = '';
  for (let i = 0; i < bytes.length; i += CHUNK) {
    bin += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(bin);
}

function applyProjectStateForExport(state) {
  const safe = state || {};
  svcTitle.value = safe.svcTitle || '';
  svcDate.value = safe.svcDate || '';
  svcChurch.value = safe.svcChurch || '';
  welcomeHeading = typeof safe.welcomeHeading === 'string' ? safe.welcomeHeading : '';
  welcomeItems = Array.isArray(safe.welcomeItems) ? safe.welcomeItems.slice() : [...WELCOME_ITEMS];
  optCover.checked = safe.optCover !== false;
  optWelcome.checked = safe.optWelcome !== false;
  optFooter.checked = safe.optFooter === true;
  optCal.checked = safe.optCal !== false;
  optBookletSize.value = safe.optBookletSize || 'auto';
  optAnnouncements.checked = safe.optAnnouncements !== false;
  optVolunteers.checked = safe.optVolunteers !== false;
  optVolunteerRoles.checked = safe.optVolunteerRoles !== false;
  optStaff.checked = safe.optStaff !== false;
  setItems(Array.isArray(safe.items) ? cloneItems(safe.items) : []);
  setAnnData(Array.isArray(safe.announcements)
    ? safe.announcements.map(a => ({ title: a.title || '', body: a.body || '', url: a.url || '', _breakBefore: !!a._breakBefore, _noBreakBefore: !!a._noBreakBefore }))
    : []);
  coverImageUrl = safe.coverImageUrl || null;
  if (safe.staffLogoUrl) staffLogoUrl = safe.staffLogoUrl;
  giveOnlineUrl = safe.giveOnlineUrl || '';
  giveOnlineUrlInput.value = giveOnlineUrl;
  servingSchedule = safe.servingSchedule || null;
  calEvents = Array.isArray(safe.calEvents)
    ? safe.calEvents.map(e => Object.assign({}, e, { start: Object.assign({}, e.start), end: e.end ? Object.assign({}, e.end) : null }))
    : null;
  breakBeforeCalendar = !!safe.breakBeforeCalendar;
  breakBeforeStaff = !!safe.breakBeforeStaff;
  calBreakBeforeDates = Array.isArray(safe.calBreakBeforeDates) ? safe.calBreakBeforeDates.slice() : [];
  const bmExport = (safe.bottomMerge && typeof safe.bottomMerge === 'object') ? safe.bottomMerge : {};
  bottomMerge.oow      = !!bmExport.oow;
  bottomMerge.serving  = !!bmExport.serving;
  bottomMerge.calendar = !!bmExport.calendar;
  bottomMerge.staff    = !!bmExport.staff;
  setActiveDocTemplate(safe.activeDocTemplate || activeDocTemplate);
  applyDocTemplate();
}

// ── Server-side PDF helpers ────────────────────────────────────────────────────

async function buildPrintDocHtml(pagesHtml, title) {
  // Collect CSS from all <link rel="stylesheet"> files (the 1.07 modular structure)
  // plus any inline <style> blocks. Falls back gracefully if a fetch fails.
  const linkEls   = [...document.querySelectorAll('link[rel="stylesheet"]')];
  const fetched   = await Promise.allSettled(
    linkEls.map(el => fetch(el.href).then(r => r.ok ? r.text() : '').catch(() => ''))
  );
  const rawLinkedCss = fetched.map(r => r.status === 'fulfilled' ? r.value : '').join('\n');

  // Embed font files as base64 data URIs so headless Chrome (running as file://) needs
  // no network access for fonts. Absolute-path URLs like /fonts/cache/... resolve to
  // file:///fonts/... in a file:// context, which doesn't exist on disk.
  const fontUrlRe = /url\((['"]?)(\/fonts\/[^)'"\s]+)\1\)/g;
  const fontUrls = [...new Set([...rawLinkedCss.matchAll(fontUrlRe)].map(m => m[2]))];
  const fontDataMap = {};
  await Promise.allSettled(fontUrls.map(async path => {
    try {
      const resp = await fetch(path);
      if (!resp.ok) return;
      const buf  = await resp.arrayBuffer();
      const b64  = btoa(String.fromCharCode(...new Uint8Array(buf)));
      const ext  = path.split('.').pop().toLowerCase();
      const mime = ext === 'woff2' ? 'font/woff2' : ext === 'woff' ? 'font/woff'
                 : ext === 'ttf'   ? 'font/truetype' : 'font/opentype';
      fontDataMap[path] = `data:${mime};base64,${b64}`;
    } catch {}
  }));
  const linkedCss = rawLinkedCss.replace(fontUrlRe, (_, q, path) =>
    fontDataMap[path] ? `url(${q}${fontDataMap[path]}${q})` : `url(${q}${path}${q})`
  );
  const inlineCss = [...document.querySelectorAll('style')].map(s => s.textContent).join('\n');
  const css       = linkedCss + '\n' + inlineCss;

  const safeTitle = escAttr(title || 'Bulletin');
  const { w, h } = getPageDims();
  const cssVars = activeDocTemplate.cssVars || {};
  const templateFont = cssVars.fontFamily || DEFAULT_TEMPLATE_CSS_VARS.fontFamily;
  // Append Arial fallback so custom Google Fonts have a reliable cross-platform fallback.
  // When no custom font is set, templateFont is already 'Arial, Helvetica, sans-serif',
  // making this redundant but harmless.
  const pdfFontSans  = `${templateFont}, Arial, Helvetica, sans-serif`;
  const pdfPrimary = cssVars.primary || cssVars.text || DEFAULT_TEMPLATE_CSS_VARS.primary;
  const pdfMuted = cssVars.muted || DEFAULT_TEMPLATE_CSS_VARS.muted;
  const pdfAccent = cssVars.accent || DEFAULT_TEMPLATE_CSS_VARS.accent;
  const pdfBorder = cssVars.border || DEFAULT_TEMPLATE_CSS_VARS.border;
  const pdfBg = cssVars.background || '#ffffff';
  return `<!DOCTYPE html>
<html lang="en" style="--doc-page-w:${w}in;--doc-page-h:${h}in;"><head>
<meta charset="UTF-8">
<title>${safeTitle}</title>
<style>
${css}
/* Headless PDF overrides — placed after embedded CSS so page-size variables win */
:root {
  --doc-page-w: ${w}in; --doc-page-h: ${h}in;
  --font-sans: ${pdfFontSans};
  --text: ${pdfPrimary};
  --muted: ${pdfMuted};
  --accent: ${pdfAccent};
  --border: ${pdfBorder};
  --ui-font: ${pdfFontSans};
  --ui-ink: ${pdfPrimary};
  --ui-muted: ${pdfMuted};
  --ui-accent: ${pdfAccent};
  --ui-border: ${pdfBorder};
  --ui-bg: ${pdfBg};
  --ui-surface: ${pdfBg};
  --ui-surface-2: ${pdfBg};
}
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

  const _pdfSession = typeof getSession === 'function' ? getSession() : null;
  const _pdfHeaders = { 'Content-Type': 'application/json' };
  if (_pdfSession?.access_token) _pdfHeaders['Authorization'] = `Bearer ${_pdfSession.access_token}`;

  let resp;
  try {
    resp = await fetch('/api/pdf', {
      method: 'POST',
      headers: _pdfHeaders,
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

async function buildProjectPdfBlob(id) {
  let project = projectById(id);
  if (!project) return null;

  // The file list holds metadata only (no `state`); fetch the full state on
  // demand for export of a non-active project.
  if (!project.state) {
    try {
      const _em = typeof isElectronMode === 'function' && isElectronMode();
      if (_em) {
        project = await sdGetProject(id);
      } else {
        const res = await apiFetch('/api/projects/' + id);
        project = res.project || project;
      }
    } catch (_) { /* fall through with whatever we have */ }
  }

  const prevState = collectCurrentProjectState();
  const prevStaffLogoUrl = staffLogoUrl;
  let pagesHtml = '';
  let html = '';
  let pageDims = null;
  let filename = '';
  applyingProjectState = true;
  try {
    applyProjectStateForExport(project.state || {});
    renderPreview();
    const pageEls = [...previewPane.querySelectorAll('.booklet-page')];
    pagesHtml = pageEls.map(el => el.outerHTML).join('\n');
    if (pagesHtml) {
      pageDims = getPageDims();
      const sizeTag = (activeDocTemplate.pageSize || '5.5x8.5').replace('x', 'x');
      filename = (project.name || 'Bulletin') + ' - ' + sizeTag + '.pdf';
      html = await buildPrintDocHtml(pagesHtml, filename.replace(/\.pdf$/i, ''));
    }
  } finally {
    applyProjectStateForExport(prevState);
    staffLogoUrl = prevStaffLogoUrl;
    renderPreview();
    applyingProjectState = false;
  }

  if (!pagesHtml) {
    setStatus('Nothing to print for this project.', 'error');
    return null;
  }

  try { html = await inlineExternalImages(html); } catch (e) { /* proceed anyway */ }

  const _pdfSess2 = typeof getSession === 'function' ? getSession() : null;
  const _pdfHdrs2 = { 'Content-Type': 'application/json' };
  if (_pdfSess2?.access_token) _pdfHdrs2['Authorization'] = `Bearer ${_pdfSess2.access_token}`;

  const resp = await fetch('/api/pdf', {
    method: 'POST',
    headers: _pdfHdrs2,
    body: JSON.stringify({ html, filename, pageWidth: pageDims.w, pageHeight: pageDims.h }),
  });

  if (!resp.ok) {
    let msg = 'PDF generation failed.';
    try { const err = await resp.json(); msg = err.error || msg; } catch (e) {}
    throw new Error(msg);
  }

  return { blob: await resp.blob(), filename, project };
}

async function downloadProjectAsPdf(id) {
  setStatus('Generating PDF…', 'info');
  try {
    const result = await buildProjectPdfBlob(id);
    if (!result) return;
    const url = URL.createObjectURL(result.blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = result.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setStatus('PDF downloaded!', 'success');
  } catch (e) {
    setStatus(e.message || 'PDF generation failed.', 'error');
  }
}

function handleFilesListClick(e) {
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
  } else if (action === 'handoff') {
    handleHandoff(id);
  }
}

async function handleHandoff(projectId) {
  const proj = projectById(projectId);
  if (!proj) return;

  // Fetch workspace members (excluding self)
  let members = [];
  try {
    const _electronMode = typeof isElectronMode === 'function' && isElectronMode();
    if (_electronMode) {
      const rows = await sdGetMembers();
      // sdGetMembers returns rows with profiles join: { user_id, role, profiles: { display_name, email } }
      members = (rows || []).map(m => ({
        user_id: m.user_id,
        role: m.role,
        display_name: m.profiles?.display_name || '',
        email: m.profiles?.email || '',
      }));
    } else {
      const res = await apiFetch('/api/workspace/members');
      members = res.members || [];
    }
  } catch (e) {
    setStatus('Could not load workspace members.', 'error');
    return;
  }

  if (members.length === 0) {
    alert('No other workspace members to hand off to.\nAdd teammates to the workspace first.');
    return;
  }

  // Build a simple select dialog
  const options = members.map(m => {
    const label = m.display_name || m.email || m.user_id;
    return `<option value="${escAttr(m.user_id)}">${esc(label)}</option>`;
  }).join('');

  const modal = document.createElement('dialog');
  modal.className = 'modal modal-open';
  modal.innerHTML = `
    <div class="modal-box max-w-sm">
      <h3 class="font-bold text-lg mb-1">Hand off project</h3>
      <p class="text-sm text-base-content/60 mb-4">"${esc(proj.name)}" will be transferred.<br>They become the editor; you keep view access.</p>
      <select id="handoff-select" class="select select-bordered w-full mb-4">
        <option value="">— Pick a person —</option>
        ${options}
      </select>
      <div class="modal-action">
        <button id="handoff-cancel" class="btn btn-ghost btn-sm">Cancel</button>
        <button id="handoff-confirm" class="btn btn-primary btn-sm">Hand off →</button>
      </div>
    </div>`;

  document.body.appendChild(modal);

  modal.querySelector('#handoff-cancel').onclick = () => modal.remove();
  modal.querySelector('#handoff-confirm').onclick = async () => {
    const toUserId = modal.querySelector('#handoff-select').value;
    if (!toUserId) { alert('Please pick a person.'); return; }
    const confirmBtn = modal.querySelector('#handoff-confirm');
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Transferring…';
    try {
      const _emTransfer = typeof isElectronMode === 'function' && isElectronMode();
      if (_emTransfer) {
        await sdTransferProject(projectId, toUserId);
        modal.remove();
        const freshProjects = await sdGetProjects();
        setProjects(freshProjects);
      } else {
        await apiFetch(`/api/projects/${projectId}/transfer`, 'POST', { to_user_id: toUserId });
        modal.remove();
        const res = await apiFetch('/api/projects');
        setProjects(res.projects || []);
      }
      renderProjectSelect();
      renderFilesList();
      setStatus(`"${proj.name}" handed off.`, 'success');
    } catch (e) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Hand off →';
      setStatus(e.message || 'Transfer failed.', 'error');
    }
  };
}

// ─── Bulk action bar handlers ─────────────────────────────────────────────────
function handleBulkSelectAll() {
  if (selectedProjectIds.size === projects.length && projects.length > 0) {
    selectedProjectIds.clear();
  } else {
    projects.forEach(p => selectedProjectIds.add(p.id));
  }
  renderFilesList();
  updateBulkBar();
}

async function handleBulkExportProPresenter() {
  const ids = [...selectedProjectIds];
  const btn = document.getElementById('bulk-export-pp');
  btn.disabled = true;
  btn.textContent = `PP 0 / ${ids.length}`;
  try {
    for (let i = 0; i < ids.length; i++) {
      btn.textContent = `PP ${i + 1} / ${ids.length}`;
      await exportToProPresenter(ids[i]);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Export ProPresenter';
  }
}

function handleBulkDownloadJson() {
  const ids = [...selectedProjectIds];
  ids.forEach((id, i) => setTimeout(() => downloadProjectJson(id), i * 150));
  setStatus(`Downloading ${ids.length} project${ids.length !== 1 ? 's' : ''}…`, 'info');
}

async function handleBulkDownloadPdf() {
  const ids = [...selectedProjectIds];
  const btn = document.getElementById('bulk-download-pdf');
  btn.disabled = true;
  btn.textContent = `↓ 0 / ${ids.length}`;
  for (let i = 0; i < ids.length; i++) {
    btn.textContent = `↓ ${i + 1} / ${ids.length}`;
    await downloadProjectAsPdf(ids[i]);
  }
  btn.disabled = false;
  btn.textContent = '↓ Download PDFs';
  setStatus(`Downloaded ${ids.length} PDF${ids.length !== 1 ? 's' : ''}.`, 'success');
}

function handleBulkDelete() {
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
}

function handleBulkClear() {
  selectedProjectIds.clear();
  renderFilesList();
  updateBulkBar();
}

function handleFilesNew() {
  clearEditorForNewProject();
  document.querySelector('.tab-btn[data-tab="page-editor"]').click();
}

function handleFilesImport(e) {
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
}

function handleProjectBrowse() {
  document.querySelector('.tab-btn[data-tab="page-files"]').click();
}


// ── Save to Google Drive ───────────────────────────────────────────────────────

async function saveProjectToDrive(projectId, type) {
  if (type !== 'json' && type !== 'pdf') return;
  const project = projectById(projectId);
  if (!project) throw new Error('Project not found.');
  const title = project.name || 'bulletin';

  setStatus(`Saving ${type.toUpperCase()} for "${title}" to Drive…`, 'info');

  let content_b64, mimeType, filename;
  if (type === 'json') {
    const jsonStr = JSON.stringify(project, null, 2);
    const bytes = new TextEncoder().encode(jsonStr);
    content_b64 = bytesToB64(bytes);
    mimeType = 'application/json';
    filename = `${title}.json`;
  } else {
    const pdfResult = await buildProjectPdfBlob(projectId);
    if (!pdfResult) return;
    const arrBuf = await pdfResult.blob.arrayBuffer();
    content_b64 = bytesToB64(new Uint8Array(arrBuf));
    mimeType = 'application/pdf';
    filename = pdfResult.filename;
  }

  const result = await apiFetch('/api/drive/upload', 'POST', {
    filename,
    content: content_b64,
    mimeType,
  });

  if (result.reconnectNeeded) {
    setStatus('Google Drive access expired. Reconnect Google in Settings.', 'error');
    return;
  }

  const linkHtml = result.fileUrl
    ? ` <a href="${result.fileUrl}" target="_blank" rel="noopener">Open in Drive</a>`
    : '';
  setStatus(`Saved ${filename} to Drive.${linkHtml}`, 'success');
}

async function handleBulkDriveJson() {
  const ids = [...selectedProjectIds];
  const btn = document.getElementById('bulk-drive-json');
  btn.disabled = true;
  btn.textContent = `Drive JSON 0 / ${ids.length}`;
  try {
    for (let i = 0; i < ids.length; i++) {
      btn.textContent = `Drive JSON ${i + 1} / ${ids.length}`;
      await saveProjectToDrive(ids[i], 'json');
    }
  } catch (e) {
    setStatus(`Drive save failed: ${e.message || e}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save JSON to Drive';
  }
}

async function handleBulkDrivePdf() {
  const ids = [...selectedProjectIds];
  const btn = document.getElementById('bulk-drive-pdf');
  btn.disabled = true;
  btn.textContent = `Drive PDF 0 / ${ids.length}`;
  try {
    for (let i = 0; i < ids.length; i++) {
      btn.textContent = `Drive PDF ${i + 1} / ${ids.length}`;
      await saveProjectToDrive(ids[i], 'pdf');
    }
  } catch (e) {
    setStatus(`Drive save failed: ${e.message || e}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save PDF to Drive';
  }
}

function initProjects() {
  if (_projectsInitialized) return;
  _projectsInitialized = true;

  // Send DELETE /api/presence on page unload (best-effort)
  window.addEventListener('pagehide', () => _stopPresenceHeartbeat());
  window.addEventListener('beforeunload', () => {
    const _emUnload = typeof isElectronMode === 'function' && isElectronMode();
    if (_emUnload) {
      // Electron path: delete presence via supabase-data.js (best-effort, fire-and-forget)
      const currentUser = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
      const userId = currentUser?.id || currentUser?.user_id || null;
      sdDeletePresence({ userId }).catch(() => {});
    } else if (isServerMode()) {
      apiFetch('/api/presence', 'DELETE').catch(() => {});
    }
  });

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

  document.getElementById('files-list').addEventListener('click', handleFilesListClick);
  document.getElementById('bulk-select-all').addEventListener('click', handleBulkSelectAll);
  document.getElementById('bulk-export-pp').addEventListener('click', handleBulkExportProPresenter);
  document.getElementById('bulk-download-json').addEventListener('click', handleBulkDownloadJson);
  document.getElementById('bulk-download-pdf').addEventListener('click', handleBulkDownloadPdf);
  document.getElementById('bulk-delete').addEventListener('click', handleBulkDelete);
  document.getElementById('bulk-clear').addEventListener('click', handleBulkClear);
  document.getElementById('files-new-btn').addEventListener('click', handleFilesNew);
  document.getElementById('files-import-input').addEventListener('change', handleFilesImport);
  document.getElementById('project-browse-btn').addEventListener('click', handleProjectBrowse);
  document.getElementById('bulk-drive-json').addEventListener('click', handleBulkDriveJson);
  document.getElementById('bulk-drive-pdf').addEventListener('click', handleBulkDrivePdf);
  document.getElementById('bulk-bar')?.addEventListener('click', e => {
    if (e.target instanceof Element && e.target.closest('.bulk-bar-btn')) {
      e.currentTarget.querySelector('details')?.removeAttribute('open');
    }
  });
}
