---
date: 2026-06-11
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# Issue #299: `_`-prefix is a reserved test namespace in workspace_settings

**Context.** The nightly E2E Live lane signs in as `e2e-live@e2e.bulletin.test`, a viewer in the **production** Visalia CRC workspace. `POST /api/settings` is merge-style, so any settings write a (now-removed) e2e spec performed merged into the production `workspace_settings` row, leaving `_testKey` and `_screenshots`. The dry-run sweep confirmed exactly those 2 keys in workspace `614505d2-…94fe` and no others.

**Decision — define `_`-prefixed settings keys as a reserved test-only namespace.** The product uses no `_`-prefixed top-level settings key, so treating the `_` prefix as reserved gives a single, durable rule for both prevention and cleanup without enumerating individual test keys.

**Decision — prevention is a server-side guard, not (only) a test convention.** `server.py` gains a pure `_strip_reserved_settings_keys(partial)` applied in `_handle_post_settings` before the merge, so a stray test write can never persist regardless of which client/spec sends it. The live-lane "read-only by convention" rule (documented in `tests/e2e/README.md` + a comment on the `live` project in `playwright.config.ts`) remains the primary rule; the server guard is defense-in-depth. Alternatives considered: rely on convention alone (rejected — already failed once); reject the whole POST with 4xx (rejected — would break a legit write that merely *includes* a stray key; silent strip is safer and matches the merge handler's forgiving style).

**Decision — cleanup is a reviewable Python script, dry-run by default.** `scripts/sweep_settings_test_keys.py` mirrors `scripts/migrate_to_supabase.py`: dry-run is the default, `--execute` opts in, connects via `db.admin_transaction()` (service_role/owner, RLS-bypassing), one transaction. Pure helpers `find_test_keys()` / `clean_settings()` are module-level and unit-tested. **The destructive `--execute` against production is intentionally left as a manual step** (see PR body) — this PR ran only the dry-run.

**Consequences.** `_handle_post_settings` strips `_` keys (the merge still treats `null` as delete for legit keys). The sweep removes only `_`-prefixed keys; OAuth tokens, branding, volunteer roles are preserved byte-identically. c4 (post-sweep prod state) and c5 (live-lane byte-identical row) are manual — they require executing against / running the lane against production.
