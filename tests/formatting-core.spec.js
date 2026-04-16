import { describe, expect, it } from 'vitest';
import { bestMatchingZone, getEffectiveFmt, migrateItemType } from '../src/js/modules/formatting-core.js';

describe('formatting core', () => {
  it('merges type defaults with item overrides', () => {
    const typeFormats = {
      song: {
        titleBold: true,
        titleAlign: 'center',
        bodySize: 'lg',
      },
    };
    const item = {
      type: 'song',
      _fmt: {
        titleBold: false,
        bodyColor: '#333',
      },
    };

    expect(getEffectiveFmt(typeFormats, item)).toEqual({
      titleBold: false,
      titleItalic: false,
      titleAlign: 'center',
      titleSize: '',
      titleColor: '',
      bodyAlign: '',
      bodySize: 'lg',
      bodyColor: '#333',
    });
  });

  it('merges template element formatting between type defaults and item overrides', () => {
    const typeFormats = {
      song: {
        titleBold: false,
        titleAlign: 'left',
        bodySize: 'sm',
      },
    };
    const template = {
      zones: [
        {
          binding: 'pco_items',
          enabled: true,
          match: { type: 'song' },
          elements: {
            songTitle: { bold: true, align: 'center', color: '#123456' },
            stanzaText: { size: 'lg', color: '#222222' },
          },
        },
      ],
    };
    const item = {
      type: 'song',
      title: 'Be Thou My Vision',
      _fmt: { titleAlign: 'right' },
    };

    expect(getEffectiveFmt(typeFormats, item, template, 'songTitle')).toEqual({
      titleBold: true,
      titleItalic: false,
      titleAlign: 'right',
      titleSize: '',
      titleColor: '#123456',
      bodyAlign: '',
      bodySize: 'sm',
      bodyColor: '',
    });

    expect(getEffectiveFmt(typeFormats, item, template, 'stanzaText')).toMatchObject({
      bodySize: 'lg',
      bodyColor: '#222222',
    });
  });

  it('selects the most specific matching template zone', () => {
    const template = {
      zones: [
        { id: 'base', binding: 'pco_items', enabled: true, match: {}, elements: {} },
        { id: 'type', binding: 'pco_items', enabled: true, match: { type: 'song' }, elements: {} },
        { id: 'contains', binding: 'pco_items', enabled: true, match: { type: 'song', titleContains: 'Vision' }, elements: {} },
        { id: 'exact', binding: 'pco_items', enabled: true, match: { type: 'song', title: 'Be Thou My Vision' }, elements: {} },
      ],
    };

    expect(bestMatchingZone(template, { type: 'song', title: 'Be Thou My Vision' })?.id).toBe('exact');
    expect(bestMatchingZone(template, { type: 'song', title: 'Another Vision' })?.id).toBe('contains');
    expect(bestMatchingZone(template, { type: 'song', title: 'Other' })?.id).toBe('type');
    expect(bestMatchingZone(template, { type: 'label', title: 'Other' })?.id).toBe('base');
  });

  it('falls back cleanly without a template or matching element', () => {
    const item = { type: 'label', title: 'Sermon' };

    expect(getEffectiveFmt({ label: { titleSize: 'lg' } }, item, null, 'title')).toMatchObject({
      titleSize: 'lg',
    });
    expect(bestMatchingZone(null, item)).toBeNull();
  });

  it('migrates legacy item types', () => {
    expect(migrateItemType('hymn')).toBe('song');
    expect(migrateItemType('creed')).toBe('liturgy');
    expect(migrateItemType('sermon')).toBe('label');
    expect(migrateItemType('page-break')).toBe('page-break');
  });
});
