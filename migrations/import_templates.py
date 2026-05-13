"""
migrations/import_templates.py — One-shot import of legacy templates.json
into the Postgres ``templates`` table.

Usage (CLI)::

    python -m migrations.import_templates --json-path data/templates.json
    python -m migrations.import_templates --json-path data/templates.json --dry-run

Programmatic usage::

    from migrations.import_templates import import_templates_from_json
    result = import_templates_from_json("data/templates.json")
    # result == {"imported": 2, "skipped": 0, "built_in": 2, "custom": 0, "dry_run": False}
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Lazy DB import — ``transaction`` is only available in server mode.
# We import it at module level (guarded) so unit tests can patch it cleanly
# via ``patch("import_templates.transaction", ...)``.
# ---------------------------------------------------------------------------

try:
    from db import transaction  # type: ignore[import]
except Exception:  # desktop mode or psycopg not installed
    transaction = None  # type: ignore[assignment]

# Names of built-in templates that receive built_in=True protection.
BUILT_IN_NAMES = ["Classic", "Modern"]

# Namespace for stable UUID5 generation from template name.
_TEMPLATE_NAMESPACE = uuid.UUID("b01e7e00-7e00-4000-8000-000000000000")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_templates_from_json(
    json_path: str,
    dry_run: bool = False,
) -> dict:
    """Import every template from *json_path* into the Postgres templates table.

    Behaviour
    ---------
    * Missing file → returns immediately with zero counts (no error).
    * Malformed top-level JSON (not a list) → recorded in ``errors``.
    * Each template is upserted with ``ON CONFLICT (id) DO NOTHING`` so
      re-running is safe (idempotent).
    * Stable UUIDs are generated from existing id (if UUID-valid) or from
      the template name via uuid5 so re-runs produce the same UUID.
    * Templates whose ``name`` is in BUILT_IN_NAMES receive ``built_in=True``.
    * The full template object is stored as JSONB in the ``data`` column.

    Parameters
    ----------
    json_path:
        Path to the templates JSON file (e.g. ``data/templates.json``).
    dry_run:
        When ``True`` the function reads and validates the JSON but does not
        write anything to the database.

    Returns
    -------
    dict with keys ``imported``, ``skipped``, ``built_in``, ``custom``, ``dry_run``.
    """
    path = Path(json_path)
    result: dict[str, Any] = {
        "imported": 0,
        "skipped": 0,
        "built_in": 0,
        "custom": 0,
        "dry_run": dry_run,
    }

    # ── 1. Read file ──────────────────────────────────────────────────────────
    if not path.exists():
        return result

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        result["errors"] = [f"Failed to read {json_path}: {exc}"]
        return result

    if not isinstance(raw, list):
        result["errors"] = [
            f"Expected a JSON array in {json_path}, got {type(raw).__name__}"
        ]
        return result

    # ── 2. Parse rows ─────────────────────────────────────────────────────────
    rows = []
    errors = []
    for idx, item in enumerate(raw):
        try:
            row = _parse_template(item, idx)
            rows.append(row)
        except Exception as exc:
            errors.append(f"Template at index {idx}: {exc}")

    if errors:
        result["errors"] = errors

    if dry_run:
        # Validate only — no DB interaction.
        result["imported"] = len(rows)
        result["built_in"] = sum(1 for r in rows if r["built_in"])
        result["custom"] = sum(1 for r in rows if not r["built_in"])
        return result

    # ── 3. Write to DB ────────────────────────────────────────────────────────
    if transaction is None:
        raise RuntimeError(
            "Database is not available (desktop mode or psycopg not installed). "
            "Run import_templates_from_json only in server mode."
        )

    with transaction() as conn:
        for row in rows:
            inserted = _upsert_template(conn, row)
            if inserted:
                result["imported"] += 1
                if row["built_in"]:
                    result["built_in"] += 1
                else:
                    result["custom"] += 1
            else:
                result["skipped"] += 1

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_template(item: Any, idx: int) -> dict:
    """Validate and normalise a single raw template dict."""
    if not isinstance(item, dict):
        raise ValueError(f"expected a dict, got {type(item).__name__}")

    name = str(item.get("name") or "")

    # id — use existing UUID if valid; otherwise generate stable UUID from name.
    raw_id = item.get("id") or ""
    if raw_id:
        try:
            template_id = str(uuid.UUID(str(raw_id)))
        except ValueError:
            # Non-UUID string id (e.g. "classic", "modern") → derive stable UUID via uuid5.
            template_id = str(uuid.uuid5(_TEMPLATE_NAMESPACE, str(raw_id)))
    else:
        # No id → derive stable UUID from name.
        template_id = str(uuid.uuid5(_TEMPLATE_NAMESPACE, name))

    # Determine built_in: honour explicit flag OR match against BUILT_IN_NAMES.
    built_in = bool(item.get("builtIn")) or (name in BUILT_IN_NAMES)

    # Store the full template object as data (strip the builtIn key from the
    # stored blob since built_in is a DB column — keep it for round-trip compat).
    data = dict(item)

    return {
        "id": template_id,
        "name": name,
        "data": data,
        "built_in": built_in,
    }


def _upsert_template(conn, row: dict) -> bool:
    """Insert template; return True if a new row was created, False if skipped."""
    sql = """
        INSERT INTO templates (
            id,
            name,
            data,
            built_in
        ) VALUES (
            %(id)s::uuid,
            %(name)s,
            %(data)s::jsonb,
            %(built_in)s
        )
        ON CONFLICT (id) DO NOTHING
    """
    cursor = conn.execute(
        sql,
        {
            "id": row["id"],
            "name": row["name"],
            "data": json.dumps(row["data"], ensure_ascii=False),
            "built_in": row["built_in"],
        },
    )
    return cursor.rowcount == 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Import legacy templates.json into Postgres."
    )
    parser.add_argument(
        "--json-path",
        default="data/templates.json",
        help="Path to templates.json (default: data/templates.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only — no DB writes.",
    )
    args = parser.parse_args()

    result = import_templates_from_json(args.json_path, dry_run=args.dry_run)
    label = "[DRY RUN] " if result["dry_run"] else ""
    print(
        f"{label}imported={result['imported']}  skipped={result['skipped']}  "
        f"built_in={result['built_in']}  custom={result['custom']}"
    )
    for err in result.get("errors", []):
        print(f"  ERROR: {err}", file=sys.stderr)
    if result.get("errors"):
        sys.exit(1)
