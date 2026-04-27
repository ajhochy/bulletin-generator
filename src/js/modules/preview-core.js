import { splitLyricsCopyright, splitLyricSectionIntoStanzas } from './text-core.js';

export const DEFAULT_PREVIEW_ZONE_ORDER = [
  'cover',
  'announcements',
  'pco_items',
  'calendar',
  'serving_schedule',
  'staff',
];

export function derivePreviewZoneOrder(template, supportedBindings = DEFAULT_PREVIEW_ZONE_ORDER) {
  const supported = new Set(supportedBindings);
  const zones = Array.isArray(template?.zones) ? template.zones : [];
  if (!zones.length) return DEFAULT_PREVIEW_ZONE_ORDER.filter(binding => supported.has(binding));

  const bindingOrder = new Map();
  zones.forEach(zone => {
    if (!zone || zone.enabled === false || !supported.has(zone.binding)) return;
    const fallbackOrder = DEFAULT_PREVIEW_ZONE_ORDER.indexOf(zone.binding);
    const numericOrder = Number(zone.order);
    const order = Number.isFinite(numericOrder)
      ? numericOrder
      : (fallbackOrder >= 0 ? fallbackOrder : Number.MAX_SAFE_INTEGER);
    const current = bindingOrder.get(zone.binding);
    if (current === undefined || order < current) bindingOrder.set(zone.binding, order);
  });

  return Array.from(bindingOrder.entries())
    .sort((a, b) => a[1] - b[1])
    .map(([binding]) => binding);
}

export function isInlineLayout(fmt, row = 'title-row') {
  const layout = fmt?.layout;
  if (!layout || layout.position !== 'inline') return false;
  return (layout.row || 'title-row') === row;
}

export function deriveInlineRowKeys(elementFormats, row = 'title-row', anchorKey = '') {
  const formats = elementFormats || {};
  const inlineKeys = Object.keys(formats).filter(key => isInlineLayout(formats[key], row));
  const keys = anchorKey ? [anchorKey].concat(inlineKeys.filter(key => key !== anchorKey)) : inlineKeys;
  return keys.sort((a, b) => {
    const aAlign = formats[a]?.layout?.align || (a === anchorKey ? 'left' : 'right');
    const bAlign = formats[b]?.layout?.align || (b === anchorKey ? 'left' : 'right');
    const rank = { left: 0, center: 1, right: 2, 'space-between': 2 };
    return (rank[aAlign] ?? 2) - (rank[bAlign] ?? 2);
  });
}

export function deriveInlineDropLayout(dragBox, targetBox, threshold = 12) {
  if (!dragBox || !targetBox) return null;
  const dragMidY = (dragBox.top + dragBox.bottom) / 2;
  const targetMidY = (targetBox.top + targetBox.bottom) / 2;
  const verticallyAligned = Math.abs(dragMidY - targetMidY) <= threshold;
  const besideTarget = dragBox.left >= targetBox.left - threshold || dragBox.right <= targetBox.right + threshold;
  if (!verticallyAligned || !besideTarget) return null;
  const dragMidX = (dragBox.left + dragBox.right) / 2;
  const targetMidX = (targetBox.left + targetBox.right) / 2;
  return {
    position: 'inline',
    row: 'title-row',
    align: dragMidX >= targetMidX ? 'right' : 'left',
    verticalAlign: 'baseline',
    gap: '0.45rem',
  };
}

export function deriveChunkPlan(item, idx) {
  const safeItem = item || {};
  if (safeItem.type === 'page-break') {
    return [{ renderKind: 'sentinel', forceBreak: true, breakItemIdx: idx, itemIdx: idx, sourceId: idx, section: 'oow' }];
  }
  if (safeItem.type === 'note' || safeItem.type === 'media') return [];
  if (safeItem.type === 'section') {
    const sectionDetail = (safeItem.detail || '').trim();
    if (sectionDetail) {
      const paragraphs = sectionDetail.split(/\n\n+/);
      if (paragraphs.length > 1) {
        const forceBreakSet = new Set(Array.isArray(safeItem._forceBreakBeforeParagraph) ? safeItem._forceBreakBeforeParagraph : []);
        const noBreakSet   = new Set(Array.isArray(safeItem._noBreakBeforeParagraph)    ? safeItem._noBreakBeforeParagraph    : []);
        const noBreakBefore = !!safeItem._noBreakBefore;
        const plan = [];
        paragraphs.forEach((paragraph, paragraphIdx) => {
          if (paragraphIdx > 0 && forceBreakSet.has(paragraphIdx)) {
            plan.push({ renderKind: 'sentinel', forceBreak: true, paragraphBreakItemIdx: idx, paragraphBreakIdx: paragraphIdx, itemIdx: idx, sourceId: idx, section: 'oow' });
          }
          plan.push({
            renderKind: 'paragraph',
            paragraph, paragraphIdx,
            itemIdx: idx, sourceId: idx, section: 'oow',
            noBreakBefore: paragraphIdx === 0 ? noBreakBefore : noBreakSet.has(paragraphIdx),
            stickyToNext: paragraphIdx === 0,
            isFirstParagraph: paragraphIdx === 0,
            title: (safeItem.title || '').trim(),
          });
        });
        return plan;
      }
    }
    return [{ renderKind: 'full-item', stickyToNext: true, noBreakBefore: !!safeItem._noBreakBefore, itemIdx: idx, sourceId: idx, section: 'oow' }];
  }

  const detail = (safeItem.detail || '').trim();
  const noBreakBefore = !!safeItem._noBreakBefore;

  if (safeItem.type === 'song' && detail) {
    const { body: lyricBody, copyright } = splitLyricsCopyright(detail);
    const sections = lyricBody ? lyricBody.split(/\n---\n/) : [''];
    let totalStanzas = 0;
    sections.forEach(section => { totalStanzas += splitLyricSectionIntoStanzas(section).length; });

    if (totalStanzas <= 1) {
      return [{ renderKind: 'full-item', noBreakBefore, itemIdx: idx, sourceId: idx, section: 'oow' }];
    }

    const noBreakStanzas = new Set(Array.isArray(safeItem._noBreakBeforeStanzas) ? safeItem._noBreakBeforeStanzas : []);
    const plan = [];
    let globalStanzaIdx = 0;

    sections.forEach((section, sectionIdx) => {
      if (sectionIdx > 0) {
        plan.push({
          renderKind: 'sentinel',
          forceBreak: true,
          separatorItemIdx: idx,
          separatorStanzaIdx: globalStanzaIdx,
          itemIdx: idx,
          sourceId: idx,
          section: 'oow',
        });
      }
      const stanzas = splitLyricSectionIntoStanzas(section);
      stanzas.forEach((stanza, localIdx) => {
        const stanzaIdx = globalStanzaIdx;
        plan.push({
          renderKind: 'song-stanza',
          stanza,
          stanzaIdx,
          itemIdx: idx,
          sourceId: idx,
          section: 'oow',
          noBreakBefore: localIdx === 0 && sectionIdx === 0 ? noBreakBefore : noBreakStanzas.has(stanzaIdx),
          isFirstStanza: sectionIdx === 0 && localIdx === 0,
          isLastStanza: stanzaIdx === totalStanzas - 1,
          title: (safeItem.title || '').trim(),
          copyright: stanzaIdx === totalStanzas - 1 ? copyright : '',
        });
        globalStanzaIdx++;
      });
    });

    return plan;
  }

  if ((safeItem.type === 'liturgy' || safeItem.type === 'label') && detail) {
    const paragraphs = detail.split(/\n\n+/);
    if (paragraphs.length > 1) {
      const forceBreakSet = new Set(Array.isArray(safeItem._forceBreakBeforeParagraph) ? safeItem._forceBreakBeforeParagraph : []);
      const noBreakSet = new Set(Array.isArray(safeItem._noBreakBeforeParagraph) ? safeItem._noBreakBeforeParagraph : []);
      const plan = [];
      paragraphs.forEach((paragraph, paragraphIdx) => {
        if (paragraphIdx > 0 && forceBreakSet.has(paragraphIdx)) {
          plan.push({
            renderKind: 'sentinel',
            forceBreak: true,
            paragraphBreakItemIdx: idx,
            paragraphBreakIdx: paragraphIdx,
            itemIdx: idx,
            sourceId: idx,
            section: 'oow',
          });
        }
        plan.push({
          renderKind: 'paragraph',
          paragraph,
          paragraphIdx,
          itemIdx: idx,
          sourceId: idx,
          section: 'oow',
          noBreakBefore: paragraphIdx === 0 ? noBreakBefore : noBreakSet.has(paragraphIdx),
          isFirstParagraph: paragraphIdx === 0,
          title: (safeItem.title || '').trim(),
        });
      });
      return plan;
    }
  }

  return [{ renderKind: 'full-item', noBreakBefore, itemIdx: idx, sourceId: idx, section: 'oow' }];
}
