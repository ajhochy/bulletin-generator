# Exhaustive Playwright E2E Suite — Design

**Date:** 2026-06-05
**Status:** Approved design, pending implementation plan
**Author:** AI pairing session with @ajhochy

---

## 1. Goal

Build an exhaustive, durable Playwright end-to-end test suite that guards every future
change to Bulletin Generator. It must exercise the *real* application stack — real
`server.py`, real Supabase (auth + multitenancy + RLS), real PCO API, real Google
Calendar, real headless-Chrome PDF generation — and cover every tab, button, field,
modal, render path, export, and persistence flow, while remaining trustworthy enough
to gate every pull request.

Non-goal: replacing the existing `vitest` unit specs in `tests/*.spec.js`. Those remain
the fast inner loop. This suite is the integration/E2E layer above them.

---

## 2. The central tension and its resolution

A PR-blocking gate that depends on live third parties (PCO, Google) will go red for
reasons unrelated to the change under test: third-party downtime, OAuth token expiry,
rate limits, and the interactive consent screen that cannot be clicked headlessly. A
flaky gate gets ignored — strictly worse than no gate.

**Resolution: two lanes that share Page Objects, fixtures, helpers, and test bodies.**

| | **Lane A — Core (PR gate)** | **Lane B — Live (real integrations)** |
|---|---|---|
| Backend | Real `server.py`, server mode | Real `server.py`, server mode |
| Supabase | Real hosted test project, **ephemeral isolated user/workspace per run** | Real hosted test project, `worship@visaliacrc.com` account |
| PCO / Google | **Recorded/replayed** real responses (deterministic) | **Live API**, read-only, using the workspace's already-connected tokens |
| PDF | Real headless Chrome | Real headless Chrome |
| Runs | Every push/PR, **blocking** | Nightly cron + `workflow_dispatch` + `run-live` PR label, **soft-report** |
| Answers | "Did this change break the app?" | "Do the real integrations still work end-to-end?" |

Properties:

- **The Live lane is the fixture-refresh mechanism.** When Lane B runs against live
  PCO/Google, it can re-record the HTTP exchanges that Lane A replays — so the
  deterministic gate never drifts from reality.
- **The interactive OAuth consent screen is never automated.** Lane B inherits the
  `worship@` workspace's already-connected tokens; Lane A's ephemeral users have nothing
  connected, so their PCO/Google paths are served from recordings.
- **Isolation via the app's own multitenancy.** Both lanes hit the real hosted Supabase
  project. Lane A stays deterministic because each CI run gets its own throwaway user +
  workspace; RLS guarantees parallel runs cannot see each other's rows.

**Accepted dependency:** the PR gate depends on hosted Supabase being reachable. This is
a controlled, highly-reliable, first-party dependency (unlike PCO/Google) and is the
deliberate price of the fidelity requirement.

---

## 3. Architecture & repository layout

```
tests/
  unit/                      # existing vitest specs — unchanged, still the fast loop
  e2e/
    fixtures/                # seed JSON: projects, songs, settings, templates, announcements
    recordings/              # captured PCO/Google HTTP (HAR) for Lane A replay
    pages/                   # Page Object Model — one module per feature area
      EditorPage.ts ProjectsPage.ts PcoPanel.ts CalendarPanel.ts
      SongDbPage.ts FormatPage.ts TemplatesPage.ts SettingsPage.ts
      AnnouncementsPanel.ts StaffPanel.ts VolunteerRolesPanel.ts
      PreviewPane.ts AuthFlow.ts
    flows/                   # golden-path, multi-feature journeys
    features/                # exhaustive per-area specs (every control + route)
    helpers/
      server.ts              # boot real server.py in server mode, wait-for-ready, teardown
      supabase.ts            # create/seed/delete ephemeral user + workspace (service_role)
      auth.ts                # programmatic sign-in, storageState reuse
      clock.ts               # page.clock helpers for debounces/heartbeat/cache
      pdf.ts                 # validate PDF bytes + page count; snapshot print HTML
      record-replay.ts       # PCO/Google HAR record (live) / replay (core)
  playwright.config.ts       # two projects: "core" and "live"; shared use{} config
```

### Testing pyramid

1. `vitest` unit specs (existing) — pure functions, fast.
2. Playwright **core** — deterministic integration/E2E; the PR gate.
3. Playwright **live** — real third-party integrations; scheduled/on-demand.

---

## 4. Enabling code changes (prerequisites — approved)

Small, low-risk, user-invisible edits to the app source that make reliable testing
possible:

1. **Stable selectors on dynamic rows.** Add `data-testid` / `data-index` at render time
   to every repeated row: order-of-worship items, announcements, welcome items,
   volunteers, volunteer roles, staff, song-db items, calendar events, template cards.
   Rationale: the survey confirmed these render without stable hooks; "click the Nth
   row's remove button" is otherwise fragile.
2. **Test-determinism seam.** Primary mechanism is Playwright's `page.clock` to control
   time deterministically across the known timers:
   - preview debounce 250ms, persist/autosave debounce 350ms
   - presence heartbeat 30s, files auto-refresh 30s
   - calendar cache 15min, toast dismiss 3s, designer render 300ms
   Where `page.clock` cannot drive a behavior, a guarded `window.__E2E__` flag (set only
   when an explicit test env var is present) shrinks the interval. The flag must be inert
   in production builds.
3. **No behavioral changes.** These edits add hooks only; they must not alter runtime
   behavior for real users.

---

## 5. Determinism strategy

- **Time:** `page.clock.install()` + `fastForward`/`runFor`; never `waitForTimeout`.
- **PCO/Google in Lane A:** route interception serving recorded HAR; recordings live in
  `tests/e2e/recordings/` and are refreshed by Lane B.
- **Supabase isolation (Lane A):** per-run ephemeral user + workspace created in global
  setup via `service_role` admin key; deleted in global teardown. Seed fixtures scoped to
  that workspace.
- **PDF assertion:** PDF bytes are non-reproducible. Assert `/api/pdf` → 200, valid `%PDF`
  magic bytes, and expected page count. For visual regression, snapshot the *print-ready
  HTML preview* (stable DOM), not the rasterized PDF.
- **Downloads:** use Playwright's `page.waitForEvent('download')` and assert filename +
  content type + non-empty body, rather than racing the browser's download lifecycle.
- **Traces:** record trace/video/screenshot on failure; upload as CI artifacts.

---

## 6. Coverage matrix (definition of "exhaustive")

Every surface below maps to at least one test, tracked to completion with a `@core` /
`@live` tag. Source inventory: full UI + API survey performed 2026-06-05.

### Navigation
- All 6 tabs (`page-editor`, `page-files`, `page-songdb`, `page-format`,
  `page-templates`, `page-settings`) render and switch; keyboard nav (arrows/Home/End);
  `aria-selected` correctness.

### Editor — File / Sync / Document dropdowns
- File: bulletin title, Save, Save New Version, New, Delete, Browse, project meta,
  presence badge.
- Sync (PCO): connect view, service-type select, plan select, show-past toggle, Import,
  Refresh, ignore chips add/remove, disconnect.
- Document: service title/date, cover image upload + clear, all 8 `#opt-*` toggles,
  booklet-size targets (auto/8/12).

### Editor — content sections
- Order of worship: add item, add page break, every item type
  (song/liturgy/label/section/note/media), title + detail edit, per-item format override,
  remove, **drag-reorder**, move up/down.
- Welcome: heading, add/remove items.
- Announcements: add/remove, title/body/url edit, page-break toggles.
- Volunteers: rows from PCO import, name/role/time edit, remove, empty/error states.
- Volunteer Roles: add/remove, title/body/url edit.
- Staff: add person, name/role/email, move up/down, remove, email linking.
- Calendar: refresh, manual add/edit/delete event, all-day toggle.

### Preview pane
- Empty state → populated; page-split correctness (section stickiness, forced breaks);
  `.preview-linkable` click scrolls editor; page-count display.

### Projects (Files tab)
- New, import JSON, per-card open/select, bulk: select-all, export ProPresenter,
  download JSON, download PDFs, delete-selected, clear; server-mode subtabs (My/Workspace).

### Song Database
- Add manually (title/author/lyrics/copyright), edit, delete; search; all sort options;
  source filter; paste-from-clipboard (incl. fallback dialog); ProPresenter import
  (disclaimer → import → preview modals); export/import JSON; clear-all.

### Format
- Page-size select; per-type formatting cards for every type; filter; save; reset;
  verify override precedence (`getEffectiveFmt`).

### Templates
- Apply built-in (apply dialog confirm/cancel); designer overlay (open, edit element
  formatting, name, save, save-as, export, back); import; new; font upload/list/delete.

### Settings
- Identity (server: display name); Branding (church name, give URL, logo upload/clear);
  Google Calendar (connect/disconnect, calendar picker save/refresh, Drive folder,
  iCal URLs save/reset, exclude titles save); Serving teams filter; Song DB export/import/
  clear; App Updates (current version, check, banner, apply [desktop], progress).

### Auth & server-mode behaviors
- Login screen (magic link + Google sign-in); `/api/me`; logout; ownership enforcement
  (non-owner POST → 403 → toast); read-only banner + Duplicate; 409 conflict dialog (all
  three buttons: review, save-as-copy, replace); stale-revision poll banner; presence
  badge with second editor; workspace members.

### API routes (each hit ≥ once, status + side effect asserted)
- `/api/bootstrap`, `/api/projects` (GET/POST/DELETE, `?id=`, `/revisions`),
  `/api/announcements`, `/api/volunteer-roles`, `/api/settings`, `/api/songs`,
  `/api/templates` (GET/POST/DELETE), `/api/fonts` (GET/POST/DELETE), `/api/pdf`,
  `/api/propresenter-export`, `/api/drive/upload`, `/api/presence` (GET/POST/DELETE),
  `/api/google-calendars`, `/pco-proxy/*`, `/cal`, `/api/admin/check-update`,
  `/api/admin/apply-update`, `/api/me`, `/api/workspace/members`, `/auth/*`.

### Golden-path flows (Lane A recorded + Lane B live)
1. PCO import → edit items → autosave → save named version → export PDF.
2. Build bulletin from scratch (no PCO) → all sections → export.
3. Bulk export (JSON + PDF + ProPresenter) of multiple projects.
4. Google Calendar connect (Lane B: pre-connected) → select calendars → events render.
5. Conflict: two sessions → 409 → each resolution path.

Each matrix row carries a tracking status so completeness is measurable, not aspirational.

---

## 7. CI wiring

- **`.github/workflows/e2e-core.yml`** — on push/PR. Sets up Python + Node + Chromium;
  installs Playwright browsers; provisions ephemeral Supabase user/workspace; boots
  `server.py` in server mode; runs `@core` project. **Blocks merge.** Uploads
  trace/video/screenshot artifacts on failure. Tears down the ephemeral identity.
- **`.github/workflows/e2e-live.yml`** — nightly cron + `workflow_dispatch` +
  `run-live` PR label. Reads `worship@visaliacrc.com` credentials and Supabase project
  URL/anon/`service_role` keys from **GitHub Secrets**. Runs `@live` read-only.
  Optionally re-records PCO/Google fixtures and opens a PR if they changed.
  **Soft-report** by default; can be marked required on release branches.
- **Secrets required:** Supabase project URL, anon key, `service_role` key (setup/
  teardown), `worship@` auth credential, any PCO/Google config the server needs.

### Local scripts (package.json)
- `test:e2e` — Lane A core
- `test:e2e:live` — Lane B live
- `test:e2e:ui` — Playwright UI mode for debugging
- existing `test` (`vitest run`) unchanged

---

## 8. Delivery sequence

"Exhaustive from day one" is the target coverage, but it must be built in dependency
order so each PR is reviewable. This is an **epic** — one issue per layer/area, landing
incrementally toward full matrix coverage on a shared feature branch.

1. **Foundation** — `playwright.config.ts`; helpers (`server`, `supabase`, `auth`,
   `clock`, `pdf`, `record-replay`); the `data-testid` selector pass + `window.__E2E__`
   seam. Exit: one smoke test green in both lanes.
2. **Page Object layer** — all feature-area page objects with typed accessors.
3. **Golden-path flows** — highest-value end-to-end journeys (§6 flows).
4. **Exhaustive per-feature specs** — fill every remaining matrix row.
5. **CI workflows** — core gate, then live lane + fixture auto-refresh.

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Live lane flakiness from PCO/Google | Lane B is non-blocking; only Lane A (recorded) gates PRs. |
| `worship@` tokens revoked/expired | Live lane fails loudly (alert), gate unaffected; document re-connect runbook. |
| Hosted Supabase outage blocks gate | Accepted; first-party reliable dependency; retry-with-backoff on setup. |
| Recordings drift from real APIs | Live lane re-records and PRs the diff; recordings reviewed like code. |
| `service_role` key in CI | Stored as GitHub Secret; scoped to a dedicated test project, never prod. |
| Ephemeral-user buildup if teardown fails | Idempotent teardown + periodic sweep of `e2e-*` users. |
| Desktop/Electron paths not covered by server-mode suite | Out of scope for v1; a thin Electron boot-smoke can be a later epic issue. |
| PDF non-determinism | Assert structure + page count; visual-snapshot stable preview HTML, not PDF raster. |

---

## 10. Open items to resolve during planning

- Exact mechanism for seeding an ephemeral workspace (Supabase admin API vs. app
  bootstrap) — confirm against current `db.py` / `storage.py`.
- Whether PCO Personal Access Token is preferable to the OAuth-stored token for any
  Lane A fixture *recording* step.
- TypeScript vs. plain JS for the suite (repo is ESM; Playwright supports TS out of box).
- Desktop/Electron smoke lane: defer to a follow-up epic (noted in §9).
