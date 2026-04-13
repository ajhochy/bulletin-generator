import { describe, expect, it } from 'vitest';
import { getEffectiveFmt, migrateItemType } from '../src/js/modules/formatting-core.js';

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

  it('migrates legacy item types', () => {
    expect(migrateItemType('hymn')).toBe('song');
    expect(migrateItemType('creed')).toBe('liturgy');
    expect(migrateItemType('sermon')).toBe('label');
    expect(migrateItemType('page-break')).toBe('page-break');
  });
});
