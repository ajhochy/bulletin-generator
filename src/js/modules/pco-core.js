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

// ─── Next week's offering addendum ──────────────────────────────────────────
// Prefix used for the auto-managed trailing line on the OFFERING item.detail.
// Kept as a constant so derivation, append, and idempotent-replace all agree.
export const NEXT_WEEK_OFFERING_PREFIX = "Next week's offering is for";

// Derive the offering <cause> from the NEXT week's OFFERING note body.
// Rule (per church convention): the first non-empty line of the note, trimmed,
// with any surrounding markdown emphasis markers (* / ** / ***) stripped.
// Returns '' for blank / non-string input so callers can skip cleanly.
export function deriveNextWeekOfferingCause(noteBody) {
  if (typeof noteBody !== 'string') return '';
  for (const raw of noteBody.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    return line.replace(/^\*{1,3}/, '').replace(/\*{1,3}$/, '').trim();
  }
  return '';
}

// Append (or idempotently replace) the managed "Next week's offering is for
// **<cause>**" line at the end of an OFFERING item's detail.
// - Existing managed lines (matched by NEXT_WEEK_OFFERING_PREFIX) are always
//   stripped first, so re-running never duplicates and a new cause replaces the
//   old one in place.
// - The body above the managed line is preserved verbatim (manual edits safe).
// - An empty / falsy cause removes any managed line and adds nothing (no-op for
//   plain detail), so disabling the feature or a missing next-note self-heals.
export function applyNextWeekOfferingLine(detail, cause) {
  const base = String(detail == null ? '' : detail);
  const cleaned = base
    .split('\n')
    .filter(line => !line.trimStart().startsWith(NEXT_WEEK_OFFERING_PREFIX))
    .join('\n')
    .replace(/\s+$/, '');
  const c = String(cause == null ? '' : cause).trim();
  if (!c) return cleaned;
  const line = `${NEXT_WEEK_OFFERING_PREFIX} **${c}**`;
  return cleaned ? `${cleaned}\n${line}` : line;
}

// Wrap the first non-empty line of a detail block in markdown bold (`**…**`),
// so this week's offering charity/cause renders bold like the next-week line.
// Idempotent (a line already wrapped in `**…**` is left untouched) and a no-op
// for blank / non-string input. The rest of the body is preserved verbatim.
export function boldFirstLine(text) {
  const base = String(text == null ? '' : text);
  const lines = base.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (!trimmed) continue;
    if (/^\*\*[\s\S]*\*\*$/.test(trimmed)) return base; // already bold — idempotent
    const inner = trimmed.replace(/^\*{1,3}/, '').replace(/\*{1,3}$/, '').trim();
    if (!inner) return base;
    const leading = lines[i].match(/^\s*/)[0];
    lines[i] = `${leading}**${inner}**`;
    return lines.join('\n');
  }
  return base;
}
