// ─── ProPresenter Import ───────────────────────────────────────────────────────

// ─── ProPresenter Import Helpers ─────────────────────────────────────────────

const SONG_GROUP_RE = /^(verse|chorus|bridge|pre.?chorus|refrain|tag\b|intro|outro|hook)/i;

// ─── Minimal Protobuf Decoder (browser-compatible, no dependencies) ─────────

function _pbReadVarint(buf, offset) {
  let result = 0, shift = 0, bytesRead = 0;
  while (offset < buf.length) {
    const b = buf[offset++]; bytesRead++;
    result |= (b & 0x7f) << shift;
    if ((b & 0x80) === 0) break;
    shift += 7;
    if (shift > 35) break;
  }
  return { value: result >>> 0, bytesRead };
}

function _pbParseFields(buf, start, end) {
  if (start === undefined) start = 0;
  if (end === undefined) end = buf.length;
  const fields = [];
  let offset = start;
  while (offset < end) {
    const tag = _pbReadVarint(buf, offset);
    if (tag.bytesRead === 0) break;
    offset += tag.bytesRead;
    const fieldNumber = tag.value >>> 3;
    const wireType = tag.value & 0x7;
    if (fieldNumber === 0) break;
    if (wireType === 0) {
      const val = _pbReadVarint(buf, offset);
      offset += val.bytesRead;
      fields.push({ fieldNumber, wireType, data: val.value });
    } else if (wireType === 1) {
      fields.push({ fieldNumber, wireType, data: buf.slice(offset, offset + 8) });
      offset += 8;
    } else if (wireType === 2) {
      const len = _pbReadVarint(buf, offset);
      offset += len.bytesRead;
      const dataEnd = offset + len.value;
      if (dataEnd > end) break;
      fields.push({ fieldNumber, wireType, data: buf.slice(offset, dataEnd) });
      offset = dataEnd;
    } else if (wireType === 5) {
      fields.push({ fieldNumber, wireType, data: buf.slice(offset, offset + 4) });
      offset += 4;
    } else {
      break;
    }
  }
  return fields;
}

function _pbGetFields(fields, num) { return fields.filter(f => f.fieldNumber === num); }
function _pbGetField(fields, num) { return fields.find(f => f.fieldNumber === num) || null; }
function _pbDecodeString(data) {
  if (!data || data.length === 0) return '';
  return new TextDecoder('utf-8').decode(data);
}
function _pbExtractUUID(data) {
  if (!data || data.length === 0) return '';
  const fields = _pbParseFields(data);
  const f1 = _pbGetField(fields, 1);
  return (f1 && f1.wireType === 2) ? _pbDecodeString(f1.data) : '';
}

// ─── RTF Text Extraction ────────────────────────────────────────────────────

/**
 * Strip RTF formatting to plain text.
 * Handles control words, Unicode escapes, hex escapes, nested groups.
 */
function _stripRtf(rtf) {
  if (!rtf || rtf.length === 0) return '';
  let text = '', i = 0, depth = 0, skipDepth = 0;
  while (i < rtf.length) {
    const ch = rtf[i];
    if (ch === '{') { depth++; i++; continue; }
    if (ch === '}') { if (skipDepth > 0 && depth <= skipDepth) skipDepth = 0; depth--; i++; continue; }
    if (skipDepth > 0) { i++; continue; }
    if (ch === '\\') {
      i++;
      if (i >= rtf.length) break;
      const next = rtf[i];
      if (next === '*') { i++; skipDepth = depth; continue; }
      if (next === '\\') { text += '\\'; i++; continue; }
      if (next === '{')  { text += '{';  i++; continue; }
      if (next === '}')  { text += '}';  i++; continue; }
      if (next === '\n') { text += '\n'; i++; continue; }
      if (next === '\r') { i++; if (i < rtf.length && rtf[i] === '\n') i++; text += '\n'; continue; }
      if (next === '\'') {
        if (i + 2 < rtf.length) {
          const code = parseInt(rtf[i+1] + rtf[i+2], 16);
          if (!isNaN(code)) text += (code === 0xA0) ? ' ' : String.fromCharCode(code);
          i += 3;
        } else { i++; }
        continue;
      }
      let word = '';
      while (i < rtf.length && /[a-zA-Z]/.test(rtf[i])) { word += rtf[i]; i++; }
      let param = '';
      if (i < rtf.length && (rtf[i] === '-' || /[0-9]/.test(rtf[i]))) {
        if (rtf[i] === '-') { param += '-'; i++; }
        while (i < rtf.length && /[0-9]/.test(rtf[i])) { param += rtf[i]; i++; }
      }
      if (i < rtf.length && rtf[i] === ' ') i++;
      if (/^(fonttbl|colortbl|stylesheet|info|pict|object|themedata|colorschememapping|datastore|latentstyles|xmlnstbl|listtable|listoverridetable|generator|fldinst|mmathPr|pgdsctbl)$/.test(word)) {
        skipDepth = depth; continue;
      }
      if (word === 'par' || word === 'line') { text += '\n'; continue; }
      if (word === 'tab') { text += '\t'; continue; }
      if (word === 'u') {
        const code = parseInt(param);
        if (!isNaN(code)) text += String.fromCharCode(code < 0 ? code + 65536 : code);
        if (i < rtf.length && rtf[i] !== '\\' && rtf[i] !== '{' && rtf[i] !== '}') i++;
        continue;
      }
      continue;
    }
    if (ch === '\n' || ch === '\r') { i++; continue; }
    text += ch; i++;
  }
  return text.trim();
}

// ─── Deep RTF Block Finder ──────────────────────────────────────────────────

function _findRTFBlocks(buf) {
  const results = [];
  const RTF_MAGIC = [0x7b, 0x5c, 0x72, 0x74, 0x66]; // {\rtf
  function searchBytes(data) {
    if (!data || data.length < 10) return;
    if (data.length >= 5 && data[0] === RTF_MAGIC[0] && data[1] === RTF_MAGIC[1] &&
        data[2] === RTF_MAGIC[2] && data[3] === RTF_MAGIC[3] && data[4] === RTF_MAGIC[4]) {
      const rtfStr = _pbDecodeString(data);
      const text = _stripRtf(rtfStr);
      if (text.length > 0) results.push(text);
      return;
    }
    try {
      const fields = _pbParseFields(data);
      if (fields.length === 0) return;
      for (const f of fields) {
        if (f.wireType === 2 && f.data.length > 4) searchBytes(f.data);
      }
    } catch (e) { /* not valid protobuf */ }
  }
  searchBytes(buf);
  return results;
}

// ─── ProPresenter 7 Protobuf Parser ─────────────────────────────────────────

/**
 * Parse a .pro file (Uint8Array) using real protobuf decoding.
 * Schema: rv.data.Presentation from ProPresenter7-Proto.
 */
function _parsePresentationProto(bytes) {
  const rootFields = _pbParseFields(bytes);

  // Field 3: name
  const nameField = _pbGetField(rootFields, 3);
  const name = nameField ? _pbDecodeString(nameField.data) : '';

  // Field 10: selected_arrangement UUID
  const selArr = _pbGetField(rootFields, 10);
  const selectedArrangement = selArr ? _pbExtractUUID(selArr.data) : '';

  // Field 11: repeated Arrangement { uuid, name, group_identifiers[] }
  const arrangements = _pbGetFields(rootFields, 11).map(af => {
    const aFields = _pbParseFields(af.data);
    return {
      uuid: (_pbGetField(aFields, 1) ? _pbExtractUUID(_pbGetField(aFields, 1).data) : ''),
      name: (_pbGetField(aFields, 2) ? _pbDecodeString(_pbGetField(aFields, 2).data) : ''),
      groupIdentifiers: _pbGetFields(aFields, 3).map(g => _pbExtractUUID(g.data))
    };
  });

  // Field 12: repeated CueGroup { group { uuid, name }, cue_identifiers[] }
  const cueGroups = _pbGetFields(rootFields, 12).map(cgf => {
    const cgFields = _pbParseFields(cgf.data);
    const groupField = _pbGetField(cgFields, 1);
    let groupUUID = '', groupName = '';
    if (groupField) {
      const gFields = _pbParseFields(groupField.data);
      groupUUID = _pbGetField(gFields, 1) ? _pbExtractUUID(_pbGetField(gFields, 1).data) : '';
      groupName = _pbGetField(gFields, 2) ? _pbDecodeString(_pbGetField(gFields, 2).data) : '';
    }
    return {
      groupUUID, groupName,
      cueIdentifiers: _pbGetFields(cgFields, 2).map(c => _pbExtractUUID(c.data))
    };
  });

  // Field 13: repeated Cue { uuid, actions[] → deep search for RTF }
  const cues = _pbGetFields(rootFields, 13).map(cf => {
    const cFields = _pbParseFields(cf.data);
    const cUUID = _pbGetField(cFields, 1);
    return {
      uuid: cUUID ? _pbExtractUUID(cUUID.data) : '',
      rtfTexts: _findRTFBlocks(cf.data)
    };
  });

  // Field 14: CCLI { author, song_title, publisher, copyright_year, song_number }
  let ccli = null;
  const ccliField = _pbGetField(rootFields, 14);
  if (ccliField) {
    const ccFields = _pbParseFields(ccliField.data);
    const author = _pbGetField(ccFields, 1);
    const publisher = _pbGetField(ccFields, 4);
    const copyrightYear = _pbGetField(ccFields, 5);
    const songNumber = _pbGetField(ccFields, 6);
    ccli = {
      author: author ? _pbDecodeString(author.data) : '',
      publisher: publisher ? _pbDecodeString(publisher.data) : '',
      copyrightYear: copyrightYear ? copyrightYear.data : 0,
      songNumber: songNumber ? songNumber.data : 0
    };
  }

  return { name, selectedArrangement, arrangements, cueGroups, cues, ccli };
}

/**
 * Reconstruct lyrics in arrangement order with deduplication.
 * Falls back to file-order (cue order) if no arrangement exists.
 */
function _getArrangementOrderedLyrics(pres) {
  const { arrangements, cueGroups, cues, selectedArrangement } = pres;

  // Build lookup maps
  const cueMap = new Map();
  for (const cue of cues) { if (cue.uuid) cueMap.set(cue.uuid, cue); }
  const cueGroupMap = new Map();
  for (const cg of cueGroups) { if (cg.groupUUID) cueGroupMap.set(cg.groupUUID, cg); }

  // Find the selected arrangement or fall back to first
  let arrangement = null;
  if (selectedArrangement) arrangement = arrangements.find(a => a.uuid === selectedArrangement);
  if (!arrangement && arrangements.length > 0) arrangement = arrangements[0];

  // Collect lyrics in order with section headings
  const ordered = [];
  const seen = new Set();
  const HEADING_RE = /^(verse|chorus|bridge|pre.?chorus|refrain|tag|intro|outro|hook|ending|interlude|vamp|instrumental)/i;

  if (arrangement) {
    // Follow arrangement → groups → cues → RTF
    for (const groupId of arrangement.groupIdentifiers) {
      const cueGroup = cueGroupMap.get(groupId);
      if (!cueGroup) continue;
      const sectionTexts = [];
      for (const cueId of cueGroup.cueIdentifiers) {
        const cue = cueMap.get(cueId);
        if (!cue) continue;
        for (const text of cue.rtfTexts) {
          const key = text.trim();
          if (seen.has(key)) continue;
          seen.add(key);
          sectionTexts.push(text);
        }
      }
      if (sectionTexts.length) {
        const label = cueGroup.groupName || '';
        const showLabel = label && HEADING_RE.test(label);
        // Merge consecutive groups that share the same label (e.g. two "Verse 1" slides)
        const lastLabel = ordered.length > 0 ? ordered[ordered.length - 1].split('\n')[0] : null;
        if (label && lastLabel === label) {
          ordered[ordered.length - 1] += '\n' + sectionTexts.join('\n');
        } else {
          ordered.push((showLabel ? label + '\n' : '') + sectionTexts.join('\n'));
        }
      }
    }
  }

  // Fall back to file-order cues with group names from cueGroups
  if (ordered.length === 0) {
    // Build reverse map: cueId → groupName
    const cueToGroup = new Map();
    for (const cg of cueGroups) {
      for (const cueId of cg.cueIdentifiers) {
        if (!cueToGroup.has(cueId)) cueToGroup.set(cueId, cg.groupName || '');
      }
    }
    let lastGroup = '';
    for (const cue of cues) {
      const groupName = cueToGroup.get(cue.uuid) || '';
      for (const text of cue.rtfTexts) {
        const key = text.trim();
        if (seen.has(key)) continue;
        seen.add(key);
        const showLabel = groupName && groupName !== lastGroup && HEADING_RE.test(groupName);
        ordered.push((showLabel ? groupName + '\n' : '') + text);
        if (groupName) lastGroup = groupName;
      }
    }
  }

  return ordered;
}

/**
 * Parse a ProPresenter 7 binary protobuf .pro file.
 * Uses real protobuf decoding + arrangement ordering.
 */
function _parsePropresenterProto7(filename, rawText, bytes) {
  const title = filename.replace(/\.(pro[67]?|propresenter)$/i, '').trim();

  const pres = _parsePresentationProto(bytes);
  const lyricSections = _getArrangementOrderedLyrics(pres);

  if (!lyricSections.length) throw new Error(`${filename}: no slide content found`);

  const lyrics = lyricSections.join('\n');

  // Build metadata from CCLI protobuf field
  let author = '', copyright = '', ccliNumber = '';
  if (pres.ccli) {
    author = pres.ccli.author || '';
    ccliNumber = pres.ccli.songNumber ? String(pres.ccli.songNumber) : '';
    const parts = [];
    if (pres.ccli.copyrightYear) parts.push(`© ${pres.ccli.copyrightYear}`);
    if (pres.ccli.publisher) parts.push(pres.ccli.publisher);
    if (ccliNumber) parts.push(`CCLI Song # ${ccliNumber}`);
    copyright = parts.join(' | ');
  }

  return {
    title: title.toUpperCase(), author, lyrics,
    copyright, ccli_number: ccliNumber,
    date_added: new Date().toISOString(),
    _isSong: !!(ccliNumber || author),
  };
}

/**
 * Parse a ProPresenter 6 XML file (.pro6 or XML-based .pro).
 */
function _parsePropresenterXml(filename, xmlText) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlText, 'text/xml');
  const root = doc.documentElement;
  if (root.nodeName === 'parseerror' || root.tagName === 'html') {
    throw new Error(`${filename}: unrecognized ProPresenter XML format`);
  }

  const title = (root.getAttribute('CCLISongTitle') || root.getAttribute('title') ||
    filename.replace(/\.(pro[67]?|propresenter)$/i, '')).trim();
  const author   = (root.getAttribute('CCLIArtistCredits') || root.getAttribute('artist') || '').trim();
  const ccliSong = (root.getAttribute('CCLISongNumber') || '').trim();
  const ccliYear = (root.getAttribute('CCLICopyrightYear') || '').trim();
  const ccliPub  = (root.getAttribute('CCLIPublisher') || '').trim();
  const ccliLic  = (root.getAttribute('CCLILicenseNumber') || '').trim();
  let copyright  = (root.getAttribute('CCLICopyrightInfo') || '').trim();
  if (!copyright) {
    const parts = [];
    if (ccliSong) parts.push(`CCLI Song # ${ccliSong}`);
    if (ccliYear && author) parts.push(`© ${ccliYear} ${author}`);
    else if (ccliYear) parts.push(`© ${ccliYear}`);
    if (ccliPub) parts.push(ccliPub);
    if (ccliLic) parts.push(`CCLI License # ${ccliLic}`);
    copyright = parts.join(' ');
  }

  const groupEls = [...root.querySelectorAll('RVSlideGrouping')];
  const lyricSections = [];
  groupEls.forEach(group => {
    const sectionName = group.getAttribute('name') || '';
    const slideTexts = [];
    group.querySelectorAll('RVDisplaySlide').forEach(slide => {
      const lines = [];
      slide.querySelectorAll('NSString').forEach(ns => {
        const txt = (ns.textContent || '').replace(/\r\n|\r/g, '\n').trim();
        if (txt) lines.push(txt);
      });
      if (lines.length) slideTexts.push(lines.join('\n'));
    });
    if (slideTexts.length) {
      // Merge consecutive groups that share the same label (e.g. two "Verse 1" slides)
      const lastLabel = lyricSections.length > 0 ? lyricSections[lyricSections.length - 1].split('\n')[0] : null;
      if (sectionName && lastLabel === sectionName) {
        lyricSections[lyricSections.length - 1] += '\n' + slideTexts.join('\n');
      } else {
        lyricSections.push((sectionName ? sectionName + '\n' : '') + slideTexts.join('\n'));
      }
    }
  });

  return {
    title: title.toUpperCase(), author, lyrics: lyricSections.join('\n'),
    copyright, ccli_number: ccliSong, date_added: new Date().toISOString(),
    _isSong: !!(ccliSong || author),
  };
}

async function parsePropresenterFile(file) {
  const buf = await file.arrayBuffer();
  const bytes = new Uint8Array(buf);

  // Binary plist (ProPresenter 4/5) — starts with "bplist"
  if (bytes[0] === 0x62 && bytes[1] === 0x70) {
    throw new Error(`${file.name}: binary plist format (ProPresenter 4/5) — re-save in ProPresenter 6 or 7 to import`);
  }

  // XML format (ProPresenter 5/6) — starts with '<'
  if (bytes[0] === 0x3C || (bytes[0] === 0xEF && bytes[3] === 0x3C)) {
    const text = new TextDecoder('utf-8', { fatal: false }).decode(buf);
    const parser = new DOMParser();
    const doc = parser.parseFromString(text, 'text/xml');
    const root = doc.documentElement;
    if (root.nodeName !== 'parseerror' && root.tagName !== 'html') {
      return _parsePropresenterXml(file.name, text);
    }
  }

  // ProPresenter 7 protobuf format (default)
  return _parsePropresenterProto7(file.name, null, bytes);
}

// State for the ProPresenter import flow
let _proImportParsed = [];

// Disclaimer gate — show modal before opening the file picker
document.getElementById('pro-import-btn').addEventListener('click', () => {
  document.getElementById('pro-disclaimer-modal').style.display = '';
});
document.getElementById('pro-disclaimer-close-btn').addEventListener('click', () => {
  document.getElementById('pro-disclaimer-modal').style.display = 'none';
});
document.getElementById('pro-disclaimer-cancel-btn').addEventListener('click', () => {
  document.getElementById('pro-disclaimer-modal').style.display = 'none';
});
// Continue button opens the file picker — must be a real click handler to preserve user gesture
document.getElementById('pro-disclaimer-continue-btn').addEventListener('click', () => {
  document.getElementById('pro-disclaimer-modal').style.display = 'none';
  document.getElementById('pro-import-input').click();
});

let _proImportErrors = [];

document.getElementById('pro-import-input').addEventListener('change', async e => {
  const files = [...e.target.files];
  e.target.value = '';
  if (!files.length) return;

  const parsed = [];
  const errors = [];
  for (const file of files) {
    try {
      const song = await parsePropresenterFile(file);
      parsed.push(song);
    } catch (err) {
      errors.push({ file: file.name, msg: err.message });
    }
  }

  if (!parsed.length && errors.length) {
    alert('Could not parse any of the selected files:\n' + errors.map(e => e.msg).join('\n'));
    return;
  }

  // Classify each parsed file: new / duplicate
  const results = parsed.map(song => {
    const existing = songDb.find(s => normTitle(s.title) === normTitle(song.title));
    return { song, status: existing ? 'duplicate' : 'new' };
  });

  _proImportParsed = results;
  _proImportErrors = errors;

  // ── Show preview modal with sample songs ──
  _showProPreview(results);
});

function _showProPreview(results) {
  const body = document.getElementById('pro-preview-body');
  body.innerHTML = '';

  const songs = results.filter(r => r.song._isSong);
  if (!songs.length) {
    // No songs detected — skip preview, go straight to review
    _showProReview();
    return;
  }

  const intro = document.createElement('p');
  intro.style.cssText = 'font-size:0.82rem;margin-bottom:0.2rem;';
  intro.textContent = `${results.length} file(s) parsed. Here are sample results — review the lyrics to make sure they look right before continuing.`;
  body.appendChild(intro);

  const beta = document.createElement('p');
  beta.style.cssText = 'font-size:0.74rem;color:#888;margin-bottom:1rem;';
  beta.textContent = 'This feature is in beta. Some songs may have incomplete lyrics or missing section headings.';
  body.appendChild(beta);

  // Pick up to 5 diverse samples: first, last, and a few from the middle
  const sampleCount = Math.min(5, songs.length);
  const indices = new Set();
  indices.add(0);
  if (songs.length > 1) indices.add(songs.length - 1);
  while (indices.size < sampleCount) {
    indices.add(Math.floor(Math.random() * songs.length));
  }
  const samples = [...indices].sort((a, b) => a - b).map(i => songs[i]);

  samples.forEach(({ song }, idx) => {
    const card = document.createElement('div');
    card.style.cssText = 'border:1px solid #ddd;border-radius:6px;padding:0.7rem 0.9rem;margin-bottom:0.7rem;background:#fafafa;';

    const titleEl = document.createElement('div');
    titleEl.style.cssText = 'font-weight:600;font-size:0.85rem;margin-bottom:0.3rem;';
    titleEl.textContent = song.title;
    if (song.author) {
      const authorSpan = document.createElement('span');
      authorSpan.style.cssText = 'font-weight:400;font-size:0.76rem;color:#777;margin-left:0.5rem;';
      authorSpan.textContent = song.author;
      titleEl.appendChild(authorSpan);
    }
    card.appendChild(titleEl);

    const lyricsEl = document.createElement('pre');
    lyricsEl.style.cssText = 'font-family:inherit;font-size:0.78rem;white-space:pre-wrap;word-break:break-word;margin:0;max-height:180px;overflow-y:auto;color:#333;line-height:1.45;';
    const lyrics = song.lyrics || '(no lyrics extracted)';
    // Show first ~600 chars with ellipsis if truncated
    lyricsEl.textContent = lyrics.length > 600 ? lyrics.slice(0, 600) + '\n...' : lyrics;
    card.appendChild(lyricsEl);

    body.appendChild(card);
  });

  if (songs.length > sampleCount) {
    const more = document.createElement('p');
    more.style.cssText = 'font-size:0.74rem;color:#888;text-align:center;';
    more.textContent = `Showing ${sampleCount} of ${songs.length} songs. More can be reviewed after import.`;
    body.appendChild(more);
  }

  document.getElementById('pro-preview-modal').style.display = '';
}

// Preview modal buttons
document.getElementById('pro-preview-close-btn').addEventListener('click', () => {
  document.getElementById('pro-preview-modal').style.display = 'none';
});
document.getElementById('pro-preview-cancel-btn').addEventListener('click', () => {
  document.getElementById('pro-preview-modal').style.display = 'none';
  _proImportParsed = [];
});
document.getElementById('pro-preview-continue-btn').addEventListener('click', () => {
  document.getElementById('pro-preview-modal').style.display = 'none';
  _showProReview();
});

// ── Review modal (select which songs to import) ──
function _showProReview() {
  const results = _proImportParsed;
  const errors = _proImportErrors;

  const body = document.getElementById('pro-import-body');
  body.innerHTML = '';

  if (errors.length) {
    const errNote = document.createElement('p');
    errNote.style.cssText = 'font-size:0.78rem;color:#8b2020;margin-bottom:0.8rem;';
    errNote.textContent = `${errors.length} file(s) could not be parsed and were skipped.`;
    body.appendChild(errNote);
  }

  const songResults    = results.filter(r => r.song._isSong);
  const nonSongResults = results.filter(r => !r.song._isSong);
  const newSongCount   = songResults.filter(r => r.status === 'new').length;
  const dupSongCount   = songResults.filter(r => r.status === 'duplicate').length;

  const summary = document.createElement('p');
  summary.style.cssText = 'font-size:0.82rem;margin-bottom:0.4rem;';
  let summaryText = `${songResults.length} song(s) detected — ${newSongCount} new, ${dupSongCount} duplicate.`;
  if (nonSongResults.length) summaryText += ` ${nonSongResults.length} file(s) without CCLI/author info excluded (scripture, announcements, etc.). Check below to import anyway.`;
  summary.textContent = summaryText;
  body.appendChild(summary);

  const hint = document.createElement('p');
  hint.style.cssText = 'font-size:0.74rem;color:#777;margin-bottom:0.8rem;';
  hint.textContent = 'Review below — uncheck anything you don\'t want to import, or check non-songs to import them too.';
  body.appendChild(hint);

  function updateConfirmBtn() {
    const n = document.querySelectorAll('#pro-import-body input[type=checkbox]:checked').length;
    document.getElementById('pro-import-confirm-btn').textContent = `Import ${n} Item${n !== 1 ? 's' : ''}`;
  }

  results.forEach(({ song, status }) => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:0.6rem;padding:0.3rem 0;border-bottom:1px solid #eee;font-size:0.8rem;';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = song._isSong && status === 'new';
    cb.dataset.songTitle = song.title;
    cb.addEventListener('change', updateConfirmBtn);
    row.appendChild(cb);

    const label = document.createElement('span');
    label.style.flex = '1';
    label.textContent = song.title;
    if (!song._isSong) label.style.color = '#888';
    row.appendChild(label);

    if (!song._isSong) {
      const badge = document.createElement('span');
      badge.style.cssText = 'font-size:0.72rem;background:#f0ede8;color:#7a6e62;padding:0.1em 0.4em;border-radius:3px;white-space:nowrap;';
      badge.textContent = 'non-song';
      row.appendChild(badge);
    } else if (status === 'duplicate') {
      const badge = document.createElement('span');
      badge.style.cssText = 'font-size:0.72rem;color:#7a6e62;white-space:nowrap;';
      badge.textContent = 'duplicate — will replace';
      row.appendChild(badge);
    }

    body.appendChild(row);
  });

  updateConfirmBtn();
  document.getElementById('pro-import-modal').style.display = '';
}

document.getElementById('pro-import-close-btn').addEventListener('click',  () => { document.getElementById('pro-import-modal').style.display = 'none'; });
document.getElementById('pro-import-cancel-btn').addEventListener('click', () => { document.getElementById('pro-import-modal').style.display = 'none'; });

document.getElementById('pro-import-confirm-btn').addEventListener('click', () => {
  const checked = new Set(
    [...document.querySelectorAll('#pro-import-body input[type=checkbox]:checked')].map(cb => cb.dataset.songTitle)
  );
  let imported = 0, replaced = 0;
  _proImportParsed.forEach(({ song, status }) => {
    if (!checked.has(song.title)) return;
    const { _isSong: _, ...clean } = song;  // strip internal flag before storing
    clean.source = 'propresenter';
    const idx = songDb.findIndex(s => normTitle(s.title) === normTitle(clean.title));
    if (idx >= 0) { songDb[idx] = clean; replaced++; }
    else           { songDb.push(clean); imported++; }
  });
  saveSongDb();
  renderSongDb();
  document.getElementById('pro-import-modal').style.display = 'none';
  setStatus(`ProPresenter import complete — ${imported} added, ${replaced} replaced.`, 'success');
});

