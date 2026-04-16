// Template gallery and designer

let _templatesInitialized = false;
let _pendingTemplateApply = null;
let _pendingApplyExitAfterChoice = false;
let _editingTemplate = null;
let _editingSavedSnapshot = '';
let _selectedZoneId = '';
let _selectedElement = null;
let _designerRenderTimer = null;
let _designerDrag = null;
let _designerFonts = [];
let _installedFonts = [];

const TEMPLATE_BINDINGS = ['cover', 'announcements', 'pco_items', 'calendar', 'serving_schedule', 'staff'];
const PCO_TYPES = ['song', 'liturgy', 'section', 'label'];
const DESIGNER_FONTS = [
  'system-ui',
  'Arial',
  'Helvetica',
  'Georgia',
  'Times New Roman',
  'Trebuchet MS',
  'Verdana',
  'Inter',
  'Roboto',
  'Lora',
  'Merriweather',
  'Montserrat',
];
_designerFonts = DESIGNER_FONTS.slice();

function cloneTemplate(template) {
  return JSON.parse(JSON.stringify(template || getClassicTemplateFallback()));
}

function templateSnapshot(template) {
  return JSON.stringify(template || {});
}

function designerIsDirty() {
  return !!_editingTemplate && templateSnapshot(_editingTemplate) !== _editingSavedSnapshot;
}

function getClassicTemplateFallback() {
  return {
    id: 'classic',
    name: 'Classic',
    builtIn: true,
    pageSize: '5.5x8.5',
    cssVars: {},
    typeFormats: {},
    zones: [
      { id: 'z-cover',   binding: 'cover',            order: 1, enabled: true, match: {}, elements: {} },
      { id: 'z-ann',     binding: 'announcements',    order: 2, enabled: true, match: {}, elements: {} },
      { id: 'z-oow',     binding: 'pco_items',        order: 3, enabled: true, match: {}, elements: {} },
      { id: 'z-cal',     binding: 'calendar',         order: 4, enabled: true, match: {}, elements: {} },
      { id: 'z-serving', binding: 'serving_schedule', order: 5, enabled: true, match: {}, elements: {} },
      { id: 'z-staff',   binding: 'staff',            order: 6, enabled: true, match: {}, elements: {} },
    ],
  };
}

function getTemplateList() {
  const list = Array.isArray(templates) && templates.length ? templates : [getClassicTemplateFallback()];
  if (list.some(t => t && t.id === 'classic')) return list;
  return [getClassicTemplateFallback()].concat(list);
}

function makeTemplateId() {
  return `tpl_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function templateSlug(value) {
  return String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'template';
}

function makeZoneId(binding) {
  return `z-${binding.replace(/_/g, '-')}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

function deterministicZoneId(zone, index) {
  const m = zone.match || {};
  return [
    'z',
    zone.binding || 'zone',
    m.type || 'all',
    m.title || m.titleContains || '',
    index + 1,
  ].map(templateSlug).filter(Boolean).join('-');
}

function bindingLabel(binding) {
  return ({
    cover: 'Cover',
    announcements: 'Announcements',
    pco_items: 'Order of Worship',
    calendar: 'Calendar',
    serving_schedule: 'Serving',
    staff: 'Staff',
  })[binding] || binding || 'Zone';
}

function zoneLabel(zone) {
  if (!zone) return 'Zone';
  const m = zone.match || {};
  if (zone.binding === 'pco_items' && m.type) {
    const typeLabel = m.type.charAt(0).toUpperCase() + m.type.slice(1);
    if (m.title) return `${typeLabel}: "${m.title}"`;
    if (m.titleContains) return `${typeLabel}: contains "${m.titleContains}"`;
    return `${typeLabel} Items`;
  }
  return bindingLabel(zone.binding);
}

function zoneSpecificityText(zone) {
  if (!zone) return '';
  const m = zone.match || {};
  const binding = bindingLabel(zone.binding).toLowerCase();
  if (zone.binding !== 'pco_items') return `This zone matches: ${binding}`;
  if (!m.type) return 'This zone matches: all order of worship items';
  if (m.title) return `This zone matches: ${m.type} items titled "${m.title}" exactly`;
  if (m.titleContains) return `This zone matches: ${m.type} items containing "${m.titleContains}"`;
  return `This zone matches: all ${m.type} items`;
}

function sortedZones() {
  return (_editingTemplate?.zones || [])
    .slice()
    .sort((a, b) => (a.order || 0) - (b.order || 0));
}

function templateDisplayOrder(template) {
  const zones = Array.isArray(template?.zones) ? template.zones : [];
  return zones
    .filter(z => z && z.enabled !== false)
    .slice()
    .sort((a, b) => (a.order || 0) - (b.order || 0));
}

function getZoneById(zoneId) {
  return (_editingTemplate?.zones || []).find(z => z.id === zoneId) || null;
}

function getSelectedZone() {
  return getZoneById(_selectedZoneId) || sortedZones()[0] || null;
}

function getZoneElements(zone) {
  if (!zone) return [];
  return getRegistryElements(zone.binding, zone.match?.type);
}

function getZoneElementFmt(zone, elementKey) {
  if (!zone) return {};
  if (!zone.elements || typeof zone.elements !== 'object') zone.elements = {};
  if (!zone.elements[elementKey] || typeof zone.elements[elementKey] !== 'object') zone.elements[elementKey] = {};
  return zone.elements[elementKey];
}

function readZoneElementFmt(zone, elementKey) {
  if (!zone || !zone.elements || typeof zone.elements !== 'object') return {};
  const fmt = zone.elements[elementKey];
  return fmt && typeof fmt === 'object' ? fmt : {};
}

function markDesignerDirty() {
  renderZoneTree();
  renderMatchEditor();
  renderDesignerToolbar();
  scheduleDesignerCanvasRender();
}

function designerFontOptions() {
  const names = new Set(_designerFonts.concat(_installedFonts.map(f => f.family)).concat([_editingTemplate?.cssVars?.fontFamily].filter(Boolean)));
  return Array.from(names).sort((a, b) => a.localeCompare(b)).map(name => ({
    value: name,
    label: _installedFonts.some(f => f.family === name) ? `${name} (Installed)` : name,
  }));
}

async function loadDesignerFonts() {
  try {
    const data = await apiFetch('/api/fonts');
    _installedFonts = [].concat(data.user || [], data.cached || []);
    _installedFonts.forEach(font => {
      if (font.family) _designerFonts.push(font.family);
    });
    renderFontManager();
    renderDesignerToolbar();
  } catch (err) {
    // Font APIs are optional for older servers; keep local/system fonts available.
  }
  if (typeof window === 'undefined' || typeof window.queryLocalFonts !== 'function') return;
  try {
    const localFonts = await window.queryLocalFonts();
    const names = new Set(_designerFonts);
    localFonts.forEach(font => {
      if (font.family) names.add(font.family);
    });
    _designerFonts = Array.from(names);
    renderDesignerToolbar();
  } catch (err) {
    // Browsers may require permission for local font access; the curated list remains available.
  }
}

function renderFontManager() {
  const list = document.getElementById('tpl-font-list');
  if (!list) return;
  const userFonts = _installedFonts.filter(font => font.source === 'user');
  list.innerHTML = '';
  if (!userFonts.length) {
    const empty = document.createElement('div');
    empty.className = 'text-xs text-base-content/50';
    empty.textContent = 'No uploaded fonts';
    list.appendChild(empty);
    return;
  }
  userFonts.forEach(font => {
    const row = document.createElement('div');
    row.className = 'flex items-center justify-between gap-2 rounded border border-base-300 px-2 py-1';
    const name = document.createElement('span');
    name.className = 'text-sm';
    name.textContent = font.family;
    name.style.fontFamily = font.family;
    row.appendChild(name);
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn btn-ghost btn-xs text-error';
    del.textContent = 'Delete';
    del.addEventListener('click', () => deleteUploadedFont(font));
    row.appendChild(del);
    list.appendChild(row);
  });
}

async function uploadFontFile(file) {
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  form.append('family', file.name.replace(/\.(ttf|otf|woff2?|TTF|OTF|WOFF2?)$/, '').replace(/[-_]+/g, ' '));
  try {
    const res = await fetch('/api/fonts', { method: 'POST', body: form });
    if (!res.ok) {
      let err = null;
      try { err = await res.json(); } catch (_) {}
      throw new Error(err?.error || `Font upload failed (${res.status})`);
    }
    setStatus(`Uploaded font "${file.name}".`, 'success');
    await loadDesignerFonts();
  } catch (err) {
    setStatus('Font upload failed: ' + (err.message || err), 'error');
  }
}

async function deleteUploadedFont(font) {
  if (!font || !confirm(`Delete uploaded font "${font.family}"?`)) return;
  try {
    await apiFetch(`/api/fonts/${encodeURIComponent(font.slug)}`, 'DELETE');
    setStatus(`Deleted "${font.family}".`, 'success');
    await loadDesignerFonts();
  } catch (err) {
    setStatus('Font delete failed: ' + (err.message || err), 'error');
  }
}

function normalizeTemplateForExport(template) {
  const copy = cloneTemplate(template);
  copy.id = templateSlug(copy.name || copy.id);
  copy.builtIn = false;
  copy.zones = (copy.zones || []).map((zone, index) => {
    const z = cloneTemplate(zone);
    z.id = deterministicZoneId(z, index);
    return z;
  });
  return copy;
}

function validateImportedTemplate(template) {
  if (!template || typeof template !== 'object' || Array.isArray(template)) return 'Template JSON must be an object.';
  if (!Array.isArray(template.zones) || !template.zones.length) return 'Template must include zones.';
  const validBindings = new Set(TEMPLATE_BINDINGS);
  for (const zone of template.zones) {
    if (!zone || typeof zone !== 'object') return 'Each zone must be an object.';
    if (!validBindings.has(zone.binding)) return `Invalid zone binding: ${zone.binding || '(missing)'}`;
    if (zone.elements && (typeof zone.elements !== 'object' || Array.isArray(zone.elements))) return 'Zone elements must be objects.';
  }
  return '';
}

function exportTemplate(template = _editingTemplate) {
  if (!template) return;
  const normalized = normalizeTemplateForExport(template);
  const blob = new Blob([JSON.stringify(normalized, null, 2) + '\n'], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${templateSlug(normalized.name || normalized.id)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function importTemplateFile(file) {
  if (!file) return;
  try {
    const imported = JSON.parse(await file.text());
    const error = validateImportedTemplate(imported);
    if (error) throw new Error(error);
    const template = cloneTemplate(imported);
    template.name = String(template.name || 'Imported Template').trim();
    template.id = templateSlug(template.id || template.name);
    template.builtIn = false;
    const ids = new Set(getTemplateList().map(t => t.id));
    if (ids.has(template.id)) template.id = `${template.id}-${Date.now().toString(36)}`;
    template.zones = template.zones.map((zone, index) => Object.assign({}, zone, {
      id: zone.id || deterministicZoneId(zone, index),
      order: Number.isFinite(Number(zone.order)) ? Number(zone.order) : index + 1,
      enabled: zone.enabled !== false,
      match: zone.match && typeof zone.match === 'object' ? zone.match : {},
      elements: zone.elements && typeof zone.elements === 'object' ? zone.elements : {},
    }));
    await apiFetch('/api/templates', 'POST', template);
    setTemplates(templates.concat([template]));
    renderTemplateGallery();
    openTemplateDesigner(template);
    setStatus(`Imported "${template.name}".`, 'success');
  } catch (err) {
    setStatus('Template import failed: ' + (err.message || err), 'error');
  } finally {
    const input = document.getElementById('tpl-import-input');
    if (input) input.value = '';
  }
}

function renderTemplateThumb(template) {
  const wrap = document.createElement('div');
  wrap.className = 'rounded border border-base-300 bg-base-200 p-2';
  wrap.style.cssText = 'height:8.5rem; display:flex; justify-content:center;';

  const page = document.createElement('div');
  page.className = 'bg-base-100 shadow-sm';
  page.style.cssText = 'width:4.25rem; height:6.6rem; padding:0.35rem; display:flex; flex-direction:column; gap:0.22rem;';

  templateDisplayOrder(template).slice(0, 7).forEach(zone => {
    const bar = document.createElement('div');
    const height = zone.binding === 'pco_items' ? '1.3rem' : '0.48rem';
    bar.style.cssText = `height:${height}; border-radius:2px; background:#cbd5e1;`;
    page.appendChild(bar);
  });

  wrap.appendChild(page);
  return wrap;
}

function renderTemplateGallery() {
  initTemplateControls();
  const grid = document.getElementById('tpl-grid');
  if (!grid) return;
  grid.innerHTML = '';

  getTemplateList().forEach(template => {
    const card = document.createElement('div');
    card.className = 'border border-base-300 rounded-lg bg-base-100 p-3 shadow-sm flex flex-col gap-3';
    card.appendChild(renderTemplateThumb(template));

    const titleRow = document.createElement('div');
    titleRow.className = 'flex items-start justify-between gap-2';

    const name = document.createElement('div');
    name.className = 'font-semibold text-sm leading-tight';
    name.textContent = template.name || 'Untitled Template';
    titleRow.appendChild(name);

    if (template.builtIn) {
      const badge = document.createElement('span');
      badge.className = 'badge badge-ghost badge-sm';
      badge.textContent = 'Built-in';
      titleRow.appendChild(badge);
    }
    card.appendChild(titleRow);

    const meta = document.createElement('div');
    meta.className = 'text-xs text-base-content/60';
    meta.textContent = templateDisplayOrder(template).map(z => bindingLabel(z.binding)).join(' / ') || 'No enabled zones';
    card.appendChild(meta);

    const actions = document.createElement('div');
    actions.className = 'flex gap-2 mt-auto';

    const applyBtn = document.createElement('button');
    applyBtn.className = 'btn btn-primary btn-xs';
    applyBtn.textContent = 'Apply';
    applyBtn.addEventListener('click', () => showApplyTemplateDialog(template, false));
    actions.appendChild(applyBtn);

    const editBtn = document.createElement('button');
    editBtn.className = 'btn btn-ghost btn-xs';
    editBtn.textContent = 'Design';
    editBtn.addEventListener('click', () => openTemplateDesigner(template));
    actions.appendChild(editBtn);

    const exportBtn = document.createElement('button');
    exportBtn.className = 'btn btn-ghost btn-xs';
    exportBtn.textContent = 'Export';
    exportBtn.addEventListener('click', () => exportTemplate(template));
    actions.appendChild(exportBtn);

    card.appendChild(actions);
    grid.appendChild(card);
  });
}

function ensureDesignerShell() {
  const overlay = document.getElementById('tpl-designer-overlay');
  const canvas = document.getElementById('tpl-designer-canvas');
  const toolbar = document.getElementById('tpl-designer-toolbar');
  if (!overlay || !canvas || !toolbar) return;

  if (!document.getElementById('tpl-designer-delete')) {
    const saveBtn = document.getElementById('tpl-designer-save');
    const del = document.createElement('button');
    del.className = 'btn btn-ghost btn-sm text-error';
    del.id = 'tpl-designer-delete';
    del.textContent = 'Delete';
    del.addEventListener('click', deleteEditingTemplate);
    saveBtn?.parentElement?.insertBefore(del, saveBtn);
  }

  if (!document.getElementById('tpl-designer-workspace')) {
    canvas.innerHTML = '';
    canvas.style.cssText = 'flex:1; overflow:hidden; background:#d7dde5; display:grid; grid-template-columns:260px minmax(0,1fr) 300px;';

    const left = document.createElement('aside');
    left.id = 'tpl-zone-panel';
    left.style.cssText = 'overflow:auto; background:var(--base-100,#fff); border-right:1px solid var(--base-300,#d1d5db); padding:0.75rem;';

    const center = document.createElement('main');
    center.id = 'tpl-designer-workspace';
    center.style.cssText = 'position:relative; overflow:auto; padding:1.5rem; display:flex; justify-content:center;';
    const live = document.createElement('div');
    live.id = 'tpl-live-canvas';
    live.style.cssText = 'position:relative;';
    center.appendChild(live);

    const right = document.createElement('aside');
    right.id = 'tpl-match-panel';
    right.style.cssText = 'overflow:auto; background:var(--base-100,#fff); border-left:1px solid var(--base-300,#d1d5db); padding:0.75rem;';

    canvas.appendChild(left);
    canvas.appendChild(center);
    canvas.appendChild(right);

    const guide = document.createElement('div');
    guide.id = 'tpl-snap-guide';
    guide.style.cssText = 'display:none; position:absolute; z-index:50; pointer-events:none; border-left:2px solid #2563eb; border-top:2px solid #2563eb;';
    center.appendChild(guide);
  }
  initDesignerCanvasEvents();
}

function openTemplateDesigner(template) {
  ensureDesignerShell();
  loadDesignerFonts();
  const source = cloneTemplate(template);
  _editingTemplate = source;
  if (!_editingTemplate.zones?.length) _editingTemplate.zones = cloneTemplate(getClassicTemplateFallback()).zones;
  _editingSavedSnapshot = templateSnapshot(_editingTemplate);
  _selectedZoneId = sortedZones()[0]?.id || '';
  _selectedElement = null;

  const nameInput = document.getElementById('tpl-designer-name');
  if (nameInput) nameInput.value = _editingTemplate.name || '';

  const overlay = document.getElementById('tpl-designer-overlay');
  if (overlay) overlay.style.display = 'flex';

  renderZoneTree();
  renderMatchEditor();
  renderDesignerToolbar();
  renderDesignerCanvas();
}

function closeTemplateDesigner(force = false) {
  if (!force && designerIsDirty() && !confirm('Discard unsaved template changes?')) return;
  _editingTemplate = null;
  _editingSavedSnapshot = '';
  _selectedZoneId = '';
  _selectedElement = null;
  const overlay = document.getElementById('tpl-designer-overlay');
  if (overlay) overlay.style.display = 'none';
}

function scheduleDesignerCanvasRender() {
  clearTimeout(_designerRenderTimer);
  _designerRenderTimer = setTimeout(renderDesignerCanvas, 300);
}

function renderDesignerCanvas() {
  const live = document.getElementById('tpl-live-canvas');
  if (!live || !_editingTemplate) return;
  live.innerHTML = '';

  const previousTemplate = cloneTemplate(activeDocTemplate);
  setActiveDocTemplate(_editingTemplate);
  applyDocTemplate();
  renderPreview();
  previewPane.querySelectorAll('.booklet-page').forEach(page => {
    const clone = page.cloneNode(true);
    clone.querySelectorAll('.preview-page-num, .pg-break-ctrl, .pg-split-ctrl').forEach(el => el.remove());
    clone.classList.add('tpl-canvas-page');
    clone.style.position = 'relative';
    live.appendChild(clone);
  });

  setActiveDocTemplate(previousTemplate);
  applyDocTemplate();
  renderPreview();
  decorateDesignerCanvas();
}

function inferCanvasElement(target) {
  const el = target.closest('.cover-church,.cover-title,.cover-date,.ann-item-heading,.ann-body,.ann-qr-wrap,.section-heading,.item-heading,.item-body,.song-copyright,.cal-day-heading,.cal-event-title,.cal-event-time,.cal-event-loc,.serving-week-label,.serving-service-time,.serving-team-name,.serving-role,.serving-row span:not(.serving-role),.sname,.srole,.semail');
  if (!el) return null;
  const text = (el.textContent || '').trim();

  if (el.classList.contains('cover-church')) return { el, binding: 'cover', itemType: '', title: '', elementKey: 'churchName' };
  if (el.classList.contains('cover-title')) return { el, binding: 'cover', itemType: '', title: '', elementKey: 'subtitle' };
  if (el.classList.contains('cover-date')) return { el, binding: 'cover', itemType: '', title: '', elementKey: 'serviceDate' };
  if (el.classList.contains('ann-item-heading')) return { el, binding: 'announcements', itemType: '', title: text, elementKey: 'title' };
  if (el.classList.contains('ann-body')) return { el, binding: 'announcements', itemType: '', title: nearestAnnouncementTitle(el), elementKey: 'body' };
  if (el.classList.contains('ann-qr-wrap')) return { el, binding: 'announcements', itemType: '', title: nearestAnnouncementTitle(el), elementKey: 'url' };
  if (el.classList.contains('section-heading')) return { el, binding: 'pco_items', itemType: 'section', title: text, elementKey: 'heading' };
  if (el.classList.contains('song-copyright')) return { el, binding: 'pco_items', itemType: 'song', title: nearestOowTitle(el), elementKey: 'copyright' };
  if (el.classList.contains('item-heading')) {
    const item = itemByTitle(text);
    const type = item?.type || 'label';
    return { el, binding: 'pco_items', itemType: type, title: text, elementKey: type === 'song' ? 'songTitle' : 'title' };
  }
  if (el.classList.contains('item-body')) {
    const title = nearestOowTitle(el);
    const item = itemByTitle(title);
    const type = item?.type || 'label';
    return { el, binding: 'pco_items', itemType: type, title, elementKey: type === 'song' ? 'stanzaText' : type === 'liturgy' ? 'bodyParagraph' : 'body' };
  }
  if (el.classList.contains('cal-day-heading')) return { el, binding: 'calendar', itemType: '', title: text, elementKey: 'dayHeading' };
  if (el.classList.contains('cal-event-title')) return { el, binding: 'calendar', itemType: '', title: text, elementKey: 'eventTitle' };
  if (el.classList.contains('cal-event-time')) return { el, binding: 'calendar', itemType: '', title: nearestCalendarTitle(el), elementKey: 'eventTime' };
  if (el.classList.contains('cal-event-loc')) return { el, binding: 'calendar', itemType: '', title: nearestCalendarTitle(el), elementKey: 'eventDescription' };
  if (el.classList.contains('serving-week-label')) return { el, binding: 'serving_schedule', itemType: '', title: text, elementKey: 'weekHeading' };
  if (el.classList.contains('serving-service-time')) return { el, binding: 'serving_schedule', itemType: '', title: text, elementKey: 'serviceTime' };
  if (el.classList.contains('serving-team-name')) return { el, binding: 'serving_schedule', itemType: '', title: text, elementKey: 'teamName' };
  if (el.classList.contains('serving-role')) return { el, binding: 'serving_schedule', itemType: '', title: text.replace(/:\s*$/, ''), elementKey: 'positionLabel' };
  if (el.closest('.serving-row')) return { el, binding: 'serving_schedule', itemType: '', title: el.closest('.serving-row')?.querySelector('.serving-role')?.textContent?.replace(/:\s*$/, '') || '', elementKey: 'volunteerName' };
  if (el.classList.contains('sname')) return { el, binding: 'staff', itemType: '', title: text, elementKey: 'staffName' };
  if (el.classList.contains('srole')) return { el, binding: 'staff', itemType: '', title: closestStaffName(el), elementKey: 'staffRole' };
  if (el.classList.contains('semail')) return { el, binding: 'staff', itemType: '', title: closestStaffName(el), elementKey: 'staffEmail' };
  return null;
}

function nearestAnnouncementTitle(el) {
  return el.parentElement?.querySelector('.ann-item-heading')?.textContent?.trim() || '';
}

function nearestOowTitle(el) {
  return el.closest('.order-item')?.querySelector('.item-heading')?.textContent?.trim() || '';
}

function nearestCalendarTitle(el) {
  return el.closest('.cal-event-row')?.querySelector('.cal-event-title')?.textContent?.trim() || '';
}

function closestStaffName(el) {
  return el.closest('tr')?.querySelector('.sname')?.textContent?.trim() || '';
}

function itemByTitle(title) {
  return items.find(item => (item.title || '').trim() === title) || null;
}

function decorateDesignerCanvas() {
  const live = document.getElementById('tpl-live-canvas');
  if (!live) return;
  live.querySelectorAll('*').forEach(el => {
    const info = inferCanvasElement(el);
    if (!info) return;
    el.classList.add('tpl-selectable-element');
    el.style.cursor = 'pointer';
    el.style.outlineOffset = '2px';
    if (_selectedElement &&
        info.binding === _selectedElement.binding &&
        info.itemType === _selectedElement.itemType &&
        info.elementKey === _selectedElement.elementKey) {
      el.style.outline = '2px solid #2563eb';
    }
    const fmt = getElementFmtForInfo(info);
    if (fmt?.layout?.position === 'free') {
      el.style.position = 'relative';
      el.style.left = (fmt.layout.x || 0) + 'px';
      el.style.top = (fmt.layout.y || 0) + 'px';
    }
  });
}

function getElementFmtForInfo(info) {
  const zone = bestMatchingZone(_editingTemplate, info.binding, info.itemType, info.title);
  return readZoneElementFmt(zone, info.elementKey);
}

function selectCanvasElement(info) {
  const zone = ensureZoneForSelection(info);
  _selectedZoneId = zone.id;
  _selectedElement = {
    binding: info.binding,
    itemType: info.itemType,
    title: info.title || '',
    elementKey: info.elementKey,
  };
  renderZoneTree();
  renderMatchEditor();
  renderDesignerToolbar();
  decorateDesignerCanvas();
}

function ensureZoneForSelection(info) {
  let zone = bestMatchingZone(_editingTemplate, info.binding, info.itemType, info.title);
  if (zone) return zone;
  zone = {
    id: makeZoneId(info.binding),
    binding: info.binding,
    order: nextZoneOrder(),
    enabled: true,
    match: info.itemType ? { type: info.itemType } : {},
    elements: {},
  };
  _editingTemplate.zones.push(zone);
  return zone;
}

function getSelectedElementFmtForInfo(info) {
  const zone = ensureZoneForSelection(info);
  return getZoneElementFmt(zone, info.elementKey);
}

function nextZoneOrder() {
  return Math.max(0, ...(_editingTemplate?.zones || []).map(z => Number(z.order) || 0)) + 1;
}

function renderZoneTree() {
  const panel = document.getElementById('tpl-zone-panel');
  if (!panel || !_editingTemplate) return;
  panel.innerHTML = '';

  const header = document.createElement('div');
  header.className = 'font-semibold text-sm mb-2';
  header.textContent = 'Zones';
  panel.appendChild(header);

  sortedZones().forEach((zone, idx) => {
    const row = document.createElement('div');
    row.className = 'tpl-zone-row';
    row.draggable = true;
    row.dataset.zoneId = zone.id;
    row.style.cssText = `display:grid; grid-template-columns:auto auto 1fr auto auto; gap:0.35rem; align-items:center; padding:0.35rem; border-radius:6px; margin-bottom:0.2rem; border:1px solid ${zone.id === _selectedZoneId ? '#2563eb' : 'transparent'}; background:${zone.id === _selectedZoneId ? '#eff6ff' : 'transparent'};`;

    const drag = document.createElement('span');
    drag.textContent = '=';
    drag.style.cursor = 'grab';
    row.appendChild(drag);

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = zone.enabled !== false;
    cb.addEventListener('change', e => {
      zone.enabled = e.target.checked;
      markDesignerDirty();
    });
    row.appendChild(cb);

    const label = document.createElement('button');
    label.type = 'button';
    label.textContent = zoneLabel(zone);
    label.style.cssText = 'text-align:left; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
    label.addEventListener('click', () => {
      _selectedZoneId = zone.id;
      _selectedElement = null;
      renderZoneTree();
      renderMatchEditor();
      renderDesignerToolbar();
    });
    row.appendChild(label);

    const up = document.createElement('button');
    up.type = 'button';
    up.className = 'btn btn-ghost btn-xs';
    up.textContent = 'Up';
    up.disabled = idx === 0;
    up.addEventListener('click', () => moveZone(zone.id, -1));
    row.appendChild(up);

    const down = document.createElement('button');
    down.type = 'button';
    down.className = 'btn btn-ghost btn-xs';
    down.textContent = 'Down';
    down.disabled = idx === sortedZones().length - 1;
    down.addEventListener('click', () => moveZone(zone.id, 1));
    row.appendChild(down);

    row.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', zone.id));
    row.addEventListener('dragover', e => e.preventDefault());
    row.addEventListener('drop', e => {
      e.preventDefault();
      const draggedId = e.dataTransfer.getData('text/plain');
      reorderZoneBefore(draggedId, zone.id);
    });

    panel.appendChild(row);

    const elements = getZoneElements(zone);
    if (elements.length) {
      const childWrap = document.createElement('div');
      childWrap.style.cssText = 'margin:0 0 0.35rem 1.35rem; display:grid; gap:0.15rem;';
      elements.forEach(elDesc => {
        const child = document.createElement('button');
        child.type = 'button';
        child.textContent = elDesc.label;
        child.style.cssText = `font-size:0.75rem; text-align:left; padding:0.18rem 0.35rem; border-radius:4px; background:${_selectedZoneId === zone.id && _selectedElement?.elementKey === elDesc.key ? '#dbeafe' : 'transparent'};`;
        child.addEventListener('click', () => {
          _selectedZoneId = zone.id;
          _selectedElement = { binding: zone.binding, itemType: zone.match?.type || '', title: zone.match?.title || zone.match?.titleContains || '', elementKey: elDesc.key };
          renderZoneTree();
          renderMatchEditor();
          renderDesignerToolbar();
          decorateDesignerCanvas();
        });
        childWrap.appendChild(child);
      });
      if (zone.binding === 'pco_items' && zone.match?.type) {
        const addSpecific = document.createElement('button');
        addSpecific.type = 'button';
        addSpecific.className = 'btn btn-ghost btn-xs';
        addSpecific.textContent = '+ Add title match';
        addSpecific.addEventListener('click', () => addTitleMatchZone(zone));
        childWrap.appendChild(addSpecific);
      }
      panel.appendChild(childWrap);
    }
  });

  const add = document.createElement('button');
  add.className = 'btn btn-primary btn-sm w-full mt-2';
  add.type = 'button';
  add.textContent = '+ Add Zone';
  add.addEventListener('click', addZone);
  panel.appendChild(add);
}

function moveZone(zoneId, delta) {
  const zones = sortedZones();
  const idx = zones.findIndex(z => z.id === zoneId);
  const targetIdx = idx + delta;
  if (idx < 0 || targetIdx < 0 || targetIdx >= zones.length) return;
  [zones[idx], zones[targetIdx]] = [zones[targetIdx], zones[idx]];
  zones.forEach((z, i) => { z.order = i + 1; });
  markDesignerDirty();
}

function reorderZoneBefore(draggedId, beforeId) {
  if (!draggedId || draggedId === beforeId) return;
  const zones = sortedZones();
  const dragged = zones.find(z => z.id === draggedId);
  if (!dragged) return;
  const without = zones.filter(z => z.id !== draggedId);
  const beforeIdx = without.findIndex(z => z.id === beforeId);
  without.splice(beforeIdx < 0 ? without.length : beforeIdx, 0, dragged);
  without.forEach((z, i) => { z.order = i + 1; });
  markDesignerDirty();
}

function addZone() {
  const binding = prompt(`Binding (${TEMPLATE_BINDINGS.join(', ')})`, 'pco_items');
  if (!binding || !TEMPLATE_BINDINGS.includes(binding)) return;
  const zone = {
    id: makeZoneId(binding),
    binding,
    order: nextZoneOrder(),
    enabled: true,
    match: binding === 'pco_items' ? { type: 'label' } : {},
    elements: {},
  };
  _editingTemplate.zones.push(zone);
  _selectedZoneId = zone.id;
  _selectedElement = null;
  markDesignerDirty();
}

function addTitleMatchZone(parentZone) {
  const title = prompt('Item title to match');
  if (!title) return;
  const mode = prompt('Match mode: exact or contains', 'exact');
  const child = {
    id: makeZoneId(parentZone.binding),
    binding: parentZone.binding,
    order: (Number(parentZone.order) || nextZoneOrder()) + 0.1,
    enabled: true,
    match: { type: parentZone.match?.type || 'label' },
    elements: {},
  };
  if ((mode || '').toLowerCase().startsWith('contains')) child.match.titleContains = title;
  else child.match.title = title;
  _editingTemplate.zones.push(child);
  sortedZones().forEach((z, i) => { z.order = i + 1; });
  _selectedZoneId = child.id;
  _selectedElement = null;
  markDesignerDirty();
}

function renderMatchEditor() {
  const panel = document.getElementById('tpl-match-panel');
  if (!panel || !_editingTemplate) return;
  const zone = getSelectedZone();
  panel.innerHTML = '';

  const title = document.createElement('div');
  title.className = 'font-semibold text-sm mb-3';
  title.textContent = 'Match Rule';
  panel.appendChild(title);

  if (!zone) return;

  const bindingSel = makeSelect(TEMPLATE_BINDINGS, zone.binding);
  addField(panel, 'Binding', bindingSel);
  bindingSel.addEventListener('change', () => {
    zone.binding = bindingSel.value;
    zone.match = zone.binding === 'pco_items' ? { type: 'label' } : {};
    zone.elements = {};
    _selectedElement = null;
    markDesignerDirty();
  });

  if (zone.binding === 'pco_items') {
    const typeSel = makeSelect(['all'].concat(PCO_TYPES), zone.match?.type || 'all');
    addField(panel, 'Type', typeSel);
    typeSel.addEventListener('change', () => {
      zone.match = zone.match || {};
      if (typeSel.value === 'all') delete zone.match.type;
      else zone.match.type = typeSel.value;
      markDesignerDirty();
    });
  }

  const matchMode = zone.match?.title ? 'exact' : zone.match?.titleContains ? 'contains' : 'none';
  const modeSel = makeSelect(['none', 'exact', 'contains'], matchMode);
  addField(panel, 'Title Match', modeSel);

  const titleInput = document.createElement('input');
  titleInput.className = 'input input-bordered input-sm w-full';
  titleInput.value = zone.match?.title || zone.match?.titleContains || '';
  titleInput.placeholder = 'Item title';
  addField(panel, 'Title', titleInput);

  function syncTitleMatch() {
    zone.match = zone.match || {};
    delete zone.match.title;
    delete zone.match.titleContains;
    if (modeSel.value === 'exact' && titleInput.value.trim()) zone.match.title = titleInput.value.trim();
    if (modeSel.value === 'contains' && titleInput.value.trim()) zone.match.titleContains = titleInput.value.trim();
    renderZoneTree();
    renderDesignerToolbar();
    badge.textContent = zoneSpecificityText(zone);
    scheduleDesignerCanvasRender();
  }
  modeSel.addEventListener('change', syncTitleMatch);
  titleInput.addEventListener('input', syncTitleMatch);

  const badge = document.createElement('div');
  badge.className = 'text-xs text-base-content/70 bg-base-200 rounded p-2 my-3';
  badge.textContent = zoneSpecificityText(zone);
  panel.appendChild(badge);

  const addSpecific = document.createElement('button');
  addSpecific.type = 'button';
  addSpecific.className = 'btn btn-ghost btn-sm w-full';
  addSpecific.textContent = '+ Add specific item rule';
  addSpecific.disabled = !(zone.binding === 'pco_items' && zone.match?.type);
  addSpecific.addEventListener('click', () => addTitleMatchZone(zone));
  panel.appendChild(addSpecific);

  const del = document.createElement('button');
  del.type = 'button';
  del.className = 'btn btn-ghost btn-sm text-error w-full mt-2';
  del.textContent = 'Delete Zone';
  del.addEventListener('click', () => deleteZone(zone.id));
  panel.appendChild(del);
}

function addField(parent, labelText, control) {
  const label = document.createElement('label');
  label.className = 'text-xs font-medium block mt-2 mb-1';
  label.textContent = labelText;
  parent.appendChild(label);
  parent.appendChild(control);
}

function makeSelect(values, current) {
  const sel = document.createElement('select');
  sel.className = 'select select-bordered select-sm w-full';
  values.forEach(v => {
    const value = typeof v === 'object' ? v.value : v;
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = typeof v === 'object' ? v.label : v;
    sel.appendChild(opt);
  });
  sel.value = current;
  return sel;
}

function deleteZone(zoneId) {
  if (!confirm('Delete this zone?')) return;
  _editingTemplate.zones = (_editingTemplate.zones || []).filter(z => z.id !== zoneId);
  _selectedZoneId = sortedZones()[0]?.id || '';
  _selectedElement = null;
  markDesignerDirty();
}

function renderDesignerToolbar() {
  const toolbar = document.getElementById('tpl-designer-toolbar');
  if (!toolbar || !_editingTemplate) return;
  toolbar.innerHTML = '';

  if (!_selectedElement) {
    const pageSize = makeSelect(Object.keys(PAGE_SIZE_PRESETS), _editingTemplate.pageSize || '5.5x8.5');
    pageSize.addEventListener('change', () => {
      _editingTemplate.pageSize = pageSize.value;
      markDesignerDirty();
    });
    toolbar.appendChild(toolbarGroup('Page', pageSize));

    const font = makeSelect(designerFontOptions(), _editingTemplate.cssVars?.fontFamily || 'system-ui');
    font.addEventListener('change', () => {
      _editingTemplate.cssVars = _editingTemplate.cssVars || {};
      _editingTemplate.cssVars.fontFamily = font.value;
      markDesignerDirty();
    });
    toolbar.appendChild(toolbarGroup('Font', font));

    [
      ['Primary', 'primary', '#111827'],
      ['Muted', 'muted', '#6b7280'],
      ['Accent', 'accent', '#172429'],
      ['Border', 'border', '#e5e7eb'],
    ].forEach(([label, key, fallback]) => {
      const color = document.createElement('input');
      color.type = 'color';
      color.value = _editingTemplate.cssVars?.[key] || fallback;
      color.addEventListener('input', () => {
        _editingTemplate.cssVars = _editingTemplate.cssVars || {};
        _editingTemplate.cssVars[key] = color.value;
        markDesignerDirty();
      });
      toolbar.appendChild(toolbarGroup(label, color));
    });
    return;
  }

  const zone = getZoneById(_selectedZoneId);
  const fmt = getZoneElementFmt(zone, _selectedElement.elementKey);
  toolbar.appendChild(toolbarText(`${zoneLabel(zone)} / ${_selectedElement.elementKey}`));

  const font = makeSelect([''].concat(designerFontOptions()), fmt.fontFamily || '');
  font.addEventListener('change', () => updateSelectedFmt('fontFamily', font.value));
  toolbar.appendChild(toolbarGroup('Font', font));

  const size = makeSelect(['', 'sm', 'lg', 'xl'], fmt.size || '');
  size.addEventListener('change', () => updateSelectedFmt('size', size.value));
  toolbar.appendChild(toolbarGroup('Size', size));

  toolbar.appendChild(toggleButton('B', !!fmt.bold, () => updateSelectedFmt('bold', !fmt.bold)));
  toolbar.appendChild(toggleButton('I', !!fmt.italic, () => updateSelectedFmt('italic', !fmt.italic)));
  toolbar.appendChild(toggleButton('U', !!fmt.underline, () => updateSelectedFmt('underline', !fmt.underline)));

  const align = makeSelect(['', 'left', 'center', 'right'], fmt.align || '');
  align.addEventListener('change', () => updateSelectedFmt('align', align.value));
  toolbar.appendChild(toolbarGroup('Align', align));

  const color = document.createElement('input');
  color.type = 'color';
  color.value = fmt.color || '#172429';
  color.addEventListener('input', () => updateSelectedFmt('color', color.value));
  toolbar.appendChild(toolbarGroup('Color', color));

  const layoutAlign = makeSelect(['', 'left', 'center', 'right', 'space-between'], fmt.layout?.align || '');
  layoutAlign.addEventListener('change', () => updateSelectedLayout({ align: layoutAlign.value }));
  toolbar.appendChild(toolbarGroup('Layout', layoutAlign));

  const reset = document.createElement('button');
  reset.type = 'button';
  reset.className = 'btn btn-ghost btn-sm';
  reset.textContent = 'Reset';
  reset.addEventListener('click', resetSelectedFmt);
  toolbar.appendChild(reset);
}

function toolbarGroup(label, control) {
  const wrap = document.createElement('label');
  wrap.style.cssText = 'display:flex; align-items:center; gap:0.35rem;';
  const span = document.createElement('span');
  span.className = 'text-xs text-base-content/60';
  span.textContent = label;
  wrap.appendChild(span);
  wrap.appendChild(control);
  return wrap;
}

function toolbarText(text) {
  const span = document.createElement('span');
  span.className = 'text-sm font-medium';
  span.textContent = text;
  return span;
}

function toggleButton(text, active, onClick) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn btn-sm ' + (active ? 'btn-primary' : 'btn-ghost');
  btn.textContent = text;
  btn.addEventListener('click', onClick);
  return btn;
}

function updateSelectedFmt(key, value) {
  const zone = getZoneById(_selectedZoneId);
  if (!zone || !_selectedElement) return;
  const fmt = getZoneElementFmt(zone, _selectedElement.elementKey);
  if (value === '' || value === undefined) delete fmt[key];
  else fmt[key] = value;
  markDesignerDirty();
}

function updateSelectedLayout(partial) {
  const zone = getZoneById(_selectedZoneId);
  if (!zone || !_selectedElement) return;
  const fmt = getZoneElementFmt(zone, _selectedElement.elementKey);
  fmt.layout = Object.assign({}, fmt.layout || {}, partial);
  markDesignerDirty();
}

function resetSelectedFmt() {
  const zone = getZoneById(_selectedZoneId);
  if (!zone || !_selectedElement || !zone.elements) return;
  delete zone.elements[_selectedElement.elementKey];
  markDesignerDirty();
}

function showApplyTemplateDialog(template, exitAfterChoice) {
  _pendingTemplateApply = cloneTemplate(template);
  _pendingApplyExitAfterChoice = !!exitAfterChoice;
  const msg = document.getElementById('tpl-apply-dialog-msg');
  if (msg) msg.textContent = `Apply "${_pendingTemplateApply.name || 'this template'}" to the current project?`;
  const dialog = document.getElementById('tpl-apply-dialog');
  if (dialog) dialog.style.display = 'flex';
}

function hideApplyTemplateDialog() {
  _pendingTemplateApply = null;
  const dialog = document.getElementById('tpl-apply-dialog');
  if (dialog) dialog.style.display = 'none';
  if (_pendingApplyExitAfterChoice) {
    _pendingApplyExitAfterChoice = false;
    closeTemplateDesigner(true);
  }
}

function applyPendingTemplate() {
  if (!_pendingTemplateApply) return;
  setActiveDocTemplate(_pendingTemplateApply);
  applyDocTemplate();
  schedulePreviewUpdate();
  scheduleProjectPersist();
  apiFetch('/api/settings', 'POST', { docTemplate: activeDocTemplate })
    .catch(err => setStatus('Template save failed: ' + (err.message || err), 'error'));
  setStatus(`Applied "${activeDocTemplate.name || 'Template'}".`, 'success');
  const shouldExit = _pendingApplyExitAfterChoice;
  _pendingApplyExitAfterChoice = false;
  hideApplyTemplateDialog();
  if (shouldExit) closeTemplateDesigner(true);
}

async function saveEditingTemplate(saveAs) {
  if (!_editingTemplate) return;
  const nameInput = document.getElementById('tpl-designer-name');
  const nextTemplate = cloneTemplate(_editingTemplate);
  nextTemplate.name = (nameInput?.value || '').trim() || 'Untitled Template';

  if (saveAs) {
    const name = prompt('Save template as', `Copy of ${nextTemplate.name}`);
    if (!name) return;
    nextTemplate.name = name;
    nextTemplate.id = makeTemplateId();
    nextTemplate.builtIn = false;
  }

  if (nextTemplate.builtIn) {
    nextTemplate.id = makeTemplateId();
    nextTemplate.name = `Copy of ${nextTemplate.name || 'Template'}`;
    nextTemplate.builtIn = false;
  }

  try {
    await apiFetch('/api/templates', 'POST', nextTemplate);
    const existingIdx = templates.findIndex(t => t.id === nextTemplate.id);
    if (existingIdx >= 0) templates[existingIdx] = nextTemplate;
    else templates.push(nextTemplate);
    _editingTemplate = nextTemplate;
    _editingSavedSnapshot = templateSnapshot(_editingTemplate);
    setStatus(`Saved "${nextTemplate.name}".`, 'success');
    renderTemplateGallery();
    showApplyTemplateDialog(nextTemplate, true);
  } catch (err) {
    setStatus('Template save failed: ' + (err.message || err), 'error');
  }
}

function startNewTemplate() {
  const list = getTemplateList();
  const labels = list.map((t, i) => `${i + 1}. ${t.name || t.id}`).join('\n');
  const choice = prompt(`Choose a base template:\n${labels}`, '1');
  const idx = Math.max(0, Math.min(list.length - 1, parseInt(choice, 10) - 1 || 0));
  const base = cloneTemplate(list[idx]);
  base.id = makeTemplateId();
  base.name = `Copy of ${base.name || 'Template'}`;
  base.builtIn = false;
  openTemplateDesigner(base);
  _editingSavedSnapshot = '';
}

async function deleteEditingTemplate() {
  if (!_editingTemplate) return;
  if (_editingTemplate.builtIn) {
    setStatus('Built-in templates cannot be deleted.', 'error');
    return;
  }
  if (!confirm(`Delete "${_editingTemplate.name || 'this template'}"? This cannot be undone.`)) return;
  try {
    await apiFetch(`/api/templates/${encodeURIComponent(_editingTemplate.id)}`, 'DELETE');
    setTemplates(templates.filter(t => t.id !== _editingTemplate.id));
    renderTemplateGallery();
    closeTemplateDesigner(true);
    setStatus('Template deleted.', 'success');
  } catch (err) {
    setStatus('Template delete failed: ' + (err.message || err), 'error');
  }
}

function initDesignerCanvasEvents() {
  const workspace = document.getElementById('tpl-designer-workspace');
  if (!workspace || workspace.dataset.tplEvents === '1') return;
  workspace.dataset.tplEvents = '1';

  workspace.addEventListener('click', e => {
    const info = inferCanvasElement(e.target);
    if (!info) {
      _selectedElement = null;
      renderDesignerToolbar();
      decorateDesignerCanvas();
      return;
    }
    e.preventDefault();
    selectCanvasElement(info);
  });

  workspace.addEventListener('pointerdown', e => {
    const info = inferCanvasElement(e.target);
    if (!info) return;
    selectCanvasElement(info);
    const page = info.el.closest('.booklet-page');
    const pageRect = page?.getBoundingClientRect();
    const elRect = info.el.getBoundingClientRect();
    const startLeft = parseFloat(info.el.style.left || '0') || 0;
    const startTop = parseFloat(info.el.style.top || '0') || 0;
    _designerDrag = {
      info,
      startX: e.clientX,
      startY: e.clientY,
      startLeft,
      startTop,
      width: elRect.width,
      height: elRect.height,
      originPageLeft: pageRect ? elRect.left - pageRect.left - startLeft : 0,
      originPageTop: pageRect ? elRect.top - pageRect.top - startTop : 0,
    };
    info.el.setPointerCapture?.(e.pointerId);
  });

  workspace.addEventListener('pointermove', e => {
    if (!_designerDrag) return;
    const dx = e.clientX - _designerDrag.startX;
    const dy = e.clientY - _designerDrag.startY;
    const snapped = snapDrag(_designerDrag.startLeft + dx, _designerDrag.startTop + dy, _designerDrag.info.el);
    _designerDrag.info.el.style.position = 'relative';
    _designerDrag.info.el.style.left = snapped.x + 'px';
    _designerDrag.info.el.style.top = snapped.y + 'px';
  });

  workspace.addEventListener('pointerup', () => finishDesignerDrag());
  workspace.addEventListener('pointercancel', () => finishDesignerDrag());
}

function snapDrag(x, y, el) {
  const threshold = 8;
  const page = el.closest('.booklet-page');
  const guide = document.getElementById('tpl-snap-guide');
  let snappedX = x;
  let snappedY = y;
  let showGuide = false;
  if (page) {
    const pageRect = page.getBoundingClientRect();
    const drag = _designerDrag || {};
    const originLeft = drag.originPageLeft || 0;
    const originTop = drag.originPageTop || 0;
    const width = drag.width || el.getBoundingClientRect().width;
    const height = drag.height || el.getBoundingClientRect().height;
    const target = {
      left: originLeft + x,
      right: originLeft + x + width,
      top: originTop + y,
      bottom: originTop + y + height,
      midX: originLeft + x + width / 2,
      midY: originTop + y + height / 2,
    };

    const candidates = [
      { axis: 'x', value: -originLeft, delta: Math.abs(target.left) },
      { axis: 'x', value: pageRect.width - originLeft - width, delta: Math.abs(target.right - pageRect.width) },
      { axis: 'x', value: pageRect.width / 2 - originLeft - width / 2, delta: Math.abs(target.midX - pageRect.width / 2) },
      { axis: 'y', value: -originTop, delta: Math.abs(target.top) },
      { axis: 'y', value: pageRect.height - originTop - height, delta: Math.abs(target.bottom - pageRect.height) },
      { axis: 'y', value: pageRect.height / 2 - originTop - height / 2, delta: Math.abs(target.midY - pageRect.height / 2) },
    ];

    page.querySelectorAll('.tpl-selectable-element').forEach(other => {
      if (other === el) return;
      const rect = other.getBoundingClientRect();
      const otherBox = {
        left: rect.left - pageRect.left,
        right: rect.right - pageRect.left,
        top: rect.top - pageRect.top,
        bottom: rect.bottom - pageRect.top,
        midX: rect.left - pageRect.left + rect.width / 2,
        midY: rect.top - pageRect.top + rect.height / 2,
      };
      candidates.push(
        { axis: 'x', value: otherBox.left - originLeft, delta: Math.abs(target.left - otherBox.left) },
        { axis: 'x', value: otherBox.right - originLeft - width, delta: Math.abs(target.right - otherBox.right) },
        { axis: 'x', value: otherBox.midX - originLeft - width / 2, delta: Math.abs(target.midX - otherBox.midX) },
        { axis: 'y', value: otherBox.top - originTop, delta: Math.abs(target.top - otherBox.top) },
        { axis: 'y', value: otherBox.bottom - originTop - height, delta: Math.abs(target.bottom - otherBox.bottom) },
        { axis: 'y', value: otherBox.midY - originTop - height / 2, delta: Math.abs(target.midY - otherBox.midY) },
      );
    });

    const bestX = candidates.filter(c => c.axis === 'x' && c.delta < threshold).sort((a, b) => a.delta - b.delta)[0];
    const bestY = candidates.filter(c => c.axis === 'y' && c.delta < threshold).sort((a, b) => a.delta - b.delta)[0];
    if (bestX) { snappedX = bestX.value; showGuide = true; }
    if (bestY) { snappedY = bestY.value; showGuide = true; }
    if (guide && showGuide) {
      const parentRect = guide.parentElement.getBoundingClientRect();
      guide.style.left = (pageRect.left - parentRect.left + originLeft + snappedX) + 'px';
      guide.style.top = (pageRect.top - parentRect.top + originTop + snappedY) + 'px';
      guide.style.width = bestY ? pageRect.width + 'px' : '0';
      guide.style.height = bestX ? pageRect.height + 'px' : '0';
      guide.style.borderLeftWidth = bestX ? '2px' : '0';
      guide.style.borderTopWidth = bestY ? '2px' : '0';
    }
  }
  if (guide) guide.style.display = showGuide ? 'block' : 'none';
  return { x: Math.round(snappedX), y: Math.round(snappedY) };
}

function finishDesignerDrag() {
  if (!_designerDrag) return;
  const left = parseFloat(_designerDrag.info.el.style.left || '0') || 0;
  const top = parseFloat(_designerDrag.info.el.style.top || '0') || 0;
  const zone = getZoneById(_selectedZoneId);
  if (zone && _selectedElement) {
    const fmt = getZoneElementFmt(zone, _selectedElement.elementKey);
    const inlineLayout = deriveInlineLayoutForDrop(_designerDrag.info.el, _selectedElement);
    fmt.layout = inlineLayout || Object.assign({}, fmt.layout || {}, { position: 'free', x: left, y: top });
  }
  const guide = document.getElementById('tpl-snap-guide');
  if (guide) guide.style.display = 'none';
  _designerDrag = null;
  markDesignerDirty();
}

function deriveInlineLayoutForDrop(el, selected) {
  if (!el || !selected || selected.binding !== 'pco_items') return null;
  const item = el.closest('.order-item');
  if (!item) return null;
  const candidates = Array.from(item.querySelectorAll('.tpl-selectable-element')).filter(candidate => {
    if (candidate === el) return false;
    const info = inferCanvasElement(candidate);
    if (!info || info.binding !== selected.binding) return false;
    if (info.itemType !== selected.itemType || info.title !== selected.title) return false;
    return info.elementKey === 'songTitle' || info.elementKey === 'title';
  });
  const target = candidates[0];
  if (!target || typeof deriveInlineDropLayoutCore !== 'function') return null;
  const dragRect = el.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  return deriveInlineDropLayoutCore({
    left: dragRect.left,
    right: dragRect.right,
    top: dragRect.top,
    bottom: dragRect.bottom,
  }, {
    left: targetRect.left,
    right: targetRect.right,
    top: targetRect.top,
    bottom: targetRect.bottom,
  });
}

function initTemplateControls() {
  if (_templatesInitialized) return;
  _templatesInitialized = true;

  document.getElementById('tpl-new-btn')?.addEventListener('click', startNewTemplate);
  document.getElementById('tpl-designer-back')?.addEventListener('click', () => closeTemplateDesigner(false));
  document.getElementById('tpl-designer-export')?.addEventListener('click', () => exportTemplate(_editingTemplate));
  document.getElementById('tpl-designer-save')?.addEventListener('click', () => saveEditingTemplate(false));
  document.getElementById('tpl-designer-save-as')?.addEventListener('click', () => saveEditingTemplate(true));
  document.getElementById('tpl-apply-cancel')?.addEventListener('click', hideApplyTemplateDialog);
  document.getElementById('tpl-apply-confirm')?.addEventListener('click', applyPendingTemplate);
  document.getElementById('tpl-import-btn')?.addEventListener('click', () => {
    document.getElementById('tpl-import-input')?.click();
  });
  document.getElementById('tpl-import-input')?.addEventListener('change', e => {
    importTemplateFile(e.target.files?.[0]);
  });
  document.getElementById('tpl-font-upload-btn')?.addEventListener('click', () => {
    document.getElementById('tpl-font-upload-input')?.click();
  });
  document.getElementById('tpl-font-upload-input')?.addEventListener('change', e => {
    uploadFontFile(e.target.files?.[0]).finally(() => { e.target.value = ''; });
  });
  document.getElementById('tpl-designer-name')?.addEventListener('input', e => {
    if (!_editingTemplate) return;
    _editingTemplate.name = e.target.value;
    markDesignerDirty();
  });
  loadDesignerFonts();
  initDesignerCanvasEvents();
}
