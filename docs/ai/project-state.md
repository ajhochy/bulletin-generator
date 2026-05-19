# Project State

_Last updated: 2026-05-19_

## Current focus

Stabilizing the Volunteer Roles feature added in releases 1.12.9 / 1.12.10 (PRs #251, #252). Recent fixes:

- #252 — Volunteer Roles cards now render after server data loads (deferred-render bug).
- #251 — Volunteer Roles render in preview + added Document menu toggle.
- (in flight) #253 — Volunteer Roles elements are selectable / formattable in the Template Designer canvas. Branch `fix/template-editor-volunteer-roles-not-selectable`.

## Recently completed

- 1.12.10 release tagged (commit `b0b5f32`).
- Watchtower scope label typo + periodic polling enabled (`d09dbce`).

## In progress

- Draft PR #253 awaiting manual smoke + merge.
- AI-workflow doc bootstrap (this PR) to remove "missing AGENTS.md / docs/ai" self-heal pressure on future agent runs.

## Open risks

- No automated tests — every change requires manual click-through; easy to miss regressions in adjacent zones (Announcements, Calendar, Staff, Serving) when touching Template Designer code.
- Memory note re: "Do NOT create PRs unless explicitly asked" is overly broad and has caused agents to skip the workflow's terminal step. Should be scoped to "without an explicit instruction or workflow that requires it."

## Next step

Manual smoke #253, merge, then close out 1.12.x by tagging a release if any further volunteer-roles polish lands.
