---
type: project
---

# Project State — bulletin-generator

## Current focus

Maintenance + closing out the Supabase/Electron migration. `main` contains the full Supabase + multi-tenant + Electron migration (PR #276 merged `8212654`); Electron now runs as a true anon-key + RLS client and `DATABASE_URL` is removed from the release workflow (extractable-creds risk closed). Active thread: issue #299 — e2e settings pollution sweep + a server-side prevention guard.

## Active branch / PR

Branch `fix/issue-299-e2e-settings-pollution-sweep` (working tree clean). Draft PR open for #299 (intentionally non-closing — destructive prod sweep is a manual step). PR stays open until the production `--execute` sweep runs.

## In progress

- **Cutover re-sync + Electron OAuth `will-redirect` fix (folded 2026-09-29 from `workflow/cutover-resync-2026-06-09`, tip `47a765a`).** Adds `scripts/resync_synology_to_supabase.py` (Synology-wins upsert; dry-run default), corrects the `cutover-plan.md` `--source` path, and intercepts the `bulletingen://auth-callback` deep link on `will-redirect` as well as `will-navigate` (v1.12.14). Not yet on `main` before this consolidation; open issue #298 (re-sync strips PCO/Google OAuth tokens) follows from it. Details: `docs/ai/runs/2026-06-09-cutover-resync-and-electron-oauth-fix.md`, decision `docs/ai/decisions/2026-06-09-cutover-re-sync-synology-json-supabase-synology-wins-new-upsert.md`.
- **#299 production sweep (MANUAL, destructive).** Prevention guard + dry-run sweep verified; dry-run confirmed 2 stray keys (`_screenshots`, `_testKey`) in the Visalia CRC workspace row. Finish by running `APP_MODE=server python scripts/sweep_settings_test_keys.py --execute` from repo root with `.env` loaded, then verify c4/c5.
- **next-week-offering residual manual checks** (shipped v1.12.13): toggle-off suppression + best-effort next-plan fetch failure still unsmoked (low risk; unit-covered).
- Manual smoke gaps carried from prior runs: issue 023 presence read-only (needs 2 live users), OAuth connect-path workspace scoping (needs 2 workspaces), packaged Electron #279/#280 (stale-sidecar reap + onedir cold-start need a packaged build).

## Risks / known issues

- **🔴→ now CLOSED in build config:** extractable `DATABASE_URL` in the Electron DMG (#277) — removed from `release-electron.yml` (takes effect on next Electron build). Old draft betas `electron-supabase-beta-v0.0.1/2/3` still bundle it — delete them; rotate DB password if a build leaked.
- Automated coverage is partial: pytest covers `server.py` utils/handlers, vitest covers `src/js/modules/*` pure logic; UI + Electron launch are manual-only.
- `npm audit` flags electron transitive-dep vulns (devDependencies only).
- `package-lock.json` may need regeneration (`electron-updater` added to deps).
- Windows NSIS installer is unsigned (SmartScreen warns until an EV/OV cert exists).
- `worship-booklet.html` (legacy 9k-line standalone) still has old revision/stale-check code — not in the active modular build; not a runtime risk.
- `provision_first_login` (issue 008) has no live-DB integration test.

## Test status

- `python3 scripts/run_ai_workflow.py checks --level pr` last run PASS (173 pytest CI subset, 133 vitest / 1 skipped, vite build green).
- #299 contract: `tests/contract/test_issue_299.py` 7 passed (red→green). c4/c5 are manual (post-sweep prod state + live-lane byte-identical row).
- See `testing-guide.md` for the full validation surface and manual-only items.

## Next step

1. Run the #299 production `--execute` sweep (manual, destructive), verify c4/c5, then close #299.
2. Manual smoke handoff for #279/#280/#294 on a packaged Electron build (stale-sidecar reap, onedir cold-start, PCO import + Google Calendar via REST path).
3. Work the QA matrix in `docs/ai/qa-matrix-m5.md` during the cutover session (RLS/auth security suite + manual multi-tenant items).

---
**Run history:** one file per run under `docs/ai/runs/` (surfaced as `ai-runs/`). This snapshot is overwritten in place.

## Consolidation 2026-09-29

- **Mega branch:** `mega/2026-09-29-consolidation`, draft PR https://github.com/ajhochy/bulletin-generator/pull/301. Tracking issues: https://github.com/ajhochy/bulletin-generator/issues/302 (consolidation) and https://github.com/ajhochy/bulletin-generator/issues/303 (cutover re-sync + Electron OAuth `will-redirect` fix; `v1.12.14` tag is not on `main`).
- **Folded refs (name + tip SHA):**
  - `backup/local-main-pre-release-251` `bc70ce79f935e7c87a90801d5da048f77545dae9` (AGENTS.md/CLAUDE.md kept as main)
  - `stash-backup/0-2026-09-29` (from `stash@{0}`) `266e1664dd0491ccc77242cb22b3880c8fedf975`
  - `workflow/cutover-resync-2026-06-09` local `47a765a0f58470444ed183ef42d5457026e3fce1` (origin `bc29451170517e4dcd249fa97bcd7b987a7a3ce0`)
  - local `fix/issue-299-e2e-settings-pollution-sweep` WIP snapshot `4f5c3fe9fd8dcccee4841754b4fa47ad701f0637`
- **Dropped refs (bundle: `/Users/ajhochhalter/Documents/.consolidation-backups/bulletin-generator-2026-09-29.bundle`):** squash-merged via PR with head == tip: `feat/issue-181-editor-toolbar` (#183), `fix/issue-189-pdf-css-vars` (#228), `fix/explicit-default-font` (#229), `fix/lightweight-projects-poll` (#255), stale `origin/{chore/bootstrap-ai-workflow-docs (#254), fix/volunteer-roles-toggle (#251), fix/volunteer-roles-render-on-startup (#252), fix/template-editor-volunteer-roles-not-selectable (#253), fix/ci-node-bump-lazy-chrome (#282), fix/e2e-presence-flake (#283)}`; superseded docs-only `fix/watchtower-config`; and every branch already an ancestor of `origin/main` (`Volunteer-Roles-Page`, `claude/*`, `docs/277-progress`, `feat/supabase-multitenant-electron`, `fix/e2e-live-pco-refresh-creds`, `fix/next-week-offering`, `issue-216`, `issue-277-A..G`, `test/*`, 20 `worktree-agent-*`).
- **In-flight worktrees:** none (no live process in any linked worktree).
- **Cleanup script (not run yet):** `/Users/ajhochhalter/Documents/.consolidation-backups/cleanup/bulletin-generator-2026-09-29-cleanup.sh`; manifest beside it.
