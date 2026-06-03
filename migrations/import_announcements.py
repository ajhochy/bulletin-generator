"""
migrations/import_announcements.py — One-shot import of legacy announcements.json
into the Postgres ``announcements`` table.

Usage (CLI)::

    python -m migrations.import_announcements --json-path data/announcements.json
    python -m migrations.import_announcements --json-path data/announcements.json --dry-run

Programmatic usage::

    from migrations.import_announcements import import_announcements_from_json
    result = import_announcements_from_json("data/announcements.json")
    # result == {"imported": 3, "skipped": 0, "errors": [], "dry_run": False}
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Lazy DB import — ``transaction`` is only available in server mode.
# We import it at module level (guarded) so unit tests can patch it cleanly
# via ``patch("import_announcements.transaction", ...)``.
# ---------------------------------------------------------------------------

try:
    from db import transaction  # type: ignore[import]
except Exception:  # desktop mode or psycopg not installed
    transaction = None  # type: ignore[assignment]

# Namespace for stable UUID5 generation from title+body fingerprints.
_ANN_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def import_announcements_from_json(
    json_path: str,
    dry_run: bool = False,
) -> dict:
    """Import every announcement from *json_path* into the Postgres announcements table.

    Behaviour
    ---------
    * Missing file → returns immediately with zero counts (no error).
    * Malformed top-level JSON (not a list) → recorded in ``errors``.
    * Each announcement is upserted with ``ON CONFLICT (id) DO NOTHING`` so
      re-running is safe.
    * Stable UUIDs are generated from existing id (if UUID-valid) or from
      title+body content via uuid5 so re-runs produce the same UUID.
    * ``ordering`` is set from list index if not present.
    * Missing optional fields (url, etc.) default to empty string.

    Parameters
    ----------
    json_path:
        Path to the announcements JSON file (e.g. ``data/announcements.json``).
    dry_run:
        When ``True`` the function reads and validates the JSON but does not
        write anything to the database.

    Returns
    -------
    dict with keys ``imported``, ``skipped``, ``errors``, ``dry_run``.
    """
    path = Path(json_path)
    result: dict[str, Any] = {
        "imported": 0,
        "skipped": 0,
        "errors": [],
        "dry_run": dry_run,
    }

    # ── 1. Read file ──────────────────────────────────────────────────────────
    if not path.exists():
        return result

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        result["errors"].append(f"Failed to read {json_path}: {exc}")
        return result

    if not isinstance(raw, list):
        result["errors"].append(
            f"Expected a JSON array in {json_path}, got {type(raw).__name__}"
        )
        return result

    # ── 2. Parse rows ─────────────────────────────────────────────────────────
    rows = []
    for idx, item in enumerate(raw):
        try:
            row = _parse_announcement(item, idx)
            rows.append(row)
        except Exception as exc:
            result["errors"].append(f"Announcement at index {idx}: {exc}")

    if dry_run:
        # Validate only — no DB interaction.
        result["imported"] = len(rows)
        return result

    # ── 3. Write to DB ────────────────────────────────────────────────────────
    if transaction is None:
        raise RuntimeError(
            "Database is not available (desktop mode or psycopg not installed). "
            "Run import_announcements_from_json only in server mode."
        )

    with transaction() as conn:
        for row in rows:
            inserted = _upsert_announcement(conn, row)
            if inserted:
                result["imported"] += 1
            else:
                result["skipped"] += 1

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_announcement(item: Any, idx: int) -> dict:
    """Validate and normalise a single raw announcement dict."""
    if not isinstance(item, dict):
        raise ValueError(f"expected a dict, got {type(item).__name__}")

    title = str(item.get("title") or "")
    body = str(item.get("body") or "")
    url = str(item.get("url") or "")
    ordering = int(item.get("ordering") if item.get("ordering") is not None else idx)

    # id — use existing UUID if valid; otherwise generate stable UUID from content.
    raw_id = item.get("id") or ""
    if raw_id:
        try:
            ann_id = str(uuid.UUID(str(raw_id)))
        except ValueError:
            # Non-UUID string id → generate stable UUID via uuid5.
            ann_id = str(uuid.uuid5(_ANN_NAMESPACE, str(raw_id)))
    else:
        # No id at all → derive stable UUID from title+body fingerprint.
        fingerprint = f"{title}\x00{body}"
        ann_id = str(uuid.uuid5(_ANN_NAMESPACE, fingerprint))

    return {
        "id": ann_id,
        "title": title,
        "body": body,
        "url": url,
        "ordering": ordering,
    }


def _upsert_announcement(conn, row: dict) -> bool:
    """Insert announcement; return True if a new row was created, False if skipped."""
    sql = """
        INSERT INTO announcements (
            id,
            title,
            body,
            url,
            ordering
        ) VALUES (
            %(id)s::uuid,
            %(title)s,
            %(body)s,
            %(url)s,
            %(ordering)s
        )
        ON CONFLICT (id) DO NOTHING
    """
    cursor = conn.execute(sql, row)
    return cursor.rowcount == 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Import legacy announcements.json into Postgres."
    )
    parser.add_argument(
        "--json-path",
        default="data/announcements.json",
        help="Path to announcements.json (default: data/announcements.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only — no DB writes.",
    )
    args = parser.parse_args()

    result = import_announcements_from_json(args.json_path, dry_run=args.dry_run)
    label = "[DRY RUN] " if result["dry_run"] else ""
    print(f"{label}imported={result['imported']}  skipped={result['skipped']}")
    for err in result["errors"]:
        print(f"  ERROR: {err}", file=sys.stderr)
    if result["errors"]:
        sys.exit(1)
