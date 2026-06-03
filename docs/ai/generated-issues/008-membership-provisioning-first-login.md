# 008: Membership provisioning on first login

**Milestone:** M2  ·  **Plan ref:** issue 12
**Depends on:** 006, 007

## Context

When a new user logs in via Supabase Auth for the first time, they need to be mapped to a workspace. The plan uses a per-workspace domain allow-list for v1 (no self-serve onboarding). `auth.py`'s current hard-coded `visaliacrc.com` check is the single-domain predecessor. This issue generalizes it: on successful JWT verification, if the user has no `workspace_members` row, check their email domain (or address) against a configurable allow-list stored in `workspace_settings` or a new `workspace_invites` table; if matched, insert into `workspace_members`. Users not on any allow-list receive 403.

## Acceptance criteria

- [ ] A `workspace_invites` table (or an `allowed_domains` JSONB column in `workspace_settings`) stores the per-workspace email domain allow-list. If using a new table: `workspace_id uuid`, `domain text`, `created_at timestamptz`; service_role only can write (no authenticated insert policy). If using a column: `workspace_settings.settings->>'allowed_domains'` is a JSON array of strings.
- [ ] `server.py`'s `_require_auth()` (from issue 006): after verifying the JWT and finding no `workspace_members` row, queries the allow-list for the user's email domain; if matched, inserts a new `workspace_members` row (role = 'editor') using `db.admin_transaction()` (service_role — needed to write a row that didn't exist yet without an authenticated insert policy).
- [ ] If the user's email domain matches no allow-list entry across all workspaces, `_require_auth()` returns HTTP 403 with body `{"error": "no_workspace_access"}`.
- [ ] Hard-coded `visaliacrc.com` references are removed from `auth.py` and `server.py`.
- [ ] `MANUAL-STEPS.md` documents how to add a domain to the allow-list (service_role SQL, or seed script from issue 015).
- [ ] `tests/test_auth_middleware.py` (extend): `test_first_login_allow_listed_domain_gets_workspace`, `test_first_login_unlisted_domain_gets_403`, `test_existing_member_skips_provisioning`.
- [ ] `python3 -c "import server"` succeeds.

## Likely files

- `server.py` (modify — first-login provisioning in `_require_auth()`)
- `auth.py` (modify — remove hard-coded domain)
- `migrations/` or `supabase/migrations/20260602000003_workspace_invites.sql` (new — if adding a `workspace_invites` table; otherwise `workspace_settings` schema change)
- `tests/test_auth_middleware.py` (modify — add provisioning tests)
- `MANUAL-STEPS.md` (modify — allow-list management)

## Tests / validation

```bash
python3 -c "import server"

pytest tests/test_auth_middleware.py -v

# Full regression:
pytest -v
```

Manual smoke: log in with a test account whose domain is on the allow-list for workspace_A → confirm `workspace_members` row created, `/api/me` returns correct workspace. Log in with an unlisted address → 403.

## Data-safety / out of scope

- The allow-list insert into `workspace_members` uses `db.admin_transaction()` (service_role), which is acceptable for this trust-bootstrapping step. The rationale must be commented in code.
- Do not use the user's JWT claims to self-provision — the allow-list check must be server-side so users cannot forge their own membership.
- Out of scope: invite tokens, self-serve signup, or any UI for managing the allow-list (v1 is manual-seed only).
- Out of scope: roles admin (owner/editor/viewer promotion) — first-login always sets role = 'editor'.
