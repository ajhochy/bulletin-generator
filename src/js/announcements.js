// ─── Announcement cards ───────────────────────────────────────────────────────
function annRender() {
  annList.innerHTML = '';
  annData.forEach((ann, idx) => {
    const card = document.createElement('div');
    card.className = 'ann-card';
    card.dataset.annIdx = idx;

    // Row 1: title input + move + delete
    const row1 = document.createElement('div');
    row1.className = 'ann-card-row1';

    const titleIn = document.createElement('input');
    titleIn.type = 'text';
    titleIn.className = 'ann-title-input';
    titleIn.placeholder = 'Heading (optional)';
    titleIn.value = ann.title || '';
    titleIn.addEventListener('input', () => {
      annData[idx].title = titleIn.value;
      saveAnnGlobal();
      schedulePreviewUpdate();
      scheduleProjectPersist();
    });

    const upBtn = document.createElement('button');
    upBtn.className = 'ann-icon-btn';
    upBtn.title = 'Move up';
    upBtn.textContent = '↑';
    upBtn.disabled = idx === 0;
    upBtn.addEventListener('click', () => annMove(idx, -1));

    const downBtn = document.createElement('button');
    downBtn.className = 'ann-icon-btn';
    downBtn.title = 'Move down';
    downBtn.textContent = '↓';
    downBtn.disabled = idx === annData.length - 1;
    downBtn.addEventListener('click', () => annMove(idx, 1));

    const delBtn = document.createElement('button');
    delBtn.className = 'ann-icon-btn ann-del-btn';
    delBtn.title = 'Remove';
    delBtn.textContent = '✕';
    delBtn.addEventListener('click', () => annDelete(idx));

    // Break-before toggle (Feature 1)
    const breakToggle = document.createElement('button');
    breakToggle.className = 'ann-break-toggle' + (ann._breakBefore ? ' active' : '');
    breakToggle.title = ann._breakBefore ? 'Remove forced page break before this announcement' : 'Insert page break before this announcement';
    breakToggle.textContent = '⊞';
    breakToggle.addEventListener('click', () => {
      annData[idx]._breakBefore = !annData[idx]._breakBefore;
      annData[idx]._noBreakBefore = false; // clear suppress flag too
      saveAnnGlobal();
      annRender();
      schedulePreviewUpdate();
      scheduleProjectPersist();
    });

    row1.appendChild(titleIn);
    row1.appendChild(breakToggle);
    row1.appendChild(upBtn);
    row1.appendChild(downBtn);
    row1.appendChild(delBtn);

    // Row 2: formatting toolbar
    const toolbar = document.createElement('div');
    toolbar.className = 'ann-card-toolbar';

    const boldBtn = document.createElement('button');
    boldBtn.type = 'button';
    boldBtn.className = 'ann-fmt-btn ann-fmt-bold';
    boldBtn.title = 'Bold — select text then click';
    boldBtn.textContent = 'B';
    boldBtn.addEventListener('mousedown', e => e.preventDefault());
    boldBtn.addEventListener('click', () => annFmtBold(bodyTA));

    const bulletBtn = document.createElement('button');
    bulletBtn.type = 'button';
    bulletBtn.className = 'ann-fmt-btn';
    bulletBtn.title = 'Toggle bullet point on current line';
    bulletBtn.textContent = '•';
    bulletBtn.addEventListener('mousedown', e => e.preventDefault());
    bulletBtn.addEventListener('click', () => annFmtBullet(bodyTA));

    toolbar.appendChild(boldBtn);
    toolbar.appendChild(bulletBtn);

    // Body textarea
    const bodyTA = document.createElement('textarea');
    bodyTA.className = 'ann-body-input';
    bodyTA.rows = 3;
    bodyTA.placeholder = 'Announcement text…';
    bodyTA.value = ann.body || '';
    bodyTA.addEventListener('input', () => {
      annData[idx].body = bodyTA.value;
      autoResize(bodyTA);
      saveAnnGlobal();
      schedulePreviewUpdate();
      scheduleProjectPersist();
    });
    // Track selection so Bold/Bullet buttons can restore it after mousedown steals focus
    const saveAnnSel = () => { bodyTA._savedSel = { start: bodyTA.selectionStart, end: bodyTA.selectionEnd }; };
    bodyTA.addEventListener('select', saveAnnSel);
    bodyTA.addEventListener('mouseup', saveAnnSel);
    bodyTA.addEventListener('keyup', saveAnnSel);

    // URL input for QR code (Feature 6)
    const urlRow = document.createElement('div');
    urlRow.className = 'ann-url-row';
    const urlLabel = document.createElement('span');
    urlLabel.className = 'ann-url-label';
    urlLabel.textContent = 'QR URL:';
    const urlInput = document.createElement('input');
    urlInput.type = 'url';
    urlInput.className = 'ann-url-input';
    urlInput.placeholder = 'https://… (optional, generates QR code)';
    urlInput.value = ann.url || '';
    urlInput.addEventListener('input', () => {
      annData[idx].url = urlInput.value;
      saveAnnGlobal();
      schedulePreviewUpdate();
      scheduleProjectPersist();
    });
    urlRow.appendChild(urlLabel);
    urlRow.appendChild(urlInput);

    card.appendChild(row1);
    card.appendChild(toolbar);
    card.appendChild(bodyTA);
    card.appendChild(urlRow);
    annList.appendChild(card);
    autoResize(bodyTA);
  });
  updateSectionPreviews();
}

function saveAnnGlobal() {
  apiFetch('/api/announcements', 'POST', annData).catch(() => {});
}

function annAdd() {
  annData.push({ title: '', body: '' });
  annRender();
  saveAnnGlobal();
  const inputs = annList.querySelectorAll('.ann-title-input');
  if (inputs.length) inputs[inputs.length - 1].focus();
  scheduleProjectPersist();
}

function annDelete(idx) {
  annData.splice(idx, 1);
  annRender();
  saveAnnGlobal();
  schedulePreviewUpdate();
  scheduleProjectPersist();
}

function annMove(idx, dir) {
  const other = idx + dir;
  if (other < 0 || other >= annData.length) return;
  [annData[idx], annData[other]] = [annData[other], annData[idx]];
  annRender();
  saveAnnGlobal();
  schedulePreviewUpdate();
  scheduleProjectPersist();
}

function annFmtBold(ta) {
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

function annFmtBullet(ta) {
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

// Insert *italic* markers around selected text in a textarea
function fmtItalic(ta) {
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

// ─── Welcome items editor ────────────────────────────────────────────────────
function welcomeRender() {
  welcomeList.innerHTML = '';
  welcomeItems.forEach((text, idx) => {
    const row = document.createElement('div');
    row.className = 'welcome-item-row';
    row.style.cssText = 'display:flex;gap:0.3rem;align-items:center;margin-bottom:0.3rem;';

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'ann-title-input';
    input.style.cssText = 'flex:1;';
    input.value = text;
    input.placeholder = 'Welcome item text…';
    input.addEventListener('input', () => {
      welcomeItems[idx] = input.value;
      schedulePreviewUpdate();
      scheduleProjectPersist();
    });

    const delBtn = document.createElement('button');
    delBtn.className = 'ann-icon-btn ann-del-btn';
    delBtn.title = 'Remove';
    delBtn.textContent = '✕';
    delBtn.addEventListener('click', () => {
      welcomeItems.splice(idx, 1);
      welcomeRender();
      schedulePreviewUpdate();
      scheduleProjectPersist();
    });

    row.appendChild(input);
    row.appendChild(delBtn);
    welcomeList.appendChild(row);
  });
}

function welcomeAdd() {
  welcomeItems.push('');
  welcomeRender();
  const inputs = welcomeList.querySelectorAll('input');
  if (inputs.length) inputs[inputs.length - 1].focus();
  scheduleProjectPersist();
}

// ─── Linked preview scroll ────────────────────────────────────────────────────
// Clicking an announcement card scrolls the preview to that announcement,
// mirroring the linked-preview behaviour of the Order of Worship editor.
annList.addEventListener('click', e => {
  const card = e.target.closest('.ann-card');
  if (!card) return;
  const idx = parseInt(card.dataset.annIdx, 10);
  if (!Number.isInteger(idx)) return;
  if (typeof scrollPreviewToAnn === 'function') scrollPreviewToAnn(idx);
});

// ─── Per-item formatting toolbar ──────────────────────────────────────────────
