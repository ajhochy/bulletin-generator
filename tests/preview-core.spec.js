import { describe, expect, it } from 'vitest';
import { deriveChunkPlan } from '../src/js/modules/preview-core.js';

describe('preview chunk planner', () => {
  it('marks section headings as sticky', () => {
    expect(deriveChunkPlan({ type: 'section', title: 'Gathering' }, 2)).toEqual([
      expect.objectContaining({
        renderKind: 'full-item',
        stickyToNext: true,
        itemIdx: 2,
      }),
    ]);
  });

  it('creates stanza plans and separator sentinels for multi-stanza songs', () => {
    const plan = deriveChunkPlan({
      type: 'song',
      title: 'Song',
      detail: 'Verse 1\nA\n---\nVerse 2\nB\n\nCCLI #123',
    }, 4);

    expect(plan.map(part => part.renderKind)).toEqual(['song-stanza', 'sentinel', 'song-stanza']);
    expect(plan[1]).toMatchObject({
      forceBreak: true,
      separatorItemIdx: 4,
      separatorStanzaIdx: 1,
    });
    expect(plan[2]).toMatchObject({
      isLastStanza: true,
      copyright: 'CCLI #123',
    });
  });

  it('creates paragraph plans and forced break sentinels for liturgy', () => {
    const plan = deriveChunkPlan({
      type: 'liturgy',
      title: 'Prayer',
      detail: 'Para 1\n\nPara 2\n\nPara 3',
      _forceBreakBeforeParagraph: [2],
      _noBreakBeforeParagraph: [1],
    }, 7);

    expect(plan.map(part => part.renderKind)).toEqual(['paragraph', 'paragraph', 'sentinel', 'paragraph']);
    expect(plan[1]).toMatchObject({ paragraphIdx: 1, noBreakBefore: true });
    expect(plan[2]).toMatchObject({ forceBreak: true, paragraphBreakIdx: 2, paragraphBreakItemIdx: 7 });
  });
});
