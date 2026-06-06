// auth.js — frontend auth state for server mode

// ── State ──────────────────────────────────────────────────────────────────────

let _currentUser = null;

function getCurrentUser() {
  return _currentUser;
}

// ── API calls ──────────────────────────────────────────────────────────────────

/**
 * GET /api/me — return the user object or null on 401.
 */
async function fetchCurrentUser() {
  try {
    const data = await apiFetch('/api/me');
    return data.user || null;
  } catch (e) {
    if (e.status === 401) return null;
    // Any other error (network, 500) — treat as unauthenticated to be safe
    console.warn('[auth] fetchCurrentUser error:', e.message);
    return null;
  }
}

/**
 * POST /auth/logout — clear session cookie server-side, then show login screen.
 */
async function logout() {
  try {
    await apiFetch('/auth/logout', 'POST');
  } catch (_) {
    // Ignore errors — proceed with client-side cleanup regardless
  }
  _currentUser = null;
  showLoginScreen();
}

// ── UI ─────────────────────────────────────────────────────────────────────────

/**
 * Hide the main app, show the login screen.
 */
function showLoginScreen() {
  const loginScreen = document.getElementById('login-screen');
  const appContainer = document.getElementById('app-container');
  if (loginScreen)   loginScreen.style.display  = 'flex';
  if (appContainer)  appContainer.style.display  = 'none';
}

/**
 * Hide the login screen, show the app, and update the user info area.
 */
function showApp(user) {
  const loginScreen = document.getElementById('login-screen');
  const appContainer = document.getElementById('app-container');
  if (loginScreen)  loginScreen.style.display  = 'none';
  if (appContainer) appContainer.style.display  = '';

  _currentUser = user;
  _renderUserInfo(user);
}

/**
 * Populate #user-info with avatar, display name, and sign-out button.
 * Hidden entirely in desktop mode (no user object).
 */
function _renderUserInfo(user) {
  const userInfo = document.getElementById('user-info');
  if (!userInfo) return;

  if (!user) {
    // Desktop mode — hide the area entirely
    userInfo.style.display = 'none';
    return;
  }

  userInfo.style.display = 'flex';

  // Avatar
  let avatarEl = userInfo.querySelector('.user-info-avatar');
  if (!avatarEl) {
    avatarEl = document.createElement('img');
    avatarEl.className = 'user-info-avatar';
    avatarEl.alt = '';
    avatarEl.width = 32;
    avatarEl.height = 32;
    userInfo.appendChild(avatarEl);
  }
  avatarEl.src   = user.avatarUrl  || '';
  avatarEl.title = user.email      || '';
  avatarEl.style.display = user.avatarUrl ? '' : 'none';

  // Name
  let nameEl = userInfo.querySelector('.user-info-name');
  if (!nameEl) {
    nameEl = document.createElement('span');
    nameEl.className = 'user-info-name';
    userInfo.appendChild(nameEl);
  }
  nameEl.textContent = user.displayName || user.email || '';

  // Sign-out button
  let signOutBtn = userInfo.querySelector('.user-info-signout');
  if (!signOutBtn) {
    signOutBtn = document.createElement('button');
    signOutBtn.className = 'user-info-signout btn btn-ghost btn-xs';
    signOutBtn.textContent = 'Sign out';
    signOutBtn.addEventListener('click', () => logout());
    userInfo.appendChild(signOutBtn);
  }
}

// ── Entry point ────────────────────────────────────────────────────────────────

/**
 * Main auth init — call this before loading app data.
 *
 * - Desktop mode: calls showApp(null) immediately (no login gate).
 * - Server mode:  fetches /api/me; shows login screen on 401, app otherwise.
 */
async function initAuth() {
  // isServerMode() is defined in api.js.  At this point _publicConfig may not
  // yet be populated (bootstrap hasn't run), so we do a direct /api/me call
  // which also tells us the mode via the 'mode' field.
  let rawData = null;
  try {
    const res = await fetch('/api/me');
    if (res.status === 401) {
      showLoginScreen();
      return false;   // signals that the app should not proceed
    }
    rawData = await res.json();
  } catch (e) {
    // Network failure — let app continue; it will show its own error
    showApp(null);
    return true;
  }

  if (rawData.mode === 'desktop') {
    showApp(null);
    return true;
  }

  // Server mode
  if (rawData.user) {
    showApp(rawData.user);
    return true;
  }

  // Server mode but no user (shouldn't happen — server returns 401 — but guard)
  showLoginScreen();
  return false;
}
