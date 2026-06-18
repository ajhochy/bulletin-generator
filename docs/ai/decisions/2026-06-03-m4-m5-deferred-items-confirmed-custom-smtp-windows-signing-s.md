---
date: 2026-06-03
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# M4/M5 deferred items confirmed: custom SMTP, Windows signing, staging=production

**Context.** Issue 017 (operator runbook) required documenting the current deployment posture to avoid confusion between staging and production and to record items that are explicitly deferred rather than forgotten.

**Decisions recorded:**

- **Custom SMTP deferred.** Supabase's built-in mailer (rate-limited, project-team-only) is acceptable for the current single-church deployment. Custom SMTP (Resend / AWS SES / Postmark) must be configured before expanding to multi-church testing. This is a known operational gap, not a bug. See `docs/operator-runbook.md` section 1.3 for setup steps.

- **Windows code signing deferred.** Issue 014 (packaging + auto-update) will produce a signed macOS `.app` via `electron-builder`. Windows code signing (EV certificate, Microsoft Partner Center submission) is deferred until there is a Windows user base. Unsigned Windows builds will show a SmartScreen warning; this is acceptable for v1.

- **Staging = production confirmed.** The Supabase project `dgydekhfzrmeoscpgmvo` is the sole Supabase deployment for this app — it serves as both "staging" (for pre-release smoke testing on the branch) and "production" (for the Visalia CRC deployment). There is no separate production project. A new project would only be created if the user base grows beyond Supabase's free tier limits or if a second fully-isolated tenant environment is needed.

**Consequences.**
- `docs/operator-runbook.md` and `MANUAL-STEPS.md` both reference the staging/production project ID directly — this is intentional.
- Before multi-church testing, the SMTP gap must be resolved. The runbook includes the setup steps so any operator can complete it without code changes.
- Packaging issues (014) should note the Windows signing gap and include a placeholder in the CI workflow.
