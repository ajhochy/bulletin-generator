export const LYRIC_SECTION_RE = /^(verse|chorus|pre-?chorus|bridge|tag|ending|intro|outro|interlude|refrain|coda|vamp|hook|stanza)\s*\d*[:.)]?\s*$/i;
export const VERSE_NUM_RE = /^([1-9])\s+(.+)$/;

export function splitLyricsCopyright(detail) {
  const paras = String(detail || '').split(/\n\n/);
  const last = paras[paras.length - 1] || '';
  const attributionRe = /ccli|©|\bpublic domain\b|license\s*#|trinity hymnal|psalter hymnal|lift up your hearts|luyh|hymn\s*#|th\s*#|luyh\s*#/i;
  if (paras.length > 1 && attributionRe.test(last)) {
    return { body: paras.slice(0, -1).join('\n\n'), copyright: last };
  }
  return { body: String(detail || ''), copyright: '' };
}

export function splitLyricSectionIntoStanzas(text) {
  const lines = String(text || '').split('\n');
  const stanzas = [];
  let current = [];
  const flush = () => {
    const s = current.join('\n').trim();
    if (s) stanzas.push(s);
    current = [];
  };
  for (const line of lines) {
    const t = line.trim();
    const isLabel = t && (VERSE_NUM_RE.test(t) || LYRIC_SECTION_RE.test(t));
    if (isLabel && current.some(l => l.trim())) flush();
    current.push(line);
  }
  flush();
  if (stanzas.length <= 1) {
    const fallback = String(text || '').split(/\n\n+/).map(s => s.trim()).filter(Boolean);
    if (fallback.length > 1) return fallback;
  }
  return stanzas;
}

export function parseSongStanzas(lyricBody) {
  const sections = String(lyricBody || '').split(/\n---\n/);
  const stanzas = [];
  const separatorsBefore = new Set();
  sections.forEach((section, si) => {
    if (si > 0) separatorsBefore.add(stanzas.length);
    splitLyricSectionIntoStanzas(section).forEach(s => stanzas.push(s));
  });
  return { stanzas, separatorsBefore };
}

export function buildSongDetail(stanzas, separatorsBefore, copyright) {
  let result = '';
  for (let i = 0; i < stanzas.length; i++) {
    if (i > 0) result += separatorsBefore.has(i) ? '\n---\n' : '\n\n';
    result += stanzas[i];
  }
  if (copyright) result += '\n\n' + copyright;
  return result;
}

export function insertSongSeparatorAfter(detail, afterIdx) {
  const { body: lyricBody, copyright } = splitLyricsCopyright(detail);
  const { stanzas, separatorsBefore } = parseSongStanzas(lyricBody);
  separatorsBefore.add(afterIdx + 1);
  return buildSongDetail(stanzas, separatorsBefore, copyright);
}

export function removeSongSeparatorBefore(detail, beforeIdx) {
  const { body: lyricBody, copyright } = splitLyricsCopyright(detail);
  const { stanzas, separatorsBefore } = parseSongStanzas(lyricBody);
  separatorsBefore.delete(beforeIdx);
  return buildSongDetail(stanzas, separatorsBefore, copyright);
}
