# Layout Regression Checklist

Manual verification matrix for the Unified Section Layout Model (milestone #117).
Run this checklist after any change to `preview.js`, `projects.js`, `calendar.js`,
`announcements.js`, or `state.js` that touches layout, break controls, or persistence.

---

## How to use

Work through each section below in a browser session with at least one active project.
Check each item as you verify it. A fresh agent picking up this repo should be able
to follow these steps without reading code history.

---

## 1. Order of Worship (OOW) breaks

### 1a. Item-level page break (explicit)
1. In the OOW editor, click the **⊞** (split) icon between two items to insert a page-break item.
2. Preview should show a new page starting at that item.
3. Click **✕ Remove** on the break control between the pages — the break item should be removed
   and the content should flow back onto one page.

### 1b. Auto page break (suppress)
1. Add enough items to the OOW to trigger an automatic page break.
2. Click **✕** on the auto-break control — the break should be suppressed and the content
   should remain on one page.

### 1c. Song stanza separator break
1. On a song item with multiple stanzas, click **⊞** between two stanzas.
2. A `---` separator should appear in the song's detail field; the preview should break at that stanza.
3. Click **✕** to remove — the `---` is removed and stanzas flow together.

### 1d. Liturgy/label paragraph break
1. On a liturgy or label item with multiple paragraphs, click **⊞** between two paragraphs.
2. Preview should break at that paragraph.
3. Click **✕** to suppress — the break is removed.

### 1e. OOW ↔ Announcements merge
1. With both OOW and Announcements enabled, if OOW fits on the last announcements page
   a merge toggle should appear.
2. Click it — OOW merges onto the announcements page.
3. Click **✕** — OOW returns to its own page.

---

## 2. Announcements breaks

### 2a. Manual break before card
1. In the Announcements editor, use the "Break before" toggle on a card.
2. Preview should start a new page before that card.
3. Disable the toggle — the break should disappear.

### 2b. Auto break (suppress)
1. Add enough announcement cards to trigger an auto break.
2. Click **✕** on the auto-break control — `_noBreakBefore` is set and the break is suppressed.

### 2c. Announcement "Break here" split
1. Click **⊞ Break here** between two announcement cards.
2. A new page should start at the second card.
3. Verify the button is responsive and the new break shows a **✕ Remove** control.

---

## 3. Serving schedule breaks

### 3a. Week-level break
1. Import or create a serving schedule with two or more weeks.
2. Click **⊞ Break here** between two weeks in the preview.
3. Preview should start a new page at the second week.
4. Click **✕** — the break is removed.

### 3b. Intra-week team break
1. Click **⊞ Break here** between two service-time groups within the same week.
2. A `{type:'page-break'}` entry should be inserted into `servingSchedule.weeks[i].teams`.
3. Preview should break at that service time.
4. Click **✕** — the page-break team entry is removed.

### 3c. Serving merge toggle
1. With the serving schedule fitting on the last content page, a merge toggle should appear.
2. Click it — serving merges onto the previous page.
3. Click **✕** — serving moves to its own page.

---

## 4. Calendar breaks

### 4a. "Start calendar on new page" toggle
1. With Calendar enabled, click the toggle to start it on a new page.
2. Preview should start a new page at the calendar section.
3. Click **✕** — calendar flows back onto the prior page.

### 4b. Day-group break
1. With multiple calendar day groups, click **⊞ Break here** between two days.
2. The day's date should be added to `calBreakBeforeDates`.
3. Preview should start a new page at that day group.
4. Click **✕** — the date is removed from `calBreakBeforeDates`.

### 4c. Calendar merge toggle
1. With the first calendar group fitting on the last content page, a merge toggle should appear.
2. Toggle on and off — verify the merge state changes.

---

## 5. Staff page breaks

### 5a. "Start on new page" toggle
1. Enable the Staff section.
2. Use the "Start on new page" toggle.
3. Preview should start a new page before the staff section.
4. Click **✕** — staff flows back onto the prior page.

---

## 6. Save/load round-trip

For each layout choice below, verify it survives a project save and reload:

| Layout choice | Where persisted | Round-trip passes? |
|---|---|---|
| OOW item `_noBreakBefore` | `items[i]._noBreakBefore` | ☐ |
| OOW stanza `_noBreakBeforeStanzas` | `items[i]._noBreakBeforeStanzas[]` | ☐ |
| OOW `---` separator | `items[i].detail` text | ☐ |
| OOW paragraph break | `items[i]._forceBreakBeforeParagraph[]` | ☐ |
| Announcement `_breakBefore` | `announcements[i]._breakBefore` | ☐ |
| Announcement `_noBreakBefore` | `announcements[i]._noBreakBefore` | ☐ |
| Serving week `_breakBefore` | `servingSchedule.weeks[i]._breakBefore` | ☐ |
| Serving intra-week team break | `servingSchedule.weeks[i].teams[j].type === 'page-break'` | ☐ |
| Calendar `breakBeforeCalendar` | `breakBeforeCalendar` top-level field | ☐ |
| Calendar `calBreakBeforeDates` | `calBreakBeforeDates[]` top-level field | ☐ |
| Staff `breakBeforeStaff` | `breakBeforeStaff` top-level field | ☐ |
| OOW merge | `bottomMerge.oow` | ☐ |
| Serving merge | `bottomMerge.serving` | ☐ |
| Calendar merge | `bottomMerge.calendar` | ☐ |
| Staff merge | `bottomMerge.staff` | ☐ |

**How to test a round-trip:**
1. Set the layout choice.
2. Save the project (wait for the autosave debounce or click Save).
3. Reload the page (or switch to another project and back).
4. Verify the layout choice is still applied in the preview.

---

## 7. Preview-to-editor navigation

Click each type of element in the preview and verify the editor scrolls to the correct panel:

| Preview element | Expected editor destination |
|---|---|
| OOW item text | Scrolls to that item in the OOW editor |
| Serving section | Scrolls to the Volunteers/Serving panel |
| Calendar section | Scrolls to the Calendar panel |
| Staff section | (no navigation; staff is display-only) |

---

## 8. PDF export

1. With a full bulletin (OOW, announcements, serving, calendar, staff), set at least one
   explicit break or merge toggle in each section.
2. Click **Print / Save as PDF**.
3. Open the generated PDF and verify:
   - All explicit breaks are honored (pages break at the expected places).
   - No section is missing or duplicated.
   - Footer (if enabled) appears on all pages.
   - Serving and calendar sections reflect the same layout as the preview.

---

## 9. Server-mode conflict detection (server mode only)

1. Open the same project in two browser tabs.
2. Make a layout change in Tab A (e.g., set a calendar break) and save.
3. Make a different layout change in Tab B and save.
4. Tab B should receive a **409 conflict** banner.
5. Click "Reload latest" — Tab B should load Tab A's version, including its layout state.

---

## Related files

- `src/js/projects.js` — `collectCurrentProjectState()`, `applyProjectState()`, `applyProjectStateForExport()`
- `src/js/state.js` — all layout globals (`bottomMerge`, `breakBeforeCalendar`, `calBreakBeforeDates`, etc.)
- `src/js/preview.js` — click handler reads `data-breakType` / `data-breakStanzaIdx` etc. to mutate state
- `src/js/calendar.js` — `buildCalendarChunks()`, `buildServingChunks()`
- `docs/ARCHITECTURE.md` — deployment mode and data flow overview

## Related issues

- #117 (umbrella: Unified Section Layout Model)
- #118 (chunk contract)
- #119 (centralize break controls)
- #120 (calendar adapter)
- #122 (this issue: persistence and regression coverage)
- #123 (serving adapter)
