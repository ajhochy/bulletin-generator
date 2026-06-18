# Project State — bulletin-generator

## Current focus

Maintenance + closing out the Supabase/Electron migration. `main` contains the full Supabase + multi-tenant + Electron migration (PR #276 merged `8212654`); Electron now runs as a true anon-key + RLS client and `DATABASE_URL` is removed from the release workflow (extractable-creds risk closed). Active thread: issue #299 — e2e settings pollution sweep + a server-side prevention guard.

## Active branch / PR

Branch `fix/issue-299-e2e-settings-pollution-sweep` (working tree clean). Draft PR open for #299 (intentionally non-closing — destructive prod sweep is a manual step). PR stays open until the production `--execute` sweep runs.

## In progress

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
