# Architecture Notes

## Deployment Modes

This project is expected to support two first-class deployment modes from one codebase.

### Desktop Mode

- packaged local app
- optimized for single-user installs and testing
- local data storage
- simple onboarding
- no required multi-user collaboration features
- updates should come from app releases, not raw Git operations

### Server Mode

- shared self-hosted deployment
- browser access for multiple users
- shared data storage
- collaboration metadata and conflict protection
- admin-only deployment/update controls
- optional account/auth infrastructure later

## Guiding Principle

Keep one repository and one core application, but allow mode-specific behavior where the product needs differ.

Do not split the project into separate repos unless the codebases diverge significantly.

## Feature Scoping

Use runtime configuration to gate mode-specific behavior.

Example:

- `APP_MODE=desktop`
- `APP_MODE=server`

Features that should usually be mode-specific:

### Desktop-first

- packaging/installer flow
- release-based update flow
- local file import/export helpers
- single-user assumptions

### Server-first

- multi-user attribution
- stale document detection
- revision/conflict protection
- admin-managed update tools
- future account infrastructure

### Shared Core

- bulletin editing
- PCO import
- Google Calendar integration
- formatting templates
- song database management
- rendering and PDF generation

## GitHub Organization

Issues are organized with:

### Mode labels

- `mode:desktop`
- `mode:server`
- `mode:both`

### Area labels

- `area:deployment`
- `area:collaboration`
- `area:editor`
- `area:formatting`
- `area:integrations`
- `area:song-db`

### Milestones

- `Desktop MVP`
- `Server MVP`
- `Shared Core`

## Current Planning Rule

When adding a new issue:

1. Decide whether it applies to desktop mode, server mode, or both.
2. Add the most relevant `area:*` label.
3. Assign it to the matching milestone.

If a feature only solves shared multi-user needs, it should usually be `mode:server`.
If a feature only affects packaging or local install/update behavior, it should usually be `mode:desktop`.

