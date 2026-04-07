// ─── State ────────────────────────────────────────────────────────────────────
//
// Ownership convention:
//   OWNER  — the one module that may replace the whole array/value via setItems() etc.
//   READER — any module may read the variable directly; in-place mutations are allowed
//            for fine-grained updates (push/splice/property set) as long as a
//            schedulePreviewUpdate() / scheduleProjectPersist() call follows.
//
// items[]     OWNER: projects.js (load/reset), pco.js (import)  READERS: all
// annData[]   OWNER: projects.js (load/reset), api.js (initial load)  READERS: announcements.js, preview.js
// All other state variables follow the same pattern — see comments below.

// Setter functions for whole-array replacement — use these instead of direct assignment.
// They document the write boundary and can be extended with side-effects later.
function setItems(arr)   { items   = Array.isArray(arr) ? arr : []; }
function setAnnData(arr) { annData = Array.isArray(arr) ? arr : []; }

let items = [];
let pcoIgnore = [];              // string[] — PCO item names to skip on import/resync  OWNER: pco.js
let pcoLastImportedTitles = [];  // string[] — raw PCO item titles from last import/resync  OWNER: pco.js
let annData = []; // [{ title, body, _breakBefore?, _noBreakBefore? }]
let welcomeItems = []; // populated from WELCOME_ITEMS after staff.js loads
let welcomeHeading = ''; // custom heading; empty = auto "Welcome to {church}"
let bottomMerge = { oow: false, serving: false, calendar: false, staff: false };
let giveOnlineUrl = '';
let breakBeforeCalendar = false;
let breakBeforeStaff    = false;
let calBreakBeforeDates = []; // string[] of ISO date strings (YYYY-MM-DD) with forced page breaks
let servingSchedule = null; // { weeks: [{date, planId, teams:[{name,serviceTime,positions:[{role,names[]}]}]}, ...] }
// servingTeamFilter: global team visibility for the Settings → Serving Teams list.
//   Key: teamName (string). Value: true/false.
//   Persists in settings.json (global across all projects). Owned by pco.js / api.js.
let servingTeamFilter = {};

// volTeamFilter: per-week, per-service-time team visibility in the bulletin editor.
//   Key: 'w<weekIndex>:<serviceTime>:<teamName>'. Value: true (visible) / false (hidden).
//   Persists with the project in projects.json. Owned by calendar.js / projects.js.
let volTeamFilter = {};
let calEvents = null;  // array from /cal endpoint, null = not yet fetched, false = fetch failed
let calLastFetch = 0;  // ms timestamp of last successful fetch
let coverImageUrl = null;
let staffLogoUrl  = null;
let debounceTimer = null;
let persistTimer  = null;
let projects = [];
let activeProjectId = '';
const selectedProjectIds = new Set();
let applyingProjectState = false;
let linkedPreviewTimer = null;
let suppressLinkedFocusSync = false;

// ─── Collaboration state (server mode) ────────────────────────────────────────
let _loadedRevision = null;   // revision of the project as loaded from server
let _editorDisplayName = '';  // local editor identity
let _staleCheckTimer = null;

// Note: both server mode and desktop mode persist projects through the local
// Python server API (data/projects.json). localStorage is only used to track
// the active project ID across page reloads and to store the unsaved draft.
// PROJECTS_STORAGE_KEY was an earlier localStorage-only path that is no longer used.
const ACTIVE_PROJECT_STORAGE_KEY = 'worshipActiveProjectId';
const DRAFT_STORAGE_KEY = 'worshipProjectDraftV1';
const TYPE_FORMATS_KEY = 'worshipTypeFormatsV1';

// Per-type default formatting (keyed by item type, value is an _fmt-shaped object)
let typeFormats = {};

// ─── Document template (page size + future typography/spacing) ─────────────
const PAGE_SIZE_PRESETS = {
  '5.5x8.5':  { label: '5.5 × 8.5 in — half-letter (default)', w: 5.5,  h: 8.5  },
  '8.5x11':   { label: '8.5 × 11 in — letter',                 w: 8.5,  h: 11   },
  '8.5x14':   { label: '8.5 × 14 in — legal',                  w: 8.5,  h: 14   },
  '11x17':    { label: '11 × 17 in — tabloid / ledger',         w: 11,   h: 17   },
};

let activeDocTemplate = { pageSize: '5.5x8.5' };

function getPageDims() {
  return PAGE_SIZE_PRESETS[activeDocTemplate.pageSize] || PAGE_SIZE_PRESETS['5.5x8.5'];
}

function applyDocTemplate() {
  const { w, h } = getPageDims();
  document.documentElement.style.setProperty('--doc-page-w', w + 'in');
  document.documentElement.style.setProperty('--doc-page-h', h + 'in');
  // Inject @page size — CSS variables cannot be used inside @page size
  let pageStyle = document.getElementById('doc-page-style');
  if (!pageStyle) {
    pageStyle = document.createElement('style');
    pageStyle.id = 'doc-page-style';
    document.head.appendChild(pageStyle);
  }
  pageStyle.textContent = `@page { size: ${w}in ${h}in; margin: 0; }`;
  // Sync the page size picker if it exists
  const sel = document.getElementById('doc-page-size-sel');
  if (sel) sel.value = activeDocTemplate.pageSize;
}

function saveTypeFormats() {
  apiFetch('/api/settings', 'POST', { typeFormats }).catch(err => setStatus('Format save failed: ' + (err.message || err), 'error'));
}

// Merge per-type default with per-item override (_fmt); item-level wins.
// For boolean flags (titleBold/titleItalic) an explicit false is meaningful,
// so we check !== undefined. For string properties the empty string '' means
// "reset to default", so we use a truthy check — this ensures stale ''
// overrides in saved projects don't silently block type-level formatting.
function getEffectiveFmt(item) {
  const base = typeFormats[item.type] || {};
  const over = item._fmt || {};
  return {
    titleBold:   over.titleBold   !== undefined ? over.titleBold   : (base.titleBold   || false),
    titleItalic: over.titleItalic !== undefined ? over.titleItalic : (base.titleItalic || false),
    titleAlign:  over.titleAlign  || base.titleAlign  || '',
    titleSize:   over.titleSize   || base.titleSize   || '',
    titleColor:  over.titleColor  || base.titleColor  || '',
    bodyAlign:   over.bodyAlign   || base.bodyAlign   || '',
    bodySize:    over.bodySize    || base.bodySize    || '',
    bodyColor:   over.bodyColor   || base.bodyColor   || '',
  };
}
const CAL_CACHE_MS   = 15 * 60 * 1000;
const CAL_URLS_KEY   = 'worshipCalUrls';
const ANN_GLOBAL_KEY = 'worshipAnnouncementsGlobal';
const CAL_EXCL_KEY   = 'worshipCalExclude';
const CAL_DEFAULT_EXCL = ['Sunday Morning Worship', 'Sunday Service', 'Worship Service'];
const DRAFT_OPTION_VALUE = '__draft__';

// Calendar settings cache (populated from server at startup)
let _calUrls = null;
let _calExclude = null;

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const statusEl             = null; // replaced by toast notifications
const bulletinTitleInput   = document.getElementById('bulletin-title');
const svcTitle             = document.getElementById('svc-title');
const svcDate              = document.getElementById('svc-date');
const svcChurch            = document.getElementById('svc-church');
const giveOnlineUrlInput   = document.getElementById('give-online-url-input');
const logoImgZone          = document.getElementById('logo-img-zone');
const logoImgInput         = document.getElementById('logo-img-input');
const logoImgLabel         = document.getElementById('logo-img-label');
const logoImgPreviewWrap   = document.getElementById('logo-img-preview-wrap');
const logoImgThumb         = document.getElementById('logo-img-thumb');
const logoImgName          = document.getElementById('logo-img-name');
const logoImgClear         = document.getElementById('logo-img-clear');
const coverImgZone         = document.getElementById('cover-img-zone');
const coverImgInput        = document.getElementById('cover-img-input');
const coverImgLabel        = document.getElementById('cover-img-label');
const coverImgPreviewWrap  = document.getElementById('cover-img-preview-wrap');
const coverImgThumb        = document.getElementById('cover-img-thumb');
const coverImgName         = document.getElementById('cover-img-name');
const coverImgClear        = document.getElementById('cover-img-clear');
const optCover             = document.getElementById('opt-cover');
const optFooter            = document.getElementById('opt-footer');
const optCal               = document.getElementById('opt-cal');
const optBookletSize       = document.getElementById('opt-booklet-size');
const optAnnouncements     = document.getElementById('opt-announcements');
const optVolunteers        = document.getElementById('opt-volunteers');
const optStaff             = document.getElementById('opt-staff');
const pageCountDisplay     = document.getElementById('page-count-display');
const itemList             = document.getElementById('item-list');
const addItemBtn           = document.getElementById('add-item-btn');
const addBreakBtn          = document.getElementById('add-break-btn');
const annList              = document.getElementById('ann-list');
const annAddBtn            = document.getElementById('ann-add-btn');
const welcomeList          = document.getElementById('welcome-list');
const welcomeHeadingInput  = document.getElementById('welcome-heading-input');
const welcomeAddBtn        = document.getElementById('welcome-add-btn');
const previewPane          = document.getElementById('preview-pane');
const previewEmpty         = document.getElementById('preview-empty');
const btnPrint             = document.getElementById('btn-print');
const projectSelect        = document.getElementById('project-select');
const projectSaveBtn       = document.getElementById('project-save-btn');
const projectSaveAsBtn     = document.getElementById('project-save-as-btn');
const projectNewBtn        = document.getElementById('project-new-btn');
const projectDeleteBtn     = document.getElementById('project-delete-btn');
const projectMeta          = document.getElementById('project-meta');
const projectBrowseBtn     = document.getElementById('project-browse-btn');

// ─── Type options ─────────────────────────────────────────────────────────────
// Types starting with 'section:' render as large section headings with a rule.
const TYPE_OPTIONS = [
  ['section',    '— Section Heading —'],
  ['song',       'Song / Hymn / Psalm'],
  ['liturgy',    'Liturgy (spoken/read)'],
  ['label',      'Label (title only)'],
  ['note',       '— PCO Note (hidden) —'],
  ['media',      '— PCO Media (hidden) —'],
];

// Migrate a legacy item type string to the new 6-type system.
// Safe to call on already-migrated types — they pass through unchanged.
function migrateItemType(type) {
  switch (type) {
    // Already valid new types — pass through
    case 'section':
    case 'song':
    case 'liturgy':
    case 'label':
    case 'note':
    case 'media':
    case 'page-break':
      return type;
    // Old song variants → song
    case 'hymn':
    case 'psalm':
      return 'song';
    // Old liturgical types with body text → liturgy
    case 'creed':
    case 'prayer':
    case 'confession':
    case 'assurance':
    case 'law':
    case 'scripture':
    case 'responsive-reading':
    case 'call-to-worship':
    case 'doxology':
    case 'benediction':
      return 'liturgy';
    // Old title-only / structural types → label
    case 'sermon':
    case 'offering':
    case 'prelude':
    case 'postlude':
    case 'announcements':
    case 'other':
    default:
      return 'label';
  }
}

function typeLabel(type) {
  return (TYPE_OPTIONS.find(([k]) => k === type) || ['', type.replace(/-/g, ' ')])[1];
}
function typeSelectHTML(selected) {
  return TYPE_OPTIONS.map(([val, label]) =>
    `<option value="${val}"${val === selected ? ' selected' : ''}>${label}</option>`
  ).join('');
}

