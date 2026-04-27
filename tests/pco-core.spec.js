import { describe, expect, it } from 'vitest';
import { mapPcoItemType } from '../src/js/modules/pco-core.js';

describe('PCO item mapping', () => {
  it('maps the children dismissed header to a label', () => {
    expect(mapPcoItemType({
      item_type: 'header',
      title: 'CHILDREN DISMISSED (AGES 3-K)',
    })).toBe('label');
  });

  it('keeps other PCO headers as section headers', () => {
    expect(mapPcoItemType({
      item_type: 'header',
      title: 'WORD',
    })).toBe('section');
  });
});
