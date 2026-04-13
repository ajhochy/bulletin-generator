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
