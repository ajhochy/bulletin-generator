import { splitLyricsCopyright, splitLyricSectionIntoStanzas } from './text-core.js';

export function deriveChunkPlan(item, idx) {
  const safeItem = item || {};
  if (safeItem.type === 'page-break') {
    return [{ renderKind: 'sentinel', forceBreak: true, breakItemIdx: idx, itemIdx: idx, sourceId: idx, section: 'oow' }];
  }
  if (safeItem.type === 'note' || safeItem.type === 'media') return [];
  if (safeItem.type === 'section') {
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
