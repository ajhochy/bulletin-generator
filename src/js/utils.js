// ─── Helpers ──────────────────────────────────────────────────────────────────
function setStatus(msg, type = '') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const alertClass = type === 'success' ? 'alert-success'
                   : type === 'error'   ? 'alert-error'
                   : type === 'info'    ? 'alert-info'
                   : '';

  const toast = document.createElement('div');
  toast.className = 'alert shadow-md text-sm py-2 px-4' + (alertClass ? ' ' + alertClass : '');

  const msgEl = document.createElement('span');
  msgEl.textContent = msg;
  toast.appendChild(msgEl);

  if (type === 'error') {
    // Errors stay until manually dismissed
    const closeBtn = document.createElement('button');
    closeBtn.className = 'btn btn-ghost btn-xs ml-2';
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

