function applyCoverImage(url, label) {
  coverImageUrl = url || null;
  coverImgInput.value = '';
  if (coverImageUrl) {
    coverImgThumb.src = coverImageUrl;
    coverImgName.textContent = label || '(saved image)';
    coverImgLabel.textContent = '\u2713 Image selected';
    coverImgZone.classList.add('has-image');
    coverImgPreviewWrap.style.display = 'flex';
  } else {
    coverImgThumb.src = '';
    coverImgName.textContent = '';
    coverImgLabel.textContent = 'Click to select an image';
    coverImgZone.classList.remove('has-image');
    coverImgPreviewWrap.style.display = 'none';
  }
  renderPreview();
  updateSectionPreviews();
  if (!applyingProjectState) scheduleProjectPersist();
}

function applyStaffLogo(url, label) {
  staffLogoUrl = url || null;
  logoImgInput.value = '';
  if (staffLogoUrl) {
    apiFetch('/api/settings', 'POST', { staffLogo: staffLogoUrl }).catch(() => {});
    logoImgThumb.src = staffLogoUrl;
    logoImgName.textContent = label || '(saved logo)';
    logoImgLabel.textContent = '\u2713 Logo selected';
    logoImgZone.classList.add('has-image');
    logoImgPreviewWrap.style.display = 'flex';
  } else {
    apiFetch('/api/settings', 'POST', { staffLogo: null }).catch(() => {});
    logoImgThumb.src = '';
    logoImgName.textContent = '';
    logoImgLabel.textContent = 'Click to upload church logo';
    logoImgZone.classList.remove('has-image');
    logoImgPreviewWrap.style.display = 'none';
  }
  renderPreview();
  if (!applyingProjectState) scheduleProjectPersist();
}

function restoreDefaultStaffLogo() {
  if (_serverSettings.staffLogo) {
    applyStaffLogo(_serverSettings.staffLogo, '(saved logo)');
  }
}

function restoreGiveOnlineUrl() {
  const saved = _serverSettings.giveOnlineUrl || '';
  if (saved) { giveOnlineUrl = saved; giveOnlineUrlInput.value = saved; }
}

function restoreEditorIdentity() {
  if (isServerMode()) {
    try {
      const local = localStorage.getItem('editorDisplayName');
      if (local) _editorDisplayName = local;
    } catch (_) {}
  }
  if (_editorDisplayName) editorDisplayNameInput.value = _editorDisplayName;
  applyIdentitySectionVisibility();
}

// ─── Cover image ──────────────────────────────────────────────────────────────
coverImgZone.addEventListener('click', () => coverImgInput.click());
coverImgZone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') coverImgInput.click(); });
coverImgInput.addEventListener('change', () => {
  const file = coverImgInput.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => applyCoverImage(e.target.result, file.name);
  reader.readAsDataURL(file);
});
coverImgClear.addEventListener('click', () => applyCoverImage(null, ''));

// ─── Church logo (staff page) ─────────────────────────────────────────────────
logoImgZone.addEventListener('click', () => logoImgInput.click());
logoImgZone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') logoImgInput.click(); });
logoImgInput.addEventListener('change', () => {
  const file = logoImgInput.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => applyStaffLogo(e.target.result, file.name);
  reader.readAsDataURL(file);
});
logoImgClear.addEventListener('click', () => applyStaffLogo(null, ''));

// ─── Church Name (Settings → Church Branding) ─────────────────────────────────
function restoreChurchName() {
  const saved = _serverSettings.churchName || '';
  if (saved) svcChurch.value = saved;
}
svcChurch.addEventListener('input', () => {
  apiFetch('/api/settings', 'POST', { churchName: svcChurch.value }).catch(() => {});
  schedulePreviewUpdate();
});

// ─── Give Online URL (Feature 7) ──────────────────────────────────────────────
giveOnlineUrlInput.addEventListener('input', () => {
  giveOnlineUrl = giveOnlineUrlInput.value;
  apiFetch('/api/settings', 'POST', { giveOnlineUrl }).catch(() => {});
  schedulePreviewUpdate();
});

// ─── Editor identity (server mode) ───────────────────────────────────────────
const editorDisplayNameInput = document.getElementById('editor-display-name-input');
// Hide identity section in desktop mode (will be applied after bootstrap loads)
function applyIdentitySectionVisibility() {
  document.getElementById('stg-identity-group').style.display = isServerMode() ? '' : 'none';
}
editorDisplayNameInput.addEventListener('input', () => {
  _editorDisplayName = editorDisplayNameInput.value.trim();
  if (isServerMode()) {
    try { localStorage.setItem('editorDisplayName', _editorDisplayName); } catch (_) {}
  } else {
    apiFetch('/api/settings', 'POST', { editorDisplayName: _editorDisplayName }).catch(() => {});
  }
});

// ─── PDF text extraction ──────────────────────────────────────────────────────
// ─── PDF parser removed — import now via PCO API only ─────────────────────────
// (extractPdfText / parsePcoText removed)

// PDF import removed — stub retained so any stale call fails gracefully
async function extractPdfText(file) {
  throw new Error('PDF import has been removed. Use Planning Center import.');
}

// ─── Item list UI ─────────────────────────────────────────────────────────────
function renderItemList() {
  // Saves aside scroll pos so deleting/inserting items doesn't jump the editor back to the top.
  const _listScroll = itemList.parentElement ? itemList.parentElement.scrollTop : 0;
  // Proactively blur any focused element inside itemList so the browser
  // doesn't fire a "scroll focused element into view" correction after
  // we wipe the DOM.
  if (document.activeElement && itemList.contains(document.activeElement)) {
    document.activeElement.blur();
  }
  itemList.innerHTML = '';
  items.forEach((item, idx) => {
    // ── Inline insert-break zone before each card ──────────────────────────
    const zone = document.createElement('div');
    zone.className = 'item-insert-zone';
    const zoneBtn = document.createElement('button');
    zoneBtn.className = 'item-insert-break-btn';
    zoneBtn.dataset.action = 'insert-break-before';
    zoneBtn.dataset.insertBefore = idx;
    zoneBtn.title = 'Insert page break before this item';
    zoneBtn.textContent = '⊞ Insert page break here';
    zone.appendChild(zoneBtn);
    itemList.appendChild(zone);

    const card = document.createElement('div');
    card.dataset.idx = idx;

    // ── Page-break: compact dashed divider card ──────────────────────────────
    if (item.type === 'page-break') {
      card.className = 'item-card is-break-card';
      card.innerHTML = `
        <div class="item-card-header">
          <button class="icon-btn" data-action="up"   title="Move up">&#8593;</button>
          <span class="break-card-label">── Page Break ──</span>
          <button class="icon-btn" data-action="down" title="Move down">&#8595;</button>
          <button class="icon-btn danger" data-action="delete" title="Remove page break">&#215;</button>
        </div>
      `;
      itemList.appendChild(card);
      return;
    }

    // ── Normal item card ─────────────────────────────────────────────────────
    const isSection    = item.type === 'section';
    const isSongType   = item.type === 'song';
    const isHiddenType = ['note', 'media'].includes(item.type);
    const isLabelType  = item.type === 'label';
    const collapsed    = !!item._collapsed;
    const detailPlaceholder =
      isSection    ? 'Optional subtitle' :
      isSongType   ? 'Lyrics — paste verses, label sections (Verse 1, Chorus, etc.), copyright on last line' :
      item.type === 'liturgy' ? 'Text — line breaks preserved' :
      'Leave blank for title-only display, or add a subtitle/note';
    card.className = `item-card${isSection ? ' is-section-card' : ''}${isHiddenType ? ' is-hidden-card' : ''}${isLabelType ? ' is-label-card' : ''}${collapsed ? ' item-collapsed' : ''}`;
    // Title goes in header (visible when collapsed); type select goes below header
    card.innerHTML = `
      <div class="item-card-header">
        <button class="item-collapse-btn" data-action="collapse" title="${collapsed ? 'Expand' : 'Collapse'}">&#9660;</button>
        <input class="item-title-input" type="text"
               placeholder="${isSection ? 'Section name (e.g. GATHERING)' : 'Item heading…'}"
               value="${escAttr(item.title)}" />
        <button class="icon-btn" data-action="up"     title="Move up">&#8593;</button>
        <button class="icon-btn" data-action="down"   title="Move down">&#8595;</button>
        ${isSongType ? `<button class="icon-btn" data-action="db-lookup" title="Populate from Song Database">&#9835;</button>` : ''}
        ${isSongType ? `<button class="icon-btn" data-action="db-save" title="Save / Override Song in Database">&#128190;</button>` : ''}
        <button class="icon-btn danger" data-action="delete" title="Remove">&#215;</button>
      </div>
      <select class="item-type-select">${typeSelectHTML(item.type)}</select>
      ${isHiddenType ? `<span class="hidden-type-badge">hidden from print</span>` : ''}
      <textarea class="item-detail-input"
                placeholder="${escAttr(detailPlaceholder)}"
                rows="2">${escAttr(item.detail)}</textarea>
    `;
    itemList.appendChild(card);
    // Auto-size the detail textarea to its content
    const ta = card.querySelector('.item-detail-input');
    if (ta) {
      autoResize(ta);
      // Track last selection so toolbar buttons can restore it after focus moves
      const saveSelection = () => {
        ta._savedSel = { start: ta.selectionStart, end: ta.selectionEnd };
      };
      ta.addEventListener('select', saveSelection);
      ta.addEventListener('mouseup', saveSelection);
      ta.addEventListener('keyup', saveSelection);
    }
    // Append per-item formatting toolbar (not for break cards or section cards — still show for section)
    card.appendChild(buildItemFmtToolbar(item, idx));
  });
  updatePrintBtn();
  updateSectionPreviews();
  // Restore scroll position — do it in the next frame so the DOM has
  // finished painting and any browser focus-scroll correction has settled.
  if (_listScroll > 0 && itemList.parentElement) {
    requestAnimationFrame(() => { itemList.parentElement.scrollTop = _listScroll; });
  }
}

// Event delegation
itemList.addEventListener('click', e => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  // ── Insert page break between items (btn is outside any .item-card) ─────
  if (btn.dataset.action === 'insert-break-before') {
    const insertBefore = parseInt(btn.dataset.insertBefore, 10);
    syncAllItems();
    items.splice(insertBefore, 0, { type: 'page-break', title: '', detail: '' });
    renderItemList();
    schedulePreviewUpdate();
    autosaveProjectState(); // flush immediately — don't wait for the 350ms debounce
    return;
  }
  const card = btn.closest('.item-card');
  if (!card) return;
  const idx  = parseInt(card.dataset.idx, 10);
  if (btn.dataset.action === 'collapse') {
    const expanding = !!items[idx]._collapsed;
    if (expanding) {
      // Collapse all others when expanding this one
      items.forEach((item, i) => { if (i !== idx) item._collapsed = true; });
    }
    items[idx]._collapsed = !items[idx]._collapsed;
    renderItemList();
    return;
  }
  syncItemFromCard(card, idx);
  if (btn.dataset.action === 'up' && idx > 0) {
    [items[idx - 1], items[idx]] = [items[idx], items[idx - 1]];
  } else if (btn.dataset.action === 'down' && idx < items.length - 1) {
    [items[idx], items[idx + 1]] = [items[idx + 1], items[idx]];
  } else if (btn.dataset.action === 'delete') {
    items.splice(idx, 1);
  } else if (btn.dataset.action === 'db-lookup') {
    const match = findSongInDb(items[idx].title);
    if (match) {
      const parts = [];
      if (match.lyrics) parts.push(match.lyrics);
      if (match.copyright) parts.push(match.copyright);
      items[idx].detail = parts.join('\n\n');
    } else {
      alert(`No match found for "${items[idx].title}" in the Song Database.`);
    }
  } else if (btn.dataset.action === 'db-save') {
    upsertSongFromItem(idx);
  }
  renderItemList();
  schedulePreviewUpdate();
  // For structural changes (reorder, delete) flush the save immediately so
  // page-break positions are never lost if the user reloads shortly after.
  if (['up', 'down', 'delete'].includes(btn.dataset.action)) {
    autosaveProjectState();
  }
});

itemList.addEventListener('input', e => {
  if (e.target.classList.contains('item-detail-input')) autoResize(e.target);
  const card = e.target.closest('.item-card');
  if (!card) return;
  const idx = parseInt(card.dataset.idx, 10);
  syncItemFromCard(card, idx);
  // Update section/hidden card styling and placeholders if type changed
  if (e.target.classList.contains('item-type-select')) {
    const newType = e.target.value;
    card.classList.toggle('is-section-card', newType === 'section');
    card.classList.toggle('is-hidden-card', ['note', 'media'].includes(newType));
    card.classList.toggle('is-label-card', newType === 'label');
    // Show/hide song DB buttons based on new type
    const dbLookupBtn = card.querySelector('[data-action="db-lookup"]');
    const dbSaveBtn   = card.querySelector('[data-action="db-save"]');
    if (dbLookupBtn) dbLookupBtn.style.display = newType === 'song' ? '' : 'none';
    if (dbSaveBtn)   dbSaveBtn.style.display   = newType === 'song' ? '' : 'none';
    card.querySelector('.item-title-input').placeholder =
      newType === 'section' ? 'Section name (e.g. GATHERING)' : 'Item heading…';
    card.querySelector('.item-detail-input').placeholder =
      newType === 'section' ? 'Optional subtitle' :
      newType === 'song'    ? 'Lyrics — paste verses, label sections (Verse 1, Chorus, etc.), copyright on last line' :
      newType === 'liturgy' ? 'Text — line breaks preserved' :
      'Leave blank for title-only display, or add a subtitle/note';
  }
  schedulePreviewUpdate();
});

itemList.addEventListener('click', e => {
  if (suppressLinkedFocusSync) return;
  const targetEl = e.target instanceof Element ? e.target : null;
  if (!targetEl) return;
  const card = targetEl.closest('.item-card');
  if (!card) return;
  const idx = parseInt(card.dataset.idx, 10);
  if (!Number.isInteger(idx)) return;
  scrollPreviewToItem(idx, 'smooth');
});

// Auto-grow a textarea to fit its content.
// field-sizing:content (CSS) handles this in modern browsers;
// this JS path is a fallback that defers to rAF so layout is ready.
const _fieldSizingSupported = CSS.supports('field-sizing', 'content');
function autoResize(ta) {
  if (_fieldSizingSupported) return; // CSS handles it
  const _do = () => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; };
  if (document.readyState === 'complete') requestAnimationFrame(_do); else _do();
}

function syncItemFromCard(card, idx) {
  if (!items[idx]) return;
  if (items[idx].type === 'page-break') return; // no inputs on break cards
  const typeEl   = card.querySelector('.item-type-select');
  if (!typeEl) return; // safety guard
  items[idx].type   = typeEl.value;
  items[idx].title  = card.querySelector('.item-title-input')?.value  ?? items[idx].title;
  items[idx].detail = card.querySelector('.item-detail-input')?.value ?? items[idx].detail;
}

function syncAllItems() {
  itemList.querySelectorAll('.item-card').forEach(card =>
    syncItemFromCard(card, parseInt(card.dataset.idx, 10))
  );
}

function clearLinkedPreviewHighlight() {
  previewPane.querySelectorAll('.preview-linkable.is-linked')
    .forEach(el => el.classList.remove('is-linked'));
}

function clearLinkedEditorHighlight() {
  itemList.querySelectorAll('.item-card.is-linked')
    .forEach(el => el.classList.remove('is-linked'));
}

function highlightLinkedPair(idx) {
  clearLinkedEditorHighlight();
  clearLinkedPreviewHighlight();
  const card = itemList.querySelector(`.item-card[data-idx="${idx}"]`);
  const preview = previewPane.querySelector(`[data-preview-idx="${idx}"]`);
  if (card) card.classList.add('is-linked');
  if (preview) preview.classList.add('is-linked');
}

function scrollElementIntoContainer(container, element, behavior = 'smooth') {
  if (!container || !element) return;
  const containerRect = container.getBoundingClientRect();
  const elementRect = element.getBoundingClientRect();
  const currentTop = container.scrollTop;
  const targetTop = currentTop + (elementRect.top - containerRect.top) - ((container.clientHeight - elementRect.height) / 2);
  const maxTop = Math.max(0, container.scrollHeight - container.clientHeight);
  const clampedTop = Math.min(maxTop, Math.max(0, targetTop));
  container.scrollTo({ top: clampedTop, behavior });
}

function scrollPreviewToItem(idx, behavior = 'smooth') {
  const linked = previewPane.querySelector(`[data-preview-idx="${idx}"]`);
  if (!linked) return;
  clearTimeout(linkedPreviewTimer);
  highlightLinkedPair(idx);
  scrollElementIntoContainer(previewPane, linked, behavior);
  linkedPreviewTimer = setTimeout(() => {
    clearLinkedPreviewHighlight();
  }, 1600);
}

// Scroll the preview pane to a specific announcement and briefly highlight it.
// Mirrors scrollPreviewToItem but uses data-preview-ann-idx instead of data-preview-idx.
function scrollPreviewToAnn(idx) {
  const linked = previewPane.querySelector(`[data-preview-ann-idx="${idx}"]`);
  if (!linked) {
    // Announcement page may not be visible yet — scroll to the section heading instead
    const heading = previewPane.querySelector('[data-preview-section="announcements"]');
    if (heading) scrollElementIntoContainer(previewPane, heading, 'smooth');
    return;
  }
  clearTimeout(linkedPreviewTimer);
  // Highlight both the preview element and the editor card
  previewPane.querySelectorAll('[data-preview-ann-idx].is-linked')
    .forEach(el => el.classList.remove('is-linked'));
  annList.querySelectorAll('.ann-card.is-linked')
    .forEach(el => el.classList.remove('is-linked'));
  linked.classList.add('is-linked');
  const card = annList.querySelector(`.ann-card[data-ann-idx="${idx}"]`);
  if (card) card.classList.add('is-linked');
  scrollElementIntoContainer(previewPane, linked, 'smooth');
  linkedPreviewTimer = setTimeout(() => {
    linked.classList.remove('is-linked');
    if (card) card.classList.remove('is-linked');
  }, 1600);
}

function collapseOtherSections(keepSection) {
  document.querySelectorAll('aside .panel-section').forEach(s => {
    if (s === keepSection || s.classList.contains('collapsed')) return;
    s.classList.add('collapsed');
    const toggle = s.querySelector('.collapse-toggle');
    if (toggle) toggle.textContent = '+';
  });
  updateSectionPreviews();
}

function scrollEditorToItem(idx, behavior = 'smooth') {
  // 1. Expand the parent panel-section (Order of Worship) if it is collapsed
  const section = itemList.closest('.panel-section');
  collapseOtherSections(section);
  if (section && section.classList.contains('collapsed')) {
    section.classList.remove('collapsed');
    const toggle = section.querySelector('.collapse-toggle');
    if (toggle) toggle.textContent = '−';
    updateSectionPreviews();
  }

  // 2. Collapse all other item cards; expand the target
  let needsRender = false;
  items.forEach((item, i) => {
    if (i === idx && item._collapsed)  { item._collapsed = false; needsRender = true; }
    else if (i !== idx && !item._collapsed) { item._collapsed = true;  needsRender = true; }
  });
  if (needsRender) renderItemList();

  // 3. Scroll to the (possibly re-rendered) card
  const card = itemList.querySelector(`.item-card[data-idx="${idx}"]`);
  if (!card) return;
  clearTimeout(linkedPreviewTimer);
  highlightLinkedPair(idx);
  scrollElementIntoContainer(itemList.closest('aside'), card, behavior);
  linkedPreviewTimer = setTimeout(() => {
    clearLinkedEditorHighlight();
    clearLinkedPreviewHighlight();
  }, 1600);
}

function scrollEditorToSection(sectionId, behavior = 'smooth') {
  const section = document.getElementById(sectionId);
  if (!section) return;
  collapseOtherSections(section);
  if (section.classList.contains('collapsed')) {
    section.classList.remove('collapsed');
    const toggle = section.querySelector('.collapse-toggle');
    if (toggle) toggle.textContent = '−';
    updateSectionPreviews();
  }
  clearLinkedEditorHighlight();
  const label = section.querySelector('.section-label');
  if (label) {
    label.style.transition = 'background 0.15s';
    label.style.background = '#f8f2ea';
    setTimeout(() => { label.style.background = ''; }, 1600);
  }
  const aside = document.querySelector('aside');
  scrollElementIntoContainer(aside, section, behavior);
}

addItemBtn.addEventListener('click', () => {
  syncAllItems();
  items.push({ type: 'song', title: '', detail: '' });
  renderItemList();
  schedulePreviewUpdate();
  setTimeout(() => {
    const cards = itemList.querySelectorAll('.item-card');
    const last = cards[cards.length - 1];
    last?.querySelector('.item-title-input')?.focus();
    last?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, 50);
});

addBreakBtn.addEventListener('click', () => {
  syncAllItems();
  items.push({ type: 'page-break', title: '', detail: '' });
  renderItemList();
  schedulePreviewUpdate();
  autosaveProjectState(); // flush immediately
  setTimeout(() => {
    const cards = itemList.querySelectorAll('.item-card');
    const last = cards[cards.length - 1];
    last?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, 50);
});

// ─── Live preview ─────────────────────────────────────────────────────────────
function schedulePreviewUpdate() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(renderPreview, 250);
  scheduleProjectPersist();
}

function updateDocTitle() {
  const d = svcDate.value.trim();
  document.title = d ? `${d} Bulletin` : 'Bulletin Generator';
}

svcTitle.addEventListener('input',        schedulePreviewUpdate);
svcDate.addEventListener('input',         () => { updateDocTitle(); schedulePreviewUpdate(); updateSectionPreviews(); });
bulletinTitleInput.addEventListener('input', () => { updateSectionPreviews(); });
svcChurch.addEventListener('input',       schedulePreviewUpdate);
annAddBtn.addEventListener('click', () => annAdd());
welcomeAddBtn.addEventListener('click', () => welcomeAdd());
welcomeHeadingInput.addEventListener('input', () => {
  welcomeHeading = welcomeHeadingInput.value;
  schedulePreviewUpdate();
  scheduleProjectPersist();
});

// ─── Collapsible sidebar panels ───────────────────────────────────────────────
document.querySelectorAll('aside .panel-section').forEach(section => {
  const label = section.querySelector('.section-label');
  if (!label) return;

  // Right-side wrapper holds preview text + toggle glyph
  const rightEl = document.createElement('span');
  rightEl.className = 'section-label-right';

  const preview = document.createElement('span');
  preview.className = 'section-preview';
  rightEl.appendChild(preview);

  const toggle = document.createElement('span');
  toggle.className = 'collapse-toggle';
  toggle.textContent = '+'; // starts collapsed
  rightEl.appendChild(toggle);

  label.appendChild(rightEl);

  // Start every section collapsed
  section.classList.add('collapsed');
  label.addEventListener('click', () => {
    section.classList.toggle('collapsed');
    toggle.textContent = section.classList.contains('collapsed') ? '+' : '−';
  });
});

// ─── Section preview strings ──────────────────────────────────────────────────
function updateSectionPreviews() {
  document.querySelectorAll('aside .panel-section').forEach(section => {
    const label = section.querySelector('.section-label');
    if (!label) return;
    const previewEl = label.querySelector('.section-preview');
    if (!previewEl) return;
    // Label text is the first text node, before the .section-label-right wrapper
    const labelText = (label.childNodes[0]?.textContent || '').trim().toUpperCase();
    let text = '';
    if (labelText === 'FILE') {
      text = bulletinTitleInput?.value?.trim() || 'No file';
    } else if (labelText === 'SERVICE DETAILS') {
      text = svcDate?.value?.trim() || '—';
    } else if (labelText === 'COVER IMAGE') {
      text = coverImgName?.textContent?.trim() || 'No image';
    } else if (labelText === 'ANNOUNCEMENTS') {
      text = `${annData.length} item${annData.length !== 1 ? 's' : ''}`;
    } else if (labelText === 'ORDER OF WORSHIP') {
      text = `${items.length} item${items.length !== 1 ? 's' : ''}`;
    } else if (labelText === 'CALENDAR') {
      text = "This week's events";
    } else if (labelText === 'VOLUNTEERS') {
      if (servingSchedule?.weeks?.length) {
        const allPositions = servingSchedule.weeks.flatMap(w =>
          (w.teams || []).filter(t => servingTeamFilter[t.name] !== false).flatMap(t => t.positions || [])
        );
        const unfilled = allPositions.filter(p => !p.names || p.names.length === 0).length;
        const weekCount = servingSchedule.weeks.length;
        const suffix = weekCount > 1 ? ` (${weekCount} weeks)` : '';
        text = allPositions.length === 0 ? '—' : (unfilled === 0 ? 'All filled' : `${unfilled} unfilled`) + suffix;
      } else {
        text = '—';
      }
    } else if (labelText.startsWith('CHURCH STAFF')) {
      text = 'Staff info';
    } else if (labelText === 'OPTIONS') {
      text = 'Print options';
    }
    previewEl.textContent = text;
  });
}
updateSectionPreviews();

