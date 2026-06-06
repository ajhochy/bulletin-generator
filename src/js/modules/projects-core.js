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

export function buildProjectSaveRequest(project, { isServerMode, editorDisplayName }) {
  const requestProject = { ...project };
  if (isServerMode && editorDisplayName) {
    requestProject.updatedBy = editorDisplayName;
  }
  return requestProject;
}

export function deriveProjectSaveFailure({ errorStatus, isDesktopMode }) {
  if (errorStatus === 403) {
    return {
      type: 'forbidden',
      message: 'Only the project owner can edit this bulletin.',
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
 * Rules:
 * - Server mode: NEVER auto-loads a workspace project when no id is remembered.
 * - Desktop mode: preserves the legacy behavior of loading the newest project.
 */
export function deriveStartupRestore({ rememberedId, projects, isServerMode }) {
  const projectList = Array.isArray(projects) ? projects : [];

  if (rememberedId) {
    const found = projectList.find(p => p.id === rememberedId) || null;
    if (found) {
      return { action: 'load', project: found };
    }
    return {
      action: 'blank',
      reason: 'not-found',
      statusMessage: 'Your previous project is no longer accessible.',
    };
  }

  if (isServerMode) {
    return { action: 'blank', reason: 'none-remembered' };
  }

  if (projectList.length > 0) {
    const newest = projectList
      .slice()
      .sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''))[0];
    return { action: 'load-newest', project: newest };
  }

  return { action: 'blank', reason: 'none-remembered' };
}
