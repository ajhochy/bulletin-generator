// ─── Template Registry ────────────────────────────────────────────────────────
//
// ELEMENT_REGISTRY defines the named sub-elements each content zone exposes for
// independent formatting in the template designer.
//
// Key format:  'binding'  or  'binding/type'
// Value:       array of element descriptors
//
// Each element descriptor:
//   key         — camelCase identifier used in zone.elements and template designer
//   label       — human-readable name shown in the designer UI
//   supportsFmt — which fmt controls apply to this element
//
// supportsFmt values: 'bold' | 'italic' | 'size' | 'color' | 'align'
// ─────────────────────────────────────────────────────────────────────────────

const ELEMENT_REGISTRY = {
  'cover': [
    { key: 'churchName',  label: 'Church Name',  supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'serviceDate', label: 'Service Date', supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'subtitle',    label: 'Subtitle',     supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
  ],
  'announcements': [
    { key: 'title', label: 'Card Title',    supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'body',  label: 'Card Body',     supportsFmt: ['size', 'color', 'align'] },
    { key: 'url',   label: 'URL / QR Label', supportsFmt: ['size', 'color', 'align'] },
  ],
  'pco_items/section': [
    { key: 'heading', label: 'Heading', supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
  ],
  'pco_items/song': [
    { key: 'songTitle',  label: 'Song Title',  supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'stanzaText', label: 'Stanza Text', supportsFmt: ['size', 'color', 'align'] },
    { key: 'copyright',  label: 'Copyright',   supportsFmt: ['italic', 'size', 'color', 'align'] },
  ],
  'pco_items/liturgy': [
    { key: 'title',        label: 'Title',     supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'bodyParagraph', label: 'Body Text', supportsFmt: ['size', 'color', 'align'] },
  ],
  'pco_items/label': [
    { key: 'title', label: 'Title',     supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'body',  label: 'Body Text', supportsFmt: ['size', 'color', 'align'] },
  ],
  'calendar': [
    { key: 'dayHeading',       label: 'Day Heading',       supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'eventTitle',       label: 'Event Title',       supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'eventTime',        label: 'Event Time',        supportsFmt: ['italic', 'size', 'color', 'align'] },
    { key: 'eventDescription', label: 'Event Description', supportsFmt: ['size', 'color', 'align'] },
  ],
  'serving_schedule': [
    { key: 'weekHeading',   label: 'Week Heading',   supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'teamName',      label: 'Team Name',      supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'serviceTime',   label: 'Service Time',   supportsFmt: ['italic', 'size', 'color', 'align'] },
    { key: 'positionLabel', label: 'Position',       supportsFmt: ['bold', 'size', 'color', 'align'] },
    { key: 'volunteerName', label: 'Volunteer Name', supportsFmt: ['size', 'color', 'align'] },
  ],
  'staff': [
    { key: 'staffName',  label: 'Name',  supportsFmt: ['bold', 'italic', 'size', 'color', 'align'] },
    { key: 'staffRole',  label: 'Role',  supportsFmt: ['italic', 'size', 'color', 'align'] },
    { key: 'staffEmail', label: 'Email', supportsFmt: ['size', 'color', 'align'] },
  ],
};

// Returns the element descriptor array for a given binding + optional item type.
// Falls back to binding-only if no binding/type key exists.
function getRegistryElements(binding, itemType) {
  if (itemType && ELEMENT_REGISTRY[`${binding}/${itemType}`]) {
    return ELEMENT_REGISTRY[`${binding}/${itemType}`];
  }
  return ELEMENT_REGISTRY[binding] || [];
}

// ─── Zone matching ────────────────────────────────────────────────────────────
//
// Given a template and an item context (binding, itemType, itemTitle), finds the
// most-specific enabled zone whose match criteria apply.
//
// Specificity scoring (higher = wins):
//   3 — binding + match.type + match.title  (exact title match)
//   2 — binding + match.type + match.titleContains  (pattern match)
//   1 — binding + match.type
//   0 — binding only (no type constraint)
//
// Returns the winning zone object, or null if no zones match.
function bestMatchingZone(template, binding, itemType, itemTitle) {
  if (!template || !Array.isArray(template.zones)) return null;
  let best = null;
  let bestScore = -1;

  for (const zone of template.zones) {
    if (!zone.enabled) continue;
    if (zone.binding !== binding) continue;

    const m = zone.match || {};
    let score = 0;

    if (m.type) {
      if (m.type !== itemType) continue;  // type specified but doesn't match this item
      score = 1;

      if (m.title) {
        if (m.title !== itemTitle) continue;
        score = 3;
      } else if (m.titleContains) {
        if (!itemTitle || !itemTitle.toLowerCase().includes(m.titleContains.toLowerCase())) continue;
        score = 2;
      }
    }
    // If no m.type, score stays 0 — matches any item in this binding

    if (score > bestScore) {
      best = zone;
      bestScore = score;
    }
  }
  return best;
}

// Returns the element-level fmt object for a specific element key, resolved
// through the zone specificity cascade.
//
// Element fmt shape: { bold?, italic?, size?, color?, align?, layout? }
//   bold   — true/false
//   italic — true/false
//   size   — 'sm' | '' | 'lg' | 'xl'
//   color  — hex string e.g. '#333'
//   align  — 'left' | 'center' | 'right'
//   layout — { row?, align?, position? }  (set by drag-and-drop in designer)
//
// Returns {} if no template or no matching zone/element (caller uses CSS default).
function getTemplateElementFmt(template, binding, itemType, itemTitle, elementKey) {
  const zone = bestMatchingZone(template, binding, itemType, itemTitle);
  if (!zone || !zone.elements) return {};
  return zone.elements[elementKey] || {};
}

// Applies an element fmt object to a DOM element via inline styles.
// Only sets styles for properties that are explicitly specified in fmt.
function applyElementFmt(el, fmt) {
  if (!fmt || !el) return;
  if (fmt.bold    !== undefined) el.style.fontWeight  = fmt.bold    ? 'bold' : 'normal';
  if (fmt.italic  !== undefined) el.style.fontStyle   = fmt.italic  ? 'italic' : 'normal';
  if (fmt.underline !== undefined) el.style.textDecoration = fmt.underline ? 'underline' : '';
  if (fmt.fontFamily)             el.style.fontFamily    = fmt.fontFamily;
  if (fmt.color)                 el.style.color        = fmt.color;
  if (fmt.align)                 el.style.textAlign    = fmt.align;
  if (fmt.size) {
    const sizeMap = { sm: '0.78em', lg: '1.1em', xl: '1.25em' };
    if (sizeMap[fmt.size]) el.style.fontSize = sizeMap[fmt.size];
    else if (/^\d+(\.\d+)?(pt|px|em|rem)$/.test(fmt.size)) el.style.fontSize = fmt.size;
  }
  if (fmt.layout && fmt.layout.position === 'free') {
    el.style.position = 'relative';
    el.style.left = (fmt.layout.x || 0) + 'px';
    el.style.top = (fmt.layout.y || 0) + 'px';
  }
}

// Returns the layout order of unique content sections from a template,
// sorted by the minimum zone.order among enabled zones for each binding.
// Used by renderPreview() to iterate sections in the right order.
//
// Returns array of binding strings in order, e.g.:
//   ['cover', 'announcements', 'pco_items', 'calendar', 'serving_schedule', 'staff']
function getTemplateSectionOrder(template) {
  const DEFAULT_ORDER = [
    'cover', 'announcements', 'pco_items', 'calendar', 'serving_schedule', 'staff',
  ];
  if (!template || !Array.isArray(template.zones)) return DEFAULT_ORDER;

  const bindingOrder = new Map();  // binding → min order value
  for (const zone of template.zones) {
    if (!zone.enabled) continue;
    const current = bindingOrder.get(zone.binding);
    if (current === undefined || zone.order < current) {
      bindingOrder.set(zone.binding, zone.order);
    }
  }

  // Sort bindings by their minimum order; any binding not in the template keeps default position
  const sorted = Array.from(bindingOrder.entries())
    .sort((a, b) => a[1] - b[1])
    .map(([binding]) => binding);

  // Add any default bindings not present in template (disabled = skip)
  for (const b of DEFAULT_ORDER) {
    if (!bindingOrder.has(b)) sorted.push(b);
  }
  return sorted;
}

// Returns true if a given binding is enabled in the template.
function isBindingEnabled(template, binding) {
  if (!template || !Array.isArray(template.zones)) return true; // default on
  // A binding is enabled if at least one of its zones is enabled
  return template.zones.some(z => z.binding === binding && z.enabled);
}
