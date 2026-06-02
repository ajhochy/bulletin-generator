# 016: End-to-end multi-tenant QA

**Milestone:** M5  ·  **Plan ref:** issue 20
**Depends on:** 014, 015

## Context

Before the production cutover (issue 018), the entire system must be verified end-to-end with two real workspaces and two users per workspace, exercising the security and collaboration surfaces that matter most. This is a structured manual smoke matrix — no new code is written; the deliverable is a documented pass/fail result and a sign-off in `docs/ai/project-state.md`.

## Acceptance criteria

- [ ] **Setup**: Two staging workspaces seeded (`Workspace A` = Visalia CRC data, `Workspace B` = a test church with synthetic data). Two users per workspace (User A1 + A2 for workspace A, User B1 + B2 for workspace B). Users A1 and A2 are NOT members of workspace B, and vice versa.
- [ ] **Cross-tenant isolation**: User A1 logs in, attempts to access any Workspace B resource (via API directly or browser devtools) → all attempts return 0 rows or 403. No Workspace B data visible. BLOCKER if any cross-tenant data leaks.
- [ ] **Within-workspace sharing**: User A1 creates a project; User A2 (logged in separately) can open and edit it. 409 conflict UX fires correctly when A1 and A2 save concurrently.
- [ ] **Revision history**: User A1 makes and saves 3 edits; revision history endpoint returns 3 entries; User A1 can restore to revision 1 and the correct state loads.
- [ ] **PDF export**: User A1 exports a project to PDF (Electron + `printToPDF`); output visually matches pre-migration baseline (pagination, images, fonts, QR codes).
- [ ] **PCO import**: User A1 imports a service plan from Planning Center; items appear in the order-of-worship list; notes hidden from print.
- [ ] **Calendar fetch**: User A1 fetches calendar events; events filtered to the current week appear in the announcements section.
- [ ] **Image/font isolation**: User B1 cannot access User A1's uploaded cover image or font (confirmed via direct Storage URL attempt → 403 or 404 from RLS).
- [ ] **Electron auto-update**: a new version is published; the running Electron app detects it and completes the update.
- [ ] **Session persistence**: close and reopen Electron; session is restored without re-login.
- [ ] All smoke-matrix items checked off in `MANUAL-STEPS.md` or a dedicated `docs/ai/qa-matrix-m5.md`. Any BLOCKER items must be resolved before issue 018.

## Likely files

- `MANUAL-STEPS.md` or `docs/ai/qa-matrix-m5.md` (new — the smoke matrix checklist)
- `docs/ai/project-state.md` (update — record QA pass/fail)

## Tests / validation

This issue is entirely manual smoke testing. Automated tests (RLS isolation, unit tests, vitest) must be green before QA begins:

```bash
pytest -v
npm test
```

Then execute the manual matrix above against the staging Supabase project with real Electron builds from issue 014.

## Data-safety / out of scope

- Staging data only — never run this QA against the production Synology deployment.
- If any cross-tenant leak is found, issue 016 is a BLOCKER; do not proceed to issue 017 or 018.
- Out of scope: load testing or concurrency beyond 2 simultaneous users — that is a post-v1 concern.
- Out of scope: iOS/Android clients — desktop (Electron) + browser-server are the v1 targets.
