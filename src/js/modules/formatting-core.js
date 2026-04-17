export function migrateItemType(type) {
  switch (type) {
    case 'section':
    case 'song':
    case 'liturgy':
    case 'label':
    case 'note':
    case 'media':
    case 'page-break':
      return type;
    case 'hymn':
    case 'psalm':
      return 'song';
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

function itemTitle(item) {
  return (item && (item.title || item.name || item.text || '')) || '';
}

function itemBinding(item, binding) {
  return binding || item?._templateBinding || 'pco_items';
}

export function bestMatchingZone(template, item, binding) {
  if (!template || !Array.isArray(template.zones)) return null;
  const safeItem = item || {};
  const targetBinding = itemBinding(safeItem, binding);
  const targetType = safeItem.type || '';
  const targetTitle = itemTitle(safeItem);
  let best = null;
  let bestScore = -1;

  for (const zone of template.zones) {
    if (!zone || zone.enabled === false || zone.binding !== targetBinding) continue;
    const match = zone.match || {};
    let score = 0;

    if (match.type) {
      if (match.type !== targetType) continue;
      score = 1;

      if (match.title) {
        if (match.title !== targetTitle) continue;
        score = 3;
      } else if (match.titleContains) {
        if (!targetTitle.toLowerCase().includes(String(match.titleContains).toLowerCase())) continue;
        score = 2;
      }
    }

    if (score > bestScore) {
      best = zone;
      bestScore = score;
    }
  }

  return best;
}

function elementFmtToLegacyFmt(elementKey, elementFmt) {
  if (!elementFmt || typeof elementFmt !== 'object') return {};
  const titleElements = new Set([
    'heading', 'title', 'songTitle', 'churchName', 'serviceDate', 'subtitle',
    'dayHeading', 'eventTitle', 'weekHeading', 'teamName', 'serviceTime',
    'positionLabel', 'volunteerName', 'staffName', 'staffRole', 'staffEmail',
  ]);
  const prefix = titleElements.has(elementKey) ? 'title' : 'body';
  const out = {};

  if (prefix === 'title') {
    if (elementFmt.bold !== undefined) out.titleBold = !!elementFmt.bold;
    if (elementFmt.italic !== undefined) out.titleItalic = !!elementFmt.italic;
  }
  if (elementFmt.align) out[`${prefix}Align`] = elementFmt.align;
  if (elementFmt.size) out[`${prefix}Size`] = elementFmt.size;
  if (elementFmt.color) out[`${prefix}Color`] = elementFmt.color;
  if (elementFmt.fontFamily) out[`${prefix}Font`] = elementFmt.fontFamily;
  return out;
}

export function getEffectiveFmt(typeFormats, item, template = null, elementKey = '', binding = '') {
  const safeItem = item || {};
  const base = (typeFormats && typeFormats[safeItem.type]) || {};
  const zone = elementKey ? bestMatchingZone(template, safeItem, binding) : null;
  const elementFmt = zone?.elements ? elementFmtToLegacyFmt(elementKey, zone.elements[elementKey]) : {};
  const over = safeItem._fmt || {};
  const layer = Object.assign({}, base, elementFmt);
  return {
    titleBold:   over.titleBold   !== undefined ? over.titleBold   : (layer.titleBold   || false),
    titleItalic: over.titleItalic !== undefined ? over.titleItalic : (layer.titleItalic || false),
    titleAlign:  over.titleAlign  || layer.titleAlign  || '',
    titleSize:   over.titleSize   || layer.titleSize   || '',
    titleColor:  over.titleColor  || layer.titleColor  || '',
    titleFont:   over.titleFont   || layer.titleFont   || '',
    bodyAlign:   over.bodyAlign   || layer.bodyAlign   || '',
    bodySize:    over.bodySize    || layer.bodySize    || '',
    bodyColor:   over.bodyColor   || layer.bodyColor   || '',
    bodyFont:    over.bodyFont    || layer.bodyFont    || '',
  };
}
