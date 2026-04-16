# Template Designer Live Testing Checklist

Use this checklist on the `feat/template-designer` branch. Test with a real or representative bulletin project that includes cover text, announcements, songs, liturgy/labels/sections, calendar events, serving data, and staff data if available.

## Setup

- [ ] Start the app locally and open the browser UI.
- [ ] Load or create a project with at least one song, one liturgy/label item, one announcement, and one non-OOW section such as calendar, serving, or staff.
- [ ] Confirm the app opens without console errors.
- [ ] Confirm existing projects still render with the Classic template by default.

## Template Gallery

- [ ] Open the Templates tab.
- [ ] Confirm Classic and Modern built-in templates are visible.
- [ ] Confirm each template card has Apply, Design, and Export actions.
- [ ] Apply Classic to the project and confirm the preview remains visually consistent with the pre-template app.
- [ ] Apply Modern and confirm the preview visibly changes typography/color/layout.
- [ ] Confirm applying a template persists after reload or project save/load.

## Designer Launch And Save Flow

- [ ] Click Design on a built-in template.
- [ ] Confirm the full-screen designer opens with the current bulletin rendered in the canvas.
- [ ] Click Back without changes and confirm it closes cleanly.
- [ ] Reopen the designer, make a small formatting change, click Back, and confirm the unsaved-change prompt appears.
- [ ] Click Save on a built-in template and confirm it saves as an editable copy rather than overwriting the built-in.
- [ ] Confirm the Apply to Project dialog appears after save.
- [ ] Click Apply and confirm the bulletin preview updates and persists.
- [ ] Use Save As on a custom template and confirm a second custom template appears in the gallery.
- [ ] Delete a custom template and confirm it disappears.
- [ ] Try deleting a built-in template and confirm the UI blocks it.

## Zone Tree And Match Rules

- [ ] Select zones in the left panel and confirm the right match panel updates.
- [ ] Toggle a zone off and confirm that content section disappears from the designer canvas and preview.
- [ ] Toggle the zone back on and confirm the section returns.
- [ ] Reorder zones with up/down or drag-and-drop and confirm preview order changes.
- [ ] Select a PCO zone and change the type match between song, liturgy, section, label, and all.
- [ ] Confirm the specificity badge updates live.
- [ ] Add a specific title-match rule under a PCO type zone.
- [ ] Confirm the child zone appears in the tree.
- [ ] Apply formatting to the child rule and confirm it overrides the parent type rule for that item only.
- [ ] Delete the child rule and confirm the item falls back to the parent/type formatting.

## Formatting Toolbar

- [ ] Click blank canvas space and confirm the toolbar shows global template controls.
- [ ] Change page size and confirm preview/PDF page dimensions update.
- [ ] Change base font and palette colors and confirm the canvas updates.
- [ ] Select a song title and confirm text controls appear.
- [ ] Change font family, size, bold, italic, underline, alignment, and color.
- [ ] Confirm changes are immediately visible in the designer canvas.
- [ ] Click Reset and confirm the selected element returns to inherited/default styling.
- [ ] Deselect and confirm the toolbar returns to global controls.

## Drag And Layout

- [ ] Hover a selectable canvas element and confirm a drag handle appears.
- [ ] Drag a sub-element and confirm snap guides appear near page edges or aligned elements.
- [ ] Release in free space and confirm the element keeps a free-position offset.
- [ ] Drag a compatible sub-element beside a title row and confirm it snaps inline where supported.
- [ ] Save/apply the template and confirm the layout persists after reload.
- [ ] Export PDF and confirm the layout is reflected there too.

## Fonts

- [ ] Open the Fonts section in the Templates tab.
- [ ] Upload a valid `.ttf`, `.otf`, `.woff`, or `.woff2` file.
- [ ] Confirm the font appears in the installed font list.
- [ ] Confirm it appears in designer font pickers with an `(Installed)` badge.
- [ ] Apply the uploaded font to an element and confirm it renders in preview.
- [ ] Export PDF and confirm the uploaded font renders there.
- [ ] Delete the uploaded font and confirm it is removed from the list.
- [ ] Apply a Google-font-based template such as Modern and confirm font CSS is served from `/fonts/cache/...`.

## Import And Export

- [ ] Export a built-in template and confirm a JSON file downloads.
- [ ] Import that JSON and confirm it opens as an editable custom copy, not an overwrite of the built-in.
- [ ] Export a custom template, import it again, and confirm the imported copy matches the original settings.
- [ ] Try importing invalid JSON and confirm the app shows an error without crashing.
- [ ] Confirm imported templates can be saved, applied, exported, and deleted.

## Regression Pass

- [ ] Edit announcement text and confirm preview/autosave still work.
- [ ] Edit OOW items and confirm preview/autosave still work.
- [ ] Change old per-item formatting overrides and confirm they still win over template defaults.
- [ ] Load an older project with no template data and confirm it opens without errors.
- [ ] Generate a PDF from Classic.
- [ ] Generate a PDF from Modern or a custom template.
- [ ] Confirm no data files such as `data/fonts/cache` or `data/fonts/user` are committed.

## Issues/Milestones Covered

- M1 Data Model & Backend: #158, #159, #160, #161
- M2 Rendering Engine: #162, #163, #164, #165
- M3 Designer UI: #166, #167, #168, #169, #170, #171, #177, #178
- M4 Built-in Templates & Font Management: #172, #173, #174, #175, #176
