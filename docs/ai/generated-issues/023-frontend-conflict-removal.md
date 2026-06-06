# 023: Frontend — remove conflict detection, add presence badge + read-only state

**Milestone:** M5  ·  **Plan ref:** Issue 023 (D7)
**Depends on:** 021, 022

## Context

Issues 021 and 022 move the server to owner-only writes and presence heartbeats. This issue makes the frontend match: the conflict-detection machinery (30 s stale poll, `_clientRevision`, conflict banner, conflict dialog) is removed entirely, replaced by a 30 s presence-poll that drives a lightweight "User X is editing" badge. Non-owner users visiting a workspace-visible project see a read-only state — save button disabled, a "View only" hint — instead of being allowed to attempt a save that would now return 403.

Removal order follows plan D7: frontend conflicts are removed before the stale-poll timer, so there is no window where the banner can trigger on a non-existent server path.

## Acceptance criteria

- [ ] **AC-023-1:** The project list no longer calls `/api/projects/revisions`. DevTools Network tab shows zero requests to that path after page load and during normal usage.
- [ ] **AC-023-2:** `#conflict-banner` and `#conflict-dialog` DOM elements are removed from `index.html`. No JS code references either ID after this change.
- [ ] **AC-023-3:** `_clientRevision` is no longer included in the `POST /api/projects` payload. The `projects.js` save path sends the project state without a revision field.
- [ ] **AC-023-4:** `startStaleCheck` (and its 30 s `setInterval`) is removed from `projects.js`. No polling to `/api/projects/revisions` exists anywhere in the JS source.
- [ ] **AC-023-5:** When the current user is NOT the project owner and the project has `visibility='workspace'`, the save button is disabled (or removed) and a "View only" or "Read only" hint is visible in the project card or editor header.
- [ ] **AC-023-6:** A project card for a workspace-visible project shows a "User X is editing" badge when `GET /api/presence?project_id=X` returns at least one entry whose `user_id` is not the current user.
- [ ] **AC-023-7:** The presence badge disappears within 2 poll cycles (~60 s) after the editing user closes the project (no more heartbeats reach the server).
- [ ] **AC-023-8:** The owner's browser calls `POST /api/presence/heartbeat` every 30 s while a project is open (verify in DevTools Network).
- [ ] **AC-023-9:** Browser console is clean (zero new errors) after exercising: project list load, project open (owner), project open (non-owner), save (owner), and navigation between projects.
- [ ] **AC-023-10:** `node --check src/js/projects.js` passes; `node --check src/js/api.js` passes; `vite build` (if present) produces no new warnings.

## Likely files

- `src/js/projects.js` — remove `startStaleCheck`, `_clientRevision` from save payload, conflict-banner/dialog DOM references, stale-poll `setInterval`; add `startPresencePoll(projectId)` + `stopPresencePoll()` (30 s interval to `GET /api/presence`); add `renderPresenceBadge(users)` on project cards; add read-only guard (`isOwner` check before enabling save button)
- `index.html` — remove `#conflict-banner` and `#conflict-dialog` elements and any inline styles/scripts attached to them
- `src/js/api.js` — remove any helper that builds the conflict-check request body or reads `_clientRevision` from state (if any)
- `src/js/state.js` — remove `_loadedRevision` state variable and any setter/getter (if used only by the conflict path)
- `src/css/` or inline styles — remove conflict banner/dialog CSS if extracted (check `index.html` for `<style>` blocks referencing `#conflict-banner`)
- `docs/ai/testing-guide.md` — remove "409 conflict" manual smoke item; add write-protection + presence smoke items

## Tests / validation

```bash
# Syntax checks — must all pass
node --check src/js/projects.js
node --check src/js/api.js
node --check src/js/state.js
python3 -c "import server"
```

Manual smoke (two browser sessions, staging):

**Owner flow:**
1. Log in as owner (User A). Open the project list. Open a project.
2. DevTools → Network tab: confirm `POST /api/presence/heartbeat` fires every ~30 s.
3. Edit and save the project — no 409 error, no conflict banner, saves successfully.

**Non-owner flow (after User A has shared the project):**
4. Log in as User B (same workspace). Open the project list — the workspace-visible project appears.
5. Open the project. Save button is disabled or absent; a "View only" hint is visible.
6. Confirm no `POST /api/presence/heartbeat` is sent from User B's tab.
7. In User B's project list, confirm the badge "User A is editing" is visible (User A's tab still open).

**Badge expiry:**
8. User A closes the project tab. Wait up to 60 s (2 poll cycles).
9. User B's tab: badge disappears without a page reload.

**Console cleanliness:**
10. In both tabs, open DevTools → Console. Confirm zero new errors after all steps above.

## Data-safety / out of scope

- Removing `_clientRevision` from the frontend payload does NOT delete any server-side revision history. `project_revisions` table and the restore feature (issue 019) are unaffected.
- `ConflictError` and `save_project_transactional` remain in `storage.py` as dead code — this frontend issue does not touch Python files.
- The `/api/projects/revisions` GET endpoint in `server.py` is removed as part of this issue (it existed solely for the stale poll — no other callers per plan D7). Confirm with `grep -r "revisions"` in `server.py` before removing.
- Out of scope: the transfer UI (assigning a new owner via the project card) — the transfer API endpoint lands in issue 021; a dedicated UI can follow in a future issue.
- Out of scope: desktop mode JS paths — `isServerMode()` guards already separate desktop from server paths; no desktop-mode JS changes are required.
- Out of scope: any announcement, song, template, or settings write-protection — ownership is a project-level concept only.
