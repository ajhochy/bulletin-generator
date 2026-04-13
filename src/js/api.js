
// ─── Server API ────────────────────────────────────────────────────────────
async function apiFetch(path, method = 'GET', body = null) {
  const opts = { method, headers: {} };
  if (body !== null) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) { const e = new Error(`API ${method} ${path} → ${res.status}`); e.status = res.status; throw e; }
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

async function loadAllFromServer() {
  try {
    const [projectsData, bootstrap, annsData] = await Promise.all([
      apiFetch('/api/projects').catch(() => ({ projects: [] })),
      apiFetch('/api/bootstrap').catch(() => ({ settings: {}, config: {} })),
      apiFetch('/api/announcements').catch(() => [])
    ]);
    setProjects(projectsData.projects);
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
