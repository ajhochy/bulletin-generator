export const CHILDREN_DISMISSED_TITLE = 'CHILDREN DISMISSED (AGES 3-K)';

export function normalizePcoTitle(title) {
  return String(title || '').trim().replace(/\s+/g, ' ').toUpperCase();
}

export function mapPcoItemType(attrs = {}) {
  if (attrs.item_type === 'header') {
    return normalizePcoTitle(attrs.title) === CHILDREN_DISMISSED_TITLE ? 'label' : 'section';
  }
  if (attrs.item_type === 'song') return 'song';
  if (attrs.item_type === 'note') return 'note';
  if (attrs.item_type === 'media') return 'media';
  return 'label';
}
