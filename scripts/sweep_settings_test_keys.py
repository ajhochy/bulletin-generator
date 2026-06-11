"""
scripts/sweep_settings_test_keys.py — Sweep e2e test pollution from
``workspace_settings`` (issue #299).

E2E runs that signed in to a real workspace (the live lane uses
``e2e-live@e2e.bulletin.test``, a viewer in the production Visalia CRC
workspace) historically wrote test-only keys — ``_testKey``, ``_screenshots``,
and any other ``_``-prefixed key — into the production ``workspace_settings``
row via the merge-style ``POST /api/settings``. The ``_`` prefix is a reserved
test namespace the product never uses, so any ``_``-prefixed key in
``workspace_settings.settings`` is stray pollution.

This script finds and removes those keys. **Dry-run is the DEFAULT** — it lists
exactly what it would delete and writes nothing. ``--execute`` is an explicit
opt-in that writes the cleaned settings blob back via the RLS-bypassing admin
connection.

The companion server-side guard (``server.py`` ``_strip_reserved_settings_keys``
applied in ``_handle_post_settings``) prevents *recurrence*; this script cleans
up rows already polluted before that guard landed.

Usage::

    # Dry-run (default — no DB writes): list stray test keys per workspace
    APP_MODE=server python scripts/sweep_settings_test_keys.py

    # Execute (writes the cleaned blob back):
    APP_MODE=server python scripts/sweep_settings_test_keys.py --execute

Environment variables (for both modes — a connection is needed even to read):
    SUPABASE_SERVICE_ROLE_URL  — preferred (service_role bypasses RLS)
    DATABASE_URL               — fallback (DB-owner credentials)
    APP_MODE=server            — required by db.py

Data-safety rules:
    * Dry-run is the DEFAULT; --execute is an explicit opt-in.
    * The service_role / DATABASE_URL string is never logged.
    * Only ``_``-prefixed keys are removed; every other key is preserved
      byte-identically (OAuth tokens, branding, volunteer roles, etc.).
    * The whole run is one transaction (admin_transaction): all-or-nothing.
"""

from __future__ import annotations

import argparse
import sys


# ---------------------------------------------------------------------------
# Pure helpers (no DB) — unit-tested by tests/contract/test_issue_299.py
# ---------------------------------------------------------------------------

def _is_test_key(key) -> bool:
    """True if *key* is a reserved (``_``-prefixed) test-only key."""
    return isinstance(key, str) and key.startswith("_")


def find_test_keys(settings: dict) -> list[str]:
    """Return the sorted list of ``_``-prefixed keys present in *settings*.

    These are the keys the sweep would delete. An empty list means the row is
    already clean."""
    if not isinstance(settings, dict):
        return []
    return sorted(k for k in settings if _is_test_key(k))


def clean_settings(settings: dict) -> dict:
    """Return a NEW dict with every ``_``-prefixed key removed.

    Pure — does not mutate *settings* (so dry-run can safely call it). Every
    non-test key is preserved unchanged."""
    if not isinstance(settings, dict):
        return settings
    return {k: v for k, v in settings.items() if not _is_test_key(k)}


# ---------------------------------------------------------------------------
# DB sweep
# ---------------------------------------------------------------------------

def sweep(execute: bool = False) -> int:
    """Scan ``workspace_settings`` for stray test keys.

    Dry-run (default): print what would be deleted, write nothing.
    Execute: write the cleaned settings blob back for each polluted row.

    Returns a process exit code (0 = success / nothing to do)."""
    # Deferred import so the module (and its pure helpers) can be imported
    # without a DB connection — the contract tests rely on this.
    import os.path  # noqa: PLC0415
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    try:
        from db import admin_transaction, from_jsonb  # type: ignore[import]
    except Exception as exc:  # pragma: no cover - import-environment guard
        sys.stderr.write(
            f"ERROR: cannot import from db.py: {exc}\n"
            "Set APP_MODE=server and ensure SUPABASE_SERVICE_ROLE_URL or "
            "DATABASE_URL is set.\n"
        )
        return 2

    import json  # noqa: PLC0415

    mode = "EXECUTE" if execute else "DRY RUN"
    print(f"=== sweep_settings_test_keys.py  [{mode}] ===")

    polluted = 0
    total_keys = 0
    try:
        with admin_transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT workspace_id, settings FROM public.workspace_settings"
                )
                rows = cur.fetchall()

                for workspace_id, settings_raw in rows:
                    settings = from_jsonb(settings_raw) or {}
                    stray = find_test_keys(settings)
                    if not stray:
                        continue
                    polluted += 1
                    total_keys += len(stray)
                    print(f"\nworkspace {workspace_id}:")
                    print(f"  stray test keys ({len(stray)}): {', '.join(stray)}")
                    if execute:
                        cleaned = clean_settings(settings)
                        cur.execute(
                            "UPDATE public.workspace_settings "
                            "SET settings = %s::jsonb WHERE workspace_id = %s",
                            (json.dumps(cleaned), workspace_id),
                        )
                        print(f"  -> removed {len(stray)} key(s)")
            # admin_transaction commits on clean exit; on dry-run nothing was written.
    except Exception as exc:
        sys.stderr.write(f"ERROR: sweep failed: {exc}\n")
        return 1

    print()
    if polluted == 0:
        print("No stray _-prefixed test keys found. workspace_settings is clean.")
    elif execute:
        print(f"Removed {total_keys} stray key(s) across {polluted} workspace(s).")
    else:
        print(
            f"Would remove {total_keys} stray key(s) across {polluted} workspace(s)."
        )
        print("  Re-run with --execute to write the cleaned settings back.")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep stray _-prefixed e2e test keys from workspace_settings "
            "(issue #299). Dry-run is the DEFAULT; pass --execute to write."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        dest="execute",
        action="store_false",
        default=False,
        help="List stray test keys without writing (the default).",
    )
    parser.add_argument(
        "--execute",
        dest="execute",
        action="store_true",
        help=(
            "Write the cleaned settings blob back via admin_transaction(). "
            "Requires SUPABASE_SERVICE_ROLE_URL (or DATABASE_URL) and APP_MODE=server."
        ),
    )
    args = parser.parse_args(argv)
    sys.exit(sweep(execute=args.execute))


if __name__ == "__main__":
    main()
