import { describe, expect, it } from 'vitest';
import {
  mapPcoItemType,
  deriveNextWeekOfferingCause,
  applyNextWeekOfferingLine,
} from '../src/js/modules/pco-core.js';

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

// ─── Next week's offering addendum (issue next-week-offering) ────────────────

describe('deriveNextWeekOfferingCause', () => {
  it('issue-next-week-offering-c1: derives first non-empty line', () => {
    // leading blank lines are skipped; the first content line is the cause
    expect(deriveNextWeekOfferingCause('\n\n  Faith Promise  \nSome details below'))
      .toBe('Faith Promise');
    expect(deriveNextWeekOfferingCause('Benevolence Fund'))
      .toBe('Benevolence Fund');
  });

  it('issue-next-week-offering-c2: strips bold markers', () => {
    expect(deriveNextWeekOfferingCause('**Faith Promise**')).toBe('Faith Promise');
    expect(deriveNextWeekOfferingCause('  **World Renew**  \nextra')).toBe('World Renew');
    // a single trailing/leading asterisk pair should also be cleaned
    expect(deriveNextWeekOfferingCause('*Deacon Fund*')).toBe('Deacon Fund');
  });

  it('issue-next-week-offering-c3: blank note yields empty cause', () => {
    expect(deriveNextWeekOfferingCause('')).toBe('');
    expect(deriveNextWeekOfferingCause('   \n  \n ')).toBe('');
    expect(deriveNextWeekOfferingCause(null)).toBe('');
    expect(deriveNextWeekOfferingCause(undefined)).toBe('');
  });
});

describe('applyNextWeekOfferingLine', () => {
  const LINE = (cause) => `Next week's offering is for **${cause}**`;

  it('issue-next-week-offering-c4: appends line when absent', () => {
    const result = applyNextWeekOfferingLine('This week we collect for the General Fund.', 'Faith Promise');
    expect(result).toBe(`This week we collect for the General Fund.\n${LINE('Faith Promise')}`);
    // appending to empty detail yields just the line (no leading newline)
    expect(applyNextWeekOfferingLine('', 'Faith Promise')).toBe(LINE('Faith Promise'));
  });

  it('issue-next-week-offering-c5: idempotent replace, never duplicates', () => {
    const once = applyNextWeekOfferingLine('Body text.', 'Faith Promise');
    // re-running with the same cause is a no-op
    expect(applyNextWeekOfferingLine(once, 'Faith Promise')).toBe(once);
    // re-running with a new cause replaces in place — exactly one managed line
    const replaced = applyNextWeekOfferingLine(once, 'World Renew');
    expect(replaced).toBe(`Body text.\n${LINE('World Renew')}`);
    const occurrences = (replaced.match(/Next week's offering is for/g) || []).length;
    expect(occurrences).toBe(1);
  });

  it('issue-next-week-offering-c6: preserves existing body', () => {
    const body = 'Line one of offering text.\nLine two with details.';
    const result = applyNextWeekOfferingLine(body, 'Benevolence');
    expect(result.startsWith(body)).toBe(true);
    expect(result).toContain(LINE('Benevolence'));
    // replacing the managed line keeps the full original body intact
    const replaced = applyNextWeekOfferingLine(result, 'Deacon Fund');
    expect(replaced.startsWith(body)).toBe(true);
    expect(replaced).not.toContain('Benevolence');
  });

  it("issue-next-week-offering-c7: empty cause is a no-op / clears stale line", () => {
    // empty cause against plain detail: unchanged, no dangling line
    expect(applyNextWeekOfferingLine('Just the body.', '')).toBe('Just the body.');
    expect(applyNextWeekOfferingLine('Just the body.', null)).toBe('Just the body.');
    // empty cause against detail that already has a managed line: line removed
    const withLine = applyNextWeekOfferingLine('Body.', 'Faith Promise');
    expect(applyNextWeekOfferingLine(withLine, '')).toBe('Body.');
    expect(applyNextWeekOfferingLine(withLine, '')).not.toContain('Next week');
  });
});
