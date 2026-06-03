// auth-ui.js - Supabase browser auth for server mode

let _supabaseClient = null;
let _currentSession = null;
let _currentUser = null;

function _authConfig() {
  return globalThis.BULLETIN_SUPABASE_CONFIG || {};
}

function _authRedirectUrl() {
  return `${window.location.origin}${window.location.pathname}`;
}

function _getSupabaseClient() {
  if (_supabaseClient) return _supabaseClient;
  const config = _authConfig();
  const createClient = typeof createSupabaseClient === 'function'
    ? createSupabaseClient
    : globalThis.supabase?.createClient;
  if (!config.url || !config.anonKey || typeof createClient !== 'function') {
    return null;
  }
  _supabaseClient = createClient(config.url, config.anonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      storage: window.localStorage,
    },
  });
  return _supabaseClient;
}

function getCurrentUser() {
  return _currentUser;
}

function getSession() {
  return _currentSession;
}

function showLoginScreen(message = '') {
  const loginScreen = document.getElementById('login-screen');
  const appContainer = document.getElementById('app-container');
  const loginMessage = document.getElementById('login-message');
  if (loginScreen) loginScreen.style.display = 'flex';
  if (appContainer) appContainer.style.display = 'none';
  if (loginMessage) {
    loginMessage.textContent = message;
    loginMessage.style.display = message ? 'block' : 'none';
  }
}

function showApp(user = null) {
  const loginScreen = document.getElementById('login-screen');
  const appContainer = document.getElementById('app-container');
  if (loginScreen) loginScreen.style.display = 'none';
  if (appContainer) appContainer.style.display = '';
  _currentUser = user;
  _renderUserInfo(user);
}

function _renderUserInfo(user) {
  const userInfo = document.getElementById('user-info');
  if (!userInfo) return;
  userInfo.innerHTML = '';

  if (!user) {
    userInfo.style.display = 'none';
    return;
  }

  const metadata = user.user_metadata || user.raw_user_meta_data || {};
  const avatarUrl = user.avatarUrl || metadata.avatar_url || metadata.picture || '';
  const label = user.displayName || metadata.full_name || metadata.name || user.email || '';

  userInfo.style.display = 'flex';

  if (avatarUrl) {
    const avatarEl = document.createElement('img');
    avatarEl.className = 'user-info-avatar';
    avatarEl.alt = '';
    avatarEl.width = 32;
    avatarEl.height = 32;
    avatarEl.src = avatarUrl;
    avatarEl.title = user.email || '';
    userInfo.appendChild(avatarEl);
  }

  const nameEl = document.createElement('span');
  nameEl.className = 'user-info-name';
  nameEl.textContent = label;
  userInfo.appendChild(nameEl);

  const signOutBtn = document.createElement('button');
  signOutBtn.className = 'user-info-signout btn btn-ghost btn-xs';
  signOutBtn.type = 'button';
  signOutBtn.textContent = 'Sign out';
  signOutBtn.addEventListener('click', () => signOut());
  userInfo.appendChild(signOutBtn);
}

async function _fetchIdentityWithSession(session) {
  const token = session?.access_token;
  if (!token) return null;
  const res = await fetch('/api/me', {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = new Error(`Identity check failed with ${res.status}`);
    err.status = res.status;
    throw err;
  }
  const data = await res.json();
  return data.user || session.user || null;
}

async function _isDesktopModeWithoutAuth() {
  try {
    const res = await fetch('/api/me');
    if (!res.ok) return false;
    const data = await res.json();
    return data.mode === 'desktop';
  } catch (_) {
    return false;
  }
}

async function signInWithGoogle() {
  const client = _getSupabaseClient();
  if (!client) {
    showLoginScreen('Supabase Auth is not configured for this deployment.');
    return null;
  }
  const { data, error } = await client.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: _authRedirectUrl() },
  });
  if (error) {
    showLoginScreen(error.message || 'Google sign-in failed.');
    throw error;
  }
  return data;
}

async function signInWithMagicLink(email) {
  const normalizedEmail = String(email || '').trim();
  if (!normalizedEmail) {
    showLoginScreen('Enter an email address to receive a magic link.');
    return null;
  }
  const client = _getSupabaseClient();
  if (!client) {
    showLoginScreen('Supabase Auth is not configured for this deployment.');
    return null;
  }
  const { data, error } = await client.auth.signInWithOtp({
    email: normalizedEmail,
    options: { emailRedirectTo: _authRedirectUrl() },
  });
  if (error) {
    showLoginScreen(error.message || 'Magic-link sign-in failed.');
    throw error;
  }
  showLoginScreen('Check your email for a sign-in link.');
  return data;
}

async function signOut() {
  const client = _getSupabaseClient();
  if (client) {
    await client.auth.signOut().catch(() => {});
  }
  _currentSession = null;
  _currentUser = null;
  showLoginScreen();
}

function _wireLoginControls() {
  const googleBtn = document.getElementById('login-google-btn');
  const emailInput = document.getElementById('login-email-input');
  const magicBtn = document.getElementById('login-magic-btn');

  if (googleBtn && !googleBtn.dataset.authWired) {
    googleBtn.dataset.authWired = '1';
    googleBtn.addEventListener('click', () => {
      signInWithGoogle().catch(err => console.warn('[auth] Google sign-in failed:', err.message || err));
    });
  }

  if (magicBtn && !magicBtn.dataset.authWired) {
    magicBtn.dataset.authWired = '1';
    magicBtn.addEventListener('click', () => {
      signInWithMagicLink(emailInput?.value).catch(err => console.warn('[auth] Magic link failed:', err.message || err));
    });
  }
}

async function initAuth() {
  _wireLoginControls();

  if (await _isDesktopModeWithoutAuth()) {
    showApp(null);
    return true;
  }

  const client = _getSupabaseClient();
  if (!client) {
    showLoginScreen('Supabase Auth is not configured for this deployment.');
    return false;
  }

  async function _applySession(session) {
    if (!session) {
      _currentSession = null;
      _currentUser = null;
      showLoginScreen();
      return;
    }
    _currentSession = session;
    try {
      _currentUser = await _fetchIdentityWithSession(session);
      showApp(_currentUser || session.user || null);
    } catch (err) {
      await client.auth.signOut().catch(() => {});
      _currentSession = null;
      _currentUser = null;
      showLoginScreen(err.status === 403 ? 'Your account is not assigned to a workspace.' : '');
    }
  }

  // Wire BEFORE getSession so the SIGNED_IN event from an in-progress
  // OAuth PKCE exchange is not missed if getSession() returns null.
  client.auth.onAuthStateChange(async (event, session) => {
    if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
      await _applySession(session);
    } else if (event === 'SIGNED_OUT') {
      _currentSession = null;
      _currentUser = null;
      showLoginScreen();
    }
  });

  const { data, error } = await client.auth.getSession();
  if (!error && data?.session) {
    await _applySession(data.session);
    return true;
  }

  showLoginScreen();
  return false;
}

Object.assign(globalThis, {
  BulletinAuthUI: {
    initAuth,
    signInWithGoogle,
    signInWithMagicLink,
    signOut,
    getSession,
    getCurrentUser,
    showLoginScreen,
    showApp,
  },
  initAuth,
  signInWithGoogle,
  signInWithMagicLink,
  signOut,
  getSession,
  getCurrentUser,
  showLoginScreen,
  showApp,
});
