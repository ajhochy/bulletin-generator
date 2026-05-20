import { migrateItemType } from './formatting-core.js';

export function cloneItemsData(list) {
  return (Array.isArray(list) ? list : []).map(item => {
    const cloned = {
      type: migrateItemType(item.type || 'label'),
      title: item.title || '',
      detail: item.detail || '',
    };
    if (item._noBreakBefore) cloned._noBreakBefore = true;
    if (Array.isArray(item._noBreakBeforeStanzas) && item._noBreakBeforeStanzas.length > 0)
      cloned._noBreakBeforeStanzas = [...item._noBreakBeforeStanzas];
    if (item._collapsed) cloned._collapsed = true;
    if (item._fmt && typeof item._fmt === 'object') cloned._fmt = Object.assign({}, item._fmt);
    if (Array.isArray(item._forceBreakBeforeParagraph) && item._forceBreakBeforeParagraph.length > 0)
      cloned._forceBreakBeforeParagraph = [...item._forceBreakBeforeParagraph];
    if (Array.isArray(item._noBreakBeforeParagraph) && item._noBreakBeforeParagraph.length > 0)
      cloned._noBreakBeforeParagraph = [...item._noBreakBeforeParagraph];
    return cloned;
  });
}

export function buildProjectSaveRequest(project, { isServerMode, editorDisplayName, loadedRevision }) {
  const requestProject = { ...project };
  if (isServerMode && editorDisplayName) {
    requestProject.updatedBy = editorDisplayName;
  }
  if (isServerMode) {
    requestProject._clientRevision = loadedRevision;
  }
  return requestProject;
}

export function deriveProjectSaveSuccess({ result, isServerMode, currentLoadedRevision, storedProject }) {
  let loadedRevision = currentLoadedRevision;
  let storedRevision = storedProject && typeof storedProject.revision === 'number'
    ? storedProject.revision
    : null;

  if (isServerMode && result && typeof result.revision === 'number') {
    loadedRevision = result.revision;
    storedRevision = result.revision;
  }

  return {
    loadedRevision,
    storedRevision,
    hideStaleBanner: true,
    hideConflictBanner: true,
  };
}

export function deriveProjectSaveFailure({ errorStatus, isDesktopMode }) {
  if (errorStatus === 409) {
    return {
      type: 'conflict',
      message: 'This bulletin was updated by someone else.',
    };
  }

  return {
    type: 'generic',
    message: isDesktopMode ? 'Could not save project.' : 'Could not save project to server.',
  };
}

/**
 * Derive what the startup restore flow should do given the current remembered
 * project ID and the list of projects fetched from the server.
 *
 * Returns one of:
 *   { action: 'load',  project }           — restore this project
 *   { action: 'blank', reason: 'none-remembered' }  — no remembered id, start blank
 *   { action: 'blank', reason: 'not-found',
 *     statusMessage: string }              — id remembered but project missing / inaccessible
 *   { action: 'load-newest', project }    — desktop only: no remembered, fall back to newest
 *
 * The caller decides how to present the statusMessage and whether to clear
 * the stored project ID from localStorage.
 *
 * Rules:
 * - Server mode: NEVER auto-loads a workspace project when no id is remembered.
 *   Doing so would silently open another user's work in a fresh browser session.
 * - Desktop mode: preserves the legacy behavior of loading the newest project as
 *   a convenience fallback (single-user environment, no privacy concern).
 */
export function deriveStartupRestore({ rememberedId, projects, isServerMode }) {
  const projectList = Array.isArray(projects) ? projects : [];

  // Case 1: a project was remembered for this browser session.
  if (rememberedId) {
    const found = projectList.find(p => p.id === rememberedId) || null;
    if (found) {
      return { action: 'load', project: found };
    }
    // Remembered project is gone or inaccessible (deleted, 403/404, or wrong user).
    return {
      action: 'blank',
      reason: 'not-found',
      statusMessage: 'Your previous project is no longer accessible.',
    };
  }

  // Case 2: no remembered project.
  if (isServerMode) {
    // Server mode: start blank. Do NOT auto-load the newest workspace project —
    // it may belong to a different user and would surprise them with unexpected content.
    return { action: 'blank', reason: 'none-remembered' };
  }

  // Desktop mode: single-user environment, load the newest project as a convenience.
  if (projectList.length > 0) {
    const newest = projectList
      .slice()
      .sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''))[0];
    return { action: 'load-newest', project: newest };
  }

  return { action: 'blank', reason: 'none-remembered' };
}
