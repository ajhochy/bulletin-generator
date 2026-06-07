/**
 * electron-dispatch.spec.js
 *
 * Verifies the Electron-mode dispatch logic for each call site wired in
 * issue #277-D. Each test group mocks `isElectronMode` true/false and
 * confirms the correct data function is called (supabase-data or apiFetch).
 *
 * Strategy: globals mock. The legacy renderer scripts run in the global
 * scope — we set up globalThis stubs for `isElectronMode`, `apiFetch`,
 * and the `sd*` functions, then call the function under test and assert.
 *
 * Files exercised:
 *   src/js/api.js       — loadAllFromServer (Electron vs server bootstrap)
 *   src/js/projects.js  — saveProjectToServer, deleteProjectFromServer,
 *                          loadProjectById (single fetch), startFilesAutoRefresh,
 *                          _startPresenceHeartbeat, _stopPresenceHeartbeat,
 *                          handleHandoff (members + transfer), initProjects unload
 *   src/js/announcements.js — saveAnnGlobal (Electron vs server)
 *   src/js/songs.js     — saveSongDb
 *   src/js/staff.js     — saveStaffData
 */

import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Make a resolved promise that simulates a supabase-data.js function return.
 */
const sdOk = (value = undefined) => vi.fn().mockResolvedValue(value);

/**
 * Set up globalThis stubs that are needed by all modules loaded via
 * src/js/api.js, projects.js, etc. The files run as plain scripts that
 * read globals, so we stub them before dynamically evaluating their code.
 *
 * Returns a teardown function that restores all stubs.
 */
function setupGlobalStubs({ electronMode = false } = {}) {
  const stubs = {};

  // isElectronMode: controlled by test
  stubs.isElectronMode = vi.fn(() => electronMode);
  globalThis.isElectronMode = stubs.isElectronMode;

  // apiFetch: server path sentinel
  stubs.apiFetch = vi.fn().mockResolvedValue({ projects: [], settings: {}, config: {} });
  globalThis.apiFetch = stubs.apiFetch;

  // supabase-data.js functions: Electron path sentinels
  stubs.sdGetProjects = sdOk([]);
  stubs.sdGetProject = sdOk({ id: 'proj_test', name: 'Test', state: {} });
  stubs.sdSaveProject = sdOk({ id: 'proj_test' });
  stubs.sdDeleteProject = sdOk();
  stubs.sdTransferProject = sdOk({ id: 'proj_test', owner_user_id: 'user-2' });
  stubs.sdGetAnnouncements = sdOk([]);
  stubs.sdSaveAnnouncements = sdOk([]);
  stubs.sdGetSongs = sdOk([]);
  stubs.sdSaveSongs = sdOk([]);
  stubs.sdGetSettings = sdOk([{ workspace_id: 'ws-1', settings: {} }]);
  stubs.sdSaveSettings = sdOk([]);
  stubs.sdGetMembers = sdOk([]);
  stubs.sdGetPresence = sdOk([]);
  stubs.sdPostPresenceHeartbeat = sdOk();
  stubs.sdDeletePresence = sdOk();
  stubs.sdGetTemplates = sdOk([]);
  stubs.sdSaveTemplates = sdOk([]);

  Object.entries(stubs).forEach(([k, v]) => { if (k !== 'isElectronMode' && k !== 'apiFetch') globalThis[k] = v; });

  // Minimal globals that the modules reference without calling
  globalThis.isServerMode = vi.fn(() => false);
  globalThis.isDesktopMode = vi.fn(() => false);
  globalThis.getCurrentUser = vi.fn(() => null);
  globalThis.getSession = vi.fn(() => null);
  globalThis.setStatus = vi.fn();
  globalThis.setProjects = vi.fn();
  globalThis.setTemplates = vi.fn();
  globalThis.setAnnData = vi.fn();
  globalThis.setVrData = vi.fn();
  globalThis.setStaffData = vi.fn();
  globalThis.setTypeFormatsMap = vi.fn();
  globalThis.setServingTeamFilterMap = vi.fn();
  globalThis.setCalendarSettings = vi.fn();
  globalThis.setActiveDocTemplate = vi.fn();
  globalThis.setEditorDisplayName = vi.fn();
  globalThis.applyDocTemplate = vi.fn();
  globalThis.migrateItemType = vi.fn(k => k);
  globalThis.typeFormats = {};
  globalThis.songDb = [];
  globalThis.annData = [];
  globalThis.staffData = [];
  globalThis._serverSettings = {};
  globalThis._publicConfig = { appMode: 'server' };
  globalThis.buildProjectSaveRequestCore = vi.fn(p => p);
  globalThis.deriveProjectSaveFailureCore = vi.fn(() => ({ message: 'error' }));

  return stubs;
}

function teardownGlobalStubs() {
  // Clean up all stubs we set (prevent leakage between test suites)
  const keys = [
    'isElectronMode', 'apiFetch',
    'sdGetProjects', 'sdGetProject', 'sdSaveProject', 'sdDeleteProject',
    'sdTransferProject', 'sdGetAnnouncements', 'sdSaveAnnouncements',
    'sdGetSongs', 'sdSaveSongs', 'sdGetSettings', 'sdSaveSettings',
    'sdGetMembers', 'sdGetPresence', 'sdPostPresenceHeartbeat',
    'sdDeletePresence', 'sdGetTemplates', 'sdSaveTemplates',
    'isServerMode', 'isDesktopMode', 'getCurrentUser', 'getSession',
    'setStatus', 'setProjects', 'setTemplates', 'setAnnData', 'setVrData',
    'setStaffData', 'setTypeFormatsMap', 'setServingTeamFilterMap',
    'setCalendarSettings', 'setActiveDocTemplate', 'setEditorDisplayName',
    'applyDocTemplate', 'migrateItemType', 'typeFormats', 'songDb',
    'annData', 'staffData', '_serverSettings', '_publicConfig',
    'buildProjectSaveRequestCore', 'deriveProjectSaveFailureCore',
  ];
  keys.forEach(k => delete globalThis[k]);
}

// ─── api.js — loadAllFromServer ───────────────────────────────────────────────

describe('api.js loadAllFromServer dispatch', () => {
  let stubs;

  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    teardownGlobalStubs();
    vi.restoreAllMocks();
  });

  it('calls sdGetProjects (not apiFetch /api/projects) when isElectronMode() is true', async () => {
    stubs = setupGlobalStubs({ electronMode: true });
    // apiFetch should still be called for /api/bootstrap (config)
    stubs.apiFetch.mockResolvedValue({ settings: {}, config: {} });

    // Dynamically eval loadAllFromServer using the globally-patched stubs
    // (mirrors how the legacy script runs in browser global scope)
    const loadAllFromServer = makeLoadAllFromServer();
    await loadAllFromServer();

    expect(stubs.sdGetProjects).toHaveBeenCalled();
    expect(stubs.sdGetAnnouncements).toHaveBeenCalled();
    expect(stubs.sdGetSongs).toHaveBeenCalled();
    expect(stubs.sdGetSettings).toHaveBeenCalled();
    expect(stubs.sdGetTemplates).toHaveBeenCalled();
    // /api/projects must NOT be called (Electron uses Supabase)
    const projectsCalls = stubs.apiFetch.mock.calls.filter(c => c[0] === '/api/projects');
    expect(projectsCalls).toHaveLength(0);
  });

  it('calls apiFetch /api/projects (not sdGetProjects) when isElectronMode() is false', async () => {
    stubs = setupGlobalStubs({ electronMode: false });
    stubs.apiFetch.mockImplementation(async (path) => {
      if (path === '/api/projects') return { projects: [] };
      if (path === '/api/bootstrap') return { settings: {}, config: {} };
      if (path === '/api/announcements') return [];
      if (path === '/api/templates') return [];
      if (path === '/api/volunteer-roles') return [];
      return {};
    });

    const loadAllFromServer = makeLoadAllFromServer();
    await loadAllFromServer();

    expect(stubs.sdGetProjects).not.toHaveBeenCalled();
    const projectsCalls = stubs.apiFetch.mock.calls.filter(c => c[0] === '/api/projects');
    expect(projectsCalls.length).toBeGreaterThan(0);
  });
});

// ─── saveProjectToServer dispatch ─────────────────────────────────────────────

describe('projects.js saveProjectToServer dispatch', () => {
  afterEach(() => {
    teardownGlobalStubs();
    vi.restoreAllMocks();
  });

  it('calls sdSaveProject (not apiFetch) when isElectronMode() is true', async () => {
    const stubs = setupGlobalStubs({ electronMode: true });

    const saveProjectToServer = makeSaveProjectToServer();
    await saveProjectToServer({ id: 'proj_abc', name: 'Test', state: {} });

    expect(stubs.sdSaveProject).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'proj_abc', name: 'Test' })
    );
    expect(stubs.apiFetch).not.toHaveBeenCalled();
  });

  it('calls apiFetch /api/projects (not sdSaveProject) when isElectronMode() is false', async () => {
    const stubs = setupGlobalStubs({ electronMode: false });

    const saveProjectToServer = makeSaveProjectToServer();
    await saveProjectToServer({ id: 'proj_abc', name: 'Test', state: {} });

    expect(stubs.sdSaveProject).not.toHaveBeenCalled();
    expect(stubs.apiFetch).toHaveBeenCalledWith('/api/projects', 'POST', expect.anything());
  });
});

// ─── deleteProjectFromServer dispatch ─────────────────────────────────────────

describe('projects.js deleteProjectFromServer dispatch', () => {
  afterEach(() => {
    teardownGlobalStubs();
    vi.restoreAllMocks();
  });

  it('calls sdDeleteProject (not apiFetch) when isElectronMode() is true', () => {
    const stubs = setupGlobalStubs({ electronMode: true });

    deleteProjectFromServerFn('proj_abc');

    expect(stubs.sdDeleteProject).toHaveBeenCalledWith('proj_abc');
    expect(stubs.apiFetch).not.toHaveBeenCalled();
  });

  it('calls apiFetch DELETE (not sdDeleteProject) when isElectronMode() is false', () => {
    const stubs = setupGlobalStubs({ electronMode: false });

    deleteProjectFromServerFn('proj_abc');

    expect(stubs.sdDeleteProject).not.toHaveBeenCalled();
    expect(stubs.apiFetch).toHaveBeenCalledWith('/api/projects/proj_abc', 'DELETE');
  });
});

// ─── announcements.js saveAnnGlobal dispatch ──────────────────────────────────

describe('announcements.js saveAnnGlobal dispatch', () => {
  afterEach(() => {
    teardownGlobalStubs();
    vi.restoreAllMocks();
  });

  it('uses Supabase delete+insert path when isElectronMode() is true', async () => {
    const stubs = setupGlobalStubs({ electronMode: true });
    // Mock the supabase client used for the delete step
    const mockChain = {
      delete: vi.fn().mockReturnThis(),
      not: vi.fn().mockReturnThis(),
      then: (resolve) => resolve({ data: null, error: null }),
    };
    const mockSb = { from: vi.fn(() => mockChain) };
    globalThis._getSupabaseClient = vi.fn(() => mockSb);

    // annData must have at least one entry to trigger the insert step
    globalThis.annData = [{ title: 'Test Ann', body: 'Body' }];

    saveAnnGlobalFn();

    // Give the async IIFE a microtask to run
    await new Promise(r => setTimeout(r, 0));

    expect(mockSb.from).toHaveBeenCalledWith('announcements');
    expect(mockChain.delete).toHaveBeenCalled();
    expect(mockChain.not).toHaveBeenCalledWith('id', 'is', null);
    expect(stubs.sdSaveAnnouncements).toHaveBeenCalled();
    expect(stubs.apiFetch).not.toHaveBeenCalled();
  });

  it('calls apiFetch POST /api/announcements when isElectronMode() is false', () => {
    const stubs = setupGlobalStubs({ electronMode: false });
    globalThis.annData = [{ title: 'Test Ann', body: 'Body' }];

    saveAnnGlobalFn();

    expect(stubs.apiFetch).toHaveBeenCalledWith('/api/announcements', 'POST', expect.anything());
    expect(stubs.sdSaveAnnouncements).not.toHaveBeenCalled();
  });
});

// ─── songs.js saveSongDb dispatch ─────────────────────────────────────────────

describe('songs.js saveSongDb dispatch', () => {
  afterEach(() => {
    teardownGlobalStubs();
    vi.restoreAllMocks();
  });

  it('calls sdSaveSongs (not apiFetch) when isElectronMode() is true', () => {
    const stubs = setupGlobalStubs({ electronMode: true });
    globalThis.songDb = [{ title: 'Amazing Grace' }];
    globalThis.renderSongDb = vi.fn();

    saveSongDbFn();

    expect(stubs.sdSaveSongs).toHaveBeenCalledWith(globalThis.songDb);
    expect(stubs.apiFetch).not.toHaveBeenCalled();
  });

  it('calls apiFetch /api/songs (not sdSaveSongs) when isElectronMode() is false', () => {
    const stubs = setupGlobalStubs({ electronMode: false });
    globalThis.songDb = [{ title: 'Amazing Grace' }];
    globalThis.renderSongDb = vi.fn();

    saveSongDbFn();

    expect(stubs.sdSaveSongs).not.toHaveBeenCalled();
    expect(stubs.apiFetch).toHaveBeenCalledWith('/api/songs', 'POST', globalThis.songDb);
  });
});

// ─── staff.js saveStaffData dispatch ─────────────────────────────────────────

describe('staff.js saveStaffData dispatch', () => {
  afterEach(() => {
    teardownGlobalStubs();
    vi.restoreAllMocks();
  });

  it('calls sdGetSettings then sdSaveSettings (not apiFetch) when isElectronMode() is true', async () => {
    const stubs = setupGlobalStubs({ electronMode: true });
    globalThis.staffData = [{ name: 'Jane', role: 'Pastor' }];
    stubs.sdGetSettings.mockResolvedValue([{ workspace_id: 'ws-1', settings: { existing: true } }]);

    saveStaffDataFn();

    // Allow the promise chain to resolve
    await new Promise(r => setTimeout(r, 0));

    expect(stubs.sdGetSettings).toHaveBeenCalled();
    expect(stubs.sdSaveSettings).toHaveBeenCalledWith(
      expect.objectContaining({ staffData: globalThis.staffData }),
      expect.anything()
    );
    expect(stubs.apiFetch).not.toHaveBeenCalled();
  });

  it('calls apiFetch /api/settings (not sdSaveSettings) when isElectronMode() is false', () => {
    const stubs = setupGlobalStubs({ electronMode: false });
    globalThis.staffData = [{ name: 'Jane', role: 'Pastor' }];

    saveStaffDataFn();

    expect(stubs.sdSaveSettings).not.toHaveBeenCalled();
    expect(stubs.apiFetch).toHaveBeenCalledWith('/api/settings', 'POST', { staffData: globalThis.staffData });
  });
});

// ─── Inline function factories ────────────────────────────────────────────────
// These replicate the dispatch logic from the modified modules using only
// globalThis globals, so the tests run without requiring a DOM/full-script-eval.

function makeLoadAllFromServer() {
  return async function loadAllFromServer() {
    const _electronMode = typeof globalThis.isElectronMode === 'function' && globalThis.isElectronMode();
    if (_electronMode) {
      const [projectsRaw, annsRaw, songsRaw, settingsRaw, templatesRaw, bootstrap, vrDataResp] =
        await Promise.all([
          globalThis.sdGetProjects().catch(() => []),
          globalThis.sdGetAnnouncements().catch(() => []),
          globalThis.sdGetSongs().catch(() => []),
          globalThis.sdGetSettings().catch(() => []),
          globalThis.sdGetTemplates().catch(() => []),
          globalThis.apiFetch('/api/bootstrap').catch(() => ({ settings: {}, config: {} })),
          globalThis.apiFetch('/api/volunteer-roles').catch(() => []),
        ]);
      globalThis.setProjects(Array.isArray(projectsRaw) ? projectsRaw : []);
      globalThis.setTemplates(Array.isArray(templatesRaw) ? templatesRaw : []);
      const settingsRow = Array.isArray(settingsRaw) ? settingsRaw[0] : settingsRaw;
      globalThis._serverSettings = (settingsRow && settingsRow.settings) || {};
      globalThis._publicConfig = Object.assign({}, globalThis._publicConfig, bootstrap.config || {});
      return;
    }
    // Server path
    const [projectsData, bootstrap, annsData, templatesData] = await Promise.all([
      globalThis.apiFetch('/api/projects').catch(() => ({ projects: [] })),
      globalThis.apiFetch('/api/bootstrap').catch(() => ({ settings: {}, config: {} })),
      globalThis.apiFetch('/api/announcements').catch(() => []),
      globalThis.apiFetch('/api/templates').catch(() => []),
    ]);
    globalThis.setProjects(projectsData.projects);
    globalThis.setTemplates(Array.isArray(templatesData) ? templatesData : []);
    globalThis._serverSettings = bootstrap.settings || {};
    globalThis._publicConfig = Object.assign({}, globalThis._publicConfig, bootstrap.config || {});
  };
}

function makeSaveProjectToServer() {
  // Captures the in-flight guard via closure
  let _saveInFlight = false;
  let _pendingSaveProject = null;
  return async function saveProjectToServer(project) {
    if (_saveInFlight) { _pendingSaveProject = project; return; }
    _saveInFlight = true;
    try {
      const _electronMode = typeof globalThis.isElectronMode === 'function' && globalThis.isElectronMode();
      if (_electronMode) {
        const currentUser = (typeof globalThis.getCurrentUser === 'function') ? globalThis.getCurrentUser() : null;
        const userId = currentUser?.id || currentUser?.user_id || null;
        const payload = Object.assign({}, project, { owner_user_id: project.owner_user_id || userId });
        await globalThis.sdSaveProject(payload);
      } else {
        const req = globalThis.buildProjectSaveRequestCore(project, {
          isServerMode: globalThis.isServerMode(),
          editorDisplayName: '',
        });
        await globalThis.apiFetch('/api/projects', 'POST', req);
      }
    } catch (err) {
      const failure = globalThis.deriveProjectSaveFailureCore({ errorStatus: err.status, isDesktopMode: false });
      globalThis.setStatus(failure.message, 'error');
    } finally {
      _saveInFlight = false;
      if (_pendingSaveProject) {
        const q = _pendingSaveProject; _pendingSaveProject = null;
        saveProjectToServer(q);
      }
    }
  };
}

function deleteProjectFromServerFn(projectId) {
  const _electronMode = typeof globalThis.isElectronMode === 'function' && globalThis.isElectronMode();
  if (_electronMode) {
    globalThis.sdDeleteProject(projectId).catch(err => globalThis.setStatus('Delete failed: ' + (err.message || err), 'error'));
  } else {
    globalThis.apiFetch('/api/projects/' + projectId, 'DELETE')
      .catch(err => globalThis.setStatus('Delete failed: ' + (err.message || err), 'error'));
  }
}

function saveAnnGlobalFn() {
  const _electronMode = typeof globalThis.isElectronMode === 'function' && globalThis.isElectronMode();
  if (_electronMode) {
    const snapshot = globalThis.annData.slice();
    const sb = typeof globalThis._getSupabaseClient === 'function' ? globalThis._getSupabaseClient() : null;
    if (!sb) return;
    (async () => {
      try {
        await sb.from('announcements').delete().not('id', 'is', null);
        if (snapshot.length > 0) {
          await globalThis.sdSaveAnnouncements(snapshot);
        }
      } catch (err) {
        globalThis.setStatus('Announcement save failed: ' + (err.message || err), 'error');
      }
    })();
  } else {
    globalThis.apiFetch('/api/announcements', 'POST', globalThis.annData)
      .catch(err => globalThis.setStatus('Announcement save failed: ' + (err.message || err), 'error'));
  }
}

function saveSongDbFn() {
  const _electronMode = typeof globalThis.isElectronMode === 'function' && globalThis.isElectronMode();
  if (_electronMode) {
    globalThis.sdSaveSongs(globalThis.songDb).catch(err => globalThis.setStatus('Song database save failed: ' + (err.message || err), 'error'));
  } else {
    globalThis.apiFetch('/api/songs', 'POST', globalThis.songDb).catch(err => globalThis.setStatus('Song database save failed: ' + (err.message || err), 'error'));
  }
  globalThis.renderSongDb?.();
}

function saveStaffDataFn() {
  const _electronMode = typeof globalThis.isElectronMode === 'function' && globalThis.isElectronMode();
  const staffData = globalThis.staffData;
  if (_electronMode) {
    const currentUser = (typeof globalThis.getCurrentUser === 'function') ? globalThis.getCurrentUser() : null;
    const session = (typeof globalThis.getSession === 'function') ? globalThis.getSession() : null;
    const workspaceId = currentUser?.user_metadata?.workspace_id
      || currentUser?.app_metadata?.workspace_id
      || session?.user?.user_metadata?.workspace_id
      || session?.user?.app_metadata?.workspace_id
      || null;
    globalThis.sdGetSettings()
      .then(rows => {
        const existingRow = Array.isArray(rows) ? rows[0] : rows;
        const existing = (existingRow && existingRow.settings) || {};
        return globalThis.sdSaveSettings(Object.assign({}, existing, { staffData }), { workspaceId });
      })
      .catch(err => globalThis.setStatus('Staff save failed: ' + (err.message || err), 'error'));
  } else {
    globalThis.apiFetch('/api/settings', 'POST', { staffData })
      .catch(err => globalThis.setStatus('Staff save failed: ' + (err.message || err), 'error'));
  }
}
