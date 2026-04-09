function buildPreviewItemEl(item, idx) {
  const t = (item.title  || '').trim();
  const d = (item.detail || '').trim();
  const fmt = getEffectiveFmt(item);

  if (item.type === 'section') {
    const wrapper = document.createElement('div');
    wrapper.className = 'liturgy-section preview-linkable';
    applyPreviewLinkMeta(wrapper, { section: 'oow', itemIdx: idx });

    const heading = document.createElement('div');
    heading.className = 'section-heading';
    heading.textContent = t || 'Section';
    // Apply only color and alignment overrides — size/weight/case come from CSS
    if (fmt.titleColor) heading.style.color = fmt.titleColor;
    if (fmt.titleAlign) heading.style.textAlign = fmt.titleAlign;
    wrapper.appendChild(heading);

    if (d) {
      const body = document.createElement('div');
      body.className = 'item-body';
      body.style.marginTop = '0.3rem';
      applyBodyFmt(body, fmt);
      renderBodyText(body, d, true);
      wrapper.appendChild(body);
    }
    return wrapper;
  } else {
    const wrapper = document.createElement('div');
    wrapper.className = 'order-item preview-linkable';
    applyPreviewLinkMeta(wrapper, { section: 'oow', itemIdx: idx });

    if (t) {
      const heading = document.createElement('div');
      const hasRule = !!(item.detail || '').trim();
      heading.className = 'item-heading' + (hasRule ? ' has-rule' : '');
      heading.textContent = t;
      applyTitleFmt(heading, fmt);
      wrapper.appendChild(heading);
    }

    if (d) {
      const isSong = item.type === 'song';
      if (isSong) {
        const { body: lyricBody, copyright } = splitLyricsCopyright(d);
        if (lyricBody) {
          const body = document.createElement('div');
          body.className = 'item-body';
          applyBodyFmt(body, fmt);
          renderBodyText(body, lyricBody);
          wrapper.appendChild(body);
        }
        if (copyright) {
          const cpEl = document.createElement('div');
          cpEl.className = 'song-copyright';
          cpEl.textContent = copyright;
          wrapper.appendChild(cpEl);
        }
      } else {
        const body = document.createElement('div');
        body.className = 'item-body';
        applyBodyFmt(body, fmt);
        renderBodyText(body, d, true);
        wrapper.appendChild(body);
      }
    }
    return wrapper;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SHARED LAYOUT CONTRACT
// All sections that participate in the preview/layout pipeline MUST emit objects
// that conform to the shapes documented here.  Implementing a new section means:
//   1. Producing chunks (see CHUNK CONTRACT) via makeChunk() [Task 1 / #125]
//   2. Producing break-source entries (see BREAK-SOURCE CONTRACT) via makeBreakSrc() [Task 2 / #126]
//   3. Stamping control metadata via applySplitCtrlMeta() / applyBreakCtrlMeta() [Task 3 / #127]
//   4. Stamping navigation metadata via applyPreviewLinkMeta() [Task 4 / #128]
// ───────────────────────────────────────────────────────────────────────────────
//
// ── CHUNK CONTRACT ─────────────────────────────────────────────────────────────
// A chunk is a layout unit passed to the page-packing algorithm.
// All producers (buildChunks, bottom-section adapters) MUST emit this shape.
//
// {
//   section:               string           — which section owns this chunk
//                                             'oow' | 'serving' | 'calendar' | 'staff' | 'announcements'
//   sourceId:              *                — stable identifier within the section
//                                             OOW: items[] index (number)
//                                             Future sections: define their own stable key
//   els:                   HTMLElement[]    — DOM nodes to render on the page
//   forceBreak:            boolean          — start a new page before this chunk
//   noBreakBefore:         boolean          — suppress auto page-break before this chunk
//   stickyToNext:          boolean          — must share a page with the following chunk
//                                             (used for section headings so they never orphan)
//   breakableBefore:       boolean          — auto page-break may occur before this chunk
//                                             (false on noBreakBefore chunks and forceBreak sentinels)
//
//   // OOW-specific fields — null for non-OOW sections until migrated:
//   breakItemIdx:          number|null      — items[] index of explicit page-break item
//   separatorItemIdx:      number|null      — items[] index of song item with a '---' separator
//   separatorStanzaIdx:    number|null      — global stanza index that starts after a separator break
//   paragraphBreakItemIdx: number|null      — items[] index of liturgy/label item with a para break
//   paragraphBreakIdx:     number|null      — paragraph index within that item
//   itemIdx:               number|null      — items[] index (OOW only; equals sourceId for OOW)
//   stanzaIdx:             number|null      — global stanza index (song chunks only)
//   paragraphIdx:          number|null      — paragraph index (liturgy/label chunks only)
//   // Calendar-specific (null for non-calendar sections):
//   calDate:               string|null      — 'YYYY-MM-DD' or null (calendar segments only; '' for title segment)
//   // Serving-specific (null for non-serving sections):
//   servingWeekIdx:        number|null      — index into servingSchedule.weeks[]
//   servingLabel:          string|null      — display label ('Serving Today', etc.)
//   servingWeek:           object|null      — the full week object from servingSchedule
//   servingSegTeams:       array|null       — filtered teams for this segment (no page-break entries)
// }
//
// ── BREAK-SOURCE CONTRACT ──────────────────────────────────────────────────────
// pageBreakSources[] is a parallel array to pages[] with one entry per page boundary
// (pageBreakSources.length === pages.length - 1).
// Each entry explains why a page break occurred so controls can remove or convert it.
//
// OOW break types:
//   { type: 'item',         breakItemIdx }
//   { type: 'separator',    separatorItemIdx, separatorStanzaIdx }
//   { type: 'liturgy-para', paragraphBreakItemIdx, paragraphBreakIdx }
//   { type: 'auto',         itemIdx, stanzaIdx, paragraphIdx }
//
// Bottom-section break types (appendBottomSection):
//   { type: 'bottom-merged', bottomSection }   — section merged onto prior page
//   { type: 'bottom-auto',   bottomSection }   — section placed on its own new page
//
// OOW/Announcements boundary:
//   { type: 'oow-merged' }   — OOW merged onto last announcements page
//   { type: 'oow-auto'   }   — OOW started on its own page after announcements
//
// Serving break types:
//   { type: 'serving-week',  weekIdx }                              — forced break before a serving week
//   { type: 'serving-team',  weekIdx, teamBreakIdx }                — intra-week team page-break
//   { type: 'serving-split', weekIdx, boundary, insertBeforeIdx }   — "Break here" split control
//
// Calendar break types:
//   { type: 'cal-force', calDayDate: '' }           — whole calendar section forced to new page
//   { type: 'cal-day',   calDayDate: 'YYYY-MM-DD' } — forced break before a specific day group
//   { type: 'cal-split', calDayDate: 'YYYY-MM-DD' } — "Break here" split control between day groups
//
// ── PREVIEW CONTROL METADATA ───────────────────────────────────────────────────
// Split controls (.pg-split-ctrl) carry data-* attributes describing the two
// adjacent chunks at the boundary.  Set via applySplitCtrlMeta() [Task 3 / #127]:
//
//   data-splitAfterItemIdx        — itemIdx of the chunk just above the control
//   data-splitAfterStanzaIdx      — stanzaIdx of the chunk just above ('' if null)
//   data-splitBeforeItemIdx       — itemIdx of the chunk just below the control
//   data-splitBeforeStanzaIdx     — stanzaIdx of the chunk just below ('' if null)
//   data-splitBeforeParagraphIdx  — paragraphIdx of the chunk just below ('' if null)
//
// Break controls (.pg-break-ctrl) carry data-* attributes from the break-source entry.
// Set via applyBreakCtrlMeta() [Task 3 / #127]:
//
//   data-breakType                — break-source type string (see BREAK-SOURCE CONTRACT)
//   data-breakItemIdx             — (type:'item') items[] index
//   data-separatorItemIdx         — (type:'separator') items[] index
//   data-separatorStanzaIdx       — (type:'separator') global stanza index
//   data-paragraphBreakItemIdx    — (type:'liturgy-para') items[] index
//   data-paragraphBreakIdx        — (type:'liturgy-para') paragraph index
//   data-breakAutoItemIdx         — (type:'auto') items[] index
//   data-breakAutoStanzaIdx       — (type:'auto') stanza index
//   data-breakAutoParagraphIdx    — (type:'auto') paragraph index
//   data-bottomSection            — (type:'bottom-*') section key ('serving'|'calendar'|'staff')
//   data-fits                     — (type:'bottom-*') '1' if content fits on prior page, else '0'
//   data-calDayDate               — (type:'cal-force'|'cal-day'|'cal-split') ISO date or ''
//
// ── PREVIEW-TO-EDITOR NAVIGATION CONTRACT ─────────────────────────────────────
// Elements with class .preview-linkable are clickable in the preview pane to
// scroll the editor to the corresponding source item.
// Set via applyPreviewLinkMeta() [Task 4 / #128]:
//
//   OOW items:
//     data-previewIdx      — items[] index
//     data-stanzaIdx       — global stanza index (song chunks; omitted if null)
//     data-paragraphIdx    — paragraph index (liturgy/label chunks; omitted if null)
//
//   Calendar items:
//     data-previewSection  — 'calendar' (routes to scrollEditorToSection)
//     data-calDate         — 'YYYY-MM-DD' or '' for first/title segment
//
//   Serving items:
//     data-previewSection  — 'volunteers' (routes to scrollEditorToSection)
//
//   Future sections: extend applyPreviewLinkMeta() with a section-specific branch.
//
// ═══════════════════════════════════════════════════════════════════════════════

// ─── Chunk factory ────────────────────────────────────────────────────────────
/**
 * makeChunk(fields) → chunk
 * Factory for the shared chunk contract (see CHUNK CONTRACT above).
 * All producers MUST use this instead of raw object literals.
 */
function makeChunk(fields) {
  return {
    section:               fields.section               ?? 'oow',
    sourceId:              fields.sourceId              ?? null,
    els:                   fields.els                   ?? [],
    forceBreak:            fields.forceBreak            ?? false,
    noBreakBefore:         fields.noBreakBefore         ?? false,
    stickyToNext:          fields.stickyToNext          ?? false,
    breakableBefore:       fields.breakableBefore       ?? true,
    // OOW-specific (null for non-OOW sections until migrated)
    breakItemIdx:          fields.breakItemIdx          ?? null,
    separatorItemIdx:      fields.separatorItemIdx      ?? null,
    separatorStanzaIdx:    fields.separatorStanzaIdx    ?? null,
    paragraphBreakItemIdx: fields.paragraphBreakItemIdx ?? null,
    paragraphBreakIdx:     fields.paragraphBreakIdx     ?? null,
    itemIdx:               fields.itemIdx               ?? null,
    stanzaIdx:             fields.stanzaIdx             ?? null,
    paragraphIdx:          fields.paragraphIdx          ?? null,
    // Calendar-specific (null for non-calendar sections)
    calDate:               fields.calDate               ?? null,
    // Serving-specific (null for non-serving sections)
    servingWeekIdx:        fields.servingWeekIdx        ?? null,
    servingLabel:          fields.servingLabel          ?? null,
    servingWeek:           fields.servingWeek           ?? null,
    servingSegTeams:       fields.servingSegTeams       ?? null,
    servingTeamBreakIdx:   fields.servingTeamBreakIdx   ?? null,
  };
}

// ─── Break-source factory ─────────────────────────────────────────────────────
/**
 * makeBreakSrc(type, fields) → breakSource entry
 * Factory for the shared break-source contract (see BREAK-SOURCE CONTRACT above).
 * Used to populate pageBreakSources[] (one entry per page boundary).
 */
function makeBreakSrc(type, fields) {
  return Object.assign({ type }, fields);
}

// ─── Preview control metadata helpers ────────────────────────────────────────
/**
 * applySplitCtrlMeta(el, afterChunk, beforeChunk)
 * Stamps data-* attributes on a .pg-split-ctrl element.
 * afterChunk  — the chunk just above the control (already rendered)
 * beforeChunk — the chunk just below the control (not yet rendered)
 */
function applySplitCtrlMeta(el, afterChunk, beforeChunk) {
  el.dataset.splitAfterItemIdx       = afterChunk.itemIdx  ?? '';
  el.dataset.splitAfterStanzaIdx     = afterChunk.stanzaIdx  ?? '';
  el.dataset.splitBeforeItemIdx      = beforeChunk.itemIdx ?? '';
  el.dataset.splitBeforeStanzaIdx    = beforeChunk.stanzaIdx ?? '';
  el.dataset.splitBeforeParagraphIdx = beforeChunk.paragraphIdx ?? '';
}

/**
 * applyBreakCtrlMeta(el, src) → label string
 * Stamps data-* attributes on a .pg-break-ctrl element from a break-source entry.
 * Returns the button label so the caller can set btn.textContent.
 * Extend this function when adding break types for new sections.
 */
function applyBreakCtrlMeta(el, src) {
  el.dataset.breakType = src.type;
  switch (src.type) {
    case 'item':
      el.dataset.breakItemIdx = src.breakItemIdx;
      return '✕ Remove page break';
    case 'separator':
      el.dataset.separatorItemIdx   = src.separatorItemIdx;
      el.dataset.separatorStanzaIdx = src.separatorStanzaIdx;
      return '✕ Remove break (lyrics)';
    case 'liturgy-para':
      el.dataset.paragraphBreakItemIdx = src.paragraphBreakItemIdx;
      el.dataset.paragraphBreakIdx     = src.paragraphBreakIdx;
      return '✕ Remove break (liturgy)';
    case 'auto':
      el.dataset.breakItemIdx      = src.itemIdx;
      el.dataset.breakStanzaIdx    = src.stanzaIdx ?? '';
      el.dataset.breakParagraphIdx = src.paragraphIdx ?? '';
      return '✕ Merge with previous page';
    case 'ann-item':
      el.dataset.annIdx = src.annIdx;
      return '✕ Remove page break';
    case 'ann-auto':
      el.dataset.annIdx = src.annIdx;
      return '✕ Merge with previous page';
    case 'cal-force':
      el.dataset.calDayDate = src.calDayDate ?? '';
      return '✕ Remove "start on new page"';
    case 'cal-day':
      el.dataset.calDayDate = src.calDayDate ?? '';
      return '✕ Remove calendar break';
    case 'cal-split':
      el.dataset.calDayDate = src.calDayDate ?? '';
      return '⊞ Break here';
    case 'serving-week':
      el.dataset.servingWeekIdx = src.weekIdx ?? '';
      return '✕ Remove page break';
    case 'serving-team':
      el.dataset.servingWeekIdx      = src.weekIdx ?? '';
      el.dataset.servingTeamBreakIdx = src.teamBreakIdx ?? '';
      return '✕ Remove page break';
    case 'serving-split':
      el.dataset.servingWeekIdx         = src.weekIdx ?? '';
      el.dataset.servingBoundary        = src.boundary ?? '';
      el.dataset.servingInsertBeforeIdx = src.insertBeforeIdx ?? '';
      return '⊞ Break here';
    default:
      return '✕ Remove break';
  }
}

// ─── Preview-to-editor navigation helper ─────────────────────────────────────
/**
 * applyPreviewLinkMeta(el, chunk)
 * Stamps data-* navigation attributes on a .preview-linkable element.
 * el    — the DOM element carrying the preview-linkable class
 * chunk — the chunk object (or a plain object with section/itemIdx/stanzaIdx/paragraphIdx)
 *
 * Currently handles OOW items only.
 * To support a new section, add a branch here keyed on chunk.section
 * and set whatever data-* attributes its click handler reads.
 * See the PREVIEW-TO-EDITOR NAVIGATION CONTRACT comment block above.
 */
function applyPreviewLinkMeta(el, chunk) {
  if (chunk.section === 'oow') {
    if (chunk.itemIdx      != null) el.dataset.previewIdx   = chunk.itemIdx;
    if (chunk.stanzaIdx    != null) el.dataset.stanzaIdx    = chunk.stanzaIdx;
    if (chunk.paragraphIdx != null) el.dataset.paragraphIdx = chunk.paragraphIdx;
  } else if (chunk.section === 'calendar') {
    el.dataset.previewSection = 'calendar';
    if (chunk.calDate != null) el.dataset.calDate = chunk.calDate;
  } else if (chunk.section === 'serving') {
    el.dataset.previewSection = 'volunteers';
  }
  // Other sections: extend here when migrating (see #119)
}

// ─── Build page chunks for the interior page-split algorithm ─────────────────
// Songs are split into per-stanza chunks so individual stanzas can start on a
// new page, but no single stanza is ever split across pages.
// A `---` line inside song lyrics creates a forced-break sentinel between sections.
function buildChunks(item, idx) {
  // ── Page-break item → forced break sentinel ───────────────────────────────
  if (item.type === 'page-break') {
    return [makeChunk({ section: 'oow', sourceId: idx, els: [],
              forceBreak: true, breakItemIdx: idx, itemIdx: idx })];
  }

  // ── PCO note / media: hidden from print ───────────────────────────────────
  if (item.type === 'note' || item.type === 'media') {
    return [];  // no elements, no forced break — completely omitted from the bulletin
  }

  // ── Section heading: sticky to next item ──────────────────────────────────
  if (item.type === 'section') {
    return [makeChunk({ section: 'oow', sourceId: idx,
              els: [buildPreviewItemEl(item, idx)],
              noBreakBefore: !!item._noBreakBefore, itemIdx: idx,
              stickyToNext: true })];
  }

  const d = (item.detail || '').trim();
  const noBreakStanzas = new Set(Array.isArray(item._noBreakBeforeStanzas) ? item._noBreakBeforeStanzas : []);

  if (item.type === 'song' && d) {
    const { body: lyricBody, copyright } = splitLyricsCopyright(d);

    // Split lyricBody on --- separators to get sections; each --- becomes a forced-break sentinel.
    const sections = lyricBody ? lyricBody.split(/\n---\n/) : [''];

    // Count total stanzas across all sections (to know where to put the copyright)
    let totalStanzas = 0;
    sections.forEach(sec => { totalStanzas += splitLyricSectionIntoStanzas(sec).length; });

    if (totalStanzas <= 1) {
      // Single block — no splitting needed
      return [makeChunk({ section: 'oow', sourceId: idx,
                els: [buildPreviewItemEl(item, idx)],
                noBreakBefore: !!item._noBreakBefore, itemIdx: idx })];
    }

    const t = (item.title || '').trim();
    const fmt = getEffectiveFmt(item);
    const chunks = [];
    let globalStanzaIdx = 0;

    sections.forEach((section, sectionIdx) => {
      if (sectionIdx > 0) {
        // Insert forced-break sentinel between sections (from `---` in lyrics)
        chunks.push(makeChunk({ section: 'oow', sourceId: idx, els: [],
                      forceBreak: true, separatorItemIdx: idx,
                      separatorStanzaIdx: globalStanzaIdx, itemIdx: idx }));
      }

      const stanzas = splitLyricSectionIntoStanzas(section);
      stanzas.forEach((stanza, si) => {
        const isVeryFirst = sectionIdx === 0 && si === 0;
        const isVeryLast  = globalStanzaIdx === totalStanzas - 1;
        const stanzaGlobalIdx = globalStanzaIdx;

        const wrap = document.createElement('div');
        wrap.className = 'order-item' +
          (isVeryLast ? '' : ' song-stanza') +
          (isVeryFirst ? ' preview-linkable' : '');
        applyPreviewLinkMeta(wrap, { section: 'oow', itemIdx: idx, stanzaIdx: stanzaGlobalIdx });

        if (isVeryFirst && t) {
          const h = document.createElement('div');
          h.className = 'item-heading has-rule';
          h.textContent = t;
          applyTitleFmt(h, fmt);
          wrap.appendChild(h);
        }
        const body = document.createElement('div');
        body.className = 'item-body';
        applyBodyFmt(body, fmt);
        renderBodyText(body, stanza);
        wrap.appendChild(body);

        if (isVeryLast && copyright) {
          const cp = document.createElement('div');
          cp.className = 'song-copyright';
          cp.textContent = copyright;
          wrap.appendChild(cp);
        }

        const noBreak = isVeryFirst ? !!item._noBreakBefore : noBreakStanzas.has(stanzaGlobalIdx);
        chunks.push(makeChunk({ section: 'oow', sourceId: idx,
                      els: [wrap], noBreakBefore: noBreak,
                      itemIdx: idx, stanzaIdx: stanzaGlobalIdx }));
        globalStanzaIdx++;
      });
    });
    return chunks;
  }

  // Liturgy and label: split multi-paragraph body into per-paragraph chunks.
  // Mirrors the song-stanza pattern exactly.
  if ((item.type === 'liturgy' || item.type === 'label') && d) {
    const paragraphs = d.split(/\n\n+/);
    if (paragraphs.length > 1) {
      const t = (item.title || '').trim();
      const fmt = getEffectiveFmt(item);
      const forceBreakSet = new Set(Array.isArray(item._forceBreakBeforeParagraph) ? item._forceBreakBeforeParagraph : []);
      const noBreakSet    = new Set(Array.isArray(item._noBreakBeforeParagraph)    ? item._noBreakBeforeParagraph    : []);
      const chunks = [];
      paragraphs.forEach((para, pi) => {
        if (pi > 0 && forceBreakSet.has(pi)) {
          // Forced-break sentinel — like the `---` sentinel in songs.
          chunks.push(makeChunk({ section: 'oow', sourceId: idx, els: [],
                        forceBreak: true, paragraphBreakItemIdx: idx,
                        paragraphBreakIdx: pi, itemIdx: idx }));
        }
        const wrap = document.createElement('div');
        wrap.className = 'order-item' + (pi === 0 ? ' preview-linkable' : '');
        applyPreviewLinkMeta(wrap, { section: 'oow', itemIdx: idx, paragraphIdx: pi });
        if (pi === 0 && t) {
          const h = document.createElement('div');
          h.className = 'item-heading has-rule';
          h.textContent = t;
          applyTitleFmt(h, fmt);
          wrap.appendChild(h);
        }
        const body = document.createElement('div');
        body.className = 'item-body';
        applyBodyFmt(body, fmt);
        renderBodyText(body, para, true);
        wrap.appendChild(body);
        const noBreak = pi === 0 ? !!item._noBreakBefore : noBreakSet.has(pi);
        chunks.push(makeChunk({ section: 'oow', sourceId: idx,
                      els: [wrap], noBreakBefore: noBreak,
                      itemIdx: idx, paragraphIdx: pi }));
      });
      return chunks;
    }
  }

  // Everything else (including single-paragraph liturgy/label): one chunk, not sticky.
  return [makeChunk({ section: 'oow', sourceId: idx,
            els: [buildPreviewItemEl(item, idx)],
            noBreakBefore: !!item._noBreakBefore, itemIdx: idx })];
}

// ─── Render booklet preview ───────────────────────────────────────────────────
function renderPreview() {
  syncAllItems();

  // Blur any focused element inside the preview pane before we tear down the DOM.
  // This prevents the browser from firing a "scroll focused element into view"
  // correction that would override our manual scrollTop restore below.
  if (document.activeElement && previewPane.contains(document.activeElement)) {
    document.activeElement.blur();
  }

  // Preserve scroll position — removing all .booklet-page nodes drops content
  // height to ~0 which resets scrollTop to 0 before new pages are inserted.
  const _savedScroll = previewPane.scrollTop;

  const title         = svcTitle.value.trim() || 'Order of Worship';
  const date          = svcDate.value.trim();
  const church        = svcChurch.value.trim();
  const hasAnn = optAnnouncements.checked &&
                 annData.some(a => a.title.trim() || a.body.trim());

  // Tracks the last booklet-page rendered and how much vertical space it has used.
  // Used by appendBottomSection() to decide whether a bottom page can share it.
  let lastRenderedPageEl = null;
  let lastPageUsedH      = 0;

  previewPane.querySelectorAll('.booklet-page, .pg-break-ctrl').forEach(el => el.remove());
  previewEmpty.style.display = 'none';

  const hasContent = items.length > 0 || title || date || hasAnn;
  if (!hasContent) { previewEmpty.style.display = ''; updatePrintBtn(); return; }

  // ── Cover page ──────────────────────────────────────────────────────────────
  if (optCover.checked) {
    const cover = document.createElement('div');

    if (coverImageUrl) {
      // Full-bleed image cover — no text overlay
      cover.className = 'booklet-page cover cover-image-full';
      const img = document.createElement('img');
      img.className = 'cover-full-img';
      img.src = coverImageUrl;
      img.alt = '';
      cover.appendChild(img);
    } else {
      // Text-only cover (no image uploaded)
      cover.className = 'booklet-page cover';
      const cross = document.createElement('div');
      cross.className = 'cover-cross';
      cross.textContent = '✝';
      cover.appendChild(cross);

      if (church) {
        const el = document.createElement('div');
        el.className = 'cover-church';
        el.textContent = church;
        cover.appendChild(el);
      }

      const rule = document.createElement('div');
      rule.className = 'cover-rule';
      cover.appendChild(rule);

      const titleEl = document.createElement('div');
      titleEl.className = 'cover-title';
      titleEl.textContent = title;
      cover.appendChild(titleEl);

      if (date) {
        const dateEl = document.createElement('div');
        dateEl.className = 'cover-date';
        dateEl.textContent = date;
        cover.appendChild(dateEl);
      }
    }

    previewPane.appendChild(cover);
  }

  // ── Welcome + Announcements page(s) ─────────────────────────────────────────
  // Announcements are measured and packed like order-of-worship chunks so the
  // preview and PDF always match — no more overflow-only-in-print surprises.
  {
    const annAvailH = Math.round((getPageDims().h - 0.35 - 0.45 - (optFooter.checked ? 0.55 : 0)) * 96);

    // Build the welcome section (always on the first page)
    const welcomeSection = document.createElement('div');
    welcomeSection.className = 'welcome-section';

    const welcomeTitle = document.createElement('div');
    welcomeTitle.className = 'welcome-title';
    welcomeTitle.textContent = welcomeHeading || (church ? `Welcome to ${church}` : 'Welcome');
    welcomeSection.appendChild(welcomeTitle);

    const welcomeDivider = document.createElement('hr');
    welcomeDivider.className = 'welcome-divider';
    welcomeSection.appendChild(welcomeDivider);

    const welcomeList = document.createElement('ul');
    welcomeList.className = 'welcome-list';
    welcomeItems.forEach(text => {
      const li = document.createElement('li');
      li.textContent = text;
      welcomeList.appendChild(li);
    });
    welcomeSection.appendChild(welcomeList);

    // Build individual announcement chunks: heading (sticky) + one wrap per item.
    // Each chunk carries annIdx (-1 for the heading, ≥0 for real items) so that
    // break controls can reference back to the source annData[] entry.
    const annChunks = [];
    if (hasAnn) {
      const annH = document.createElement('div');
      annH.className = 'ann-heading preview-linkable';
      annH.dataset.previewSection = 'announcements';
      annH.textContent = 'Announcements';
      annChunks.push({ el: annH, sticky: true, annIdx: -1 });

      annData.forEach((ann, ai) => {
        if (!ann.title.trim() && !ann.body.trim() && !ann.url?.trim()) return;
        const wrap = document.createElement('div');
        wrap.style.overflow = 'hidden'; // BFC: contains child margins for accurate measurement
        // QR code (if URL provided) — floated right so text wraps around it
        if (ann.url && ann.url.trim()) {
          const qrWrap = document.createElement('div');
          qrWrap.className = 'ann-qr-wrap';
          const qrImg = document.createElement('img');
          qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=68x68&data=${encodeURIComponent(ann.url.trim())}`;
          qrImg.alt = 'QR Code';
          qrImg.width = 68; qrImg.height = 68;
          qrWrap.appendChild(qrImg);
          wrap.appendChild(qrWrap);
        }
        if (ann.title.trim()) {
          const h = document.createElement('div');
          h.className = 'ann-item-heading';
          h.textContent = ann.title.trim();
          wrap.appendChild(h);
        }
        if (ann.body.trim()) {
          const b = document.createElement('div');
          b.className = 'ann-body';
          renderBodyText(b, ann.body, true);
          wrap.appendChild(b);
        }
        wrap.classList.add('preview-linkable');
        wrap.dataset.previewSection = 'announcements';
        wrap.dataset.previewAnnIdx  = ai;
        annChunks.push({ el: wrap, sticky: false, annIdx: ai });
      });
    }

    // Measure welcome section + all announcement chunks in a hidden booklet-page
    const annMeasurer = document.createElement('div');
    annMeasurer.className = 'booklet-page';
    annMeasurer.style.cssText = 'position:fixed;left:-9999px;top:0;min-height:0;visibility:hidden;pointer-events:none;';
    annMeasurer.appendChild(welcomeSection);
    annChunks.forEach(c => annMeasurer.appendChild(c.el));
    document.body.appendChild(annMeasurer);
    const welcomeH = welcomeSection.getBoundingClientRect().height;
    annChunks.forEach(c => { c.height = c.el.getBoundingClientRect().height; });
    document.body.removeChild(annMeasurer);

    // Pack announcement chunks onto pages.
    // Page 1 already has welcomeH consumed by the welcome section.
    // annPageBreakSources[i] explains why page (i+1) started — parallel to annPagesList.
    const annPagesList = [[]];
    const annPageBreakSources = []; // length = annPagesList.length - 1
    let annUsed = welcomeH;

    for (let i = 0; i < annChunks.length; i++) {
      const chunk = annChunks[i];
      const h = chunk.height;
      const ann = chunk.annIdx >= 0 ? annData[chunk.annIdx] : null;

      // Forced break: _breakBefore on this item forces a new page
      if (ann && ann._breakBefore && annPagesList[annPagesList.length - 1].length > 0) {
        annPagesList.push([]);
        annPageBreakSources.push({ type: 'ann-item', annIdx: chunk.annIdx });
        annUsed = 0;
      }
      // Auto break: overflow — suppressed when _noBreakBefore is set
      else if (!(ann && ann._noBreakBefore) &&
               annUsed + h > annAvailH &&
               annPagesList[annPagesList.length - 1].length > 0) {
        annPagesList.push([]);
        annPageBreakSources.push({ type: 'ann-auto', annIdx: chunk.annIdx });
        annUsed = 0;
      }

      // Sticky-to-next: keep "Announcements" heading with the first announcement
      if (chunk.sticky && i + 1 < annChunks.length) {
        const nextH = annChunks[i + 1].height;
        if (annUsed + h + nextH > annAvailH && annPagesList[annPagesList.length - 1].length > 0) {
          annPagesList.push([]);
          // No break source entry here — this is an implicit sticky break, not user-controlled
          annPageBreakSources.push({ type: 'ann-auto', annIdx: annChunks[i + 1].annIdx });
          annUsed = 0;
        }
      }

      annPagesList[annPagesList.length - 1].push(chunk);
      annUsed += h;
    }

    // Render each announcement page, injecting between-chunk split controls.
    const renderedAnnPageEls = [];
    annPagesList.forEach((pageChunks, pi) => {
      const pg = document.createElement('div');
      pg.className = 'booklet-page';
      if (pi === 0) pg.appendChild(welcomeSection); // welcome only on first page

      pageChunks.forEach((chunk, ci) => {
        // Inject a "Break here" split control between adjacent non-heading chunks.
        // Never between the heading (sticky) and its first item — that pairing is fixed.
        if (ci > 0) {
          const prev = pageChunks[ci - 1];
          if (prev.annIdx >= 0 && chunk.annIdx >= 0) {
            const ctrl = document.createElement('div');
            ctrl.className = 'pg-split-ctrl';
            ctrl.dataset.splitType    = 'ann';
            ctrl.dataset.annAfterIdx  = prev.annIdx;
            ctrl.dataset.annBeforeIdx = chunk.annIdx;
            const ll  = document.createElement('div'); ll.className = 'pg-split-line';
            const btn = document.createElement('button');
            btn.className   = 'pg-split-add-btn';
            btn.textContent = '⊞ Break here';
            const rl  = document.createElement('div'); rl.className = 'pg-split-line';
            ctrl.appendChild(ll); ctrl.appendChild(btn); ctrl.appendChild(rl);
            pg.appendChild(ctrl);
          }
        }
        pg.appendChild(chunk.el);
      });

      if (optFooter.checked) {
        const footer = document.createElement('div');
        footer.className = 'page-footer';
        footer.innerHTML = `<span>${esc(church)}</span><span>${esc(date)}</span>`;
        pg.appendChild(footer);
      }
      previewPane.appendChild(pg);
      renderedAnnPageEls.push(pg);
    });

    // Inject "Remove break" controls between adjacent announcement pages.
    addAnnBreakControls(renderedAnnPageEls, annPageBreakSources);

    // Track last rendered announcement page for bottom-page push-up calculation.
    if (renderedAnnPageEls.length > 0) {
      lastRenderedPageEl = renderedAnnPageEls[renderedAnnPageEls.length - 1];
      lastPageUsedH = annUsed;
    }
  }

  // ── Interior pages ────────────────────────────────────────────────────────────
  // Unified algorithm: works for both auto-packing and manual (page-break item)
  // mode.  forceBreak chunks always start a new page; noBreakBefore suppresses
  // the auto overflow-break before a specific chunk.
  if (items.length > 0) {
    // Available content height per CSS px (96 px/in).
    // Page height − 0.35in top pad − 0.45in bottom pad − optional 0.55in footer.
    const AVAIL_H = Math.round((getPageDims().h - 0.35 - 0.45 - (optFooter.checked ? 0.55 : 0)) * 96);
    const OOW_SEP_H = 16; // approximate height of the ann/OOW separator rule

    // Build all display chunks from items
    const allChunks = items.flatMap((item, idx) => buildChunks(item, idx));

    // Measure every non-forceBreak chunk off-screen inside a hidden booklet page.
    // BFC wrapper (overflow:hidden) ensures margins are included in the height.
    const measurer = document.createElement('div');
    measurer.className = 'booklet-page';
    measurer.style.cssText = 'position:fixed;left:-9999px;top:0;min-height:0;visibility:hidden;pointer-events:none;';
    document.body.appendChild(measurer);
    allChunks.forEach(chunk => {
      if (chunk.forceBreak) return;
      const wrap = document.createElement('div');
      wrap.style.overflow = 'hidden';
      chunk.els.forEach(el => wrap.appendChild(el));
      chunk._wrap = wrap;
      measurer.appendChild(wrap);
    });
    allChunks.forEach(chunk => {
      chunk.height = chunk.forceBreak ? 0 : chunk._wrap.getBoundingClientRect().height;
    });
    document.body.removeChild(measurer);

    // ── Ann→OOW merge logic (Features 2+3) ──────────────────────────────────
    // Capture the ann/OOW boundary state before packing modifies lastRenderedPageEl.
    const annLastPageEl   = lastRenderedPageEl;
    const annLastPageUsedH = lastPageUsedH;
    const doMergeOOW = bottomMerge.oow && annLastPageEl !== null;

    // Build the pg-break-ctrl for the ann/OOW boundary (visible only if ann pages exist).
    let oowBoundaryCtrl = null;
    if (annLastPageEl !== null) {
      oowBoundaryCtrl = document.createElement('div');
      oowBoundaryCtrl.className = 'pg-break-ctrl';
      oowBoundaryCtrl.dataset.breakType = doMergeOOW ? 'oow-merged' : 'oow-auto';
      const ll = document.createElement('div'); ll.className = 'pg-break-ctrl-line';
      const btn = document.createElement('button');
      btn.className = 'pg-break-remove-btn';
      btn.textContent = doMergeOOW ? '↓ Start worship on its own page' : '↑ Continue worship on announcements page';
      const rl = document.createElement('div'); rl.className = 'pg-break-ctrl-line';
      oowBoundaryCtrl.appendChild(ll); oowBoundaryCtrl.appendChild(btn); oowBoundaryCtrl.appendChild(rl);
    }

    // Pack chunks into pages.
    // pageBreakSources[i] explains why page (i+1) started — parallel array to pages[].
    const pages = [[]];
    const pageBreakSources = []; // length = pages.length - 1
    // When merging OOW onto the last ann page, start accounting from annLastPageUsedH + separator
    let used = doMergeOOW ? annLastPageUsedH + OOW_SEP_H : 0;

    for (let i = 0; i < allChunks.length; i++) {
      const chunk = allChunks[i];

      if (chunk.forceBreak) {
        // Forced break: always start a new page (even if current page is empty,
        // but only if the current page has content — otherwise skip it).
        if (pages[pages.length - 1].length > 0) {
          pages.push([]);
          let bsrc;
          if (chunk.breakItemIdx !== null) {
            bsrc = makeBreakSrc('item', { breakItemIdx: chunk.breakItemIdx });
          } else if (chunk.paragraphBreakItemIdx !== null) {
            bsrc = makeBreakSrc('liturgy-para', {
                     paragraphBreakItemIdx: chunk.paragraphBreakItemIdx,
                     paragraphBreakIdx:     chunk.paragraphBreakIdx });
          } else {
            bsrc = makeBreakSrc('separator', {
                     separatorItemIdx:   chunk.separatorItemIdx,
                     separatorStanzaIdx: chunk.separatorStanzaIdx });
          }
          pageBreakSources.push(bsrc);
          used = 0;
        }
        continue;
      }

      const h = chunk.height;

      // Auto break if the chunk would overflow AND noBreakBefore is not set.
      if (!chunk.noBreakBefore && used + h > AVAIL_H && pages[pages.length - 1].length > 0) {
        pages.push([]);
        pageBreakSources.push(makeBreakSrc('auto', {
          itemIdx: chunk.itemIdx,
          stanzaIdx: chunk.stanzaIdx,
          paragraphIdx: chunk.paragraphIdx,
        }));
        used = 0;
      }

      // Section headings: also check that the next non-forceBreak chunk fits.
      if (chunk.stickyToNext && i + 1 < allChunks.length) {
        const next = allChunks[i + 1];
        if (!next.forceBreak) {
          const nextH = next.height;
          if (used + h + nextH > AVAIL_H && pages[pages.length - 1].length > 0) {
            pages.push([]);
            pageBreakSources.push(makeBreakSrc('auto', {
              itemIdx: chunk.itemIdx,
              stanzaIdx: chunk.stanzaIdx,
              paragraphIdx: chunk.paragraphIdx,
            }));
            used = 0;
          }
        }
      }

      pages[pages.length - 1].push(chunk);
      used += h;
    }

    // Render each interior page, injecting between-chunk split controls.
    function appendInteriorPage(pg) {
      if (optFooter.checked) {
        const footer = document.createElement('div');
        footer.className = 'page-footer';
        footer.innerHTML = `<span>${esc(church)}</span><span>${esc(date)}</span>`;
        pg.appendChild(footer);
      }
      previewPane.appendChild(pg);
    }

    const renderedPageEls = [];
    pages.filter(p => p.length > 0).forEach((pageChunks, pi) => {
      const isFirstMerged = pi === 0 && doMergeOOW;
      let page;

      if (isFirstMerged) {
        // Re-use the last ann page — append a separator then OOW chunks into it.
        page = annLastPageEl;
        const sep = document.createElement('hr');
        sep.className = 'bottom-section-sep';
        page.appendChild(sep);
        // Place the boundary ctrl just before the separator so it's always visible.
        page.insertBefore(oowBoundaryCtrl, sep);
        oowBoundaryCtrl = null; // mark as consumed
      } else {
        page = document.createElement('div');
        page.className = 'booklet-page';
      }

      pageChunks.forEach((chunk, ci) => {
        // Inject a "Break here" control between adjacent chunks on the same page.
        if (ci > 0) {
          const prev = pageChunks[ci - 1];
          const ctrl = document.createElement('div');
          ctrl.className = 'pg-split-ctrl';
          applySplitCtrlMeta(ctrl, prev, chunk);
          const ll = document.createElement('div'); ll.className = 'pg-split-line';
          const btn = document.createElement('button');
          btn.className = 'pg-split-add-btn';
          btn.textContent = '⊞ Break here';
          const rl = document.createElement('div'); rl.className = 'pg-split-line';
          ctrl.appendChild(ll); ctrl.appendChild(btn); ctrl.appendChild(rl);
          page.appendChild(ctrl);
        }
        chunk.els.forEach(el => page.appendChild(el));
      });

      if (!isFirstMerged) appendInteriorPage(page);
      renderedPageEls.push(page);
    });

    // Insert ann/OOW boundary ctrl between last ann page and first OOW page
    // (only when NOT merging — in merge mode it was placed inside the page above).
    if (oowBoundaryCtrl && annLastPageEl && renderedPageEls.length > 0) {
      annLastPageEl.after(oowBoundaryCtrl);
    }

    // Inject "Remove break" controls between adjacent interior pages.
    addBreakControls(renderedPageEls, pageBreakSources);

    // Track last OOW page for bottom-page push-up calculation.
    if (renderedPageEls.length > 0) {
      lastRenderedPageEl = renderedPageEls[renderedPageEls.length - 1];
      lastPageUsedH = used;
    }
  }

  // ── Bottom pages (serving schedule, calendar, staff/contact) ────────────────
  // Each section is built as a bare content div (no booklet-page wrapper) so it
  // can optionally be merged onto the last rendered page when space allows.
  // appendBottomSection() handles the merge/split decision and inserts the
  // appropriate pg-break-ctrl between sections.

  // Helper: measure a content element off-screen and return its height.
  function measureBottomContent(contentEl) {
    const m = document.createElement('div');
    m.className = 'booklet-page';
    m.style.cssText = 'position:fixed;left:-9999px;top:0;min-height:0;visibility:hidden;pointer-events:none;';
    m.appendChild(contentEl);
    document.body.appendChild(m);
    const h = contentEl.getBoundingClientRect().height;
    document.body.removeChild(m);
    return h;
  }

  // Helper: append a bottom-section content element to either the last rendered
  // page (if merge is enabled and the content fits) or a new booklet-page.
  // Inserts a pg-break-ctrl so the user can toggle between merged / own-page.
  function appendBottomSection(contentEl, mergeKey) {
    const AVAIL_H  = Math.round((getPageDims().h - 0.35 - 0.45 - (optFooter.checked ? 0.55 : 0)) * 96);
    const contentH = measureBottomContent(contentEl);
    const fits     = lastRenderedPageEl !== null && (lastPageUsedH + contentH <= AVAIL_H);
    const doMerge  = bottomMerge[mergeKey] && fits;

    // Build the pg-break-ctrl that always appears to let the user toggle.
    const ctrl = document.createElement('div');
    ctrl.className = 'pg-break-ctrl';
    ctrl.dataset.breakType     = doMerge ? 'bottom-merged' : 'bottom-auto';
    ctrl.dataset.bottomSection = mergeKey;
    // Only show the "push up" option when content actually fits on the previous page.
    ctrl.dataset.fits = fits ? '1' : '0';
    const ll  = document.createElement('div'); ll.className = 'pg-break-ctrl-line';
    const btn = document.createElement('button');
    btn.className   = 'pg-break-remove-btn';
    btn.textContent = doMerge ? '↓ Move to own page' : '↑ Push up to previous page';
    if (!fits && !doMerge) btn.disabled = true; // grayed-out when it won't fit
    const rl  = document.createElement('div'); rl.className = 'pg-break-ctrl-line';
    ctrl.appendChild(ll); ctrl.appendChild(btn); ctrl.appendChild(rl);

    if (doMerge) {
      // Merged: add a thin separator rule then the content inside the existing page.
      const sep = document.createElement('hr');
      sep.className = 'bottom-section-sep';
      lastRenderedPageEl.appendChild(sep);
      lastRenderedPageEl.appendChild(contentEl);
      lastPageUsedH += contentH;
      // Place the ctrl INSIDE the page, just before the separator, so it's
      // always visible (not hidden behind pointer-events on .pg-split-ctrl).
      lastRenderedPageEl.insertBefore(ctrl, sep);
    } else {
      // Separate page: create a new booklet-page for this content.
      const pg = document.createElement('div');
      pg.className = 'booklet-page';
      pg.appendChild(contentEl);
      if (optFooter.checked) {
        const footer = document.createElement('div');
        footer.className = 'page-footer';
        footer.innerHTML = `<span>${esc(church)}</span><span>${esc(date)}</span>`;
        pg.appendChild(footer);
      }
      // Insert ctrl BETWEEN the pages in DOM order.
      if (lastRenderedPageEl) {
        lastRenderedPageEl.after(ctrl);
        ctrl.after(pg);
      } else {
        previewPane.appendChild(pg);
      }
      lastRenderedPageEl = pg;
      lastPageUsedH      = contentH;
    }
  }

  // ── Serving schedule ────────────────────────────────────────────────────────
  if (servingSchedule && optVolunteers.checked) {
    const srvChunks = buildServingChunks(servingSchedule, servingTeamFilter, volTeamFilter);

    // Pack chunks into pages[] using pre-resolved forceBreak flags.
    // pageSources[i] explains why serving page (i+1) started.
    const pages = [[]];
    const pageSources = [];
    srvChunks.forEach(chunk => {
      if (chunk.forceBreak && pages[pages.length - 1].length > 0) {
        const prevChunk = pages[pages.length - 1][pages[pages.length - 1].length - 1];
        if (prevChunk && prevChunk.servingWeekIdx === chunk.servingWeekIdx) {
          pageSources.push(makeBreakSrc('serving-team', {
            weekIdx: chunk.servingWeekIdx,
            teamBreakIdx: chunk.servingTeamBreakIdx,
          }));
        } else {
          pageSources.push(makeBreakSrc('serving-week', { weekIdx: chunk.servingWeekIdx }));
        }
        pages.push([]);
      }
      pages[pages.length - 1].push(chunk);
    });

    pages.forEach((pageChunks, pi) => {
      const servingContent = document.createElement('div');
      servingContent.classList.add('preview-linkable');
      applyPreviewLinkMeta(servingContent, { section: 'serving' });
      pageChunks.forEach((chunk, itemIdx) => {
        if (itemIdx > 0) {
          const prevChunk = pageChunks[itemIdx - 1];
          const ctrl = document.createElement('div');
          ctrl.className = 'pg-split-ctrl';
          const isSameWeek = prevChunk.servingWeekIdx === chunk.servingWeekIdx;
          const firstTeam = isSameWeek ? (chunk.servingSegTeams || []).find(t => t && t.type !== 'page-break') : null;
          const insertBeforeIdx = firstTeam ? (chunk.servingWeek.teams || []).indexOf(firstTeam) : -1;
          const srvSplitLabel = applyBreakCtrlMeta(ctrl, makeBreakSrc('serving-split', {
            weekIdx: chunk.servingWeekIdx,
            boundary: isSameWeek ? 'team' : 'week',
            insertBeforeIdx: isSameWeek ? insertBeforeIdx : '',
          }));
          const ll = document.createElement('div'); ll.className = 'pg-split-line';
          const btn = document.createElement('button');
          btn.className = 'pg-split-add-btn';
          btn.textContent = srvSplitLabel;
          const rl = document.createElement('div'); rl.className = 'pg-split-line';
          ctrl.appendChild(ll); ctrl.appendChild(btn); ctrl.appendChild(rl);
          servingContent.appendChild(ctrl);
        }
        renderServingWeek(servingContent, { ...chunk.servingWeek, teams: chunk.servingSegTeams }, chunk.servingLabel, chunk.servingWeekIdx);
        chunk.els = [servingContent];
      });
      if (pi === 0) {
        appendBottomSection(servingContent, 'serving');
      } else {
        // Continuation pages always get their own page (no merge toggle)
        const contentH = measureBottomContent(servingContent);
        const pg = document.createElement('div');
        pg.className = 'booklet-page';
        pg.appendChild(servingContent);
        if (optFooter.checked) {
          const footer = document.createElement('div');
          footer.className = 'page-footer';
          footer.innerHTML = `<span>${esc(church)}</span><span>${esc(date)}</span>`;
          pg.appendChild(footer);
        }
        if (lastRenderedPageEl) {
          const ctrl = document.createElement('div');
          ctrl.className = 'pg-break-ctrl';
          const src = pageSources[pi - 1] || makeBreakSrc('serving-team', {});
          const srvBrkLabel = applyBreakCtrlMeta(ctrl, src);
          const ll = document.createElement('div'); ll.className = 'pg-break-ctrl-line';
          const btn = document.createElement('button');
          btn.className = 'pg-break-remove-btn';
          btn.textContent = srvBrkLabel;
          const rl = document.createElement('div'); rl.className = 'pg-break-ctrl-line';
          ctrl.appendChild(ll); ctrl.appendChild(btn); ctrl.appendChild(rl);
          lastRenderedPageEl.after(ctrl);
          ctrl.after(pg);
        } else previewPane.appendChild(pg);
        lastRenderedPageEl = pg;
        lastPageUsedH = contentH;
      }
    });
  }

  // ── Calendar ────────────────────────────────────────────────────────────────
  if (optCal.checked) {
    const calChunks = buildCalendarChunks(church);
    calChunks.forEach((chunk, si) => {
      const calContent = document.createElement('div');
      calContent.classList.add('preview-linkable');
      applyPreviewLinkMeta(calContent, chunk);
      calContent.appendChild(chunk.els[0]);

      const forceNew = (si === 0 && breakBeforeCalendar) ||
                       (si > 0 && calBreakBeforeDates.includes(chunk.calDate));
      chunk.forceBreak = forceNew;

      if (forceNew) {
        const contentH = measureBottomContent(calContent);
        const pg = document.createElement('div');
        pg.className = 'booklet-page';
        pg.appendChild(calContent);
        if (optFooter.checked) {
          const footer = document.createElement('div');
          footer.className = 'page-footer';
          footer.innerHTML = `<span>${esc(church)}</span><span>${esc(date)}</span>`;
          pg.appendChild(footer);
        }
        if (lastRenderedPageEl) {
          const ctrl = document.createElement('div');
          ctrl.className = 'pg-break-ctrl';
          const calBrkLabel = applyBreakCtrlMeta(ctrl, makeBreakSrc(si === 0 ? 'cal-force' : 'cal-day', { calDayDate: chunk.calDate }));
          const ll = document.createElement('div'); ll.className = 'pg-break-ctrl-line';
          const btn = document.createElement('button');
          btn.className   = 'pg-break-remove-btn';
          btn.textContent = calBrkLabel;
          const rl = document.createElement('div'); rl.className = 'pg-break-ctrl-line';
          ctrl.appendChild(ll); ctrl.appendChild(btn); ctrl.appendChild(rl);
          lastRenderedPageEl.after(ctrl);
          ctrl.after(pg);
        } else {
          previewPane.appendChild(pg);
        }
        lastRenderedPageEl = pg;
        lastPageUsedH      = contentH;
      } else if (si === 0) {
        // First chunk: use appendBottomSection to control serving→calendar merge toggle
        appendBottomSection(calContent, 'calendar');
      } else {
        // Subsequent chunks without a forced break: continuation — fit onto current page
        // or overflow to a new page. No merge toggle (use the calendar editor's break buttons
        // to place explicit breaks between days).
        const AVAIL_H  = Math.round((getPageDims().h - 0.35 - 0.45 - (optFooter.checked ? 0.55 : 0)) * 96);
        const splitCtrl = document.createElement('div');
        splitCtrl.className = 'pg-split-ctrl';
        const calSplitLabel = applyBreakCtrlMeta(splitCtrl, makeBreakSrc('cal-split', { calDayDate: chunk.calDate }));
        const ll = document.createElement('div'); ll.className = 'pg-split-line';
        const btn = document.createElement('button');
        btn.className = 'pg-split-add-btn';
        btn.textContent = calSplitLabel;
        const rl = document.createElement('div'); rl.className = 'pg-split-line';
        splitCtrl.appendChild(ll); splitCtrl.appendChild(btn); splitCtrl.appendChild(rl);
        const contentH = measureBottomContent(calContent);
        if (lastRenderedPageEl !== null && lastPageUsedH + contentH <= AVAIL_H) {
          lastRenderedPageEl.appendChild(splitCtrl);
          lastRenderedPageEl.appendChild(calContent);
          lastPageUsedH += contentH;
        } else {
          const pg = document.createElement('div');
          pg.className = 'booklet-page';
          pg.appendChild(calContent);
          if (optFooter.checked) {
            const footer = document.createElement('div');
            footer.className = 'page-footer';
            footer.innerHTML = `<span>${esc(church)}</span><span>${esc(date)}</span>`;
            pg.appendChild(footer);
          }
          if (lastRenderedPageEl) lastRenderedPageEl.after(pg);
          else previewPane.appendChild(pg);
          lastRenderedPageEl = pg;
          lastPageUsedH      = contentH;
        }
      }
    });
  }

  // ── Staff / Contact ─────────────────────────────────────────────────────────
  if (optStaff.checked) {
    const staffContent = document.createElement('div');

    const content = document.createElement('div');
    content.className = 'staff-page-content';

    const sLabel = document.createElement('div');
    sLabel.className = 'staff-section-label';
    sLabel.textContent = 'Church Staff & Contact';
    content.appendChild(sLabel);

    const topRule = document.createElement('div');
    topRule.className = 'staff-top-rule';
    content.appendChild(topRule);

    const table = document.createElement('table');
    table.className = 'staff-table';
    staffData.forEach(({ name, role, email }) => {
      const tr = document.createElement('tr');
      const tdName = document.createElement('td');
      tdName.className = 'sname';
      tdName.textContent = name;
      const tdRole = document.createElement('td');
      tdRole.className = 'srole';
      tdRole.textContent = role;
      const tdEmail = document.createElement('td');
      tdEmail.className = 'semail';
      tdEmail.textContent = email;
      tr.appendChild(tdName);
      tr.appendChild(tdRole);
      tr.appendChild(tdEmail);
      table.appendChild(tr);
    });
    content.appendChild(table);
    // Staff flex container: fills the page's inner content height so the QR
    // gap (flex:1) dynamically centers itself between the staff table and logo
    // regardless of how many staff rows there are or how tall the logo is.
    const hasGive = !!(giveOnlineUrl && giveOnlineUrl.trim());
    const footerAdj = optFooter.checked ? 0.55 : 0;
    const innerH    = (getPageDims().h - 0.35 - 0.45 - footerAdj).toFixed(3);
    staffContent.className   = 'staff-flex-wrap preview-linkable';
    staffContent.dataset.previewSection = 'staff';
    staffContent.style.height = innerH + 'in';

    staffContent.appendChild(content);

    // Middle gap — QR centers within whatever space is left between the staff
    // table and the logo, growing or shrinking as the content changes.
    const giveFlexDiv = document.createElement('div');
    giveFlexDiv.className = 'staff-give-flex';

    if (hasGive) {
      const giveWrap = document.createElement('div');
      giveWrap.className = 'staff-give-online';
      const giveQrWrap = document.createElement('div');
      giveQrWrap.className = 'staff-give-qr';
      const giveQrImg = document.createElement('img');
      giveQrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=68x68&data=${encodeURIComponent(giveOnlineUrl.trim())}`;
      giveQrImg.alt = 'Give Online QR';
      giveQrImg.width = 68; giveQrImg.height = 68;
      giveQrWrap.appendChild(giveQrImg);
      const giveLabel = document.createElement('div');
      giveLabel.className = 'staff-give-label';
      giveLabel.textContent = 'Give Online';
      giveWrap.appendChild(giveQrWrap);
      giveWrap.appendChild(giveLabel);
      giveFlexDiv.appendChild(giveWrap);
    }
    staffContent.appendChild(giveFlexDiv);

    // Logo section — always anchored at the bottom of the flex container
    const logoSection = document.createElement('div');
    logoSection.className = 'staff-logo-section';
    if (staffLogoUrl) {
      const logoWrap = document.createElement('div');
      logoWrap.className = 'staff-logo-wrap';
      const logoImg = document.createElement('img');
      logoImg.src = staffLogoUrl;
      logoImg.alt = church || 'Church Logo';
      logoWrap.appendChild(logoImg);
      logoSection.appendChild(logoWrap);
    }
    staffContent.appendChild(logoSection);

    if (breakBeforeStaff) {
      const pg = document.createElement('div');
      pg.className = 'booklet-page';
      pg.appendChild(staffContent);
      if (optFooter.checked) {
        const footer = document.createElement('div');
        footer.className = 'page-footer';
        footer.innerHTML = `<span>${esc(church)}</span><span>${esc(date)}</span>`;
        pg.appendChild(footer);
      }
      if (lastRenderedPageEl) {
        const ctrl = document.createElement('div');
        ctrl.className = 'pg-break-ctrl';
        ctrl.dataset.breakType = 'staff-force';
        const ll = document.createElement('div'); ll.className = 'pg-break-ctrl-line';
        const btn = document.createElement('button');
        btn.className   = 'pg-break-remove-btn';
        btn.textContent = '✕ Remove "start on new page"';
        const rl = document.createElement('div'); rl.className = 'pg-break-ctrl-line';
        ctrl.appendChild(ll); ctrl.appendChild(btn); ctrl.appendChild(rl);
        lastRenderedPageEl.after(ctrl);
        ctrl.after(pg);
      } else {
        previewPane.appendChild(pg);
      }
      lastRenderedPageEl = pg;
      lastPageUsedH      = measureBottomContent(staffContent);
    } else {
      appendBottomSection(staffContent, 'staff');
    }
  }

  // ── Booklet size targeting: pad with blank pages or warn if over target ─────
  const bookletTarget = parseInt(optBookletSize.value, 10);
  if (!isNaN(bookletTarget)) {
    const currentCount = previewPane.querySelectorAll('.booklet-page').length;
    if (currentCount < bookletTarget) {
      // Pad with blank pages so the booklet folds to the correct page count
      for (let p = currentCount; p < bookletTarget; p++) {
        const blank = document.createElement('div');
        blank.className = 'booklet-page booklet-page-blank';
        const lbl = document.createElement('div');
        lbl.className = 'blank-page-label';
        lbl.textContent = 'this page intentionally left blank';
        blank.appendChild(lbl);
        previewPane.appendChild(blank);
      }
    }
    // Over-target is handled in the page-count display below (no pages removed)
  }

  // ── Screen-only page numbers (hidden in print) ────────────────────────────
  const allPages = previewPane.querySelectorAll('.booklet-page');
  const totalPages = allPages.length;
  allPages.forEach((page, i) => {
    const num = document.createElement('div');
    num.className = 'preview-page-num';
    num.textContent = `Page ${i + 1} of ${totalPages}`;
    page.appendChild(num);
  });

  // ── Page count display (above Print button) ───────────────────────────────
  if (pageCountDisplay) {
    if (totalPages === 0) {
      pageCountDisplay.textContent = '';
      pageCountDisplay.className = '';
    } else if (isNaN(bookletTarget)) {
      // Auto mode — just show count
      pageCountDisplay.textContent = `${totalPages} page${totalPages === 1 ? '' : 's'}`;
      pageCountDisplay.className = '';
    } else if (totalPages <= bookletTarget) {
      pageCountDisplay.textContent = `${totalPages} of ${bookletTarget} pages`;
      pageCountDisplay.className = '';
    } else {
      const over = totalPages - bookletTarget;
      pageCountDisplay.textContent =
        `⚠ ${totalPages} pages — ${over} page${over === 1 ? '' : 's'} over ${bookletTarget}-page target`;
      pageCountDisplay.className = 'over-target';
    }
  }

  updatePrintBtn();

  // Restore scroll position after DOM rebuild.
  // Use requestAnimationFrame so any browser-initiated focus-scroll correction
  // (triggered by removing a focused element) has already run before we override it.
  if (_savedScroll > 0) {
    requestAnimationFrame(() => { previewPane.scrollTop = _savedScroll; });
  }
}

function updatePrintBtn() {
  btnPrint.disabled = previewPane.querySelectorAll('.booklet-page').length === 0;
}

// ─── Break controls ────────────────────────────────────────────────────────────
// Inserts "Remove break" divs between adjacent interior pages in the previewPane.
// renderedPageEls: the booklet-page DOM elements for just the interior pages.
// pageBreakSources: array (length = renderedPageEls.length - 1) describing each break.
function addBreakControls(renderedPageEls, pageBreakSources) {
  pageBreakSources.forEach((src, i) => {
    const afterPage = renderedPageEls[i];
    const ctrl = document.createElement('div');
    ctrl.className = 'pg-break-ctrl';
    const label = applyBreakCtrlMeta(ctrl, src);
    const ll  = document.createElement('div'); ll.className  = 'pg-break-ctrl-line';
    const btn = document.createElement('button');
    btn.className   = 'pg-break-remove-btn';
    btn.textContent = label;
    const rl  = document.createElement('div'); rl.className  = 'pg-break-ctrl-line';
    ctrl.appendChild(ll); ctrl.appendChild(btn); ctrl.appendChild(rl);
    afterPage.after(ctrl);
  });
}

// ─── Announcement break controls ───────────────────────────────────────────────
// Inserts "Remove break" divs between adjacent announcement pages.
// Same structure as addBreakControls() but for ann-item and ann-auto break types.
function addAnnBreakControls(renderedAnnPageEls, annPageBreakSources) {
  annPageBreakSources.forEach((src, i) => {
    const afterPage = renderedAnnPageEls[i];
    const ctrl = document.createElement('div');
    ctrl.className = 'pg-break-ctrl';
    const label = applyBreakCtrlMeta(ctrl, src);
    const ll  = document.createElement('div'); ll.className  = 'pg-break-ctrl-line';
    const btn = document.createElement('button');
    btn.className   = 'pg-break-remove-btn';
    btn.textContent = label;
    const rl  = document.createElement('div'); rl.className  = 'pg-break-ctrl-line';
    ctrl.appendChild(ll); ctrl.appendChild(btn); ctrl.appendChild(rl);
    afterPage.after(ctrl);
  });
}

btnPrint.addEventListener('click', async () => {
  const pagesHtml = [...previewPane.querySelectorAll('.booklet-page')]
    .map(el => el.outerHTML).join('\n');
  if (!pagesHtml) { setStatus('Nothing to print.', 'error'); return; }
  const title   = (svcTitle.value.trim() || svcDate.value || 'Bulletin');
  const sizeTag = (activeDocTemplate.pageSize || '5.5x8.5');
  await generateAndDownloadPdf(pagesHtml, title + ' - ' + sizeTag + '.pdf');
});

previewPane.addEventListener('click', e => {
  const targetEl = e.target instanceof Element ? e.target : null;
  if (!targetEl) return;

  // ── "Remove break" button (between pages) ──────────────────────────────────
  if (targetEl.classList.contains('pg-break-remove-btn')) {
    const ctrl = targetEl.closest('.pg-break-ctrl');
    if (!ctrl) return;
    const type = ctrl.dataset.breakType;

    if (type === 'item') {
      // Remove the {type:'page-break'} item from items[]
      const idx = parseInt(ctrl.dataset.breakItemIdx, 10);
      if (Number.isInteger(idx) && items[idx]?.type === 'page-break') {
        items.splice(idx, 1);
        renderItemList();
        schedulePreviewUpdate();
        autosaveProjectState(); // flush immediately
      }
    } else if (type === 'separator') {
      // Remove the --- separator from the song's detail text
      const itemIdx   = parseInt(ctrl.dataset.separatorItemIdx, 10);
      const stanzaIdx = parseInt(ctrl.dataset.separatorStanzaIdx, 10);
      if (Number.isInteger(itemIdx) && items[itemIdx]) {
        items[itemIdx].detail = removeSongSeparatorBefore(items[itemIdx].detail, stanzaIdx);
        renderItemList();
        schedulePreviewUpdate();
      }
    } else if (type === 'ann-item') {
      // Remove user-added forced break before this announcement
      const idx = parseInt(ctrl.dataset.annIdx, 10);
      if (Number.isInteger(idx) && annData[idx]) {
        annData[idx]._breakBefore = false;
        schedulePreviewUpdate();
      }
    } else if (type === 'ann-auto') {
      // Suppress auto-break before this announcement
      const idx = parseInt(ctrl.dataset.annIdx, 10);
      if (Number.isInteger(idx) && annData[idx]) {
        annData[idx]._noBreakBefore = true;
        schedulePreviewUpdate();
      }
    } else if (type === 'oow-auto') {
      // Merge the Order of Worship onto the last announcements page
      bottomMerge.oow = true;
      schedulePreviewUpdate();
    } else if (type === 'oow-merged') {
      // Move OOW back to its own page
      bottomMerge.oow = false;
      schedulePreviewUpdate();
    } else if (type === 'bottom-auto') {
      // Merge the bottom section onto the previous page (if it fits)
      const section = ctrl.dataset.bottomSection;
      if (ctrl.dataset.fits === '1') {
        bottomMerge[section] = true;
        schedulePreviewUpdate();
      }
    } else if (type === 'bottom-merged') {
      // Move the bottom section back to its own page
      const section = ctrl.dataset.bottomSection;
      bottomMerge[section] = false;
      schedulePreviewUpdate();
    } else if (type === 'liturgy-para') {
      const itemIdx = parseInt(ctrl.dataset.paragraphBreakItemIdx, 10);
      const paraIdx = parseInt(ctrl.dataset.paragraphBreakIdx, 10);
      if (items[itemIdx]) {
        items[itemIdx]._forceBreakBeforeParagraph =
          (items[itemIdx]._forceBreakBeforeParagraph || []).filter(p => p !== paraIdx);
        schedulePreviewUpdate();
        scheduleProjectPersist();
      }
    } else if (type === 'staff-force') {
      breakBeforeStaff = false;
      schedulePreviewUpdate();
      scheduleProjectPersist();
    } else if (type === 'serving-week') {
      const weekIdx = parseInt(ctrl.dataset.servingWeekIdx, 10);
      if (Number.isInteger(weekIdx) && servingSchedule?.weeks?.[weekIdx]) {
        delete servingSchedule.weeks[weekIdx]._breakBefore;
        schedulePreviewUpdate();
        scheduleProjectPersist();
      }
    } else if (type === 'serving-team') {
      const weekIdx = parseInt(ctrl.dataset.servingWeekIdx, 10);
      const teamBreakIdx = parseInt(ctrl.dataset.servingTeamBreakIdx, 10);
      if (Number.isInteger(weekIdx) && Number.isInteger(teamBreakIdx) && servingSchedule?.weeks?.[weekIdx]?.teams?.[teamBreakIdx]?.type === 'page-break') {
        servingSchedule.weeks[weekIdx].teams.splice(teamBreakIdx, 1);
        schedulePreviewUpdate();
        scheduleProjectPersist();
      }
    } else if (type === 'cal-force') {
      breakBeforeCalendar = false;
      schedulePreviewUpdate();
      scheduleProjectPersist();
    } else if (type === 'cal-day') {
      const d = ctrl.dataset.calDayDate;
      if (d) {
        calBreakBeforeDates = calBreakBeforeDates.filter(x => x !== d);
        schedulePreviewUpdate();
        scheduleProjectPersist();
      }
    } else {
      // Auto break (OOW): suppress it by setting a noBreakBefore flag on the item/stanza/paragraph
      const itemIdx      = parseInt(ctrl.dataset.breakItemIdx, 10);
      const stanzaIdxStr = ctrl.dataset.breakStanzaIdx;
      const paraStr      = ctrl.dataset.breakParagraphIdx;
      if (!Number.isInteger(itemIdx) || !items[itemIdx]) return;
      if (paraStr !== undefined && paraStr !== '' && parseInt(paraStr, 10) > 0) {
        // Paragraph-level (pi > 0): suppress auto-break before this paragraph.
        // pi === 0 falls through to the item-level path below because buildChunks
        // uses item._noBreakBefore (not _noBreakBeforeParagraph) for the first paragraph.
        const paraIdx = parseInt(paraStr, 10);
        const arr = Array.isArray(items[itemIdx]._noBreakBeforeParagraph)
          ? [...items[itemIdx]._noBreakBeforeParagraph] : [];
        if (!arr.includes(paraIdx)) arr.push(paraIdx);
        items[itemIdx]._noBreakBeforeParagraph = arr;
        schedulePreviewUpdate();
        scheduleProjectPersist();
      } else if (stanzaIdxStr && stanzaIdxStr !== '') {
        // Stanza-level: suppress auto-break before this specific stanza
        const stanzaIdx = parseInt(stanzaIdxStr, 10);
        if (!Array.isArray(items[itemIdx]._noBreakBeforeStanzas))
          items[itemIdx]._noBreakBeforeStanzas = [];
        if (!items[itemIdx]._noBreakBeforeStanzas.includes(stanzaIdx))
          items[itemIdx]._noBreakBeforeStanzas.push(stanzaIdx);
        schedulePreviewUpdate();
      } else {
        // Item-level: suppress auto-break before the whole item
        items[itemIdx]._noBreakBefore = true;
        schedulePreviewUpdate();
      }
    }
    return;
  }

  // ── "Break here" button (between chunks within a page) ─────────────────────
  if (targetEl.classList.contains('pg-split-add-btn')) {
    const ctrl = targetEl.closest('.pg-split-ctrl');
    if (!ctrl) return;

    // Announcement split: set _breakBefore on the "before" item
    if (ctrl.dataset.splitType === 'ann') {
      const beforeIdx = parseInt(ctrl.dataset.annBeforeIdx, 10);
      if (Number.isInteger(beforeIdx) && annData[beforeIdx]) {
        annData[beforeIdx]._breakBefore = true;
        schedulePreviewUpdate();
      }
      return;
    }

    if (ctrl.dataset.breakType === 'cal-split') {
      const d = ctrl.dataset.calDayDate;
      if (d && !calBreakBeforeDates.includes(d)) {
        calBreakBeforeDates.push(d);
        schedulePreviewUpdate();
        scheduleProjectPersist();
      }
      return;
    }

    if (ctrl.dataset.breakType === 'serving-split') {
      const weekIdx = parseInt(ctrl.dataset.servingWeekIdx, 10);
      if (!Number.isInteger(weekIdx) || !servingSchedule?.weeks?.[weekIdx]) return;
      if (ctrl.dataset.servingBoundary === 'week') {
        servingSchedule.weeks[weekIdx]._breakBefore = true;
      } else {
        const insertBeforeIdx = parseInt(ctrl.dataset.servingInsertBeforeIdx, 10);
        if (!Number.isInteger(insertBeforeIdx) || insertBeforeIdx < 0) return;
        if (servingSchedule.weeks[weekIdx].teams[insertBeforeIdx - 1]?.type === 'page-break') return;
        servingSchedule.weeks[weekIdx].teams.splice(insertBeforeIdx, 0, { type: 'page-break' });
      }
      schedulePreviewUpdate();
      scheduleProjectPersist();
      return;
    }

    // OOW split
    const afterItemIdx    = parseInt(ctrl.dataset.splitAfterItemIdx, 10);
    const beforeItemIdx   = parseInt(ctrl.dataset.splitBeforeItemIdx, 10);
    const afterStanzaStr  = ctrl.dataset.splitAfterStanzaIdx;

    if (afterItemIdx === beforeItemIdx) {
      const beforeParagraphStr = ctrl.dataset.splitBeforeParagraphIdx;
      if (beforeParagraphStr !== undefined && beforeParagraphStr !== '') {
        const paraIdx = parseInt(beforeParagraphStr, 10);
        if (items[beforeItemIdx]) {
          const arr = Array.isArray(items[beforeItemIdx]._forceBreakBeforeParagraph)
            ? [...items[beforeItemIdx]._forceBreakBeforeParagraph] : [];
          if (!arr.includes(paraIdx)) arr.push(paraIdx);
          items[beforeItemIdx]._forceBreakBeforeParagraph = arr;
          schedulePreviewUpdate();
          scheduleProjectPersist();
        }
      } else {
        // Same item (song) — insert a --- separator after the stanza
        const afterStanzaIdx = parseInt(afterStanzaStr, 10);
        if (items[afterItemIdx]) {
          items[afterItemIdx].detail = insertSongSeparatorAfter(items[afterItemIdx].detail, afterStanzaIdx);
          renderItemList();
          schedulePreviewUpdate();
        }
      }
    } else {
      // Different items — insert a {type:'page-break'} item right after afterItemIdx
      items.splice(afterItemIdx + 1, 0, { type: 'page-break', title: '', detail: '' });
      renderItemList();
      schedulePreviewUpdate();
      autosaveProjectState(); // flush immediately
    }
    return;
  }

  // ── Click on a section-linked preview element → scroll editor to panel section
  const sectionLinked = targetEl.closest('[data-preview-section]');
  if (sectionLinked) {
    scrollEditorToSection('panel-section-' + sectionLinked.dataset.previewSection);
    return;
  }

  // ── Click on a preview item → scroll editor to it ──────────────────────────
  const linked = targetEl.closest('[data-preview-idx]');
  if (!linked) return;
  const idx = parseInt(linked.dataset.previewIdx, 10);
  if (!Number.isInteger(idx)) return;
  scrollEditorToItem(idx, 'smooth');
  suppressLinkedFocusSync = true;
  setTimeout(() => { suppressLinkedFocusSync = false; }, 200);
});
