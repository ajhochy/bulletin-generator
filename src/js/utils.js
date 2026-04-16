// ─── Helpers ──────────────────────────────────────────────────────────────────
function setStatus(msg, type = '') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  const typeClass = type === 'success' ? 'toast-success'
                  : type === 'error'   ? 'toast-error'
                  : type === 'info'    ? 'toast-info'
                  : '';
  toast.className = 'toast' + (typeClass ? ' ' + typeClass : '');

  const msgEl = document.createElement('span');
  msgEl.className = 'toast-msg';
  msgEl.textContent = msg;
  toast.appendChild(msgEl);

  if (type === 'error') {
    // Errors stay until manually dismissed
    const closeBtn = document.createElement('button');
    closeBtn.className = 'toast-close';
    closeBtn.textContent = '✕';
    closeBtn.addEventListener('click', () => dismissToast(toast));
    toast.appendChild(closeBtn);
  } else {
    // Success / info auto-dismiss after 3 s
    setTimeout(() => dismissToast(toast), 3000);
  }

  container.appendChild(toast);
}

function dismissToast(toast) {
  toast.classList.add('toast-fade');
  setTimeout(() => toast.remove(), 300);
}
function esc(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escAttr(str) { return esc(str).replace(/"/g, '&quot;'); }

function nowIso() {
  return new Date().toISOString();
}

function shortTimestamp(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  } catch (e) {
    return '';
  }
}

function generateProjectId() {
  return `proj_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

