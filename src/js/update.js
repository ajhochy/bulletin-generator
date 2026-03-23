// ─── App Update ────────────────────────────────────────────────────────────────
//
// Handles check-for-update and apply-update flows for both desktop and server
// modes. Depends on: apiFetch(), setStatus(), isDesktopMode(), isServerMode(),
// _publicConfig, _serverSettings.
//

// ── Init ───────────────────────────────────────────────────────────────────────

function initUpdateSection() {
  const versionEl = document.getElementById('update-current-version');
  if (versionEl) versionEl.textContent = _publicConfig.appVersion || '—';

  // Watchtower token field is server-mode only
  const tokenCard = document.getElementById('update-token-card');
  if (tokenCard) tokenCard.style.display = isServerMode() ? '' : 'none';

  // Pre-fill saved token
  const tokenInput = document.getElementById('update-watchtower-token');
  if (tokenInput && _serverSettings.watchtowerToken) {
    tokenInput.value = _serverSettings.watchtowerToken;
  }
}

// ── Check for update ───────────────────────────────────────────────────────────

async function checkForUpdate() {
  const btn    = document.getElementById('update-check-btn');
  const status = document.getElementById('update-status-msg');

  if (btn) btn.disabled = true;
  if (status) { status.textContent = 'Checking…'; status.className = 'pco-msg'; }

  try {
    const data = await apiFetch('/api/admin/check-update');

    if (data.error) {
      if (status) { status.textContent = data.error; status.className = 'pco-msg error'; }
      return;
    }

    const banner   = document.getElementById('update-banner');
    const applyBtn = document.getElementById('update-apply-btn');

    if (data.hasUpdate) {
      const latestEl = document.getElementById('update-latest-version');
      if (latestEl) latestEl.textContent = data.latest;
      if (banner)   banner.style.display   = '';
      if (applyBtn) applyBtn.style.display = '';
      if (status) {
        status.textContent = `Version ${data.latest} is available.`;
        status.className   = 'pco-msg success';
      }
    } else {
      if (banner)   banner.style.display   = 'none';
      if (applyBtn) applyBtn.style.display = 'none';
      if (status) {
        status.textContent = `You're on the latest version (${data.current}).`;
        status.className   = 'pco-msg';
      }
    }
  } catch (e) {
    if (status) {
      status.textContent = 'Could not check for updates. Check your internet connection.';
      status.className   = 'pco-msg error';
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Apply update ───────────────────────────────────────────────────────────────

async function applyUpdate() {
  const btn    = document.getElementById('update-apply-btn');
  const status = document.getElementById('update-status-msg');

  if (btn) btn.disabled = true;
  if (status) {
    status.textContent = isDesktopMode() ? 'Downloading update…' : 'Triggering update…';
    status.className   = 'pco-msg';
  }

  try {
    const data = await apiFetch('/api/admin/apply-update', 'POST', {});

    if (data.error) {
      if (status) { status.textContent = data.error; status.className = 'pco-msg error'; }
      if (btn) btn.disabled = false;
      return;
    }

    if (isDesktopMode()) {
      if (status) {
        status.textContent = data.message || 'Update applied. Quit and relaunch the app.';
        status.className   = 'pco-msg success';
      }
      setStatus('Update downloaded. Quit and relaunch to use the new version.', 'success');
    } else {
      // Server mode: poll until the restarted container responds
      if (status) {
        status.textContent = 'Update triggered. Waiting for server to restart…';
        status.className   = 'pco-msg';
      }
      _pollForRestart();
    }
  } catch (e) {
    if (status) {
      status.textContent = `Update failed: ${e.message || e}`;
      status.className   = 'pco-msg error';
    }
    if (btn) btn.disabled = false;
  }
}

// ── Poll for restart (server mode) ────────────────────────────────────────────

function _pollForRestart() {
  const status   = document.getElementById('update-status-msg');
  const maxWait  = 120000; // 2 minutes
  const interval = 3000;
  let elapsed    = 0;

  const timer = setInterval(async () => {
    elapsed += interval;
    try {
      await apiFetch('/api/bootstrap');
      clearInterval(timer);
      if (status) {
        status.textContent = 'Server updated and restarted. Reload this page.';
        status.className   = 'pco-msg success';
      }
      setStatus('Server updated. Reload the page to use the new version.', 'success');
    } catch (_) {
      if (elapsed >= maxWait) {
        clearInterval(timer);
        if (status) {
          status.textContent = 'Server is taking longer than expected. Try reloading manually.';
          status.className   = 'pco-msg error';
        }
      }
    }
  }, interval);
}

// ── Save Watchtower token ──────────────────────────────────────────────────────

async function saveWatchtowerToken() {
  const input = document.getElementById('update-watchtower-token');
  if (!input) return;
  const token = input.value.trim();
  try {
    await apiFetch('/api/settings', 'POST', { watchtowerToken: token || null });
    _serverSettings.watchtowerToken = token || undefined;
    setStatus('Watchtower token saved.', 'success');
  } catch (e) {
    setStatus('Failed to save Watchtower token.', 'error');
  }
}
