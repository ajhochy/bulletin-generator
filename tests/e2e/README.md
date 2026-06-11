# E2E tests (Playwright)

Two lanes, selected by tag and Playwright project:

| Lane | Tag | Project | Auth | Data |
|------|-----|---------|------|------|
| **core** (PR gate) | `@core` | `core` | ephemeral throwaway identity (created/swept per run) | a fresh, isolated workspace — safe to write |
| **live** (nightly) | `@live` | `live` | `e2e-live@e2e.bulletin.test`, a **viewer in the real Visalia CRC workspace** | the **production** workspace — must NOT be mutated |

## Live-lane read-only convention (non-negotiable)

`@live` specs exercise the real Planning Center / Google integrations using
tokens that live in the production workspace. Because the live member is signed
in to that real workspace, **any write the test performs lands in production
data.**

Therefore `@live` specs MUST be read-only:

- Never click Import on a PCO plan.
- Never persist a project (no Save, and remember autosave fires once a project
  is active).
- Never write settings. `POST /api/settings` is **merge-style**, so even a
  single field write merges into the production `workspace_settings` row.
- Read-only assertions only: dropdowns populate, the import view is visible,
  proxied data loads, etc.

If a `@live` spec genuinely needs to verify a write path, it must run in the
`core` lane against its isolated ephemeral workspace instead, or clean up after
itself in teardown (null the key it wrote).

## Defense in depth (issue #299)

E2E runs once polluted the production `workspace_settings` row with
`_testKey` / `_screenshots`. Two safeguards now exist:

1. **Prevention (server-side).** `server.py` `_handle_post_settings` strips any
   `_`-prefixed key before merging — the `_` prefix is a reserved test-only
   namespace, so a stray test write can no longer persist into
   `workspace_settings`. See `server.py` `_strip_reserved_settings_keys`.
2. **Cleanup (script).** `scripts/sweep_settings_test_keys.py` removes existing
   `_`-prefixed pollution. Dry-run is the default; `--execute` writes:

   ```bash
   # list what would be removed (no writes):
   APP_MODE=server python scripts/sweep_settings_test_keys.py
   # actually remove it:
   APP_MODE=server python scripts/sweep_settings_test_keys.py --execute
   ```

The convention above is still the primary rule — the server guard is a backstop,
not a license to write from `@live` specs.
