import { describe, expect, it } from 'vitest';
import {
  buildProjectSaveRequest,
  cloneItemsData,
  deriveProjectSaveFailure,
  deriveProjectSaveSuccess,
} from '../src/js/modules/projects-core.js';

describe('projects core', () => {
  it('clones persisted item fields without sharing references', () => {
    const source = [{
      type: 'hymn',
      title: 'Song',
      detail: 'Lyrics',
      _fmt: { titleBold: true },
      _noBreakBeforeStanzas: [1],
    }];

    const cloned = cloneItemsData(source);
    expect(cloned).toEqual([{
      type: 'song',
      title: 'Song',
      detail: 'Lyrics',
      _fmt: { titleBold: true },
      _noBreakBeforeStanzas: [1],
    }]);
    expect(cloned[0]).not.toBe(source[0]);
    expect(cloned[0]._fmt).not.toBe(source[0]._fmt);
  });

  it('adds revision and editor metadata for server saves', () => {
    const request = buildProjectSaveRequest(
      { id: 'abc', name: 'Project' },
      { isServerMode: true, editorDisplayName: 'AJ', loadedRevision: 5 }
    );
    expect(request).toMatchObject({
      id: 'abc',
      name: 'Project',
      updatedBy: 'AJ',
      _clientRevision: 5,
    });
  });

  it('derives save success state from server revision', () => {
    expect(deriveProjectSaveSuccess({
      result: { revision: 8 },
      isServerMode: true,
      currentLoadedRevision: 5,
      storedProject: { revision: 5 },
    })).toEqual({
      loadedRevision: 8,
      storedRevision: 8,
      hideStaleBanner: true,
      hideConflictBanner: true,
    });
  });

  it('derives conflict and generic save failures', () => {
    expect(deriveProjectSaveFailure({ errorStatus: 409, isDesktopMode: false })).toEqual({
      type: 'conflict',
      message: 'This bulletin was updated by someone else.',
    });

    expect(deriveProjectSaveFailure({ errorStatus: 500, isDesktopMode: true })).toEqual({
      type: 'generic',
      message: 'Could not save project.',
    });
  });
});
