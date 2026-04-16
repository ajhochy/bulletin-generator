import { describe, expect, it } from 'vitest';
import {
  deriveChunkPlan,
  deriveInlineDropLayout,
  deriveInlineRowKeys,
  derivePreviewZoneOrder,
} from '../src/js/modules/preview-core.js';

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

  it('derives preview zone order from enabled template zones', () => {
    const template = {
      zones: [
        { binding: 'staff', order: 1, enabled: true },
        { binding: 'cover', order: 2, enabled: false },
        { binding: 'pco_items', order: 3, enabled: true },
        { binding: 'calendar', order: 4, enabled: true },
        { binding: 'pco_items', order: 8, enabled: true },
      ],
    };

    expect(derivePreviewZoneOrder(template)).toEqual(['staff', 'pco_items', 'calendar']);
  });

  it('falls back to Classic zone order without active zones', () => {
    expect(derivePreviewZoneOrder(null)).toEqual([
      'cover',
      'announcements',
      'pco_items',
      'calendar',
      'serving_schedule',
      'staff',
    ]);
  });

  it('derives stable inline row key order from template element layouts', () => {
    expect(deriveInlineRowKeys({
      songTitle: {},
      copyright: { layout: { position: 'inline', row: 'title-row', align: 'right' } },
      stanzaText: { layout: { position: 'free', x: 12, y: 3 } },
    }, 'title-row', 'songTitle')).toEqual(['songTitle', 'copyright']);
  });

  it('derives inline title-row layout when a dragged element aligns beside a target', () => {
    expect(deriveInlineDropLayout(
      { left: 120, right: 170, top: 10, bottom: 30 },
      { left: 10, right: 100, top: 12, bottom: 32 },
    )).toMatchObject({
      position: 'inline',
      row: 'title-row',
      align: 'right',
    });
  });

  it('does not derive inline layout when dragged element is vertically distant', () => {
    expect(deriveInlineDropLayout(
      { left: 120, right: 170, top: 80, bottom: 100 },
      { left: 10, right: 100, top: 12, bottom: 32 },
    )).toBeNull();
  });
});
