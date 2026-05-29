# Decisions

Append-only log of architecture / workflow decisions worth preserving across sessions. Most-recent first.

---

## 2026-05-28 — Separate `/api/projects/revisions` endpoint for the stale-check poll

**Context.** The 30s stale-check poll (`startStaleCheck` in `src/js/projects.js`) called `GET /api/projects`, which returns the entire `projects.json` — ~8.6 MB because project `state` embeds base64 cover/logo images. With multiple browser tabs open this transferred ~279 GB over a few weeks and inflated server RSS (repeated multi-MB JSON parse/serialize). The poll only reads `revision`/`updatedAt`/`updatedBy`.

**Alternatives.**
- Add a `?fields=meta` query param to `/api/projects`. Rejected — the route is exact-match (`path == '/api/projects'`); supporting a variant would mean parsing query strings in the handler, and a distinct path is clearer and cache-friendlier.
- Strip `state` from the existing `/api/projects` response. Rejected — startup (`loadAllFromServer`) and the explicit "Reload latest" handlers genuinely need full `state`.
- Gzip the response. Rejected — reduces bytes but still re-parses/re-serializes 8.6 MB server-side every cycle; doesn't fix RSS.

**Decision.** Added `_project_revision_summary(projects)` (metadata-only: id/revision/updatedAt/updatedBy) and an exact-match `GET /api/projects/revisions` route → `_handle_get_project_revisions`. The poll now hits the new endpoint (~799 bytes vs 8.6 MB, ~10,800× smaller). The two explicit user-triggered "Reload latest" handlers and startup load still use full `/api/projects`.

**Consequences.**
- Stale-check bandwidth is now negligible; the Cloudflare-vs-Tailscale choice can be made on features/security rather than data volume.
- Any future field the poll needs must be added to `_project_revision_summary`, not assumed present.

---

## 2026-05-19 — Adopt the AI workflow `AGENTS.md` + `docs/ai/*` contract

**Context.** Agent runs were degrading because the orchestrator's "self-heal before doing anything else" step kept finding the seven required workflow files missing, and either skipped the check (bad) or bootstrapped placeholder content inline in unrelated PRs (also bad).

**Alternatives.**
- Keep everything in `CLAUDE.md`. Rejected — single file conflates architectural reference (durable) with planning state (volatile), and the orchestrator looks for `docs/ai/*` by name.
- Skip the contract and let each agent re-derive context. Rejected — wastes tokens and produces inconsistent assumptions across runs.

**Decision.** Adopt the standard layout:
- `AGENTS.md` — operating contract.
- `docs/ai/project-state.md` — current focus + recent work.
- `docs/ai/repo-map.md` — grep index.
- `docs/ai/architecture.md` — boundaries.
- `docs/ai/testing-guide.md` — validation commands + manual-only checks.
- `docs/ai/current-plan.md` — what's being worked on right now.
- `docs/ai/decisions.md` — this file.

`CLAUDE.md` stays as the canonical detailed architecture reference; the new files reference it instead of duplicating.

**Consequences.**
- Future agent sessions can skip the bootstrap step and dispatch specialists directly.
- `project-state.md` becomes the source of truth for "what's in flight" — must be updated by `project-state-updater` after every completed unit of work, not just at release time.
- Anyone editing `CLAUDE.md` should sanity-check that `architecture.md` / `repo-map.md` haven't drifted.
