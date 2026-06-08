
// ─── Server API ────────────────────────────────────────────────────────────
async function apiFetch(path, method = 'GET', body = null) {
  const opts = { method, headers: {} };
  const session = typeof getSession === 'function' ? getSession() : null;
  if (session?.access_token) {
    opts.headers.Authorization = `Bearer ${session.access_token}`;
  }
  if (body !== null) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let errData = null;
    try { errData = await res.json(); } catch (_) {}
    const msg = errData?.error || `API ${method} ${path} → ${res.status}`;
    const e = new Error(msg);
    e.status = res.status;
    e.code = errData?.code || null;
    e.detail = errData?.detail || null;
    e.responseBody = errData || null;
    throw e;
  }
  return res.json();
}

// Cache loaded from server at startup (replaces localStorage reads for these keys)
let _serverSettings = {};
let _publicConfig = {
  appMode: 'server',
  pcoConfigured: false,
  calendarDefaults: { urls: [], exclude: [] },
};

// Convenience accessors — use these instead of reading _publicConfig directly
function isDesktopMode() { return _publicConfig.appMode === 'desktop'; }
function isServerMode()  { return _publicConfig.appMode === 'server';  }

// ── Owner display labels (electron mode) ────────────────────────────────────
// In electron mode the project list comes from supabase-data (no profiles JOIN),
// so owner_display_name isn't populated. Resolve it from the workspace members
// list (sdGetMembers) + the current user (whom sdGetMembers excludes).
function buildOwnerLabelMap(membersRaw) {
  const map = {};
  (Array.isArray(membersRaw) ? membersRaw : []).forEach(m => {
    const p = (m && m.profiles) || {};
    const label = p.display_name || p.email || '';
    if (m && m.user_id && label) map[String(m.user_id)] = label;
  });
  const u = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
  const uid = u && (u.id || u.user_id);
  if (uid && !map[String(uid)]) {
    map[String(uid)] = (u.user_metadata && u.user_metadata.full_name) || u.email || '';
  }
  return map;
}

// Attach owner_display_name to projects from the cached owner-label map (no-op
// for rows that already carry an owner name, e.g. server mode).
function attachOwnerLabels(projectsArr) {
  const map = globalThis._bgOwnerLabels || {};
  return (Array.isArray(projectsArr) ? projectsArr : []).map(p => {
    if (!p || p.owner_display_name || p.owner_email) return p;
    const label = map[String(p.owner_user_id)];
    return label ? Object.assign({}, p, { owner_display_name: label }) : p;
  });
}

async function loadAllFromServer() {
  try {
    // ── Electron path: read data directly from Supabase via supabase-data.js ──
    // isElectronMode() is exported by auth-ui.js onto globalThis.
    const _electronMode = typeof isElectronMode === 'function' && isElectronMode();
    if (_electronMode) {
      // Fetch projects, announcements, songs, settings, and templates from Supabase.
      // bootstrap still comes from the server (needed for _publicConfig / PCO config).
      const [projectsRaw, annsRaw, songsRaw, settingsRaw, templatesRaw, bootstrap, vrDataResp, membersRaw] =
        await Promise.all([
          sdGetProjects().catch(() => []),
          sdGetAnnouncements().catch(() => []),
          sdGetSongs().catch(() => []),
          sdGetSettings().catch(() => []),
          sdGetTemplates().catch(() => []),
          apiFetch('/api/bootstrap').catch(() => ({ settings: {}, config: {} })),
          apiFetch('/api/volunteer-roles').catch(() => []),
          (typeof sdGetMembers === 'function' ? sdGetMembers().catch(() => []) : Promise.resolve([])),
        ]);

      // Build a workspace-member display map (user_id → name/email) so the file
      // list can show the project owner. sdGetMembers excludes the caller, so
      // buildOwnerLabelMap adds the current user. Cached on globalThis for the
      // background files-refresh poll to reuse (see attachOwnerLabels).
      globalThis._bgOwnerLabels = buildOwnerLabelMap(membersRaw);
      // Projects: supabase returns rows directly (not wrapped in {projects:[...]})
      setProjects(attachOwnerLabels(Array.isArray(projectsRaw) ? projectsRaw : []));
      setTemplates(Array.isArray(templatesRaw) ? templatesRaw : []);

      // Settings: workspace_settings row has a `settings` JSONB column
      const settingsRow = Array.isArray(settingsRaw) ? settingsRaw[0] : settingsRaw;
      _serverSettings = (settingsRow && settingsRow.settings) || {};
      _publicConfig = Object.assign({}, _publicConfig, bootstrap.config || {});
      if (!_publicConfig.calendarDefaults) {
        _publicConfig.calendarDefaults = { urls: [], exclude: [] };
      }
      // Electron mode: mark as desktop-like so server-mode presence guards don't fire.
      // The actual mode flag comes from bootstrap but for data-layer purposes
      // Electron behaves like desktop (single user, no conflict detection).
      _publicConfig.appMode = _publicConfig.appMode || 'desktop';

      setTypeFormatsMap(_serverSettings.typeFormats);
      const _oldKeysE = Object.keys(typeFormats);
      if (_oldKeysE.some(k => !['section','song','liturgy','label','note','media'].includes(k))) {
        const _migrated = {};
        _oldKeysE.forEach(k => {
          const newKey = migrateItemType(k);
          if (!_migrated[newKey] || Object.keys(_migrated[newKey]).length === 0) {
            _migrated[newKey] = typeFormats[k];
          }
        });
        setTypeFormatsMap(_migrated);
      }

      if (Array.isArray(_serverSettings.staffData) && _serverSettings.staffData.length)
        setStaffData(_serverSettings.staffData);

      // Songs: supabase rows have {id, title, data} — merge the data field which
      // holds the full song dict (mirrors how storage.py saves songs).
      if (Array.isArray(songsRaw)) {
        songDb = songsRaw.map(row => (row.data && typeof row.data === 'object') ? row.data : row);
      }

      // Announcements: supabase rows have {id, title, body, state} — use state
      // field which holds the full announcement dict saved by sdSaveAnnouncements.
      setAnnData(Array.isArray(annsRaw)
        ? annsRaw.map(row => {
            const a = (row.state && typeof row.state === 'object') ? row.state : row;
            return { title: a.title || '', body: a.body || '', url: a.url || '' };
          })
        : []);

      setVrData(Array.isArray(vrDataResp)
        ? vrDataResp.map(r => ({ title: r.title || '', body: r.body || '', url: r.url || '', _breakBefore: !!r._breakBefore, _noBreakBefore: !!r._noBreakBefore }))
        : []);
      setServingTeamFilterMap(_serverSettings.servingTeamFilter);
      setCalendarSettings(_serverSettings.calUrls, _serverSettings.calExclude);
      if (_serverSettings.docTemplate && typeof _serverSettings.docTemplate === 'object') {
        setActiveDocTemplate(_serverSettings.docTemplate);
      }
      applyDocTemplate();
      if (typeof _serverSettings.editorDisplayName === 'string') {
        setEditorDisplayName(_serverSettings.editorDisplayName);
      }
      // Hide Drive export buttons (not wired in Electron mode yet)
      const driveJsonE = document.getElementById('bulk-drive-json');
      const drivePdfE  = document.getElementById('bulk-drive-pdf');
      if (driveJsonE) driveJsonE.style.display = 'none';
      if (drivePdfE)  drivePdfE.style.display  = 'none';
      return; // ← early return; server path below is skipped
    }

    // ── Server/browser path: unchanged ────────────────────────────────────────
    const [projectsData, bootstrap, annsData, templatesData, vrDataResp] = await Promise.all([
      apiFetch('/api/projects').catch(() => ({ projects: [] })),
      apiFetch('/api/bootstrap').catch(() => ({ settings: {}, config: {} })),
      apiFetch('/api/announcements').catch(() => []),
      apiFetch('/api/templates').catch(() => []),
      apiFetch('/api/volunteer-roles').catch(() => []),
    ]);
    setProjects(projectsData.projects);
    setTemplates(Array.isArray(templatesData) ? templatesData : []);
    _serverSettings = bootstrap.settings || {};
    _publicConfig = Object.assign({}, _publicConfig, bootstrap.config || {});
    if (!_publicConfig.calendarDefaults) {
      _publicConfig.calendarDefaults = { urls: [], exclude: [] };
    }
    setTypeFormatsMap(_serverSettings.typeFormats);
    // Migrate any old typeFormats keys to the new 6-type system.
    // If multiple old types map to the same new type, keep the first
    // non-empty one found.
    const _oldKeys = Object.keys(typeFormats);
    if (_oldKeys.some(k => !['section','song','liturgy','label','note','media'].includes(k))) {
      const _migrated = {};
      _oldKeys.forEach(k => {
        const newKey = migrateItemType(k);
        if (!_migrated[newKey] || Object.keys(_migrated[newKey]).length === 0) {
          _migrated[newKey] = typeFormats[k];
        }
      });
      setTypeFormatsMap(_migrated);
    }
    if (Array.isArray(_serverSettings.staffData) && _serverSettings.staffData.length)
      setStaffData(_serverSettings.staffData);
    if (Array.isArray(bootstrap.songDb))
      songDb = bootstrap.songDb;
    setAnnData(Array.isArray(annsData)
      ? annsData.map(a => ({ title: a.title || '', body: a.body || '', url: a.url || '' }))
      : []);
    setVrData(Array.isArray(vrDataResp)
      ? vrDataResp.map(r => ({ title: r.title || '', body: r.body || '', url: r.url || '', _breakBefore: !!r._breakBefore, _noBreakBefore: !!r._noBreakBefore }))
      : []);
    setServingTeamFilterMap(_serverSettings.servingTeamFilter);
    setCalendarSettings(_serverSettings.calUrls, _serverSettings.calExclude);
    if (_serverSettings.docTemplate && typeof _serverSettings.docTemplate === 'object') {
      setActiveDocTemplate(_serverSettings.docTemplate);
    }
    applyDocTemplate();
    if (!isServerMode() && typeof _serverSettings.editorDisplayName === 'string') {
      setEditorDisplayName(_serverSettings.editorDisplayName);
    }
    // Show Drive export buttons if Drive scope is granted
    const driveJson = document.getElementById('bulk-drive-json');
    const drivePdf  = document.getElementById('bulk-drive-pdf');
    if (_publicConfig.driveConfigured) {
      if (driveJson) driveJson.style.display = '';
      if (drivePdf)  drivePdf.style.display  = '';
    } else {
      if (driveJson) driveJson.style.display = 'none';
      if (drivePdf)  drivePdf.style.display  = 'none';
    }
  } catch (e) {
    setStatus('Could not reach server. Working offline.', 'error');
  }
}
