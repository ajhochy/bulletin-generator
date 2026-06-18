---
date: 2026-06-08
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# next-week-offering: per-project opt-* gate, first-line cause rule, offering decoupled from volunteer checkbox

**Context.** Visalia CRC's bulletin OFFERING text comes from the selected week's PCO note; the "next week's offering is for X" line was typed by hand. Automate it: on import + re-sync, pull the next plan's OFFERING note and append the line to this week's OFFERING item.

**Decision — gate is a per-project `opt-next-week-offering` checkbox, not a global `settings.autoNextWeekOffering`.** The task floated a global setting, but there is no exported frontend settings getter (`_serverSettings` is module-private in `api.js`), and the user asked for the toggle to live in the Document Options dropdown alongside the existing `opt-*` page-inclusion checkboxes. Implemented exactly like the siblings: `state.js` DOM ref, `projects.js` collect (`!!checked`) + restore in both `applyProjectState` blocks (`!== false`, default ON) + reset-to-true in `clearEditorForNewProject`, `formatting.js` change listener (renderPreview + persist). Read at import time via the DOM ref. **Consequence:** the toggle is per-project (saved in project state), not a workspace/global default — matches the other Document Options toggles. Server mode unchanged.

**Decision — cause = first non-empty line of the next OFFERING note** (strip surrounding `*`/`**`/`***`), per the user. Not "first bolded token." `deriveNextWeekOfferingCause` returns '' for blank/non-string so callers skip cleanly.

**Decision — pure logic in `pco-core.js`, exposed via the `main.js` globalThis bridge.** `deriveNextWeekOfferingCause` + `applyNextWeekOfferingLine` are pure and vitest-tested (7 contract tests c1–c7). `applyNextWeekOfferingLine` always strips any existing managed line (matched by the `NEXT_WEEK_OFFERING_PREFIX` constant) before appending, so re-running is idempotent and a new cause replaces the old in place; an empty cause removes-only. This is what makes re-sync non-duplicating even though the re-sync merge restores the user's prior detail (which already contains the previous line).

**Decision — offering refresh is decoupled from the volunteer checkbox.** `pcoFetchAndApplyServing` is invoked from the resync diff dialog's Apply handler **only when the volunteer checkbox is checked** (`serveCallback`). The offering line must refresh on every applied re-sync regardless, so a separate `offeringCallback` param was added to `showResyncDiffDialog` and is invoked unconditionally (after conflict resolution, so it sees the OFFERING item's final detail). On the import path and the no-changes resync path it is called directly next to `pcoFetchAndApplyServing`.

**Decision — underivable/missing cases silently skip** (no next plan, no next OFFERING note, no OFFERING item, empty cause, feature toggled off): the wiring early-returns and leaves detail untouched, per the "silently skip" requirement, rather than stripping a stale line. The whole next-plan fetch is wrapped in try/catch (best-effort) mirroring `pcoFetchAndApplyServing`, so a failure never breaks the import.

**Consequences.** New `pcoFetchAndApplyNextWeekOffering` in `pco.js`; one extra param on `showResyncDiffDialog`; additive `opt-*` checkbox. c8–c11 (live import/re-sync behavior, gate suppression, best-effort failure) are manual-smoke only — no module seam around `pcoGet`/DOM.
