// ─── PCO Integration ──────────────────────────────────────────────────────────
const PCO_BASE      = '/pco-proxy';
const PCO_LAST_IMPORT_KEY = 'worshipPcoLastImport';

async function pcoGet(path) {
  const resp = await fetch(`${PCO_BASE}${path}`);
  if (!resp.ok) {
    if (resp.status === 503) throw new Error('Planning Center credentials are not configured on the server.');
    if (resp.status === 401) throw new Error('Invalid credentials — check your App ID and Secret.');
    if (resp.status === 403) throw new Error('Access denied — check your PCO API permissions.');
    throw new Error(`PCO API error ${resp.status}.`);
  }
  return resp.json();
}
function pcoSetMsg(elId, msg, type = '') {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = msg;
  el.className = 'pco-msg' + (type ? ' ' + type : '');
}
function pcoShowCredsView() {
  document.getElementById('pco-creds-view').style.display = '';
  document.getElementById('pco-import-view').style.display = 'none';
}
function pcoShowImportView() {
  document.getElementById('pco-creds-view').style.display = 'none';
  document.getElementById('pco-import-view').style.display = '';
}

async function pcoLoadServiceTypes() {
  const sel = document.getElementById('pco-service-type-sel');
  sel.innerHTML = '<option value="">Loading…</option>';
  sel.disabled = true;
  pcoSetMsg('pco-import-msg', '');
  try {
    const data = await pcoGet('/service_types?per_page=100');
    sel.innerHTML = '<option value="">— Select service type —</option>';
    (data.data || []).forEach(st => {
      const o = document.createElement('option');
      o.value = st.id;
      o.textContent = st.attributes.name;
      sel.appendChild(o);
    });
    sel.disabled = false;
  } catch (err) {
    sel.innerHTML = '<option value="">Error loading</option>';
    pcoSetMsg('pco-import-msg', err.message, 'error');
  }
}

async function pcoLoadPlans() {
  const stId      = document.getElementById('pco-service-type-sel').value;
  const showPast  = document.getElementById('pco-show-past').checked;
  const planField = document.getElementById('pco-plan-field');
  const planSel   = document.getElementById('pco-plan-sel');
  const importBtn = document.getElementById('pco-import-btn');
  planField.style.display = 'none';
  importBtn.disabled = true;
  pcoSetMsg('pco-import-msg', '');
  if (!stId) return;
  planSel.innerHTML = '<option value="">Loading…</option>';
  planSel.disabled  = true;
  planField.style.display = '';
  try {
    const filter = showPast ? 'past' : 'future';
    const order  = showPast ? '-sort_date' : 'sort_date'; // past: newest first
    const data   = await pcoGet(`/service_types/${stId}/plans?filter=${filter}&order=${order}&per_page=100`);
    planSel.innerHTML = '<option value="">— Select plan —</option>';
    if (!data.data || data.data.length === 0) {
      planSel.innerHTML = `<option value="">No ${showPast ? 'previous' : 'upcoming'} plans found</option>`;
    } else {
      data.data.forEach(plan => {
        const o = document.createElement('option');
        o.value = plan.id;
        const d = plan.attributes.dates || '';
        const t = plan.attributes.title  || '';
        o.textContent = t ? `${d} — ${t}` : (d || `Plan ${plan.id}`);
        planSel.appendChild(o);
      });
    }
    planSel.disabled = false;
  } catch (err) {
    planSel.innerHTML = '<option value="">Error loading</option>';
    pcoSetMsg('pco-import-msg', err.message, 'error');
  }
}

document.getElementById('pco-service-type-sel').addEventListener('change', pcoLoadPlans);
document.getElementById('pco-show-past').addEventListener('change', pcoLoadPlans);

document.getElementById('pco-plan-sel').addEventListener('change', () => {
  document.getElementById('pco-import-btn').disabled =
    !document.getElementById('pco-plan-sel').value;
});

document.getElementById('pco-import-btn').addEventListener('click', async () => {
  const stId   = document.getElementById('pco-service-type-sel').value;
  const planId = document.getElementById('pco-plan-sel').value;
  if (!stId || !planId) return;
  const btn   = document.getElementById('pco-import-btn');
  btn.disabled = true;
  btn.textContent = 'Importing…';
  pcoSetMsg('pco-import-msg', '');
  try {
    const [planResp, itemsResp, notesResp] = await Promise.all([
      pcoGet(`/service_types/${stId}/plans/${planId}`),
      pcoGet(`/service_types/${stId}/plans/${planId}/items?include=song&per_page=100`),
      pcoGet(`/service_types/${stId}/plans/${planId}/notes`).catch(() => ({ data: [] })),
    ]);
    savePreImportBackup(); // snapshot pre-import state before overwriting
    applyPcoData(planResp, itemsResp, notesResp);
    const planLabel = document.getElementById('pco-plan-sel').selectedOptions[0]?.text || planId;
    pcoSaveLastImport(stId, planId, planLabel);
    pcoShowLastImport(planLabel);
    setStatus(`Imported ${items.length} items from Planning Center.`, 'success');
    document.querySelector('.tab-btn[data-tab="page-editor"]').click();
    // Fetch serving schedule in background (non-blocking)
    pcoFetchAndApplyServing(stId, planId,
      planResp.data.attributes.sort_date, planResp.data.attributes.dates);
  } catch (err) {
    pcoSetMsg('pco-import-msg', err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Import Plan';
  }
});

function applyPcoData(planResp, itemsResp, notesResp) {
  const planAttrs = planResp.data.attributes;

  // Snapshot current items so user edits can be preserved on re-sync
  const prevItems = items.slice();

  // Build included-song lookup keyed by song id
  const incSongs = {};
  (itemsResp.included || []).forEach(inc => {
    if (inc.type === 'Song') incSongs[inc.id] = inc.attributes;
  });

  // Populate service date and title
  if (planAttrs.dates)  svcDate.value  = planAttrs.dates;
  if (planAttrs.title)  svcTitle.value = planAttrs.title;
  // Default Bulletin Title to the service date (user can rename before saving)
  if (!activeProjectId && planAttrs.dates) {
    bulletinTitleInput.value = planAttrs.dates + ' Bulletin';
  }
  updateDocTitle();

  // Sort items by sequence and map to bulletin format
  const sorted = (itemsResp.data || []).slice().sort((a, b) =>
    (a.attributes.sequence || 0) - (b.attributes.sequence || 0)
  );

  items = sorted.map(item => {
    const a    = item.attributes;
    const type = pcoMapItemType(a);
    let title  = (a.title || '').trim();
    let detail = '';

    // For songs, always prefer the canonical Song record title over the item title.
    // PCO item titles often contain hymnal/arranger prefixes like
    // "Bread - Gray Hymnal 297 - O Come My Soul Sing Praise to God",
    // while the linked Song record holds the clean song name.
    if (a.item_type === 'song') {
      const songRel = item.relationships && item.relationships.song && item.relationships.song.data;
      if (songRel && incSongs[songRel.id] && incSongs[songRel.id].title) {
        title = incSongs[songRel.id].title;
      }
    }

    // Strip HTML from description and use as detail
    if (a.description) {
      const tmp = document.createElement('div');
      tmp.innerHTML = a.description;
      const stripped = (tmp.textContent || tmp.innerText || '')
        .replace(/\[[^\]]*\]/g, '')   // strip [bracket notes]
        .replace(/\s{2,}/g, ' ')
        .trim();
      if (stripped) detail = stripped;
    }

    // Section headers are rendered uppercase in the booklet
    if (type === 'section') title = title.toUpperCase();

    return { type, title, detail };
  }).filter(item => item.title);

  items = pcoDeduplicateItems(items);
  const enrichResult = enrichItemsFromDb(items);

  // Map plan-level notes onto matching items (fill blank detail only).
  if (notesResp) {
    const normalizedNotes = normalizePlanNotes(notesResp);
    mapPlanNotesToItems(items, normalizedNotes);
  }

  // Re-sync merge: for items that existed before, restore all user edits.
  // New items (not in prevItems) keep their freshly-enriched detail from above.
  // Conflicts are collected (PCO detail ≠ user's detail, both non-empty) for review.
  const refreshConflicts = [];
  if (prevItems.length > 0) {
    items.forEach((newItem, i) => {
      const match = prevItems.find(ex =>
        ex.type === newItem.type &&
        normTitle(ex.title) === normTitle(newItem.title)
      );
      if (match) {
        // Detect a conflict before overwriting
        if (match.detail && newItem.detail && match.detail.trim() !== newItem.detail.trim()) {
          refreshConflicts.push({
            idx: i,
            title: newItem.title,
            prevDetail: match.detail,   // user's current version
            pcoDetail:  newItem.detail, // PCO / DB version
          });
        }
        // Always preserve the user's edit (and all per-item overrides) by default.
        // The conflict dialog lets the user choose to accept PCO data per-item.
        items[i] = {
          ...newItem,
          detail:                match.detail,
          _fmt:                  match._fmt,
          _noBreakBefore:        match._noBreakBefore,
          _noBreakBeforeStanzas: match._noBreakBeforeStanzas,
          _collapsed:            match._collapsed,
        };
      }
    });
  }

  renderItemList();
  renderPreview();
  scheduleProjectPersist();

  // Compute songs that still need user review.
  //
  // Unmatched: show any song that still has no lyrics in the live items array
  // after re-sync (regardless of whether it was in the previous plan).
  // Also update e.item to the live items[] reference — the re-sync merge
  // replaces items[i] with a new object, so the original enrichResult reference
  // is stale and writing to it would not affect the rendered preview.
  const pendingUnmatched = enrichResult.unmatched.filter(e => {
    const live = items.find(it =>
      it.type === e.item.type && normTitle(it.title) === normTitle(e.item.title)
    );
    if (!live || live.detail) return false; // already has lyrics — skip
    e.item = live; // point to the live object so dialog writes take effect
    return true;
  });

  // withNotes: only surface songs that are new to this plan (existing ones
  // were already reviewed in a prior session).
  let pendingWithNotes = enrichResult.withNotes;
  if (prevItems.length > 0) {
    const prevKeys = new Set(prevItems.map(ex => ex.type + '|' + normTitle(ex.title)));
    pendingWithNotes = enrichResult.withNotes.filter(e => !prevKeys.has(e.item.type + '|' + normTitle(e.item.title)));
  }

  // Surface a per-item review dialog when PCO data differs from user edits.
  // Pass pending song reviews so they can be chained after conflict resolution.
  if (refreshConflicts.length > 0) {
    showRefreshConflictsDialog(refreshConflicts, pendingWithNotes, pendingUnmatched);
    return;
  }

  // No conflicts — go straight to import review if there are new songs to handle.
  if (pendingWithNotes.length || pendingUnmatched.length) {
    showImportReviewDialog(pendingWithNotes, pendingUnmatched);
  }
}

// ─── PCO Plan Notes ───────────────────────────────────────────────────────────

// Convert raw PCO notes response into a flat normalized array.
function normalizePlanNotes(notesResp) {
  // Guard against null/undefined, non-objects, or a raw array being passed
  // instead of the expected { data: [...] } JSON:API envelope.
  if (!notesResp || typeof notesResp !== 'object' || Array.isArray(notesResp)) {
    console.warn('normalizePlanNotes: unexpected input shape', notesResp);
    return [];
  }
  return (notesResp.data || []).map(note => {
    const a = note.attributes || {};
    const title = (a.category_name || '').trim();
    const body  = (a.content      || '').trim();
    return { title, normalizedTitle: normTitle(title), body };
  }).filter(n => n.title && n.body);
}

// Fill blank item.detail from matching plan notes (fill-if-blank only,
// so user-edited detail is never overwritten).
function mapPlanNotesToItems(items, normalizedNotes) {
  normalizedNotes.forEach(note => {
    const match = items.find(item =>
      normTitle(item.title) === note.normalizedTitle && !item.detail
    );
    if (match) match.detail = note.body;
  });
}

// ─── Import Review Dialog helpers ────────────────────────────────────────────

// Renders "Songs with PCO Notes" cards into body; returns a selections Map.
function irmBuildWithNotesSection(body, withNotes) {
  const selections = new Map();
  if (!withNotes.length) return selections;

  const h = document.createElement('div');
  h.className = 'irm-section-label';
  h.textContent = 'Songs with Planning Center Notes';
  body.appendChild(h);

  const desc = document.createElement('p');
  desc.className = 'irm-desc';
  desc.textContent = 'A match was found in your database for each song below. Choose which version to display in the bulletin:';
  body.appendChild(desc);

  withNotes.forEach(({ item, pcoNotes, dbMatch }) => {
    selections.set(item, 'db');
    const card = document.createElement('div');
    card.className = 'irm-song-card';

    const titleEl = document.createElement('div');
    titleEl.className = 'irm-song-title';
    titleEl.textContent = item.title;
    card.appendChild(titleEl);

    const groupName = 'irm-' + Math.random().toString(36).slice(2);

    const { row: row1 } = irmRadioRow(groupName, 'Use lyrics from song database', true, () => selections.set(item, 'db'));
    card.appendChild(row1);
    const dbFirstLine = (dbMatch.lyrics || '').split('\n').map(l => l.trim()).find(l => l) || '';
    if (dbFirstLine) {
      const prev = document.createElement('div');
      prev.className = 'irm-preview-text';
      prev.textContent = '\u201C' + dbFirstLine.slice(0, 90) + (dbFirstLine.length > 90 ? '\u2026' : '') + '\u201D';
      card.appendChild(prev);
    }

    const { row: row2 } = irmRadioRow(groupName, 'Keep Planning Center notes', false, () => selections.set(item, 'notes'));
    card.appendChild(row2);
    if (pcoNotes) {
      const prev = document.createElement('div');
      prev.className = 'irm-preview-text';
      prev.textContent = '\u201C' + pcoNotes.slice(0, 90) + (pcoNotes.length > 90 ? '\u2026' : '') + '\u201D';
      card.appendChild(prev);
    }

    const { row: row3 } = irmRadioRow(groupName, 'Leave blank', false, () => selections.set(item, 'blank'));
    card.appendChild(row3);

    body.appendChild(card);
  });

  return selections;
}

// Renders "Songs Not in Database" cards into body; returns an unmatchedSelections Map.
function irmBuildUnmatchedSection(body, unmatched) {
  const unmatchedSelections = new Map();
  if (!unmatched.length) return unmatchedSelections;

  const h = document.createElement('div');
  h.className = 'irm-section-label';
  h.textContent = 'Songs Not in Your Database';
  body.appendChild(h);

  const desc = document.createElement('p');
  desc.className = 'irm-desc';
  desc.textContent = 'These songs were not found in your song database. Paste lyrics inline to use them in this bulletin, or skip to leave them blank.';
  body.appendChild(desc);

  unmatched.forEach(({ item }) => {
    unmatchedSelections.set(item, { choice: 'skip', lyrics: '' });
    const card = document.createElement('div');
    card.className = 'irm-song-card';

    const titleEl = document.createElement('div');
    titleEl.className = 'irm-song-title';
    titleEl.textContent = item.title;
    card.appendChild(titleEl);

    const groupName = 'irm-u-' + Math.random().toString(36).slice(2);

    const lyricsArea = document.createElement('textarea');
    lyricsArea.className = 'irm-lyrics-input';
    lyricsArea.placeholder = 'Paste lyrics here\u2026';
    lyricsArea.style.display = 'none';
    lyricsArea.addEventListener('input', () => {
      unmatchedSelections.get(item).lyrics = lyricsArea.value;
    });

    const { row: skipRow } = irmRadioRow(groupName, 'Skip (leave blank)', true, () => {
      unmatchedSelections.get(item).choice = 'skip';
      lyricsArea.style.display = 'none';
    });
    card.appendChild(skipRow);

    const { row: pasteRow } = irmRadioRow(groupName, 'Paste lyrics for this bulletin', false, () => {
      unmatchedSelections.get(item).choice = 'paste';
      lyricsArea.style.display = '';
      setTimeout(() => lyricsArea.focus(), 30);
    });
    card.appendChild(pasteRow);
    card.appendChild(lyricsArea);

    body.appendChild(card);
  });

  return unmatchedSelections;
}

// Applies withNotes selections to items[].
function irmApplyWithNotes(withNotes, selections) {
  withNotes.forEach(({ item, pcoNotes, dbMatch }) => {
    const choice = selections.get(item) || 'db';
    if (choice === 'db') {
      item.detail = sdbBuildDetail(dbMatch);
      dbMatch.times_used = (dbMatch.times_used || 0) + 1;
      dbMatch.last_used  = new Date().toISOString();
      saveSongDb();
    } else if (choice === 'notes') {
      item.detail = pcoNotes;
    } else {
      item.detail = '';
    }
  });
}

// Applies unmatched paste/skip selections to items[] and saves to song DB.
function irmApplyUnmatched(unmatched, unmatchedSelections) {
  let dbChanged = false;
  unmatched.forEach(({ item }) => {
    const sel = unmatchedSelections.get(item);
    if (sel && sel.choice === 'paste' && sel.lyrics.trim()) {
      const lyrics = sel.lyrics.trim();
      item.detail = lyrics;

      // Save to song database so future imports find this song automatically.
      // Update in-place if a record already exists (e.g. from a manual add).
      const existingIdx = songDb.findIndex(s => normTitle(s.title) === normTitle(item.title));
      if (existingIdx >= 0) {
        songDb[existingIdx].lyrics     = lyrics;
        songDb[existingIdx].times_used = (songDb[existingIdx].times_used || 0) + 1;
        songDb[existingIdx].last_used  = new Date().toISOString();
      } else {
        songDb.push({
          title: item.title, author: '', lyrics, copyright: '',
          source: 'pco-import', date_added: new Date().toISOString(),
          times_used: 1, last_used: new Date().toISOString(),
        });
      }
      dbChanged = true;
    }
  });
  if (dbChanged) saveSongDb();
}

// ─── Import Review Dialog ─────────────────────────────────────────────────────
function showImportReviewDialog(withNotes, unmatched) {
  const body = document.getElementById('irm-body');
  body.innerHTML = '';

  const selections         = irmBuildWithNotesSection(body, withNotes);
  const unmatchedSelections = irmBuildUnmatchedSection(body, unmatched);

  document.getElementById('irm-apply-btn').onclick = () => {
    irmApplyWithNotes(withNotes, selections);
    irmApplyUnmatched(unmatched, unmatchedSelections);
    renderItemList();
    renderPreview();
    scheduleProjectPersist();
    closeImportReviewDialog();
  };
  document.getElementById('irm-cancel-btn').onclick = closeImportReviewDialog;
  document.getElementById('irm-close-btn').onclick  = closeImportReviewDialog;

  document.getElementById('irm-title').textContent = 'Review Imported Songs';
  document.getElementById('import-review-modal').style.display = 'flex';
}

function closeImportReviewDialog() {
  document.getElementById('import-review-modal').style.display = 'none';
}

function irmRadioRow(groupName, labelText, checked, onChange) {
  const label = document.createElement('label');
  label.className = 'irm-radio-row';

  const radio = document.createElement('input');
  radio.type    = 'radio';
  radio.name    = groupName;
  radio.checked = checked;
  radio.addEventListener('change', () => { if (radio.checked) onChange(); });

  const span = document.createElement('span');
  span.className   = 'irm-radio-label';
  span.textContent = labelText;

  label.appendChild(radio);
  label.appendChild(span);
  return { row: label, radio };
}

function pcoMapItemType(attrs) {
  if (attrs.item_type === 'header') return 'section';
  if (attrs.item_type === 'song')   return 'song';
  if (attrs.item_type === 'note')   return 'note';
  if (attrs.item_type === 'media')  return 'media';
  // PCO 'item' type — default to label (title-only liturgical items)
  // enrichItemsFromDb will upgrade liturgical text items to 'liturgy'
  // if they match LITURGICAL_RE and need a DB lookup.
  return 'label';
}


// ─── Serving schedule fetch ───────────────────────────────────────────────────

// Fetch all non-declined team members for a plan, grouped by service time → team → position.
// Each returned team object carries a `serviceTime` string (from PCO's service_time_name
// attribute) so the bulletin can show "8:00a" / "10:30a" subheadings.
async function pcoFetchPlanTeamMembers(stId, planId) {
  // Fetch plan times (to get "8:00a" / "10:30a" labels) and team members in parallel.
  // Use the service_times relationship on each team member to map to their assigned PlanTime.
  const [timesResp, resp] = await Promise.all([
    pcoGet(`/service_types/${stId}/plans/${planId}/plan_times`).catch(() => ({ data: [] })),
    pcoGet(`/service_types/${stId}/plans/${planId}/team_members?include=team&per_page=200`),
  ]);

  // Build PlanTime ID → short display label  (e.g. "8:00a", "10:30a")
  // Only include actual service times (not rehearsals)
  const planTimeLabels = {};
  const serviceTimeIds = new Set();
  (timesResp.data || []).forEach(pt => {
    let label = (pt.attributes.name || '').trim();
    if (!label && pt.attributes.starts_at) {
      const d = new Date(pt.attributes.starts_at);
      const h = d.getHours(), m = d.getMinutes();
      const ampm = h < 12 ? 'a' : 'p';
      const h12  = h % 12 || 12;
      label = m === 0 ? `${h12}:00${ampm}` : `${h12}:${String(m).padStart(2,'0')}${ampm}`;
    }
    planTimeLabels[pt.id] = label || pt.id;
    if (pt.attributes.time_type === 'service') serviceTimeIds.add(pt.id);
  });

  const teamNames = {};
  (resp.included || []).forEach(inc => {
    if (inc.type === 'Team') teamNames[inc.id] = inc.attributes.name;
  });

  // Three-level map: svcTime → teamName → positionName → [names]
  // Parallel arrays track insertion order for stable output.
  const timeOrder   = [];                 // ordered list of distinct service-time keys
  const timeTeamOrd = {};                 // svcTime → [teamName in insertion order]
  const data        = {};                 // svcTime → teamName → position → [names]

  (resp.data || []).forEach(tm => {
    if (tm.attributes.status === 'D') return; // skip declined
    const teamId   = tm.relationships?.team?.data?.id;
    const teamName = (teamId && teamNames[teamId]) || 'Team';
    const position = (tm.attributes.team_position_name || 'Volunteer').toUpperCase();
    const name     = (tm.attributes.name || '').trim();

    // Resolve service time from the service_times relationship on the team member.
    // Each entry is a PlanTime reference. Pick only service-type times (not rehearsal).
    const memberSvcTimes = (tm.relationships?.service_times?.data || [])
      .filter(d => serviceTimeIds.has(d.id));
    // If member is assigned to ALL service times (or none), group under '' (all services)
    const assignedToAll = memberSvcTimes.length === 0 || memberSvcTimes.length >= serviceTimeIds.size;
    const svcTimeKeys = assignedToAll ? [''] : memberSvcTimes.map(d => planTimeLabels[d.id] || d.id);

    svcTimeKeys.forEach(svcTime => {
      if (!data[svcTime]) {
        data[svcTime] = {};
        timeOrder.push(svcTime);
        timeTeamOrd[svcTime] = [];
      }
      if (!data[svcTime][teamName]) {
        data[svcTime][teamName] = {};
        timeTeamOrd[svcTime].push(teamName);
      }
      if (!data[svcTime][teamName][position]) data[svcTime][teamName][position] = [];
      if (name && !data[svcTime][teamName][position].includes(name))
        data[svcTime][teamName][position].push(name);
    });
  });

  // Flatten into a single teams array, sorted so blank (all-services) comes first,
  // then alphabetically / chronologically by service time name.
  const sortedTimes = timeOrder.slice().sort((a, b) => {
    if (!a && b)  return -1;
    if (a  && !b) return  1;
    return a.localeCompare(b, undefined, { numeric: true });
  });

  const teams = [];
  sortedTimes.forEach(svcTime => {
    timeTeamOrd[svcTime].forEach(tn => {
      teams.push({
        name:        tn,
        serviceTime: svcTime || null,   // null → "all services" (no subheading shown)
        positions:   Object.entries(data[svcTime][tn]).map(([role, names]) => ({ role, names })),
      });
    });
  });
  return teams;
}

// Save serving team filter to settings.json
function saveServingTeamFilter() {
  apiFetch('/api/settings', 'POST', { servingTeamFilter }).catch(() => {});
}

// Detect new team names not yet in servingTeamFilter. Returns array of new names.
function detectNewServingTeams(weeks) {
  const newTeams = [];
  weeks.forEach(week => {
    (week.teams || []).forEach(t => {
      if (!(t.name in servingTeamFilter) && !newTeams.includes(t.name)) {
        newTeams.push(t.name);
      }
    });
  });
  return newTeams;
}

// Show a dialog section for newly discovered teams inside the import review modal.
function showNewTeamsDialog(newTeams) {
  const body = document.getElementById('irm-body');
  body.innerHTML = '';

  const h = document.createElement('div');
  h.className = 'irm-section-label';
  h.textContent = 'New Serving Teams Discovered';
  body.appendChild(h);

  const desc = document.createElement('p');
  desc.className = 'irm-desc';
  desc.textContent = 'The following teams were found in Planning Center for the first time. Check the teams you want included in the bulletin. You can change this later in Settings.';
  body.appendChild(desc);

  const choices = new Map(); // teamName → checked (bool)
  newTeams.forEach(name => choices.set(name, true)); // default: included

  newTeams.forEach(name => {
    const label = document.createElement('label');
    label.style.cssText = 'display:flex;align-items:center;gap:0.5rem;font-size:0.84rem;margin-bottom:0.35rem;cursor:pointer;';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.addEventListener('change', () => choices.set(name, cb.checked));

    const span = document.createElement('span');
    span.textContent = name;

    label.appendChild(cb);
    label.appendChild(span);
    body.appendChild(label);
  });

  document.getElementById('irm-apply-btn').onclick = () => {
    choices.forEach((checked, name) => {
      servingTeamFilter[name] = checked;
    });
    saveServingTeamFilter();
    volRender();
    renderPreview();
    renderServingTeamSettings();
    closeImportReviewDialog();
  };

  document.getElementById('irm-cancel-btn').onclick = () => {
    // "Skip" = include all by default
    newTeams.forEach(name => { servingTeamFilter[name] = true; });
    saveServingTeamFilter();
    renderServingTeamSettings();
    closeImportReviewDialog();
  };
  document.getElementById('irm-close-btn').onclick = () => {
    newTeams.forEach(name => { servingTeamFilter[name] = true; });
    saveServingTeamFilter();
    renderServingTeamSettings();
    closeImportReviewDialog();
  };

  document.getElementById('irm-title').textContent = 'New Serving Teams';
  document.getElementById('import-review-modal').style.display = 'flex';
}

// Render the serving team checkboxes in the Settings tab
function renderServingTeamSettings() {
  const listEl = document.getElementById('serving-team-filter-list');
  if (!listEl) return;
  const teamNames = Object.keys(servingTeamFilter).sort((a, b) => a.localeCompare(b));
  if (teamNames.length === 0) {
    listEl.innerHTML = '<span style="font-size:0.78rem;color:var(--muted);">No teams discovered yet. Import a plan from Planning Center to populate this list.</span>';
    return;
  }
  listEl.innerHTML = '';
  teamNames.forEach(name => {
    const label = document.createElement('label');
    label.style.cssText = 'display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;margin-bottom:0.25rem;cursor:pointer;';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = servingTeamFilter[name] !== false;
    cb.addEventListener('change', () => {
      servingTeamFilter[name] = cb.checked;
      saveServingTeamFilter();
      volRender();
      renderPreview();
    });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(name));
    listEl.appendChild(label);
  });
}

// Fetch serving data for the imported plan and all future plans within 8 days, then re-render.
async function pcoFetchAndApplyServing(stId, planId, planSortDate, planDate) {
  try {
    const thisWeekTeams = await pcoFetchPlanTeamMembers(stId, planId);

    const weeks = [{ date: planDate || planSortDate || '', planId, teams: thisWeekTeams }];

    // Fetch additional plans within 8 days of the imported plan
    try {
      const cutoff = new Date(planSortDate || planDate || Date.now());
      cutoff.setDate(cutoff.getDate() + 8);
      const cutoffISO = cutoff.toISOString().slice(0, 10);

      const futurePlans = await pcoGet(
        `/service_types/${stId}/plans?filter=future&order=sort_date&per_page=25`
      );
      const upcoming = (futurePlans.data || []).filter(p =>
        p.id !== planId &&
        (p.attributes.sort_date || '') > (planSortDate || '') &&
        (p.attributes.sort_date || '') <= cutoffISO
      );
      for (const plan of upcoming) {
        try {
          const teams = await pcoFetchPlanTeamMembers(stId, plan.id);
          weeks.push({
            date:   plan.attributes.dates || plan.attributes.sort_date || '',
            planId: plan.id,
            teams,
          });
        } catch (e) { /* individual plan fetch is non-critical */ }
      }
    } catch (e) { /* future plans fetch is non-critical */ }

    // Detect newly discovered teams and prompt user
    const newTeams = detectNewServingTeams(weeks);
    if (newTeams.length > 0) {
      // If the import review modal is already showing (e.g. song review), just
      // add the new teams silently — user can adjust in Settings.
      const modalOpen = document.getElementById('import-review-modal').style.display === 'flex';
      if (modalOpen) {
        newTeams.forEach(name => { servingTeamFilter[name] = true; });
      } else {
        showNewTeamsDialog(newTeams);
        // Pre-register as visible; dialog lets user uncheck before applying
        newTeams.forEach(name => { servingTeamFilter[name] = true; });
      }
      saveServingTeamFilter();
      renderServingTeamSettings();
    }

    servingSchedule = { weeks };
    const errEl = document.getElementById('vol-error');
    if (errEl) errEl.style.display = 'none';
    volRender();
    renderPreview();
    scheduleProjectPersist();
  } catch (e) {
    console.warn('Could not fetch serving schedule:', e);
    const errEl = document.getElementById('vol-error');
    if (errEl) {
      errEl.textContent = `Could not load volunteers: ${e.message}`;
      errEl.style.display = '';
    }
  }
}

function pcoSaveLastImport(serviceTypeId, planId, planLabel) {
  localStorage.setItem(PCO_LAST_IMPORT_KEY, JSON.stringify({ serviceTypeId, planId, planLabel }));
}
function pcoGetLastImport() {
  try { const r = localStorage.getItem(PCO_LAST_IMPORT_KEY); return r ? JSON.parse(r) : null; }
  catch (e) { return null; }
}
function pcoShowLastImport(label) {
  document.getElementById('pco-last-plan-label').textContent = label;
  document.getElementById('pco-last-import-wrap').style.display = '';
}

document.getElementById('pco-refresh-btn').addEventListener('click', async () => {
  const last = pcoGetLastImport();
  if (!last) return;
  const btn   = document.getElementById('pco-refresh-btn');
  btn.disabled = true;
  btn.textContent = 'Refreshing…';
  pcoSetMsg('pco-refresh-msg', '');
  try {
    const [planResp, itemsResp, notesResp] = await Promise.all([
      pcoGet(`/service_types/${last.serviceTypeId}/plans/${last.planId}`),
      pcoGet(`/service_types/${last.serviceTypeId}/plans/${last.planId}/items?include=song&per_page=100`),
      pcoGet(`/service_types/${last.serviceTypeId}/plans/${last.planId}/notes`).catch(() => ({ data: [] })),
    ]);
    savePreImportBackup(); // snapshot pre-import state before overwriting
    applyPcoData(planResp, itemsResp, notesResp);
    pcoSetMsg('pco-refresh-msg', `Updated — ${items.length} items refreshed.`, 'success');
    setStatus(`Refreshed from Planning Center (${items.length} items).`, 'success');
    document.querySelector('.tab-btn[data-tab="page-editor"]').click();
    // Fetch serving schedule in background (non-blocking)
    pcoFetchAndApplyServing(last.serviceTypeId, last.planId,
      planResp.data.attributes.sort_date, planResp.data.attributes.dates);
  } catch (err) {
    pcoSetMsg('pco-refresh-msg', err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '↺ Refresh from PCO';
  }
});

function initPco() {
  const hint    = document.getElementById('pco-creds-hint');
  const connBtn = document.getElementById('pco-connect-btn');
  const discBtn = document.getElementById('pco-disconnect-btn');
  const badge   = document.getElementById('pco-connected-badge');

  connBtn.textContent = 'Connect Planning Center';
  if (badge) badge.textContent = 'Connected';
  if (discBtn) discBtn.style.display = '';
  if (hint) hint.textContent = 'Sign in to Planning Center to import your service plans.';

  if (_publicConfig.pcoConfigured) {
    pcoShowImportView();
    pcoLoadServiceTypes();
    const last = pcoGetLastImport();
    if (last) pcoShowLastImport(last.planLabel || last.planId);
  } else {
    pcoShowCredsView();
    if (!isDesktopMode()) {
      pcoSetMsg('pco-creds-msg', 'Planning Center is not configured on this machine yet.', 'error');
    }
  }

  // Handle OAuth redirect-back query params
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('pco_connected') === '1') {
    _publicConfig.pcoConfigured = true;
    pcoShowImportView();
    pcoLoadServiceTypes();
    setStatus('Planning Center connected successfully.', 'success');
    window.history.replaceState({}, '', window.location.pathname);
  } else if (urlParams.get('pco_error')) {
    const detail = urlParams.get('detail') || '';
    pcoSetMsg('pco-creds-msg', 'Planning Center sign-in failed or was cancelled.' + (detail ? ' Error: ' + detail : ' Please try again.'), 'error');
    window.history.replaceState({}, '', window.location.pathname);
  }
}

function initGoogle() {
  const hint        = document.getElementById('google-creds-hint');
  const connectBtn  = document.getElementById('google-connect-btn');
  const disconnBtn  = document.getElementById('google-disconnect-btn');
  const msgEl       = document.getElementById('google-oauth-msg');
  const pickerCard  = document.getElementById('google-cal-picker-card');
  const icalCard    = document.getElementById('google-ical-card');

  const params = new URLSearchParams(window.location.search);
  if (params.has('google_connected')) {
    msgEl.textContent = 'Google Calendar connected!';
    msgEl.className = 'pco-msg success';
    window.history.replaceState({}, '', '/');
  } else if (params.has('google_error')) {
    const err = params.get('google_error');
    msgEl.textContent = err === 'denied' ? 'Authorization cancelled.' : 'Connection failed. Please try again.';
    msgEl.className = 'pco-msg error';
    window.history.replaceState({}, '', '/');
  }

  if (_publicConfig.googleConfigured) {
    hint.textContent = 'Connected to Google Calendar.';
    connectBtn.style.display = 'none';
    disconnBtn.style.display = '';
    pickerCard.style.display = '';
    icalCard.style.display = 'none';
    googleLoadCalendarList();
  } else {
    hint.textContent = isDesktopMode()
      ? 'Sign in with Google using the app connection to automatically populate the "This Week" calendar page.'
      : 'Sign in with Google to automatically populate the "This Week" calendar page.';
    connectBtn.style.display = '';
    disconnBtn.style.display = 'none';
    pickerCard.style.display = 'none';
    icalCard.style.display = '';
  }

  connectBtn.addEventListener('click', () => {
    window.location.href = '/oauth/google/start';
  });

  disconnBtn.addEventListener('click', async () => {
    await apiFetch('/api/google-disconnect', 'POST', {});
    _publicConfig.googleConfigured = false;
    initGoogle();
  });

  document.getElementById('google-cal-save-btn').addEventListener('click', async () => {
    const checks = document.querySelectorAll('#google-cal-list input[type=checkbox]');
    const ids = [...checks].filter(c => c.checked).map(c => c.value);
    await apiFetch('/api/settings', 'POST', { googleCalendarIds: ids });
    setStatus('Calendar selection saved.', 'success');
  });

  document.getElementById('google-cal-refresh-list-btn').addEventListener('click', googleLoadCalendarList);
}

async function googleLoadCalendarList() {
  const listEl = document.getElementById('google-cal-list');
  listEl.innerHTML = '<span style="font-size:0.78rem;color:var(--muted);">Loading…</span>';
  try {
    const data = await apiFetch('/api/google-calendars');
    const savedIds = new Set(_serverSettings.googleCalendarIds || []);
    listEl.innerHTML = '';
    (data.calendars || []).forEach(cal => {
      const label = document.createElement('label');
      label.style.cssText = 'display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;margin-bottom:0.25rem;cursor:pointer;';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = cal.id;
      cb.checked = savedIds.has(cal.id) || (cal.primary && savedIds.size === 0);
      label.appendChild(cb);
      label.appendChild(document.createTextNode(cal.summary + (cal.primary ? ' (primary)' : '')));
      listEl.appendChild(label);
    });
    if (!data.calendars || data.calendars.length === 0) {
      listEl.innerHTML = '<span style="font-size:0.78rem;color:var(--muted);">No calendars found.</span>';
    }
  } catch (e) {
    listEl.innerHTML = `<span style="font-size:0.78rem;color:var(--danger);">${e.message}</span>`;
  }
}

// Clicking Connect Planning Center navigates to OAuth start
document.getElementById('pco-connect-btn').addEventListener('click', () => {
  window.location.href = '/oauth/pco/start';
});

document.getElementById('pco-disconnect-btn').addEventListener('click', async () => {
  if (!confirm('Disconnect Planning Center? You can reconnect any time.')) return;
  try {
    await apiFetch('/api/pco-disconnect', 'POST', {});
    _publicConfig.pcoConfigured = false;
    pcoShowCredsView();
    setStatus('Planning Center disconnected.', 'success');
  } catch (e) {
    setStatus('Could not disconnect — try again.', 'error');
  }
});

// ─── Refresh Conflicts Dialog ─────────────────────────────────────────────────
// Shows a per-item review when a PCO re-import finds that Planning Center has
// different content for items the user has already edited.
// ─── Refresh Conflicts Dialog ─────────────────────────────────────────────────
// When pendingWithNotes or pendingUnmatched are present they are appended as
// additional sections in the same dialog so the user only sees one modal.
function showRefreshConflictsDialog(conflicts, pendingWithNotes = [], pendingUnmatched = []) {
  const body = document.getElementById('irm-body');
  body.innerHTML = '';

  // ── Conflicts section ────────────────────────────────────────────────────────
  const h = document.createElement('div');
  h.className = 'irm-section-label';
  h.textContent = 'Items with Updated Content from Planning Center';
  body.appendChild(h);

  const desc = document.createElement('p');
  desc.className = 'irm-desc';
  desc.textContent = 'Planning Center has different content for the items below. Your edits have been kept by default \u2014 choose \u201CUse PCO\u201D for any item you want to override.';
  body.appendChild(desc);

  const conflictSelections = new Map();
  conflicts.forEach(({ idx }) => conflictSelections.set(idx, 'mine'));

  conflicts.forEach(({ idx, title, prevDetail, pcoDetail }) => {
    const card = document.createElement('div');
    card.className = 'irm-song-card';

    const titleEl = document.createElement('div');
    titleEl.className = 'irm-song-title';
    titleEl.textContent = title;
    card.appendChild(titleEl);

    const groupName = 'irm-rc-' + Math.random().toString(36).slice(2);

    const { row: row1 } = irmRadioRow(groupName, 'Keep my current edit', true, () => conflictSelections.set(idx, 'mine'));
    card.appendChild(row1);
    const prevFirst = prevDetail.split('\n').map(l => l.trim()).find(l => l) || '';
    if (prevFirst) {
      const prev = document.createElement('div');
      prev.className = 'irm-preview-text';
      prev.textContent = '\u201C' + prevFirst.slice(0, 90) + (prevFirst.length > 90 ? '\u2026' : '') + '\u201D';
      card.appendChild(prev);
    }

    const { row: row2 } = irmRadioRow(groupName, 'Use Planning Center data', false, () => conflictSelections.set(idx, 'pco'));
    card.appendChild(row2);
    const pcoFirst = pcoDetail.split('\n').map(l => l.trim()).find(l => l) || '';
    if (pcoFirst) {
      const prev2 = document.createElement('div');
      prev2.className = 'irm-preview-text';
      prev2.textContent = '\u201C' + pcoFirst.slice(0, 90) + (pcoFirst.length > 90 ? '\u2026' : '') + '\u201D';
      card.appendChild(prev2);
    }

    body.appendChild(card);
  });

  // ── Append song sections inline (no second dialog needed) ────────────────────
  const withNotesSelections  = irmBuildWithNotesSection(body, pendingWithNotes);
  const unmatchedSelections  = irmBuildUnmatchedSection(body, pendingUnmatched);

  // ── Wire buttons ─────────────────────────────────────────────────────────────
  document.getElementById('irm-apply-btn').onclick = () => {
    conflicts.forEach(({ idx, pcoDetail }) => {
      if (conflictSelections.get(idx) === 'pco' && items[idx]) {
        items[idx].detail = pcoDetail;
      }
    });
    irmApplyWithNotes(pendingWithNotes, withNotesSelections);
    irmApplyUnmatched(pendingUnmatched, unmatchedSelections);
    renderItemList();
    renderPreview();
    scheduleProjectPersist();
    closeImportReviewDialog();
  };
  document.getElementById('irm-cancel-btn').onclick = closeImportReviewDialog;
  document.getElementById('irm-close-btn').onclick  = closeImportReviewDialog;

  const hasExtra = pendingWithNotes.length || pendingUnmatched.length;
  document.getElementById('irm-title').textContent = hasExtra ? 'Review Imported Plan' : 'Review Refreshed Plan';
  document.getElementById('import-review-modal').style.display = 'flex';
}

