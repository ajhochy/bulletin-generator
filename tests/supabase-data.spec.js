/**
 * supabase-data.spec.js
 * Unit tests for src/js/supabase-data.js — renderer-side Supabase data-access module.
 *
 * Strategy: dependency-injection. Every exported function accepts an optional
 * `client` argument so these tests pass in a fully-mocked supabase client.
 * No network calls, no real DB.
 *
 * Mock client shape:
 *   client.from(table) → chainable builder { select, eq, order, insert, upsert, update, delete }
 *   client.rpc(name, params) → thenable { data, error }
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  sdGetProjects,
  sdGetProject,
  sdSaveProject,
  sdDeleteProject,
  sdTransferProject,
  sdGetProjectHistory,
  sdRestoreProject,
  sdGetAnnouncements,
  sdSaveAnnouncements,
  sdGetSongs,
  sdSaveSongs,
  sdGetSettings,
  sdSaveSettings,
  sdGetMembers,
  sdGetPresence,
  sdPostPresenceHeartbeat,
  sdDeletePresence,
  sdGetTemplates,
  sdSaveTemplates,
} from '../src/js/supabase-data.js';

// ---------------------------------------------------------------------------
// Mock-client factory
// ---------------------------------------------------------------------------

/**
 * Build a chainable mock for client.from(table).
 *
 * @param {object} opts  { data, error }  — resolved at the end of the chain
 */
function makeMockFrom(opts = { data: [], error: null }) {
  const chain = {
    select: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    neq: vi.fn().mockReturnThis(),
    gt: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    insert: vi.fn().mockReturnThis(),
    upsert: vi.fn().mockReturnThis(),
    update: vi.fn().mockReturnThis(),
    delete: vi.fn().mockReturnThis(),
    single: vi.fn().mockResolvedValue(opts),
    // make the chain itself awaitable for non-single queries
    then: (resolve) => resolve(opts),
  };
  return chain;
}

/**
 * Build a complete mock Supabase client.
 *
 * @param {object} fromResult  default { data, error } returned by from()
 * @param {object} rpcResult   default { data, error } returned by rpc()
 */
function makeMockClient(
  fromResult = { data: [], error: null },
  rpcResult = { data: null, error: null },
) {
  const fromFn = vi.fn(() => makeMockFrom(fromResult));
  const rpcFn = vi.fn(async () => rpcResult);
  return { from: fromFn, rpc: rpcFn };
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

describe('sdGetProjects', () => {
  it('calls projects.select with the correct columns and returns data', async () => {
    const mockProjects = [{ id: 'proj_abc', name: 'Test', visibility: 'workspace' }];
    const chain = makeMockFrom({ data: mockProjects, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdGetProjects({ client });

    expect(client.from).toHaveBeenCalledWith('projects');
    expect(chain.select).toHaveBeenCalled();
    expect(chain.order).toHaveBeenCalledWith('updated_at', expect.objectContaining({ ascending: false }));
    expect(result).toEqual(mockProjects);
  });

  it('throws when supabase returns an error', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'DB error' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdGetProjects({ client })).rejects.toThrow('DB error');
  });
});

describe('sdGetProject', () => {
  it('calls projects table with eq(id) and returns a single project', async () => {
    const mockProject = { id: 'proj_123', name: 'My Bulletin', state: { items: [] } };
    const chain = makeMockFrom({ data: mockProject, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdGetProject('proj_123', { client });

    expect(client.from).toHaveBeenCalledWith('projects');
    expect(chain.select).toHaveBeenCalled();
    expect(chain.eq).toHaveBeenCalledWith('id', 'proj_123');
    expect(chain.single).toHaveBeenCalled();
    expect(result).toEqual(mockProject);
  });

  it('throws when project is not found (error from supabase)', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'Not found', code: 'PGRST116' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdGetProject('proj_missing', { client })).rejects.toThrow();
  });
});

describe('sdSaveProject', () => {
  it('upserts project with the correct columns', async () => {
    const project = {
      id: 'proj_abc',
      name: 'My Bulletin',
      state: { items: [{ type: 'song', title: 'Amazing Grace' }] },
      owner_user_id: 'user-uuid-1',
      workspace_id: 'ws-uuid-1',
      visibility: 'workspace',
    };
    const saved = { ...project, revision: 2 };
    const chain = makeMockFrom({ data: [saved], error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdSaveProject(project, { client });

    expect(client.from).toHaveBeenCalledWith('projects');
    expect(chain.upsert).toHaveBeenCalled();
    // Verify upsert payload includes key project fields
    const upsertArg = chain.upsert.mock.calls[0][0];
    expect(upsertArg).toMatchObject({
      id: 'proj_abc',
      name: 'My Bulletin',
    });
    expect(result).toEqual(saved);
  });

  it('throws on supabase error during save', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'constraint violation' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdSaveProject({ id: 'proj_x', name: 'Test' }, { client })).rejects.toThrow('constraint violation');
  });
});

describe('sdDeleteProject', () => {
  it('calls delete on projects table with the project id', async () => {
    const chain = makeMockFrom({ data: null, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await sdDeleteProject('proj_abc', { client });

    expect(client.from).toHaveBeenCalledWith('projects');
    expect(chain.delete).toHaveBeenCalled();
    expect(chain.eq).toHaveBeenCalledWith('id', 'proj_abc');
  });

  it('throws on supabase error during delete', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'permission denied' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdDeleteProject('proj_abc', { client })).rejects.toThrow('permission denied');
  });
});

// ---------------------------------------------------------------------------
// Transfer
// ---------------------------------------------------------------------------

describe('sdTransferProject', () => {
  it('calls rpc transfer_project_owner with the correct param names', async () => {
    const client = makeMockClient(undefined, { data: { id: 'proj_abc', owner_user_id: 'user-2' }, error: null });

    const result = await sdTransferProject('proj_abc', 'user-2', { client });

    expect(client.rpc).toHaveBeenCalledWith('transfer_project_owner', {
      p_project_id: 'proj_abc',
      p_to_user_id: 'user-2',
    });
    expect(result).toMatchObject({ owner_user_id: 'user-2' });
  });

  it('throws when rpc returns an error', async () => {
    const client = makeMockClient(undefined, { data: null, error: { message: 'not owner' } });

    await expect(sdTransferProject('proj_abc', 'user-2', { client })).rejects.toThrow('not owner');
  });
});

// ---------------------------------------------------------------------------
// Project history
// ---------------------------------------------------------------------------

describe('sdGetProjectHistory', () => {
  it('queries project_revisions with the project_id filter', async () => {
    const mockRevisions = [
      { id: 'rev-1', project_id: 'proj_abc', revision_number: 2, created_at: '2026-06-01' },
      { id: 'rev-2', project_id: 'proj_abc', revision_number: 1, created_at: '2026-05-30' },
    ];
    const chain = makeMockFrom({ data: mockRevisions, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdGetProjectHistory('proj_abc', { client });

    expect(client.from).toHaveBeenCalledWith('project_revisions');
    expect(chain.select).toHaveBeenCalled();
    expect(chain.eq).toHaveBeenCalledWith('project_id', 'proj_abc');
    expect(chain.order).toHaveBeenCalledWith('revision_number', expect.objectContaining({ ascending: false }));
    expect(result).toEqual(mockRevisions);
  });

  it('throws on supabase error', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'forbidden' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdGetProjectHistory('proj_abc', { client })).rejects.toThrow('forbidden');
  });
});

// ---------------------------------------------------------------------------
// sdRestoreProject — minimal: fetch revision state + upsert as new head
// ---------------------------------------------------------------------------

describe('sdRestoreProject', () => {
  it('fetches the revision state and upserts it as the current project state', async () => {
    const revisionState = { id: 'proj_abc', name: 'My Bulletin', items: [] };
    const revisionData = {
      id: 'rev-2', project_id: 'proj_abc', revision_number: 1, state: revisionState,
    };
    // First from() call is for project_revisions (single), second for projects (upsert)
    let callCount = 0;
    const revisionChain = makeMockFrom({ data: revisionData, error: null });
    const upsertChain = makeMockFrom({ data: [{ id: 'proj_abc', name: 'My Bulletin', revision: 3 }], error: null });
    const client = {
      from: vi.fn(() => {
        callCount++;
        return callCount === 1 ? revisionChain : upsertChain;
      }),
      rpc: vi.fn(),
    };

    const result = await sdRestoreProject('proj_abc', 1, { client });

    // Should have queried project_revisions
    expect(client.from).toHaveBeenCalledWith('project_revisions');
    // Should have upserted back into projects
    expect(client.from).toHaveBeenCalledWith('projects');
    expect(result).toMatchObject({ id: 'proj_abc' });
  });

  it('throws when the target revision is not found', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'Not found', code: 'PGRST116' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdRestoreProject('proj_abc', 99, { client })).rejects.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Announcements
// ---------------------------------------------------------------------------

describe('sdGetAnnouncements', () => {
  it('queries the announcements table and returns the data array', async () => {
    const mockAnns = [{ id: 'ann-1', title: 'Event', body: 'Join us', state: {} }];
    const chain = makeMockFrom({ data: mockAnns, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdGetAnnouncements({ client });

    expect(client.from).toHaveBeenCalledWith('announcements');
    expect(chain.select).toHaveBeenCalled();
    expect(chain.order).toHaveBeenCalledWith('created_at', expect.objectContaining({ ascending: true }));
    expect(result).toEqual(mockAnns);
  });

  it('throws on supabase error', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'rls fail' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdGetAnnouncements({ client })).rejects.toThrow('rls fail');
  });
});

describe('sdSaveAnnouncements', () => {
  it('upserts each announcement with the required fields', async () => {
    const anns = [
      { id: 'ann-1', title: 'Potluck', body: 'Join us Sunday', url: '' },
    ];
    const chain = makeMockFrom({ data: anns, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdSaveAnnouncements(anns, { client });

    expect(client.from).toHaveBeenCalledWith('announcements');
    expect(chain.upsert).toHaveBeenCalled();
    const upsertArg = chain.upsert.mock.calls[0][0];
    expect(Array.isArray(upsertArg)).toBe(true);
    expect(upsertArg[0]).toMatchObject({ id: 'ann-1', title: 'Potluck' });
    expect(result).toEqual(anns);
  });

  it('throws on supabase error during save', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'constraint error' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdSaveAnnouncements([{ title: 'test' }], { client })).rejects.toThrow('constraint error');
  });
});

// ---------------------------------------------------------------------------
// Songs
// ---------------------------------------------------------------------------

describe('sdGetSongs', () => {
  it('queries the songs table ordered by title', async () => {
    const mockSongs = [{ id: 'song-1', title: 'Amazing Grace', data: {} }];
    const chain = makeMockFrom({ data: mockSongs, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdGetSongs({ client });

    expect(client.from).toHaveBeenCalledWith('songs');
    expect(chain.select).toHaveBeenCalled();
    expect(chain.order).toHaveBeenCalledWith('title', expect.objectContaining({ ascending: true }));
    expect(result).toEqual(mockSongs);
  });

  it('throws on supabase error', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'db fail' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdGetSongs({ client })).rejects.toThrow('db fail');
  });
});

describe('sdSaveSongs', () => {
  it('upserts songs without deleting existing rows', async () => {
    const songs = [{ id: 'song-1', title: 'Amazing Grace', author: 'Newton' }];
    const chain = makeMockFrom({ data: songs, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await sdSaveSongs(songs, { client });

    expect(client.from).toHaveBeenCalledWith('songs');
    expect(chain.upsert).toHaveBeenCalled();
    // Must NOT call delete (sdSaveSongs is additive like storage.save_songs)
    expect(chain.delete).not.toHaveBeenCalled();
  });

  it('throws on supabase error during save', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'upsert fail' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdSaveSongs([{ title: 'Test' }], { client })).rejects.toThrow('upsert fail');
  });
});

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

describe('sdGetSettings', () => {
  it('queries workspace_settings and returns the settings blob', async () => {
    const mockRow = { workspace_id: 'ws-1', settings: { pcoToken: 'abc' } };
    const chain = makeMockFrom({ data: [mockRow], error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdGetSettings({ client });

    expect(client.from).toHaveBeenCalledWith('workspace_settings');
    expect(chain.select).toHaveBeenCalled();
    expect(result).toEqual([mockRow]);
  });

  it('throws on supabase error', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'no row' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdGetSettings({ client })).rejects.toThrow('no row');
  });
});

describe('sdSaveSettings', () => {
  it('upserts into workspace_settings with the settings blob', async () => {
    const settings = { pcoToken: 'tok-123', typeFormats: {} };
    const chain = makeMockFrom({ data: [{ settings }], error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdSaveSettings(settings, { client });

    expect(client.from).toHaveBeenCalledWith('workspace_settings');
    expect(chain.upsert).toHaveBeenCalled();
    const upsertArg = chain.upsert.mock.calls[0][0];
    expect(upsertArg).toMatchObject({ settings });
    expect(result).toEqual([{ settings }]);
  });

  it('throws on supabase error during save', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'forbidden' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdSaveSettings({}, { client })).rejects.toThrow('forbidden');
  });
});

// ---------------------------------------------------------------------------
// Workspace members
// ---------------------------------------------------------------------------

describe('sdGetMembers', () => {
  it('queries workspace_members with profiles join', async () => {
    const mockMembers = [
      { user_id: 'user-1', role: 'owner', profiles: { display_name: 'Alice', email: 'alice@example.com' } },
    ];
    const chain = makeMockFrom({ data: mockMembers, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdGetMembers({ client });

    expect(client.from).toHaveBeenCalledWith('workspace_members');
    expect(chain.select).toHaveBeenCalledWith(expect.stringContaining('profiles'));
    expect(result).toEqual(mockMembers);
  });

  it('throws on supabase error', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'rls reject' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdGetMembers({ client })).rejects.toThrow('rls reject');
  });
});

// ---------------------------------------------------------------------------
// Presence
// ---------------------------------------------------------------------------

describe('sdGetPresence', () => {
  it('queries workspace_presences filtered by project_id', async () => {
    const mockPresence = [
      { user_id: 'user-1', display_name: 'Alice', last_seen_at: '2026-06-06T12:00:00Z' },
    ];
    const chain = makeMockFrom({ data: mockPresence, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdGetPresence('proj_abc', { client });

    expect(client.from).toHaveBeenCalledWith('workspace_presences');
    expect(chain.select).toHaveBeenCalled();
    // must NOT select the non-existent display_name column (that returns 400)
    expect(chain.select).not.toHaveBeenCalledWith(expect.stringContaining('display_name'));
    expect(chain.eq).toHaveBeenCalledWith('project_id', 'proj_abc');
    // 90s TTL filter applied server-side
    expect(chain.gt).toHaveBeenCalledWith('last_seen_at', expect.any(String));
    expect(result).toEqual(mockPresence);
  });

  it('throws on supabase error', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'not member' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdGetPresence('proj_abc', { client })).rejects.toThrow('not member');
  });
});

describe('sdPostPresenceHeartbeat', () => {
  it('upserts a presence row for the given project_id', async () => {
    const chain = makeMockFrom({ data: null, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await sdPostPresenceHeartbeat('proj_abc', { client });

    expect(client.from).toHaveBeenCalledWith('workspace_presences');
    expect(chain.upsert).toHaveBeenCalled();
    const upsertArg = chain.upsert.mock.calls[0][0];
    expect(upsertArg).toMatchObject({ project_id: 'proj_abc' });
  });

  it('throws on supabase error', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'upsert fail' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdPostPresenceHeartbeat('proj_abc', { client })).rejects.toThrow('upsert fail');
  });
});

describe('sdDeletePresence', () => {
  it('deletes workspace_presences for the current user', async () => {
    const chain = makeMockFrom({ data: null, error: null });
    // The function deletes by user_id which it resolves from the Supabase session.
    // We pass userId directly via the opts to avoid needing auth context in tests.
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await sdDeletePresence({ client, userId: 'user-test-1' });

    expect(client.from).toHaveBeenCalledWith('workspace_presences');
    expect(chain.delete).toHaveBeenCalled();
    expect(chain.eq).toHaveBeenCalledWith('user_id', 'user-test-1');
  });

  it('throws on supabase error', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'delete fail' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdDeletePresence({ client, userId: 'user-1' })).rejects.toThrow('delete fail');
  });
});

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

describe('sdGetTemplates', () => {
  it('queries the templates table ordered by is_default desc, name asc', async () => {
    const mockTemplates = [
      { id: 'tpl-1', name: 'Default', template_data: {}, is_default: true },
    ];
    const chain = makeMockFrom({ data: mockTemplates, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    const result = await sdGetTemplates({ client });

    expect(client.from).toHaveBeenCalledWith('templates');
    expect(chain.select).toHaveBeenCalled();
    expect(chain.order).toHaveBeenCalled();
    expect(result).toEqual(mockTemplates);
  });

  it('throws on supabase error', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'access denied' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdGetTemplates({ client })).rejects.toThrow('access denied');
  });
});

describe('sdSaveTemplates', () => {
  it('upserts non-default templates only (skips built-ins)', async () => {
    const templates = [
      { id: 'tpl-1', name: 'My Template', template_data: {}, is_default: false },
      { id: 'tpl-default', name: 'Classic', template_data: {}, is_default: true },
    ];
    const chain = makeMockFrom({ data: templates, error: null });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await sdSaveTemplates(templates, { client });

    expect(client.from).toHaveBeenCalledWith('templates');
    expect(chain.upsert).toHaveBeenCalled();
    // The upserted array must NOT include the default template
    const upsertArg = chain.upsert.mock.calls[0][0];
    expect(upsertArg.some(t => t.id === 'tpl-default')).toBe(false);
    expect(upsertArg.some(t => t.id === 'tpl-1')).toBe(true);
  });

  it('throws on supabase error during save', async () => {
    const chain = makeMockFrom({ data: null, error: { message: 'upsert fail' } });
    const client = { from: vi.fn(() => chain), rpc: vi.fn() };

    await expect(sdSaveTemplates([{ id: 'x', name: 'T', is_default: false }], { client })).rejects.toThrow('upsert fail');
  });
});
