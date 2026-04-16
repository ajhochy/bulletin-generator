// ─── Song Database ────────────────────────────────────────────────────────────
let songDb = [];
let sdbEditingIdx = -1; // -1 = new entry, >= 0 = editing existing

function saveSongDb() {
  apiFetch('/api/songs', 'POST', songDb).catch(err => setStatus('Song database save failed: ' + (err.message || err), 'error'));
  renderSongDb();
}

function normTitle(t) {
  return t.toLowerCase()
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\b(the|a|an)\b\s*/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function findSongInDb(itemTitle) {
  const norm = normTitle(itemTitle);
  if (!norm) return null;
  // 1. Exact normalized match
  for (const song of songDb) {
    if (normTitle(song.title) === norm) return song;
  }
  // 2. Substring: DB title is contained within item title or vice versa (min 5 chars)
  for (const song of songDb) {
    const dbNorm = normTitle(song.title);
    if (dbNorm.length >= 5 && (norm.includes(dbNorm) || dbNorm.includes(norm))) return song;
  }
  return null;
}

function upsertSongFromItem(idx) {
  const item = items[idx];
  if (!item || item.type !== 'song') return;

  const title = (item.title || '').trim();
  if (!title) {
    alert('Song title is required before saving to the database.');
    return;
  }

  const detail = item.detail || '';
  const split = splitLyricsCopyright(detail);
  const entry = {
    title,
    lyrics: split.body || '',
    copyright: split.copyright || '',
  };

  const normalizedTitle = normTitle(title);
  let existingIdx = songDb.findIndex(s => normTitle(s.title) === normalizedTitle);
  if (existingIdx < 0) {
    existingIdx = songDb.findIndex(s => s.title === title);
  }

  if (existingIdx >= 0) {
    const existingTitle = songDb[existingIdx].title;
    if (!confirm(`Override "${existingTitle}" in the Song Database with this edited version?`)) {
      return;
    }
    const existingTimesUsed = songDb[existingIdx].times_used || 0;
    const existingSource = songDb[existingIdx].source || 'manual';
    songDb[existingIdx] = { ...entry, times_used: existingTimesUsed, source: existingSource };
    saveSongDb();
    setStatus(`Updated "${title}" in Song Database.`, 'success');
  } else {
    entry.source = 'manual';
    songDb.push(entry);
    saveSongDb();
    setStatus(`Saved "${title}" to Song Database.`, 'success');
  }
}

// Liturgical texts that should always resolve to database entries
const LITURGICAL_RE = /apostles'?\s*creed|lord'?s?\s*prayer/i;

// enrichItemsFromDb — auto-matches songs to DB.
// Returns { withNotes, unmatched } for PCO import review dialog.
//   withNotes: songs that had PCO notes AND a DB match found (user chooses which)
//   unmatched: songs with no notes and no DB match (user can add to DB)
function enrichItemsFromDb(parsedItems) {
  const withNotes = []; // { item, pcoNotes, dbMatch }
  const unmatched = []; // { item }

  for (const item of parsedItems) {
    // Promote liturgical text items from 'label' to 'liturgy' if they
    // match known liturgical titles (Apostles' Creed, Lord's Prayer)
    // so the DB lookup runs on them.
    if (LITURGICAL_RE.test(item.title) && item.type === 'label') {
      item.type = 'liturgy';
    }
    const isSongType = item.type === 'song' ||
      (item.type === 'liturgy' && LITURGICAL_RE.test(item.title));
    if (!isSongType) continue;

    const hasNotes = !!item.detail; // detail came from PCO description/notes
    const match = findSongInDb(item.title);

    if (match) {
      if (hasNotes) {
        // Has PCO notes AND a DB match — defer to user via dialog (FIX 7)
        withNotes.push({ item, pcoNotes: item.detail, dbMatch: match });
      } else {
        // No notes, DB match found — auto-apply immediately
        item.detail = sdbBuildDetail(match);
        match.times_used = (match.times_used || 0) + 1;
        match.last_used  = new Date().toISOString();
      }
    } else {
      // No DB match at all (with or without PCO notes) — prompt user to add (FIX 8)
      unmatched.push({ item });
    }
  }

  return { withNotes, unmatched };
}

// Collapse section headings immediately followed by an item with the same title
function pcoDeduplicateItems(arr) {
  const result = [];
  for (let i = 0; i < arr.length; i++) {
    const item = arr[i];
    if (item.type === 'section') {
      const next = arr[i + 1];
      if (next && next.type !== 'section') {
        // Never collapse actual songs/hymns or liturgical texts — they need DB lookup
        const nextNeedsLyrics = next.type === 'song' ||
          (next.type === 'liturgy' && LITURGICAL_RE.test(next.title));
        if (!nextNeedsLyrics) {
          const hNorm = normTitle(item.title);
          const iNorm = normTitle(next.title);
          if (hNorm && iNorm && (hNorm === iNorm || hNorm.includes(iNorm) || iNorm.includes(hNorm))) {
            // Merge: keep the section heading, absorb the item's detail if heading has none
            result.push({ ...item, detail: item.detail || next.detail });
            i++; // skip the redundant item
            continue;
          }
        }
      }
    }
    result.push(item);
  }
  return result;
}

function sdbFormatDate(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' }); }
  catch (e) { return ''; }
}

function sdbBuildCopyright(song) {
  const parts = [];
  if (song.copyright) parts.push(song.copyright);
  if (song.ccli_number && !(song.copyright || '').includes(song.ccli_number)) {
    parts.push(`CCLI #${song.ccli_number}`);
  }
  return parts.join(' ');
}

function sdbBuildDetail(song) {
  const parts = [];
  if (song.lyrics) parts.push(song.lyrics);
  const cr = sdbBuildCopyright(song);
  if (cr) parts.push(cr);
  return parts.join('\n\n');
}

function renderSongDb() {
  const list     = document.getElementById('song-db-list');
  const empty    = document.getElementById('song-db-empty');
  const searchEl = document.getElementById('song-db-search');
  const sortEl   = document.getElementById('song-db-sort');
  const sourceEl = document.getElementById('song-db-source-filter');
  const countEl  = document.getElementById('sdb-count');
  const query    = searchEl ? searchEl.value.toLowerCase().trim() : '';
  const sortBy   = sortEl ? sortEl.value : 'az';
  const sourceFilter = sourceEl ? sourceEl.value : 'all';

  list.innerHTML = '';

  let visible = songDb.filter(s => {
    // Source filter
    if (sourceFilter === 'propresenter' && s.source !== 'propresenter') return false;
    if (sourceFilter === 'manual' && s.source === 'propresenter') return false;
    // Text search
    if (!query) return true;
    return s.title.toLowerCase().includes(query) ||
      (s.author || '').toLowerCase().includes(query) ||
      (s.copyright || '').toLowerCase().includes(query) ||
      (s.ccli_number || '').includes(query) ||
      (s.lyrics || '').toLowerCase().includes(query);
  });

  if (sortBy === 'az')       visible.sort((a, b) => a.title.localeCompare(b.title));
  else if (sortBy === 'za')  visible.sort((a, b) => b.title.localeCompare(a.title));
  else if (sortBy === 'used') visible.sort((a, b) => (b.times_used || 0) - (a.times_used || 0));
  else if (sortBy === 'lastused') visible.sort((a, b) => (b.last_used || '').localeCompare(a.last_used || ''));
  else if (sortBy === 'added') visible.sort((a, b) => (b.date_added || '').localeCompare(a.date_added || ''));

  if (countEl) {
    const filtered = query || sourceFilter !== 'all';
    countEl.textContent = filtered
      ? `${visible.length} of ${songDb.length} song${songDb.length !== 1 ? 's' : ''}`
      : `${songDb.length} song${songDb.length !== 1 ? 's' : ''}`;
  }

  if (visible.length === 0) {
    empty.style.display = '';
    empty.textContent = songDb.length === 0 ? 'No songs yet — use "+ Add Song" to add your first.' : 'No songs match your search.';
    return;
  }
  empty.style.display = 'none';

  visible.forEach(song => {
    const realIdx = songDb.indexOf(song);
    const entry   = document.createElement('div');
    entry.className = 'song-db-entry';

    // ── Main row (click to expand) ──
    const main = document.createElement('div');
    main.className = 'song-db-entry-main';

    const info = document.createElement('div');
    info.className = 'song-db-entry-info';

    const titleEl = document.createElement('div');
    titleEl.className = 'song-db-entry-title';
    titleEl.textContent = song.title;
    info.appendChild(titleEl);

    if (song.author) {
      const authEl = document.createElement('div');
      authEl.className = 'song-db-entry-author';
      authEl.textContent = song.author;
      info.appendChild(authEl);
    }

    const crLine = sdbBuildCopyright(song);
    if (crLine) {
      const copyEl = document.createElement('div');
      copyEl.className = 'song-db-entry-copy';
      copyEl.textContent = crLine;
      info.appendChild(copyEl);
    }

    // Meta: times used + date added
    const metaParts = [];
    if (song.times_used > 0) metaParts.push(`Used ${song.times_used}×`);
    if (song.last_used)  metaParts.push(`Last: ${sdbFormatDate(song.last_used)}`);
    else if (song.date_added) metaParts.push(`Added: ${sdbFormatDate(song.date_added)}`);
    if (metaParts.length) {
      const metaEl = document.createElement('div');
      metaEl.className = 'song-db-entry-meta';
      metaEl.textContent = metaParts.join(' · ');
      info.appendChild(metaEl);
    }

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'icon-btn sdb-insert-btn';
    toggleBtn.title = 'Insert into plan';
    toggleBtn.textContent = '▼ Insert';

    const editBtn = document.createElement('button');
    editBtn.className = 'icon-btn';
    editBtn.title = 'Edit song';
    editBtn.textContent = '\u270E';

    const delBtn = document.createElement('button');
    delBtn.className = 'icon-btn danger';
    delBtn.title = 'Delete song';
    delBtn.innerHTML = '&times;';

    main.appendChild(info);
    main.appendChild(toggleBtn);
    main.appendChild(editBtn);
    main.appendChild(delBtn);

    // ── Expand panel ──
    const panel = document.createElement('div');
    panel.className = 'song-db-expand-panel';

    // ── Preview view (default) ──
    const previewView = document.createElement('div');
    previewView.className = 'sdb-preview-view';

    if (song.lyrics) {
      const lyricsEl = document.createElement('div');
      lyricsEl.className = 'song-db-preview-lyrics';
      lyricsEl.textContent = song.lyrics.split('\n').slice(0, 6).join('\n');
      previewView.appendChild(lyricsEl);
    } else {
      const noLyrics = document.createElement('div');
      noLyrics.className = 'song-db-preview-lyrics';
      noLyrics.style.fontStyle = 'italic';
      noLyrics.textContent = 'No lyrics stored.';
      previewView.appendChild(noLyrics);
    }

    const expandActions = document.createElement('div');
    expandActions.className = 'song-db-expand-actions';

    const useBtn = document.createElement('button');
    useBtn.className = 'btn-sm btn-sm-primary';
    useBtn.textContent = '+ Use in Bulletin';

    const editBtn2 = document.createElement('button');
    editBtn2.className = 'btn-sm';
    editBtn2.textContent = 'Edit Song';

    expandActions.appendChild(useBtn);
    expandActions.appendChild(editBtn2);
    previewView.appendChild(expandActions);
    panel.appendChild(previewView);

    // ── Inline edit view (hidden by default) ──
    const editView = document.createElement('div');
    editView.className = 'sdb-inline-edit';
    editView.style.display = 'none';
    editView.innerHTML = `
      <div class="field-row"><label>Title</label><input type="text" class="sdb-inline-title" value="" /></div>
      <div class="field-row"><label>Author</label><input type="text" class="sdb-inline-author" value="" /></div>
      <div class="field-row"><label>Lyrics</label><textarea class="sdb-inline-lyrics" rows="14"></textarea></div>
      <div class="field-row"><label>Copyright</label><input type="text" class="sdb-inline-copyright" value="" /></div>
      <div class="song-db-expand-actions" style="margin-top:0.5rem;">
        <button class="btn-sm btn-sm-primary sdb-inline-save-btn">Save</button>
        <button class="btn-sm sdb-inline-cancel-btn">Cancel</button>
      </div>
    `;
    panel.appendChild(editView);

    entry.appendChild(main);
    entry.appendChild(panel);
    list.appendChild(entry);

    // ── Event handlers ──
    main.addEventListener('click', e => {
      if (e.target.closest('button')) return;
      entry.classList.toggle('is-expanded');
    });

    toggleBtn.addEventListener('click', e => {
      e.stopPropagation();
      syncAllItems();
      items.push({ type: 'song', title: song.title, detail: sdbBuildDetail(song) });
      songDb[realIdx].times_used = (songDb[realIdx].times_used || 0) + 1;
      songDb[realIdx].last_used  = new Date().toISOString();
      saveSongDb();
      renderItemList();
      renderPreview();
      scheduleProjectPersist();
      document.querySelector('.tab-btn[data-tab="page-editor"]').click();
      setTimeout(() => {
        const cards = itemList.querySelectorAll('.item-card');
        const last  = cards[cards.length - 1];
        last?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 80);
    });

    // Header edit pencil — expand and switch to inline edit
    editBtn.addEventListener('click', e => {
      e.stopPropagation();
      entry.classList.add('is-expanded');
      _openInlineEdit(entry, realIdx);
    });
    // Expand-panel edit button — switch to inline edit
    editBtn2.addEventListener('click', () => _openInlineEdit(entry, realIdx));

    delBtn.addEventListener('click', e => {
      e.stopPropagation();
      if (confirm(`Are you sure you want to delete "${song.title}"?`)) {
        songDb.splice(realIdx, 1);
        saveSongDb();
      }
    });

    useBtn.addEventListener('click', () => {
      syncAllItems();
      items.push({ type: 'song', title: song.title, detail: sdbBuildDetail(song) });
      songDb[realIdx].times_used = (songDb[realIdx].times_used || 0) + 1;
      songDb[realIdx].last_used  = new Date().toISOString();
      saveSongDb();
      renderItemList();
      renderPreview();
      scheduleProjectPersist();
      document.querySelector('.tab-btn[data-tab="page-editor"]').click();
      setTimeout(() => {
        const cards = itemList.querySelectorAll('.item-card');
        const last  = cards[cards.length - 1];
        last?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 80);
    });
  });
}

function _openInlineEdit(entryEl, idx) {
  const song = songDb[idx];
  const previewView = entryEl.querySelector('.sdb-preview-view');
  const editView = entryEl.querySelector('.sdb-inline-edit');
  if (!previewView || !editView) return;

  // Populate fields
  editView.querySelector('.sdb-inline-title').value = song.title || '';
  editView.querySelector('.sdb-inline-author').value = song.author || '';
  editView.querySelector('.sdb-inline-lyrics').value = song.lyrics || '';
  editView.querySelector('.sdb-inline-copyright').value = song.copyright || '';

  // Swap views
  previewView.style.display = 'none';
  editView.style.display = '';

  // Focus title
  editView.querySelector('.sdb-inline-title').focus();

  // Save handler
  const saveBtn = editView.querySelector('.sdb-inline-save-btn');
  const cancelBtn = editView.querySelector('.sdb-inline-cancel-btn');

  function onSave() {
    const title = editView.querySelector('.sdb-inline-title').value.trim();
    if (!title) { editView.querySelector('.sdb-inline-title').focus(); return; }
    const existingSource = songDb[idx].source || 'manual';
    songDb[idx] = {
      ...songDb[idx],
      title,
      author: editView.querySelector('.sdb-inline-author').value.trim(),
      lyrics: editView.querySelector('.sdb-inline-lyrics').value.trim(),
      copyright: editView.querySelector('.sdb-inline-copyright').value.trim(),
      source: existingSource,
    };
    saveSongDb();
    renderSongDb();
    cleanup();
  }

  function onCancel() {
    previewView.style.display = '';
    editView.style.display = 'none';
    cleanup();
  }

  function cleanup() {
    saveBtn.removeEventListener('click', onSave);
    cancelBtn.removeEventListener('click', onCancel);
  }

  saveBtn.addEventListener('click', onSave);
  cancelBtn.addEventListener('click', onCancel);
}

function openSdbForm(idx) {
  sdbEditingIdx = (idx !== undefined && idx >= 0) ? idx : -1;
  const s = sdbEditingIdx >= 0 ? songDb[sdbEditingIdx] : {};
  document.getElementById('sdb-title').value     = s.title     || '';
  document.getElementById('sdb-author').value    = s.author    || '';
  document.getElementById('sdb-lyrics').value    = s.lyrics    || '';
  document.getElementById('sdb-copyright').value = s.copyright || '';
  const heading = document.getElementById('sdb-form-heading');
  if (heading) heading.textContent = 'Add Song Manually';
  document.getElementById('sdb-title').focus();
}

function closeSdbForm() {
  sdbEditingIdx = -1;
  document.getElementById('sdb-title').value     = '';
  document.getElementById('sdb-author').value    = '';
  document.getElementById('sdb-lyrics').value    = '';
  document.getElementById('sdb-copyright').value = '';
  const heading = document.getElementById('sdb-form-heading');
  if (heading) heading.textContent = 'Add Song Manually';
}



function parseClipboardSong(raw) {
  const COPYRIGHT_RE = /©|copyright|\(c\)|admin\.|all rights reserved|www\.|ccli/i;
  const CCLI_RE      = /ccli\s*(?:song\s*)?(?:license\s*)?#?\s*(\d{5,})/i;

  const lines = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');

  let ccli = '';
  const copyrightLines = [];
  const lyricLines     = [];

  for (const line of lines) {
    const t = line.trim();

    // Extract CCLI number
    const ccliM = t.match(CCLI_RE);
    if (ccliM) { ccli = ccliM[1]; copyrightLines.push(t); continue; }

    // Separate copyright/credit lines from lyrics
    if (t && COPYRIGHT_RE.test(t)) { copyrightLines.push(t); continue; }

    lyricLines.push(line);
  }

  // Trim blank lines from top/bottom and collapse 3+ blanks to 2
  let lyrics = lyricLines.join('\n').trim().replace(/\n{3,}/g, '\n\n');

  // Build copyright string, deduping and dropping bare CCLI-number-only lines
  const seenCr = new Set();
  const copyright = copyrightLines
    .filter(l => {
      const k = l.trim().toLowerCase();
      if (seenCr.has(k)) return false;
      seenCr.add(k);
      // Drop lines that are only a CCLI number (already captured in ccli field)
      return !(CCLI_RE.test(l) && l.trim().replace(CCLI_RE, '').replace(/[^a-z]/gi, '').length === 0);
    })
    .join('  ');

  return { lyrics, copyright, ccli };
}

function _applyClipboardText(text) {
  if (!text.trim()) { alert('Clipboard is empty.'); return; }
  const parsed = parseClipboardSong(text);
  closeSdbForm();
  document.getElementById('sdb-form-heading').textContent = 'Add from Clipboard';
  document.getElementById('sdb-title').value     = '';
  document.getElementById('sdb-author').value    = '';
  document.getElementById('sdb-lyrics').value    = parsed.lyrics;
  let cr = parsed.copyright;
  if (parsed.ccli && !cr.includes(parsed.ccli)) {
    cr = (cr ? cr + '  ' : '') + `CCLI #${parsed.ccli}`;
  }
  document.getElementById('sdb-copyright').value = cr;
}

// Paste dialog fallback
document.getElementById('sdb-paste-dialog-cancel').addEventListener('click', () => {
  document.getElementById('sdb-paste-dialog').close();
});
document.getElementById('sdb-paste-dialog-ok').addEventListener('click', () => {
  const text = document.getElementById('sdb-paste-fallback-ta').value;
  document.getElementById('sdb-paste-dialog').close();
  _applyClipboardText(text);
  document.getElementById('sdb-title').scrollIntoView({ behavior: 'smooth', block: 'start' });
  document.getElementById('sdb-title').focus();
});

document.getElementById('song-db-paste-btn').addEventListener('click', async () => {
  let text = '';
  try {
    if (!navigator.clipboard || !navigator.clipboard.readText) throw new Error('unavailable');
    text = await navigator.clipboard.readText();
  } catch (e) {
    // Clipboard API unavailable or permission denied — show manual paste dialog
    const dialog = document.getElementById('sdb-paste-dialog');
    document.getElementById('sdb-paste-fallback-ta').value = '';
    dialog.showModal();
    setTimeout(() => document.getElementById('sdb-paste-fallback-ta').focus(), 50);
    return;
  }
  if (!text.trim()) { alert('Clipboard is empty.'); return; }

  _applyClipboardText(text);
  document.getElementById('sdb-title').scrollIntoView({ behavior: 'smooth', block: 'start' });
  document.getElementById('sdb-title').focus();
});

document.getElementById('sdb-save-btn').addEventListener('click', () => {
  const title       = document.getElementById('sdb-title').value.trim();
  const author      = document.getElementById('sdb-author').value.trim();
  const lyrics      = document.getElementById('sdb-lyrics').value.trim();
  const copyright   = document.getElementById('sdb-copyright').value.trim();
  if (!title) { document.getElementById('sdb-title').focus(); return; }
  songDb.push({ title, author, lyrics, copyright, source: 'manual', date_added: new Date().toISOString() });
  saveSongDb();
  closeSdbForm();
  renderSongDb();
});

document.getElementById('sdb-cancel-btn').addEventListener('click', closeSdbForm);

document.getElementById('song-db-export-btn').addEventListener('click', () => {
  const json = JSON.stringify(songDb, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = 'song-database.json';
  a.click();
  URL.revokeObjectURL(url);
});

document.getElementById('song-db-import-input').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    try {
      const data = JSON.parse(ev.target.result);
      if (!Array.isArray(data)) throw new Error('Expected a JSON array.');
      let added = 0;
      for (const song of data) {
        if (!song.title) continue;
        if (!songDb.find(s => normTitle(s.title) === normTitle(song.title))) {
          songDb.push({
            title:       song.title,
            author:      song.author      || '',
            lyrics:      song.lyrics      || '',
            copyright:   song.copyright   || song.copyright_raw || '',
            ccli_number: song.ccli_number || '',
            source:      song.source      || 'manual',
            date_added:  song.date_added  || new Date().toISOString(),
          });
          added++;
        }
      }
      saveSongDb();
      alert(`Imported ${added} new song${added !== 1 ? 's' : ''} (${data.length - added} already in DB).`);
    } catch (err) {
      alert('Import failed: ' + err.message);
    }
  };
  reader.readAsText(file);
  e.target.value = '';
});

document.getElementById('song-db-clear-btn').addEventListener('click', () => {
  if (!confirm(`Clear all ${songDb.length} songs from the database? This cannot be undone.`)) return;
  songDb = [];
  saveSongDb();
});

document.getElementById('song-db-search').addEventListener('input', renderSongDb);
document.getElementById('song-db-sort').addEventListener('change', renderSongDb);
document.getElementById('song-db-source-filter').addEventListener('change', renderSongDb);

