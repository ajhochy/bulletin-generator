// ─── Song stanza / separator helpers ─────────────────────────────────────────
// A `---` on its own line (surrounded by single newlines) acts as a forced page-
// break marker within song lyrics.  These helpers parse, insert, and remove them.

// Split a lyric section (between --- markers) into individual stanzas.
// Detects stanza boundaries using label lines (VERSE_NUM_RE / LYRIC_SECTION_RE),
// e.g. "1 Come...", "Refrain:", "Chorus:", "Bridge:", etc.
// Falls back to \n\n splitting for unlabelled songs.
function splitLyricSectionIntoStanzas(text) {
  const lines = text.split('\n');
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
    // Start a new stanza at each label line (if we already have accumulated content)
    if (isLabel && current.some(l => l.trim())) flush();
    current.push(line);
  }
  flush();
  // Fallback: if no label-based split found, try blank-line splitting
  if (stanzas.length <= 1) {
    const fallback = text.split(/\n\n+/).map(s => s.trim()).filter(Boolean);
    if (fallback.length > 1) return fallback;
  }
  return stanzas;
}

// Parse lyricBody into stanzas + a Set of stanza indices that have a --- before them.
// E.g. "1 A\nRefrain:\nB\n---\n2 C" → stanzas=['1 A','Refrain:\nB','2 C'], separatorsBefore={2}
function parseSongStanzas(lyricBody) {
  const sections = lyricBody.split(/\n---\n/);
  const stanzas = [];
  const separatorsBefore = new Set();
  sections.forEach((section, si) => {
    if (si > 0) separatorsBefore.add(stanzas.length);
    splitLyricSectionIntoStanzas(section).forEach(s => stanzas.push(s));
  });
  return { stanzas, separatorsBefore };
}

// Reassemble stanzas + separators + copyright back into a detail string.
function buildSongDetail(stanzas, separatorsBefore, copyright) {
  let result = '';
  for (let i = 0; i < stanzas.length; i++) {
    if (i > 0) result += separatorsBefore.has(i) ? '\n---\n' : '\n\n';
    result += stanzas[i];
  }
  if (copyright) result += '\n\n' + copyright;
  return result;
}

// Insert a --- separator after global stanza index afterIdx.
function insertSongSeparatorAfter(detail, afterIdx) {
  const { body: lyricBody, copyright } = splitLyricsCopyright(detail);
  const { stanzas, separatorsBefore } = parseSongStanzas(lyricBody);
  separatorsBefore.add(afterIdx + 1);
  return buildSongDetail(stanzas, separatorsBefore, copyright);
}

// Remove the --- separator that appears before global stanza index beforeIdx.
function removeSongSeparatorBefore(detail, beforeIdx) {
  const { body: lyricBody, copyright } = splitLyricsCopyright(detail);
  const { stanzas, separatorsBefore } = parseSongStanzas(lyricBody);
  separatorsBefore.delete(beforeIdx);
  return buildSongDetail(stanzas, separatorsBefore, copyright);
}

// ─── Body text renderer ───────────────────────────────────────────────────────
// Section labels (named) — e.g. Chorus, Bridge, Verse 2, Tag, Ending
const LYRIC_SECTION_RE = /^(verse|chorus|pre-?chorus|bridge|tag|ending|intro|outro|interlude|refrain|coda|vamp|hook|stanza)\s*\d*[:.)]?\s*$/i;
// Standalone verse number at the start of a line (lyrics), e.g. "1 Come all you weary"
const VERSE_NUM_RE = /^([1-9])\s+(.+)$/;
// Verse number for prose/scripture — 1-3 digits at start of line
const PROSE_VERSE_RE = /^(\d{1,3})\s+(.+)$/;
// Inline verse number within prose — digits preceded by start, punctuation+space, or whitespace, followed by space+letter/quote
const INLINE_VERSE_RE = /(^|[,.;:!?]\s+|\s)(\d{1,3})(?=\s+[A-Za-z"'"])/g;

// Render text with **bold** and *italic* markup support
function appendStyledText(el, text) {
  // Match ***bold-italic*** before **bold** before *italic*
  // so longer patterns are consumed first
  const re = /\*\*\*([^*\n]+)\*\*\*|\*\*([^*\n]+)\*\*|\*([^*\n]+)\*/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) el.appendChild(document.createTextNode(text.slice(last, m.index)));
    if (m[1] !== undefined) {
      // ***bold-italic***
      const b = document.createElement('strong');
      const i = document.createElement('em');
      i.textContent = m[1];
      b.appendChild(i);
      el.appendChild(b);
    } else if (m[2] !== undefined) {
      // **bold**
      const b = document.createElement('strong');
      b.textContent = m[2];
      el.appendChild(b);
    } else {
      // *italic*
      const i = document.createElement('em');
      i.textContent = m[3];
      el.appendChild(i);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) el.appendChild(document.createTextNode(text.slice(last)));
}

// Scan plain text for inline verse numbers, appending text nodes and <sup> elements.
// Receives text with no bold/italic markers — called by appendProseText only.
function _appendVerseNums(el, text) {
  INLINE_VERSE_RE.lastIndex = 0;
  let last = 0, m;
  while ((m = INLINE_VERSE_RE.exec(text)) !== null) {
    const beforeNum = m.index + m[1].length; // position of the digit(s)
    if (beforeNum > last) el.appendChild(document.createTextNode(text.slice(last, beforeNum)));
    const sup = document.createElement('sup');
    sup.className = 'verse-num';
    sup.textContent = m[2];
    el.appendChild(sup);
    last = beforeNum + m[2].length;
  }
  if (last < text.length) el.appendChild(document.createTextNode(text.slice(last)));
}

// Append prose text to el, handling both bold/italic markup and inline verse numbers.
// Processes bold/italic spans first so verse numbers inside *italic* or **bold** spans
// are still found and wrapped in <sup> (previously the * preceding a digit blocked matching).
function appendProseText(el, text) {
  const styleRe = /\*\*\*([^*\n]+)\*\*\*|\*\*([^*\n]+)\*\*|\*([^*\n]+)\*/g;
  let last = 0, m;
  styleRe.lastIndex = 0;
  while ((m = styleRe.exec(text)) !== null) {
    if (m.index > last) _appendVerseNums(el, text.slice(last, m.index));
    if (m[1] !== undefined) {
      const b = document.createElement('strong');
      const i = document.createElement('em');
      _appendVerseNums(i, m[1]);
      b.appendChild(i); el.appendChild(b);
    } else if (m[2] !== undefined) {
      const b = document.createElement('strong');
      _appendVerseNums(b, m[2]); el.appendChild(b);
    } else {
      const i = document.createElement('em');
      _appendVerseNums(i, m[3]); el.appendChild(i);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) _appendVerseNums(el, text.slice(last));
}

// prose=true: numbers treated as scripture verse numbers (superscript inline)
// prose=false (default): numbers treated as lyric section labels
function renderBodyText(el, text, prose = false) {
  // Block-level ** wrapping: "**entire\nblock**" → strip markers,
  // render all lines bold. Produced when user selects all and clicks Bold.
  const BLOCK_BOLD_RE = /^\*\*([\s\S]*)\*\*$/;
  const blockBoldMatch = BLOCK_BOLD_RE.exec(text.trim());
  // Only treat as block-bold if the inner content has no further ** pairs.
  // If it does, these are multiple inline bolds — don't collapse them into one block.
  let blockBold = false;
  if (blockBoldMatch && !blockBoldMatch[1].includes('**')) {
    text = blockBoldMatch[1];
    blockBold = true;
  }
  // Block-level * wrapping: "*entire\nblock*" → strip markers,
  // render all lines italic.
  let blockItalic = false;
  if (!blockBold) {
    const BLOCK_ITALIC_RE = /^\*([\s\S]*)\*$/;
    const blockItalicMatch = BLOCK_ITALIC_RE.exec(text.trim());
    // Only treat as block-italic if the inner content has no further * pairs.
    // If it does, these are multiple inline italics — don't collapse them into one block.
    if (blockItalicMatch && !blockItalicMatch[1].includes('*')) {
      text = blockItalicMatch[1];
      blockItalic = true;
    }
  }

  // ── Pass 1: tokenise into events ──────────────────────────────────────────
  const events = [];
  for (const line of text.split('\n')) {
    // Strip [bracket notes] (stage directions, director cues, etc.) before rendering
    const strippedLine = line.replace(/\[[^\]]*\]/g, '').replace(/[ \t]{2,}/g, ' ');
    const t = strippedLine.trim();
    if (!t) { events.push({ type: 'gap' }); continue; }

    if (prose) {
      const vm = t.match(PROSE_VERSE_RE);
      if (vm) {
        // "14 For this reason" → verse-line with superscript num
        events.push({ type: 'verse-line', num: vm[1], text: vm[2] });
        continue;
      }
    } else {
      const vm = t.match(VERSE_NUM_RE);
      if (vm) {
        // "1 Come all you weary" → label "1" + line "Come all you weary"
        events.push({ type: 'label', text: vm[1] });
        events.push({ type: 'line',  text: vm[2] });
        continue;
      }
      if (LYRIC_SECTION_RE.test(t)) {
        events.push({ type: 'label', text: t });
        continue;
      }
    }
    events.push({ type: 'line', text: strippedLine });
  }

  // If the last line event starts with a dash/en-dash/em-dash, treat it as a
  // verse reference / attribution line (rendered like song-copyright).
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].type === 'line') {
      if (/^[-–—]\s*\S/.test(events[i].text)) {
        events[i] = { type: 'attribution', text: events[i].text.replace(/^[-–—]\s*/, '').trim() };
      }
      break; // only inspect the last line event
    }
  }

  // ── Pass 2: render ────────────────────────────────────────────────────────
  // Rules:
  //   • Gap is emitted BEFORE a label (if content already exists).
  //   • Gap is emitted BEFORE a line that follows a blank-line gap in the
  //     source, but ONLY if the previous emitted node was not a label
  //     (labels are already separated from what follows by being labels).
  //   • Lines within the same section are separated by <br>.
  let hasContent   = false;
  let lastWasLabel = false;
  let needsGap     = false;
  let inAll        = false; // true after ALL: line, until Leader: line resets it

  for (let i = 0; i < events.length; i++) {
    const ev = events[i];

    if (ev.type === 'gap') {
      if (!hasContent) continue;
      // Look ahead: if the next non-gap event is a label, the label will
      // emit its own gap — don't double-gap.
      let j = i + 1;
      while (j < events.length && events[j].type === 'gap') j++;
      if (j >= events.length || events[j].type !== 'label') needsGap = true;
      continue;
    }

    if (ev.type === 'label') {
      if (hasContent) {
        const gap = document.createElement('div');
        gap.className = 'body-section-gap';
        el.appendChild(gap);
      }
      needsGap = false;
      const em = document.createElement('em');
      em.className = 'lyric-section-label';
      em.textContent = ev.text;
      el.appendChild(em);
      lastWasLabel = true;
      hasContent   = true;
      continue;
    }

    // attribution — last line starting with "-":
    // prose items get item-attribution (body size, lighter); songs get song-copyright (tiny)
    if (ev.type === 'attribution') {
      const attr = document.createElement('div');
      attr.className = prose ? 'item-attribution' : 'song-copyright';
      attr.textContent = ev.text;
      el.appendChild(attr);
      hasContent   = true;
      lastWasLabel = false;
      needsGap     = false;
      continue;
    }

    // type === 'line' or 'verse-line'
    if (!hasContent) {
      // very first content — no prefix
    } else if (lastWasLabel) {
      // label is immediately followed by its first lyric line — no gap, no br
      needsGap = false;
    } else if (needsGap) {
      const gap = document.createElement('div');
      gap.className = 'body-section-gap';
      el.appendChild(gap);
      needsGap = false;
    } else {
      el.appendChild(document.createElement('br'));
    }

    lastWasLabel = false;

    if (ev.type === 'verse-line') {
      // Superscript verse number, then rest of line (scanning for more inline verse nums)
      const sup = document.createElement('sup');
      sup.className = 'verse-num';
      sup.textContent = ev.num;
      el.appendChild(sup);
      el.appendChild(document.createTextNode('\u00A0')); // non-breaking space
      appendProseText(el, ev.text);
    } else if (blockBold || (() => {
      // State machine for ALL: / Leader: responsive reading mode
      const t = ev.text.trimStart();
      if (/^ALL:/i.test(t))    { inAll = true;  }
      if (/^Leader:/i.test(t)) { inAll = false; }
      return inAll;
    })()) {
      const b = document.createElement('strong');
      // Use appendProseText so inline verse numbers inside ALL: lines still get <sup>
      if (prose) appendProseText(b, ev.text); else b.textContent = ev.text;
      el.appendChild(b);
    } else if (blockItalic) {
      const em = document.createElement('em');
      if (prose) appendProseText(em, ev.text); else em.textContent = ev.text;
      el.appendChild(em);
    } else if (prose) {
      appendProseText(el, ev.text);
    } else {
      appendStyledText(el, ev.text);
    }
    hasContent = true;
  }
}

