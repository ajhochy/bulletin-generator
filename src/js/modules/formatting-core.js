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

export function getEffectiveFmt(typeFormats, item) {
  const safeItem = item || {};
  const base = (typeFormats && typeFormats[safeItem.type]) || {};
  const over = safeItem._fmt || {};
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
