"""
migrations/import_projects.py — One-shot import of legacy projects.json
into the Postgres ``projects`` and ``project_revisions`` tables.

Usage (CLI)::

    python -m migrations.import_projects --json-path data/projects.json
    python -m migrations.import_projects --json-path data/projects.json --dry-run

Programmatic usage::

    from migrations.import_projects import import_projects_from_json
    result = import_projects_from_json("data/projects.json")
    # result == {"imported": 3, "skipped": 0, "errors": [], "dry_run": False}
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Lazy DB import — ``transaction`` is only available in server mode.
# We import it at module level (guarded) so unit tests can patch it cleanly
# via ``patch("import_projects.transaction", ...)``.
# ---------------------------------------------------------------------------

try:
    from db import transaction  # type: ignore[import]
except Exception:  # desktop mode or psycopg not installed
    transaction = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def import_projects_from_json(
    json_path: str,
    dry_run: bool = False,
) -> dict:
    """Import every project from *json_path* into the Postgres projects table.

    Behaviour
    ---------
    * Missing file → returns immediately with zero counts (no error).
    * Malformed top-level JSON (not a list) → recorded in ``errors``.
    * Each project is upserted with ``ON CONFLICT (id) DO NOTHING`` so
      re-running is safe.
    * ``owner_user_id`` is set to NULL (legacy projects have no user mapping).
    * ``visibility`` is set to ``'workspace'`` (they were globally visible).
    * ``imported_from_json`` is set to ``True``.
    * One ``project_revisions`` row is inserted per newly imported project
      (also idempotent via ``ON CONFLICT DO NOTHING``).

    Parameters
    ----------
    json_path:
        Path to the projects JSON file (e.g. ``data/projects.json``).
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
            row = _parse_project(item, idx)
            rows.append(row)
        except Exception as exc:
            result["errors"].append(f"Project at index {idx}: {exc}")

    if dry_run:
        # Validate only — no DB interaction.
        result["imported"] = len(rows)
        return result

    # ── 3. Write to DB ────────────────────────────────────────────────────────
    if transaction is None:
        raise RuntimeError(
            "Database is not available (desktop mode or psycopg not installed). "
            "Run import_projects_from_json only in server mode."
        )

    with transaction() as conn:
        for row in rows:
            inserted = _upsert_project(conn, row)
            if inserted:
                _insert_revision(conn, row)
                result["imported"] += 1
            else:
                result["skipped"] += 1

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_project(item: Any, idx: int) -> dict:
    """Validate and normalise a single raw project dict."""
    if not isinstance(item, dict):
        raise ValueError(f"expected a dict, got {type(item).__name__}")

    # id — generate a fresh UUID if missing or blank
    raw_id = item.get("id") or ""
    if raw_id:
        try:
            project_id = str(uuid.UUID(str(raw_id)))
        except ValueError:
            # Legacy string ids (e.g. "proj_sunday") → generate a stable UUID
            # from the string so re-runs produce the same UUID.
            project_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(raw_id)))
    else:
        project_id = str(uuid.uuid4())

    name = str(item.get("name") or "")
    state = item  # full project dict becomes the JSONB state blob
    revision = int(item.get("revision") or 1)
    created_at = item.get("createdAt") or None
    updated_at = item.get("updatedAt") or None
    created_by_email = str(item.get("createdBy") or "")
    updated_by_email = str(item.get("updatedBy") or "")

    return {
        "id": project_id,
        "name": name,
        "state": state,
        "revision": revision,
        "created_at": created_at,
        "updated_at": updated_at,
        "created_by_email": created_by_email,
        "updated_by_email": updated_by_email,
    }


def _upsert_project(conn, row: dict) -> bool:
    """Insert project; return True if a new row was created, False if skipped."""
    sql = """
        INSERT INTO projects (
            id,
            name,
            owner_user_id,
            visibility,
            state,
            revision,
            created_at,
            updated_at,
            created_by_email,
            updated_by_email,
            imported_from_json
        ) VALUES (
            %(id)s::uuid,
            %(name)s,
            NULL,
            'workspace',
            %(state)s::jsonb,
            %(revision)s,
            COALESCE(%(created_at)s::timestamptz, now()),
            COALESCE(%(updated_at)s::timestamptz, now()),
            %(created_by_email)s,
            %(updated_by_email)s,
            TRUE
        )
        ON CONFLICT (id) DO NOTHING
    """
    params = dict(row)
    params["state"] = json.dumps(row["state"], ensure_ascii=False)

    cursor = conn.execute(sql, params)
    return cursor.rowcount == 1


def _insert_revision(conn, row: dict) -> None:
    """Insert the initial revision snapshot for a newly imported project."""
    sql = """
        INSERT INTO project_revisions (
            id,
            project_id,
            revision,
            state,
            saved_at,
            saved_by_user_id,
            saved_by_email,
            saved_by_name,
            summary
        ) VALUES (
            gen_random_uuid(),
            %(project_id)s::uuid,
            %(revision)s,
            %(state)s::jsonb,
            COALESCE(%(saved_at)s::timestamptz, now()),
            NULL,
            %(saved_by_email)s,
            '',
            'Imported from projects.json'
        )
        ON CONFLICT DO NOTHING
    """
    conn.execute(sql, {
        "project_id": row["id"],
        "revision": row["revision"],
        "state": json.dumps(row["state"], ensure_ascii=False),
        "saved_at": row.get("updated_at") or row.get("created_at"),
        "saved_by_email": row["updated_by_email"] or row["created_by_email"],
    })


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Import legacy projects.json into Postgres."
    )
    parser.add_argument(
        "--json-path",
        default="data/projects.json",
        help="Path to projects.json (default: data/projects.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only — no DB writes.",
    )
    args = parser.parse_args()

    result = import_projects_from_json(args.json_path, dry_run=args.dry_run)
    label = "[DRY RUN] " if result["dry_run"] else ""
    print(f"{label}imported={result['imported']}  skipped={result['skipped']}")
    for err in result["errors"]:
        print(f"  ERROR: {err}", file=sys.stderr)
    if result["errors"]:
        sys.exit(1)
