import { describe, expect, it } from 'vitest';
import {
  buildProjectSaveRequest,
  cloneItemsData,
  deriveProjectSaveFailure,
  deriveStartupRestore,
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

  it('adds editor metadata for server saves (no _clientRevision)', () => {
    const request = buildProjectSaveRequest(
      { id: 'abc', name: 'Project' },
      { isServerMode: true, editorDisplayName: 'AJ' }
    );
    expect(request).toMatchObject({
      id: 'abc',
      name: 'Project',
      updatedBy: 'AJ',
    });
    expect(request).not.toHaveProperty('_clientRevision');
  });

  it('does not add updatedBy in desktop mode', () => {
    const request = buildProjectSaveRequest(
      { id: 'xyz', name: 'Desktop Project' },
      { isServerMode: false, editorDisplayName: 'Local' }
    );
    expect(request).not.toHaveProperty('updatedBy');
    expect(request).not.toHaveProperty('_clientRevision');
  });

  it('shows forbidden toast when non-owner tries to save (403)', () => {
    expect(deriveProjectSaveFailure({ errorStatus: 403, isDesktopMode: false })).toEqual({
      type: 'forbidden',
      message: 'Only the project owner can edit this bulletin.',
    });
  });

  it('shows generic error for other server failures', () => {
    expect(deriveProjectSaveFailure({ errorStatus: 500, isDesktopMode: false })).toEqual({
      type: 'generic',
      message: 'Could not save project to server.',
    });

    expect(deriveProjectSaveFailure({ errorStatus: 500, isDesktopMode: true })).toEqual({
      type: 'generic',
      message: 'Could not save project.',
    });
  });
});
