"""
migrations/import_settings.py — One-shot import of legacy settings.json
into the Postgres ``org_settings`` and ``user_settings`` tables.

Key classification
------------------
ORG_KEYS
    Deployment-wide configuration stored in ``org_settings``.

OAUTH_KEYS
    OAuth tokens (pcoAccessToken, pcoRefreshToken, googleAccessToken,
    googleRefreshToken).  These are **temporarily** kept together in a single
    ``org_settings`` row under the key ``"oauth_tokens"`` as a JSONB dict.
    Long-term they should be moved to a dedicated secrets store or per-user
    credential rows.  The bundled approach avoids schema changes while the
    collab-v1 migration stabilises.

USER_KEYS
    Per-user settings stored in ``user_settings``.  During legacy import the
    ``user_id`` is set to NULL (anonymous/unattributed) because the original
    settings.json had no user identity concept.  The ``user_settings`` schema
    requires a FK to ``users``, so we skip user-key import for now — those
    keys are preserved in the returned result as ``user_keys_imported=0`` until
    a user-mapping strategy is defined.

Usage (CLI)::

    python -m migrations.import_settings --json-path data/settings.json
    python -m migrations.import_settings --json-path data/settings.json --dry-run

Programmatic usage::

    from migrations.import_settings import import_settings_from_json
    result = import_settings_from_json("data/settings.json")
    # result == {
    #     "org_keys_imported": 7,
    #     "user_keys_imported": 0,
    #     "skipped": 2,
    #     "dry_run": False,
    # }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Key classification
# ---------------------------------------------------------------------------

#: Keys stored in ``org_settings`` (one row per key).
ORG_KEYS: list[str] = [
    "churchName",
    "staffData",
    "servingTeamFilter",
    "typeFormats",
    "docTemplate",
    "giveOnlineUrl",
    "calUrls",
    "calExclude",
    "googleDriveFolderId",
]

#: OAuth tokens bundled into a single ``org_settings`` row under key
#: ``"oauth_tokens"``.  Kept here temporarily — should migrate to a dedicated
#: secrets store or per-user credential table in a future collab phase.
OAUTH_KEYS: list[str] = [
    "pcoAccessToken",
    "pcoRefreshToken",
    "googleAccessToken",
    "googleRefreshToken",
]

#: Keys that logically belong to a specific user.  Import is deferred until a
#: user-mapping strategy exists (the ``user_settings`` table requires a non-NULL
#: ``user_id`` FK in the current schema).
USER_KEYS: list[str] = [
    "editorDisplayName",
]

# ---------------------------------------------------------------------------
# Lazy DB import
# ---------------------------------------------------------------------------

try:
    from db import transaction  # type: ignore[import]
except Exception:  # desktop mode or psycopg not installed
    transaction = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_settings_from_json(
    json_path: str,
    dry_run: bool = False,
) -> dict:
    """Import settings from *json_path* into ``org_settings`` (and eventually
    ``user_settings``) in Postgres.

    Behaviour
    ---------
    * Missing file → returns immediately with zero counts (no error).
    * Each org key is upserted with ``ON CONFLICT (key) DO NOTHING`` so
      re-running is safe and existing customisations are not overwritten.
    * OAuth tokens are bundled into a single ``org_settings`` row under the key
      ``"oauth_tokens"`` as a JSONB dict, also with ``ON CONFLICT DO NOTHING``.
    * User keys are counted but **not written** in this release (user_id FK
      constraint cannot be satisfied with NULL in the current schema).
    * ``dry_run=True`` validates the JSON but performs no DB writes.

    Parameters
    ----------
    json_path:
        Path to the settings JSON file (e.g. ``data/settings.json``).
    dry_run:
        When ``True`` the function reads and validates but writes nothing.

    Returns
    -------
    dict with keys ``org_keys_imported``, ``user_keys_imported``, ``skipped``,
    ``dry_run``.
    """
    path = Path(json_path)
    result: dict[str, Any] = {
        "org_keys_imported": 0,
        "user_keys_imported": 0,
        "skipped": 0,
        "dry_run": dry_run,
    }

    # ── 1. Read file ──────────────────────────────────────────────────────────
    if not path.exists():
        return result

    try:
        with open(path, "r", encoding="utf-8") as f:
            settings: dict = json.load(f)
    except Exception as exc:
        raise ValueError(f"Failed to read {json_path}: {exc}") from exc

    if not isinstance(settings, dict):
        raise ValueError(
            f"Expected a JSON object in {json_path}, got {type(settings).__name__}"
        )

    # ── 2. Classify keys ──────────────────────────────────────────────────────
    org_rows: list[tuple[str, Any]] = []  # (key, value) pairs for org_settings
    oauth_bundle: dict[str, Any] = {}
    user_key_count = 0

    for key in ORG_KEYS:
        if key in settings:
            org_rows.append((key, settings[key]))

    for key in OAUTH_KEYS:
        if key in settings:
            oauth_bundle[key] = settings[key]

    if oauth_bundle:
        org_rows.append(("oauth_tokens", oauth_bundle))

    for key in USER_KEYS:
        if key in settings:
            user_key_count += 1

    if dry_run:
        # Count what would be imported without touching the DB.
        result["org_keys_imported"] = len(org_rows)
        # user_keys are counted but not written; reflect intent in dry-run too.
        result["user_keys_imported"] = user_key_count
        return result

    # ── 3. Write to DB ────────────────────────────────────────────────────────
    if transaction is None:
        raise RuntimeError(
            "Database is not available (desktop mode or psycopg not installed). "
            "Run import_settings_from_json only in server mode."
        )

    with transaction() as conn:
        for key, value in org_rows:
            inserted = _upsert_org_setting(conn, key, value)
            if inserted:
                result["org_keys_imported"] += 1
            else:
                result["skipped"] += 1

    # User keys are intentionally deferred — no user_id available.
    # result["user_keys_imported"] stays 0.

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _upsert_org_setting(conn, key: str, value: Any) -> bool:
    """Insert an org setting; return True if a new row was created.

    Uses ``ON CONFLICT (key) DO NOTHING`` so existing values are preserved.
    """
    sql = """
        INSERT INTO org_settings (key, value, updated_at)
        VALUES (%(key)s, %(value)s::jsonb, now())
        ON CONFLICT (key) DO NOTHING
    """
    cursor = conn.execute(sql, {"key": key, "value": json.dumps(value, ensure_ascii=False)})
    return cursor.rowcount == 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Import legacy settings.json into Postgres org_settings."
    )
    parser.add_argument(
        "--json-path",
        default="data/settings.json",
        help="Path to settings.json (default: data/settings.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only — no DB writes.",
    )
    args = parser.parse_args()

    result = import_settings_from_json(args.json_path, dry_run=args.dry_run)
    label = "[DRY RUN] " if result["dry_run"] else ""
    print(
        f"{label}org_keys_imported={result['org_keys_imported']}  "
        f"user_keys_imported={result['user_keys_imported']}  "
        f"skipped={result['skipped']}"
    )
