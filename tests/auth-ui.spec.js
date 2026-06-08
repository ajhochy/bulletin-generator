import { beforeEach, describe, expect, it, vi } from 'vitest';

async function loadAuthUi() {
  await import('../src/js/auth-ui.js');
  return globalThis.BulletinAuthUI;
}

function renderAuthDom() {
  document.body.innerHTML = `
    <div id="login-screen" style="display:none">
      <button id="login-google-btn" type="button"></button>
      <input id="login-email-input" />
      <button id="login-magic-btn" type="button"></button>
      <div id="login-message" style="display:none"></div>
    </div>
    <div id="app-container"></div>
    <div id="user-info"></div>
  `;
}

describe('auth-ui initAuth', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.resetModules();
    delete globalThis.BulletinAuthUI;
    renderAuthDom();
    globalThis.BULLETIN_SUPABASE_CONFIG = {
      url: 'https://example.supabase.co',
      anonKey: 'anon-key',
    };
  });

  it('shows the login screen when Supabase has no active session', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 401 })));
    vi.stubGlobal('createSupabaseClient', vi.fn(() => ({
      auth: {
        getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
        onAuthStateChange: vi.fn(),
      },
    })));

    const authUi = await loadAuthUi();
    const result = await authUi.initAuth();

    expect(result).toBe(false);
    expect(document.getElementById('login-screen').style.display).toBe('flex');
    expect(document.getElementById('app-container').style.display).toBe('none');
  });

  it('shows the app when Supabase has an active session and /api/me accepts it', async () => {
    const session = {
      access_token: 'token-123',
      user: { email: 'fallback@example.com' },
    };
    const fetchMock = vi.fn(async (_url, opts = {}) => {
      if (opts.headers?.Authorization === 'Bearer token-123') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ user: { email: 'user@example.com', displayName: 'User Example' } }),
        };
      }
      return { ok: false, status: 401 };
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('createSupabaseClient', vi.fn(() => ({
      auth: {
        getSession: vi.fn(async () => ({ data: { session }, error: null })),
        onAuthStateChange: vi.fn(),
      },
    })));

    const authUi = await loadAuthUi();
    const result = await authUi.initAuth();

    expect(result).toBe(true);
    expect(document.getElementById('login-screen').style.display).toBe('none');
    expect(document.getElementById('app-container').style.display).toBe('');
    expect(document.querySelector('.user-info-name').textContent).toBe('User Example');
    expect(fetchMock).toHaveBeenCalledWith('/api/me', {
      headers: { Authorization: 'Bearer token-123' },
    });
  });

  // Regression: issue #277-F electron-mode deadlock.
  //
  // supabase-js dispatches auth-state-change events while holding GoTrue's
  // internal auth lock. If the onAuthStateChange callback is `async` and awaits
  // a Supabase call (initAuth -> _applySession -> _fetchIdentityWithSession ->
  // client.from(...)), it reentrantly waits on that same lock and deadlocks
  // initialisation — getSession() never resolves and the app hangs in its
  // default shell. The callback MUST be synchronous and defer its Supabase work
  // to a fresh macrotask.
  it('defers SIGNED_IN handling out of the onAuthStateChange callback (no reentrant Supabase call)', async () => {
    vi.useFakeTimers();
    let authCallback = null;
    const session = { access_token: 'tok-x', user: { email: 'a@b.com' } };
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ user: { email: 'a@b.com' } }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('createSupabaseClient', vi.fn(() => ({
      auth: {
        getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
        onAuthStateChange: vi.fn((cb) => { authCallback = cb; }),
      },
    })));

    const authUi = await loadAuthUi();
    await authUi.initAuth();

    expect(typeof authCallback).toBe('function');
    fetchMock.mockClear();

    // Invoking the callback must return synchronously (not a Promise) and must
    // NOT trigger the /api/me identity fetch inline — that would mean the work
    // ran inside the lock-holding callback.
    const ret = authCallback('SIGNED_IN', session);
    expect(ret).toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();

    // The deferred work runs on the next macrotask.
    await vi.runAllTimersAsync();
    expect(fetchMock).toHaveBeenCalledWith('/api/me', {
      headers: { Authorization: 'Bearer tok-x' },
    });
    vi.useRealTimers();
  });

  // Regression: issue #277-F. In Electron the supabase-js Web Locks
  // (navigator.locks) auth lock can hang the sandboxed renderer, so the client
  // must be created with a pass-through `lock`. Server/browser mode keeps the
  // default lock (no `lock` option) for cross-tab coordination.
  it('creates the Supabase client with a pass-through lock in Electron mode', async () => {
    const createSpy = vi.fn(() => ({
      auth: {
        getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
        onAuthStateChange: vi.fn(),
      },
    }));
    vi.stubGlobal('createSupabaseClient', createSpy);
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 401 })));
    // Electron bridge present → _isElectronMode() true.
    window.electronAuth = { onCallback: () => {} };

    const authUi = await loadAuthUi();
    await authUi.initAuth();

    expect(createSpy).toHaveBeenCalledTimes(1);
    const opts = createSpy.mock.calls[0][2];
    expect(typeof opts.auth.lock).toBe('function');
    // Pass-through: it simply runs the critical section.
    const sentinel = Symbol('ran');
    expect(opts.auth.lock('name', 0, () => sentinel)).toBe(sentinel);

    delete window.electronAuth;
  });

  it('omits the lock option in server/browser mode (keeps default Web Locks)', async () => {
    const createSpy = vi.fn(() => ({
      auth: {
        getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
        onAuthStateChange: vi.fn(),
      },
    }));
    vi.stubGlobal('createSupabaseClient', createSpy);
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 401 })));
    // No window.electronAuth → server/browser mode.

    const authUi = await loadAuthUi();
    await authUi.initAuth();

    expect(createSpy).toHaveBeenCalledTimes(1);
    const opts = createSpy.mock.calls[0][2];
    expect(opts.auth.lock).toBeUndefined();
  });
});
