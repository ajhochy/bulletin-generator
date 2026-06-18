---
date: 2026-06-06
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# #216 revision snapshots: application-level, not a DB trigger

**Context.** #216 requires appending a `project_revisions` snapshot on every successful save (regression: only the `/restore` path snapshotted). The initial plan (and the 277-D deferral note) assumed a DB trigger so it would cover both the server (psycopg) and renderer (supabase-js) write paths uniformly.

**Decision.** Implement it **application-level** in `PostgresStorageBackend.save_project` (mirroring `save_project_transactional`), plus a unique index on `project_revisions (project_id, revision_number)`. A DB trigger was rejected for three reasons:
1. **Summary.** `project_revisions.summary` is a stored column produced by `revisions.generate_summary` (Python). A trigger can't run that, so a trigger-based snapshot would lose the #217 summaries (or require porting 176 lines of diff logic to plpgsql).
2. **Deploy gate.** The `supabase/migrations` track isn't applied by CI and the agent is (correctly) blocked from a direct live apply — so a trigger couldn't be verified live by the agent.
3. **Live-regression window.** Removing the existing app-level `/restore` snapshot in favor of an undeployed trigger would stop snapshots in production until the trigger is deployed.

**Consequences.**
- `save_project` now does a 4-statement sequence (SELECT prev state → upsert RETURNING → profiles enrich → INSERT project_revisions), matching the transactional path. Existing `save_project` mocks (`test_project_metadata`, `test_storage_assets`) were updated for the new sequence.
- A unique index migration (`20260606000002_project_revisions_unique_revision.sql`) hard-enforces "unique revision numbers per project" (verified: zero existing dupes). Needs a live `supabase db push` (human-authorized, like 277-B).
- **Renderer (electron) path still needs its own snapshot.** Electron saves go renderer→Supabase, bypassing `save_project`, so they won't snapshot until `supabase-data.js` `sdSaveProject` (277-C/D) inserts a `project_revisions` row. Tracked as a follow-up on the #277 stack.
- Also wired the previously-orphaned `tests/test_revision_snapshots.py` into the CI `python` job (it ran nowhere before).
