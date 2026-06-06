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
});
