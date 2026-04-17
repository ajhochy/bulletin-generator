let _fmtClipboard = null;

// Builds two rows (Title / Body) of compact formatting controls for a single item.
// Changes write into items[idx]._fmt and schedule a preview refresh.
function buildItemFmtToolbar(item, idx) {
  const wrapper = document.createElement('div');
  wrapper.className = 'item-fmt-toolbar';

  const fmt = item._fmt || {};

  // ── Shared helpers ─────────────────────────────────────────────────────────
  function mkBtn(text, extraCls, titleTxt, isActive) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'fmt-btn' + (extraCls ? ' ' + extraCls : '') + (isActive ? ' fmt-active' : '');
    b.title = titleTxt;
    b.textContent = text;
    b.addEventListener('mousedown', e => e.preventDefault());
    return b;
  }

  function mkSep() {
    const s = document.createElement('span');
    s.className = 'fmt-sep';
    return s;
  }

  function mkColorSwatches(fmtKey, rowEl) {
    const colorDefs = [
      ['fmt-swatch-default', '', 'Default (dark)'],
      ['fmt-swatch-gray',    '#888', 'Gray'],
      ['fmt-swatch-light',   '#aaa', 'Light gray'],
      ['fmt-swatch-brown',   '#7a5c45', 'Brown'],
    ];
    const swatches = [];
    colorDefs.forEach(([cls, val, ttl]) => {
      const sw = document.createElement('button');
      sw.type = 'button';
      sw.className = 'fmt-color-swatch ' + cls + ((fmt[fmtKey] || '') === val ? ' fmt-active' : '');
      sw.title = ttl;
      sw.addEventListener('mousedown', e => e.preventDefault());
      sw.addEventListener('click', () => {
        if (!items[idx]) return;
        if (!items[idx]._fmt) items[idx]._fmt = {};
        // Delete the key when resetting to default ('') so type-level
        // format defaults are not blocked by a stale empty override.
        if (val === '') { delete items[idx]._fmt[fmtKey]; }
        else            { items[idx]._fmt[fmtKey] = val;  }
        swatches.forEach(s => s.classList.remove('fmt-active'));
        sw.classList.add('fmt-active');
        schedulePreviewUpdate();
        scheduleProjectPersist();
      });
      rowEl.appendChild(sw);
      swatches.push(sw);
    });
  }

  function mkAlignBtns(fmtKey, rowEl) {
    // Use explicit 'left' (not '') so a per-item Left choice is a real override
    // that wins over a type-level Center/Right default. The empty string '' is
    // still treated as "no override" by getEffectiveFmt (truthy check), so old
    // saved '' values continue to fall through to the type default.
    const alignDefs = [['left', 'L', 'Left align'], ['center', 'C', 'Center'], ['right', 'R', 'Right align']];
    const btns = [];
    // Current effective alignment for active-state highlight
    const curVal = fmt[fmtKey] || '';
    alignDefs.forEach(([val, lbl, ttl]) => {
      const ab = mkBtn(lbl, '', ttl, curVal === val);
      ab.addEventListener('click', () => {
        if (!items[idx]) return;
        if (!items[idx]._fmt) items[idx]._fmt = {};
        items[idx]._fmt[fmtKey] = val;
        btns.forEach(b => b.classList.remove('fmt-active'));
        ab.classList.add('fmt-active');
        schedulePreviewUpdate();
        scheduleProjectPersist();
      });
      rowEl.appendChild(ab);
      btns.push(ab);
    });
  }

  function mkFontSel(fmtKey) {
    const fonts = (typeof _designerFonts !== 'undefined' && _designerFonts.length)
      ? _designerFonts
      : ['system-ui','Georgia','Inter','Montserrat','Open Sans','Playfair Display','Merriweather','Lora'];
    const sel = document.createElement('select');
    sel.className = 'fmt-size-sel fmt-font-sel';
    sel.title = 'Font family';
    const blank = document.createElement('option');
    blank.value = '';
    blank.textContent = 'Font…';
    sel.appendChild(blank);
    fonts.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f;
      opt.textContent = f;
      opt.selected = (f === (fmt[fmtKey] || ''));
      sel.appendChild(opt);
    });
    if (fmt[fmtKey]) sel.value = fmt[fmtKey];
    sel.addEventListener('change', () => {
      if (!items[idx]) return;
      if (!items[idx]._fmt) items[idx]._fmt = {};
      if (sel.value === '') { delete items[idx]._fmt[fmtKey]; }
      else                  { items[idx]._fmt[fmtKey] = sel.value; }
      schedulePreviewUpdate();
      scheduleProjectPersist();
    });
    return sel;
  }

  function mkSizeSelect(fmtKey, options) {
    const sel = document.createElement('select');
    sel.className = 'fmt-size-sel';
    options.forEach(([val, lbl]) => {
      const opt = document.createElement('option');
      opt.value = val;
      opt.textContent = lbl;
      opt.selected = (val === (fmt[fmtKey] || ''));
      sel.appendChild(opt);
    });
    sel.addEventListener('change', () => {
      if (!items[idx]) return;
      if (!items[idx]._fmt) items[idx]._fmt = {};
      // Delete the key when resetting to default ('') so type-level
      // format defaults are not blocked by a stale empty override.
      if (sel.value === '') { delete items[idx]._fmt[fmtKey]; }
      else                  { items[idx]._fmt[fmtKey] = sel.value; }
      schedulePreviewUpdate();
      scheduleProjectPersist();
    });
    return sel;
  }

  // ── Title row ──────────────────────────────────────────────────────────────
  const titleRow = document.createElement('div');
  titleRow.className = 'item-fmt-row';

  const titleLbl = document.createElement('span');
  titleLbl.className = 'fmt-target-label';
  titleLbl.textContent = 'Title';
  titleRow.appendChild(titleLbl);

  // Bold toggle
  const titleBoldBtn = mkBtn('B', 'fmt-bold', 'Bold title', !!fmt.titleBold);
  titleBoldBtn.addEventListener('click', () => {
    if (!items[idx]) return;
    if (!items[idx]._fmt) items[idx]._fmt = {};
    items[idx]._fmt.titleBold = !items[idx]._fmt.titleBold;
    titleBoldBtn.classList.toggle('fmt-active', !!items[idx]._fmt.titleBold);
    schedulePreviewUpdate();
    scheduleProjectPersist();
  });
  titleRow.appendChild(titleBoldBtn);

  // Italic toggle
  const titleItalicBtn = mkBtn('I', 'fmt-italic', 'Italic title', !!fmt.titleItalic);
  titleItalicBtn.addEventListener('click', () => {
    if (!items[idx]) return;
    if (!items[idx]._fmt) items[idx]._fmt = {};
    items[idx]._fmt.titleItalic = !items[idx]._fmt.titleItalic;
    titleItalicBtn.classList.toggle('fmt-active', !!items[idx]._fmt.titleItalic);
    schedulePreviewUpdate();
    scheduleProjectPersist();
  });
  titleRow.appendChild(titleItalicBtn);

  titleRow.appendChild(mkSep());
  mkColorSwatches('titleColor', titleRow);
  titleRow.appendChild(mkSep());
  mkAlignBtns('titleAlign', titleRow);
  titleRow.appendChild(mkSep());
  titleRow.appendChild(mkSizeSelect('titleSize', [['','Auto'],['sm','Small'],['lg','Large'],['xl','XL']]));
  titleRow.appendChild(mkFontSel('titleFont'));

  wrapper.appendChild(titleRow);

  // ── Body row ───────────────────────────────────────────────────────────────
  const bodyRow = document.createElement('div');
  bodyRow.className = 'item-fmt-row';

  const bodyLbl = document.createElement('span');
  bodyLbl.className = 'fmt-target-label';
  bodyLbl.textContent = 'Body';
  bodyRow.appendChild(bodyLbl);

  // Bold insert (wraps selected text in **)
  const bodyBoldBtn = mkBtn('B', 'fmt-bold', 'Bold — select text then click, or click to insert placeholder', false);
  bodyBoldBtn.addEventListener('click', () => {
    const card = bodyBoldBtn.closest('.item-card');
    const ta = card && card.querySelector('.item-detail-input');
    if (ta) annFmtBold(ta);
  });
  bodyRow.appendChild(bodyBoldBtn);

  // Italic insert (wraps selected text in *)
  const bodyItalicBtn = mkBtn('I', 'fmt-italic', 'Italic — select text then click (*italic*)', false);
  bodyItalicBtn.addEventListener('click', () => {
    const card = bodyItalicBtn.closest('.item-card');
    const ta = card && card.querySelector('.item-detail-input');
    if (ta) fmtItalic(ta);
  });
  bodyRow.appendChild(bodyItalicBtn);

  bodyRow.appendChild(mkSep());
  mkColorSwatches('bodyColor', bodyRow);
  bodyRow.appendChild(mkSep());
  mkAlignBtns('bodyAlign', bodyRow);
  bodyRow.appendChild(mkSep());
  bodyRow.appendChild(mkSizeSelect('bodySize', [['','Auto'],['sm','Small'],['lg','Large']]));
  bodyRow.appendChild(mkFontSel('bodyFont'));

  wrapper.appendChild(bodyRow);

  // ── Copy / Paste row ───────────────────────────────────────────────────────
  const cpRow = document.createElement('div');
  cpRow.className = 'item-fmt-row item-fmt-cp-row';

  const copyBtn = mkBtn('Copy Style', 'fmt-cp-btn', 'Copy this item\'s formatting', false);
  copyBtn.addEventListener('click', () => {
    _fmtClipboard = Object.assign({}, items[idx]?._fmt || {});
    copyBtn.textContent = 'Copied ✓';
    setTimeout(() => { copyBtn.textContent = 'Copy Style'; }, 1500);
  });

  const pasteBtn = mkBtn('Paste Style', 'fmt-cp-btn', 'Paste copied formatting onto this item', false);
  pasteBtn.disabled = !_fmtClipboard;
  pasteBtn.style.opacity = _fmtClipboard ? '1' : '0.4';
  pasteBtn.addEventListener('click', () => {
    if (!_fmtClipboard || !items[idx]) return;
    items[idx]._fmt = Object.assign({}, _fmtClipboard);
    schedulePreviewUpdate();
    scheduleProjectPersist();
    // Replace the toolbar in-place so button states reflect the pasted fmt
    const parent = wrapper.parentNode;
    if (parent) parent.replaceChild(buildItemFmtToolbar(items[idx], idx), wrapper);
  });

  cpRow.appendChild(copyBtn);
  cpRow.appendChild(pasteBtn);
  wrapper.appendChild(cpRow);

  // Enable paste button whenever clipboard has content (catches clipboard set by another item)
  wrapper.addEventListener('mouseenter', () => {
    pasteBtn.disabled = !_fmtClipboard;
    pasteBtn.style.opacity = _fmtClipboard ? '1' : '0.4';
  });

  return wrapper;
}

let _formattingControlsInitialized = false;

function initFormattingControls() {
  if (_formattingControlsInitialized) return;
  _formattingControlsInitialized = true;

  optCover.addEventListener('change',         () => { renderPreview(); scheduleProjectPersist(); });
  optFooter.addEventListener('change',        () => { renderPreview(); scheduleProjectPersist(); });
  optCal.addEventListener('change',           () => { renderPreview(); scheduleProjectPersist(); });
  optBookletSize.addEventListener('change',   () => { renderPreview(); scheduleProjectPersist(); });
  optAnnouncements.addEventListener('change', () => { renderPreview(); scheduleProjectPersist(); });
  optVolunteers.addEventListener('change',    () => { renderPreview(); scheduleProjectPersist(); });
  optStaff.addEventListener('change',         () => { renderPreview(); scheduleProjectPersist(); });

  document.getElementById('fmt-save-btn').addEventListener('click', () => {
    saveTypeFormats();
    schedulePreviewUpdate();
    const btn = document.getElementById('fmt-save-btn');
    const orig = btn.textContent;
    btn.textContent = 'Saved ✓';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });

  document.getElementById('fmt-reset-btn').addEventListener('click', () => {
    if (!confirm('Reset all type formatting to defaults? This cannot be undone.')) return;
    setTypeFormatsMap({});
    saveTypeFormats();
    renderFormatPage();
    schedulePreviewUpdate();
  });
}


// ─── Apply an _fmt object as inline styles to a DOM element ──────────────────
const TITLE_SIZE_MAP = { sm: '0.67rem', lg: '0.98rem', xl: '1.1rem' };
const BODY_SIZE_MAP  = { sm: '0.70rem', lg: '0.90rem' };

function applyTitleFmt(el, fmt) {
  if (fmt.titleBold)   el.style.fontWeight  = 'bold';
  if (fmt.titleItalic) el.style.fontStyle   = 'italic';
  if (fmt.titleColor)  el.style.color       = fmt.titleColor;
  if (fmt.titleAlign)  el.style.textAlign   = fmt.titleAlign;
  if (fmt.titleFont)   el.style.fontFamily  = fmt.titleFont;
  if (fmt.titleSize && TITLE_SIZE_MAP[fmt.titleSize])
    el.style.fontSize = TITLE_SIZE_MAP[fmt.titleSize];
}

function applyBodyFmt(el, fmt) {
  if (fmt.bodyColor) el.style.color      = fmt.bodyColor;
  if (fmt.bodyAlign) el.style.textAlign  = fmt.bodyAlign;
  if (fmt.bodyFont)  el.style.fontFamily = fmt.bodyFont;
  if (fmt.bodySize && BODY_SIZE_MAP[fmt.bodySize])
    el.style.fontSize = BODY_SIZE_MAP[fmt.bodySize];
}

// ─── Build one interior-page item element (used by page-split preview) ───────

// ─── Format Page ──────────────────────────────────────────────────────────────
// Builds a row of formatting controls (used in both Format page and item toolbar)
function buildFmtControls(fmtObj, fmtKey_prefix, onChange) {
  // fmtKey_prefix: 'title' or 'body'
  const isTitle = fmtKey_prefix === 'title';
  const row = document.createElement('div');
  row.className = 'fmt-type-row flex items-center gap-1 px-3 py-1.5 flex-wrap border-t border-base-200';

  const lbl = document.createElement('span');
  lbl.className = 'fmt-row-label text-xs text-base-content/60 w-8 shrink-0';
  lbl.textContent = isTitle ? 'Title' : 'Body';
  row.appendChild(lbl);

  function mkBtn(text, extraCls, ttl, isActive) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'fmt-btn' + (extraCls ? ' ' + extraCls : '') + (isActive ? ' fmt-active' : '');
    b.title = ttl;
    b.textContent = text;
    b.addEventListener('mousedown', e => e.preventDefault());
    return b;
  }
  function mkSep() {
    const s = document.createElement('span');
    s.className = 'fmt-sep';
    return s;
  }

  if (isTitle) {
    // Bold toggle
    const boldKey = 'titleBold';
    const boldBtn = mkBtn('B', 'fmt-bold', 'Bold title', !!fmtObj[boldKey]);
    boldBtn.addEventListener('click', () => {
      fmtObj[boldKey] = !fmtObj[boldKey];
      boldBtn.classList.toggle('fmt-active', !!fmtObj[boldKey]);
      onChange();
    });
    row.appendChild(boldBtn);

    // Italic toggle
    const italicKey = 'titleItalic';
    const italicBtn = mkBtn('I', 'fmt-italic', 'Italic title', !!fmtObj[italicKey]);
    italicBtn.addEventListener('click', () => {
      fmtObj[italicKey] = !fmtObj[italicKey];
      italicBtn.classList.toggle('fmt-active', !!fmtObj[italicKey]);
      onChange();
    });
    row.appendChild(italicBtn);
    row.appendChild(mkSep());
  }

  // Color swatches
  const colorKey = isTitle ? 'titleColor' : 'bodyColor';
  const colorDefs = [
    ['fmt-swatch-default', '', 'Default'],
    ['fmt-swatch-gray',    '#888', 'Gray'],
    ['fmt-swatch-light',   '#aaa', 'Light gray'],
    ['fmt-swatch-brown',   '#7a5c45', 'Brown'],
  ];
  const swatches = [];
  colorDefs.forEach(([cls, val, ttl]) => {
    const sw = document.createElement('button');
    sw.type = 'button';
    sw.className = 'fmt-color-swatch ' + cls + ((fmtObj[colorKey] || '') === val ? ' fmt-active' : '');
    sw.title = ttl;
    sw.addEventListener('mousedown', e => e.preventDefault());
    sw.addEventListener('click', () => {
      fmtObj[colorKey] = val;
      swatches.forEach(s => s.classList.remove('fmt-active'));
      sw.classList.add('fmt-active');
      onChange();
    });
    row.appendChild(sw);
    swatches.push(sw);
  });

  row.appendChild(mkSep());

  // Alignment buttons
  const alignKey = isTitle ? 'titleAlign' : 'bodyAlign';
  const alignDefs = [['', 'L', 'Left'], ['center', 'C', 'Center'], ['right', 'R', 'Right']];
  const alignBtns = [];
  alignDefs.forEach(([val, lbl2, ttl]) => {
    const ab = mkBtn(lbl2, '', ttl, (fmtObj[alignKey] || '') === val);
    ab.addEventListener('click', () => {
      fmtObj[alignKey] = val;
      alignBtns.forEach(b => b.classList.remove('fmt-active'));
      ab.classList.add('fmt-active');
      onChange();
    });
    row.appendChild(ab);
    alignBtns.push(ab);
  });

  row.appendChild(mkSep());

  // Size selector
  const sizeKey = isTitle ? 'titleSize' : 'bodySize';
  const sizeOpts = isTitle
    ? [['','Auto'],['sm','Small'],['lg','Large'],['xl','XL']]
    : [['','Auto'],['sm','Small'],['lg','Large']];
  const sizeSel = document.createElement('select');
  sizeSel.className = 'fmt-size-sel select select-bordered select-xs';
  sizeOpts.forEach(([val, lbl2]) => {
    const opt = document.createElement('option');
    opt.value = val;
    opt.textContent = lbl2;
    opt.selected = (val === (fmtObj[sizeKey] || ''));
    sizeSel.appendChild(opt);
  });
  sizeSel.addEventListener('change', () => {
    fmtObj[sizeKey] = sizeSel.value;
    onChange();
  });
  row.appendChild(sizeSel);

  return row;
}

// ─── Format page group definitions ────────────────────────────────────────────
const FMT_GROUPS = [
  { label: 'Music',   types: new Set(['song']) },
  { label: 'Liturgy', types: new Set(['liturgy']) },
  { label: 'Other',   types: null }, // catch-all: section, label
];

function fmtGetGroup(typeVal) {
  for (const g of FMT_GROUPS) {
    if (g.types && g.types.has(typeVal)) return g.label;
  }
  return 'Sermon & Other';
}

function applyFmtFilter(q) {
  const grid = document.getElementById('fmt-types-grid');
  if (!grid) return;
  const lower = q.toLowerCase().trim();
  grid.querySelectorAll('.fmt-type-card').forEach(card => {
    const match = lower === '' || (card.dataset.typeLabel || '').includes(lower);
    card.style.display = match ? '' : 'none';
  });
  // Hide group headings whose cards are all hidden
  grid.querySelectorAll('.fmt-group-label').forEach(heading => {
    let sib = heading.nextElementSibling;
    let hasVisible = false;
    while (sib && !sib.classList.contains('fmt-group-label')) {
      if (sib.style.display !== 'none') hasVisible = true;
      sib = sib.nextElementSibling;
    }
    heading.style.display = hasVisible ? '' : 'none';
  });
}

function renderFormatPage() {
  const grid = document.getElementById('fmt-types-grid');
  if (!grid) return;
  grid.innerHTML = '';

  // Sort display types by group order, preserving original order within groups
  const displayTypes = TYPE_OPTIONS.filter(
    ([val]) => !['page-break', 'note', 'media'].includes(val)
  );
  const groupIndex = label => FMT_GROUPS.findIndex(g => g.label === label);
  const sorted = displayTypes
    .map(([v, l]) => ({ val: v, label: l, group: fmtGetGroup(v) }))
    .sort((a, b) => groupIndex(a.group) - groupIndex(b.group));

  let lastGroup = null;

  sorted.forEach(({ val: typeVal, label: typeLabel2, group }) => {
    // Insert group heading when group changes
    if (group !== lastGroup) {
      const heading = document.createElement('div');
      heading.className = 'fmt-group-label text-xs font-semibold uppercase tracking-wider text-base-content/50 mt-3 mb-1 col-span-full';
      heading.textContent = group;
      grid.appendChild(heading);
      lastGroup = group;
    }

    if (!typeFormats[typeVal] || typeof typeFormats[typeVal] !== 'object') {
      typeFormats[typeVal] = {};
    }
    const fmtObj = typeFormats[typeVal];

    const card = document.createElement('div');
    card.className = 'fmt-type-card fmt-card-collapsed border border-base-300 rounded-lg bg-base-100 overflow-hidden';
    card.dataset.typeVal   = typeVal;
    card.dataset.typeLabel = typeLabel2.toLowerCase();

    const name = document.createElement('div');
    name.className = 'fmt-type-name flex items-center justify-between px-3 py-2 cursor-pointer select-none font-medium text-sm hover:bg-base-200';

    const nameText = document.createElement('span');
    nameText.textContent = typeLabel2;
    name.appendChild(nameText);

    const toggle = document.createElement('span');
    toggle.className = 'fmt-card-toggle text-base-content/50 text-lg leading-none';
    toggle.textContent = '+';
    name.appendChild(toggle);

    name.addEventListener('click', () => {
      const nowCollapsed = card.classList.toggle('fmt-card-collapsed');
      toggle.textContent = nowCollapsed ? '+' : '−';
    });

    card.appendChild(name);

    const onChange = () => { schedulePreviewUpdate(); };

    const isHidden = typeVal === 'note' || typeVal === 'media';
    if (!isHidden) {
      card.appendChild(buildFmtControls(fmtObj, 'title', onChange));
      card.appendChild(buildFmtControls(fmtObj, 'body',  onChange));
    } else {
      const hint = document.createElement('p');
      hint.className = 'text-xs text-base-content/40 italic px-3 py-2 m-0';
      hint.textContent = 'Hidden from print — no formatting needed.';
      card.appendChild(hint);
    }

    grid.appendChild(card);
  });

  // Re-apply any active filter
  const filterInput = document.getElementById('fmt-filter');
  if (filterInput && filterInput.value) applyFmtFilter(filterInput.value);
}
