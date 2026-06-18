---
date: 2026-06-06
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# New-member workspace resolution is read-after-write sensitive (presence e2e flake)

**Context.** The `e2e-core` presence test (`server-mode-behaviors.spec.ts`) flaked
intermittently: a second workspace member (B), added via `createWorkspaceMember`
immediately before signing in, sometimes received **403** on `GET/DELETE /api/presence`
(and an empty `/api/projects`) because `auth.resolve_workspace_membership(B)` found no
membership row yet. Cross-run contrast confirmed it intermittent (B saw the project on
one run, nothing on another). The membership write (Supabase PostgREST, service role) and
the read (`db.admin_transaction`, psycopg via the 6543 transaction pooler) are different
connection paths; B's first authenticated request can race ahead of the new row's
visibility, and the frontend does **not** auto-retry a 403 (the project list stays empty).

**Decision.** Treat this as a **test-setup race**, fixed in the test (PR #283): after B
signs in, reload B until A's project resolves into B's Files list before driving the UI.
In production a member is invited well before their first login, so the window is not
normally hit.

**Latent product consideration (not yet actioned).** A freshly-provisioned/invited member
whose *first* authenticated request lands before membership is visible will get a 403 and
an **empty workspace with no automatic recovery** until they manually reload. If real
invite-then-immediately-login flows are expected, consider: (a) a short server-side retry
in `resolve_workspace_membership` / `authenticate_authorization_header` before returning
403, or (b) a frontend re-fetch on an initial 403/empty-workspace. Worth verifying during
the #272 multi-tenant QA. No code change made now.

**Consequences.** Presence e2e is deterministic; the product behavior is documented for
follow-up rather than silently masked.
