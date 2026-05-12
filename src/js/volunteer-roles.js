// ─── Volunteer Roles cards ────────────────────────────────────────────────────
function vrRender() {
  const vrList = document.getElementById('vr-list');
  vrList.innerHTML = '';
  vrData.forEach((entry, idx) => {
    const card = document.createElement('div');
    card.className = 'vr-card card bg-base-100 border border-base-300 rounded-lg p-3 mb-2 shadow-sm';
    card.dataset.vrIdx = idx;

    // Row 1: title input + move + delete
    const row1 = document.createElement('div');
    row1.className = 'vr-card-row1 flex items-center gap-1.5 mb-2';

    const titleIn = document.createElement('input');
    titleIn.type = 'text';
    titleIn.className = 'vr-title-input input input-bordered input-sm flex-1 min-w-0';
    titleIn.placeholder = 'Role heading (optional)';
    titleIn.value = entry.title || '';
    titleIn.addEventListener('input', () => {
      vrData[idx].title = titleIn.value;
      saveVrGlobal();
      schedulePreviewUpdate();
    });

    const upBtn = document.createElement('button');
    upBtn.className = 'vr-icon-btn btn btn-ghost btn-xs btn-square';
    upBtn.title = 'Move up';
    upBtn.textContent = '↑';
    upBtn.disabled = idx === 0;
    upBtn.addEventListener('click', () => vrMove(idx, -1));

    const downBtn = document.createElement('button');
    downBtn.className = 'vr-icon-btn btn btn-ghost btn-xs btn-square';
    downBtn.title = 'Move down';
    downBtn.textContent = '↓';
    downBtn.disabled = idx === vrData.length - 1;
    downBtn.addEventListener('click', () => vrMove(idx, 1));

    const delBtn = document.createElement('button');
    delBtn.className = 'vr-icon-btn vr-del-btn btn btn-ghost btn-xs btn-square text-error';
    delBtn.title = 'Remove';
    delBtn.textContent = '✕';
    delBtn.addEventListener('click', () => vrDelete(idx));

    row1.appendChild(titleIn);
    row1.appendChild(upBtn);
    row1.appendChild(downBtn);
    row1.appendChild(delBtn);

    // Row 2: formatting toolbar
    const toolbar = document.createElement('div');
    toolbar.className = 'vr-card-toolbar flex items-center gap-1 mb-2';

    const boldBtn = document.createElement('button');
    boldBtn.type = 'button';
    boldBtn.className = 'vr-fmt-btn vr-fmt-bold btn btn-ghost btn-xs';
    boldBtn.title = 'Bold — select text then click';
    boldBtn.textContent = 'B';
    boldBtn.addEventListener('mousedown', e => e.preventDefault());
    boldBtn.addEventListener('click', () => vrFmtBold(bodyTA));

    const italicBtn = document.createElement('button');
    italicBtn.type = 'button';
    italicBtn.className = 'vr-fmt-btn vr-fmt-italic btn btn-ghost btn-xs';
    italicBtn.title = 'Italic — select text then click';
    italicBtn.style.fontStyle = 'italic';
    italicBtn.textContent = 'I';
    italicBtn.addEventListener('mousedown', e => e.preventDefault());
    italicBtn.addEventListener('click', () => vrFmtItalic(bodyTA));

    const bulletBtn = document.createElement('button');
    bulletBtn.type = 'button';
    bulletBtn.className = 'vr-fmt-btn btn btn-ghost btn-xs';
    bulletBtn.title = 'Toggle bullet point on current line';
    bulletBtn.textContent = '•';
    bulletBtn.addEventListener('mousedown', e => e.preventDefault());
    bulletBtn.addEventListener('click', () => vrFmtBullet(bodyTA));

    toolbar.appendChild(boldBtn);
    toolbar.appendChild(italicBtn);
    toolbar.appendChild(bulletBtn);

    // Body textarea
    const bodyTA = document.createElement('textarea');
    bodyTA.className = 'vr-body-input textarea textarea-bordered textarea-sm w-full';
    bodyTA.rows = 3;
    bodyTA.placeholder = 'Role description…';
    bodyTA.value = entry.body || '';
    bodyTA.addEventListener('input', () => {
      vrData[idx].body = bodyTA.value;
      if (typeof autoResize === 'function') autoResize(bodyTA);
      saveVrGlobal();
      schedulePreviewUpdate();
    });
    const saveVrSel = () => { bodyTA._savedSel = { start: bodyTA.selectionStart, end: bodyTA.selectionEnd }; };
    bodyTA.addEventListener('select', saveVrSel);
    bodyTA.addEventListener('mouseup', saveVrSel);
    bodyTA.addEventListener('keyup', saveVrSel);

    // URL row
    const urlRow = document.createElement('div');
    urlRow.className = 'vr-url-row flex items-center gap-2 mt-2';
    const urlLabel = document.createElement('span');
    urlLabel.className = 'vr-url-label text-xs text-base-content/50 whitespace-nowrap';
    urlLabel.textContent = 'QR URL:';
    const urlInput = document.createElement('input');
    urlInput.type = 'url';
    urlInput.className = 'vr-url-input input input-bordered input-xs flex-1 min-w-0';
    urlInput.placeholder = 'https://… (optional, generates QR code)';
    urlInput.value = entry.url || '';
    urlInput.addEventListener('input', () => {
      vrData[idx].url = urlInput.value;
      saveVrGlobal();
      schedulePreviewUpdate();
    });
    urlRow.appendChild(urlLabel);
    urlRow.appendChild(urlInput);

    card.appendChild(row1);
    card.appendChild(toolbar);
    card.appendChild(bodyTA);
    card.appendChild(urlRow);
    vrList.appendChild(card);
    if (typeof autoResize === 'function') autoResize(bodyTA);
  });
}

function saveVrGlobal() {
  apiFetch('/api/volunteer-roles', 'POST', vrData).catch(err => setStatus('Volunteer roles save failed: ' + (err.message || err), 'error'));
}

function vrAdd() {
  vrData.push({ title: '', body: '', url: '', _breakBefore: false, _noBreakBefore: false });
  vrRender();
  saveVrGlobal();
  const vrList = document.getElementById('vr-list');
  const inputs = vrList.querySelectorAll('.vr-title-input');
  if (inputs.length) inputs[inputs.length - 1].focus();
}

function vrDelete(idx) {
  vrData.splice(idx, 1);
  vrRender();
  saveVrGlobal();
  schedulePreviewUpdate();
}

function vrMove(idx, dir) {
  const other = idx + dir;
  if (other < 0 || other >= vrData.length) return;
  [vrData[idx], vrData[other]] = [vrData[other], vrData[idx]];
  vrRender();
  saveVrGlobal();
  schedulePreviewUpdate();
}

function vrFmtBold(ta) {
  if (ta._savedSel) {
    ta.selectionStart = ta._savedSel.start;
    ta.selectionEnd = ta._savedSel.end;
  }
  const start = ta.selectionStart, end = ta.selectionEnd;
  const sel = ta.value.slice(start, end);
  if (!sel) {
    ta.setRangeText('**bold**', start, end, 'select');
  } else {
    ta.setRangeText(`**${sel}**`, start, end, 'select');
  }
  ta.focus();
  ta.dispatchEvent(new Event('input', { bubbles: true }));
}

function vrFmtItalic(ta) {
  if (ta._savedSel) {
    ta.selectionStart = ta._savedSel.start;
    ta.selectionEnd = ta._savedSel.end;
  }
  const start = ta.selectionStart, end = ta.selectionEnd;
  const sel = ta.value.slice(start, end);
  if (!sel) {
    ta.setRangeText('*italic*', start, end, 'select');
  } else {
    ta.setRangeText(`*${sel}*`, start, end, 'select');
  }
  ta.focus();
  ta.dispatchEvent(new Event('input', { bubbles: true }));
}

function vrFmtBullet(ta) {
  const start = ta.selectionStart;
  const lineStart = ta.value.lastIndexOf('\n', start - 1) + 1;
  const end = ta.selectionEnd;
  const lineEnd = ta.value.indexOf('\n', end);
  const slice = ta.value.slice(lineStart, lineEnd === -1 ? undefined : lineEnd);
  const toggled = slice.split('\n').map(l => {
    if (!l.trim()) return l;
    return l.startsWith('• ') ? l.slice(2) : '• ' + l;
  }).join('\n');
  ta.setRangeText(toggled, lineStart, lineEnd === -1 ? ta.value.length : lineEnd, 'end');
  ta.focus();
  ta.dispatchEvent(new Event('input', { bubbles: true }));
}

// ─── Linked preview scroll ────────────────────────────────────────────────────
(function () {
  const vrList = document.getElementById('vr-list');
  if (!vrList) return;
  vrList.addEventListener('click', e => {
    const card = e.target.closest('.vr-card');
    if (!card) return;
    const idx = parseInt(card.dataset.vrIdx, 10);
    if (!Number.isInteger(idx)) return;
    if (typeof scrollPreviewToVr === 'function') scrollPreviewToVr(idx);
  });
})();
