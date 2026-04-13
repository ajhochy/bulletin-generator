import { describe, expect, it } from 'vitest';
import {
  splitLyricsCopyright,
  splitLyricSectionIntoStanzas,
  parseSongStanzas,
  insertSongSeparatorAfter,
  removeSongSeparatorBefore,
} from '../src/js/modules/text-core.js';

describe('text core song helpers', () => {
  it('splits copyright from the final attribution block', () => {
    expect(splitLyricsCopyright('Verse 1\n\nCCLI #123')).toEqual({
      body: 'Verse 1',
      copyright: 'CCLI #123',
    });
  });

  it('splits song sections into stanzas', () => {
    const text = 'Verse 1\nLine a\nLine b\nChorus:\nLine c';
    expect(splitLyricSectionIntoStanzas(text)).toEqual([
      'Verse 1\nLine a\nLine b',
      'Chorus:\nLine c',
    ]);
  });

  it('tracks separators between stanzas', () => {
    const parsed = parseSongStanzas('Verse 1\nOne\n---\nVerse 2\nTwo');
    expect(parsed.stanzas).toEqual(['Verse 1\nOne', 'Verse 2\nTwo']);
    expect([...parsed.separatorsBefore]).toEqual([1]);
  });

  it('adds and removes stanza separators', () => {
    const detail = 'Verse 1\nOne\n\nVerse 2\nTwo\n\nCCLI #123';
    const withSeparator = insertSongSeparatorAfter(detail, 0);
    expect(withSeparator).toContain('\n---\n');
    expect(removeSongSeparatorBefore(withSeparator, 1)).toBe(detail);
  });
});
