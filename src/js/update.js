// ─── App Update ────────────────────────────────────────────────────────────────
//
// Handles check-for-update and apply-update flows for both desktop and server
// modes. Depends on: apiFetch(), setStatus(), isDesktopMode(), isServerMode(),
// _publicConfig, _serverSettings.
//

// ── Init ───────────────────────────────────────────────────────────────────────
let _updateControlsInitialized = false;

function initUpdateSection() {
  const versionEl = document.getElementById('update-current-version');
  if (versionEl) versionEl.textContent = _publicConfig.appVersion || '—';
}

function initUpdateControls() {
  if (_updateControlsInitialized) return;
  _updateControlsInitialized = true;
  document.getElementById('update-check-btn').addEventListener('click', checkForUpdate);
  document.getElementById('update-apply-btn').addEventListener('click', applyUpdate);
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
      if (status) {
        let msg = data.error;
        if (data.manualFallback) {
          msg += `\n\nManual fallback: ${data.manualFallback}`;
        }
        status.textContent      = msg;
        status.style.whiteSpace = 'pre-wrap';
        status.className        = 'pco-msg error';
      }
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
      // Server mode: poll until the restarted container responds with new version
      const currentVersion = _publicConfig.appVersion;
      if (status) {
        status.textContent = data.message || 'Update triggered. Waiting for restart…';
        status.className   = 'pco-msg';
      }
      _pollForRestart(currentVersion);
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

function _pollForRestart(oldVersion) {
  const status   = document.getElementById('update-status-msg');
  const bar      = document.getElementById('update-progress-bar');
  const barFill  = document.getElementById('update-progress-fill');
  const barText  = document.getElementById('update-progress-text');
  const maxWait  = 300000; // 5 minutes (Docker pull can be slow on first run)
  const interval = 3000;
  let elapsed    = 0;
  let phase      = 'pulling'; // pulling → restarting → done

  // Show progress bar
  if (bar) bar.style.display = '';

  function updateProgress(pct, text) {
    if (barFill) barFill.style.width = pct + '%';
    if (barText) barText.textContent = text;
    if (status) { status.textContent = text; status.className = 'pco-msg'; }
  }

  updateProgress(10, 'Pulling new image…');

  const timer = setInterval(async () => {
    elapsed += interval;

    // Animate progress bar during pull phase (up to ~60%)
    if (phase === 'pulling') {
      const pct = Math.min(10 + (elapsed / maxWait) * 50, 60);
      updateProgress(pct, 'Pulling new image…');
    }

    try {
      const data = await apiFetch('/api/bootstrap');
      const newVersion = data.config && data.config.appVersion;

      if (newVersion && newVersion !== oldVersion) {
        // Update complete — new version detected
        clearInterval(timer);
        phase = 'done';
        updateProgress(100, `Updated to v${newVersion}!`);
        if (status) { status.className = 'pco-msg success'; }
        setStatus(`Server updated to v${newVersion}. Reloading…`, 'success');
        setTimeout(() => window.location.reload(), 2000);
        return;
      }

      // Server responded but still old version — still pulling/restarting
      if (phase === 'pulling') {
        const pct = Math.min(10 + (elapsed / maxWait) * 50, 60);
        updateProgress(pct, 'Pulling new image…');
      }
    } catch (_) {
      // Server unreachable — container is restarting
      if (phase !== 'restarting') {
        phase = 'restarting';
        updateProgress(70, 'Restarting server…');
      } else {
        const pct = Math.min(70 + ((elapsed - 30000) / maxWait) * 25, 90);
        updateProgress(Math.max(70, pct), 'Restarting server…');
      }
    }

    if (elapsed >= maxWait) {
      clearInterval(timer);
      if (bar) bar.style.display = 'none';
      if (status) {
        status.textContent =
          'The update is taking longer than expected. ' +
          'It may still be running in the background — try reloading in a minute. ' +
          'If the problem persists, SSH in and run: docker compose pull && docker compose up -d';
        status.style.whiteSpace = 'pre-wrap';
        status.className = 'pco-msg error';
      }
    }
  }, interval);
}
