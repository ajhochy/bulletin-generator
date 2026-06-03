import { describe, expect, it } from 'vitest';
import {
  buildProjectSaveRequest,
  cloneItemsData,
  deriveProjectSaveFailure,
  deriveProjectSaveSuccess,
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

describe('deriveStartupRestore', () => {
  const projectA = { id: 'a', name: 'Project A', updatedAt: '2026-05-20T10:00:00Z' };
  const projectB = { id: 'b', name: 'Project B', updatedAt: '2026-05-19T10:00:00Z' };

  it('restores the remembered project when it exists (server mode)', () => {
    const result = deriveStartupRestore({
      rememberedId: 'a',
      projects: [projectA, projectB],
      isServerMode: true,
    });
    expect(result).toEqual({ action: 'load', project: projectA });
  });

  it('restores the remembered project when it exists (desktop mode)', () => {
    const result = deriveStartupRestore({
      rememberedId: 'b',
      projects: [projectA, projectB],
      isServerMode: false,
    });
    expect(result).toEqual({ action: 'load', project: projectB });
  });

  it('returns blank with statusMessage when remembered project is not found (server mode)', () => {
    const result = deriveStartupRestore({
      rememberedId: 'missing-id',
      projects: [projectA, projectB],
      isServerMode: true,
    });
    expect(result).toMatchObject({
      action: 'blank',
      reason: 'not-found',
      statusMessage: expect.any(String),
    });
    expect(result.statusMessage.length).toBeGreaterThan(0);
  });

  it('returns blank with statusMessage when remembered project is not found (desktop mode)', () => {
    const result = deriveStartupRestore({
      rememberedId: 'missing-id',
      projects: [projectA, projectB],
      isServerMode: false,
    });
    expect(result).toMatchObject({ action: 'blank', reason: 'not-found' });
  });

  it('returns blank in server mode when no project is remembered — never auto-loads workspace project', () => {
    // Core safety rule: fresh browser in server mode must not open another user's project.
    const result = deriveStartupRestore({
      rememberedId: '',
      projects: [projectA, projectB],
      isServerMode: true,
    });
    expect(result).toEqual({ action: 'blank', reason: 'none-remembered' });
  });

  it('loads newest project in desktop mode when no project is remembered', () => {
    const result = deriveStartupRestore({
      rememberedId: '',
      projects: [projectB, projectA], // B listed first but A is newer
      isServerMode: false,
    });
    expect(result).toEqual({ action: 'load-newest', project: projectA });
  });

  it('returns blank in desktop mode when no project is remembered and list is empty', () => {
    const result = deriveStartupRestore({
      rememberedId: '',
      projects: [],
      isServerMode: false,
    });
    expect(result).toEqual({ action: 'blank', reason: 'none-remembered' });
  });

  it('returns blank in server mode regardless of how many projects exist', () => {
    // Even with 100 projects, a fresh server-mode browser must start blank.
    const manyProjects = Array.from({ length: 5 }, (_, i) => ({
      id: String(i),
      name: `Project ${i}`,
      updatedAt: `2026-05-1${i}T00:00:00Z`,
    }));
    const result = deriveStartupRestore({
      rememberedId: '',
      projects: manyProjects,
      isServerMode: true,
    });
    expect(result).toEqual({ action: 'blank', reason: 'none-remembered' });
  });
});
