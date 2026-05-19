# Decisions

Append-only log of architecture / workflow decisions worth preserving across sessions. Most-recent first.

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
