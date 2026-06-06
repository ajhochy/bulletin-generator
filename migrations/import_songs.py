"""
migrations/import_songs.py — One-shot import of legacy song_database.json
into the Postgres ``songs`` table.

Usage (CLI)::

    python -m migrations.import_songs --json-path data/song_database.json
    python -m migrations.import_songs --json-path data/song_database.json --dry-run

Programmatic usage::

    from migrations.import_songs import import_songs_from_json
    result = import_songs_from_json("data/song_database.json")
    # result == {"imported": 5, "skipped": 0, "errors": [], "dry_run": False}
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Lazy DB import — ``transaction`` is only available in server mode.
# We import it at module level (guarded) so unit tests can patch it cleanly
# via ``patch("import_songs.transaction", ...)``.
# ---------------------------------------------------------------------------

try:
    from db import transaction  # type: ignore[import]
except Exception:  # desktop mode or psycopg not installed
    transaction = None  # type: ignore[assignment]

# Namespace for stable UUID5 generation from title+author+source fingerprints.
_SONG_NAMESPACE = uuid.UUID("c0ffee00-d400-4db0-0000-000000000000")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_songs_from_json(
    json_path: str,
    dry_run: bool = False,
) -> dict:
    """Import every song from *json_path* into the Postgres songs table.

    Behaviour
    ---------
    * Missing file → returns immediately with zero counts (no error).
    * Malformed top-level JSON (not a list) → recorded in ``errors``.
    * Each song is upserted with ``ON CONFLICT (id) DO NOTHING`` so
      re-running is safe.
    * Stable UUIDs are generated from existing id (if UUID-valid) or from
      title+author+source content via uuid5 so re-runs produce the same UUID.
    * ``date_added`` is mapped from the camelCase ``dateAdded`` field.
    * Missing optional fields (author, lyrics, copyright, source, dateAdded)
      default to empty string.

    Parameters
    ----------
    json_path:
        Path to the song_database JSON file (e.g. ``data/song_database.json``).
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
            row = _parse_song(item, idx)
            rows.append(row)
        except Exception as exc:
            result["errors"].append(f"Song at index {idx}: {exc}")

    if dry_run:
        # Validate only — no DB interaction.
        result["imported"] = len(rows)
        return result

    # ── 3. Write to DB ────────────────────────────────────────────────────────
    if transaction is None:
        raise RuntimeError(
            "Database is not available (desktop mode or psycopg not installed). "
            "Run import_songs_from_json only in server mode."
        )

    with transaction() as conn:
        for row in rows:
            inserted = _upsert_song(conn, row)
            if inserted:
                result["imported"] += 1
            else:
                result["skipped"] += 1

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_song(item: Any, idx: int) -> dict:
    """Validate and normalise a single raw song dict."""
    if not isinstance(item, dict):
        raise ValueError(f"expected a dict, got {type(item).__name__}")

    title = str(item.get("title") or "")
    author = str(item.get("author") or "")
    lyrics = str(item.get("lyrics") or "")
    copyright_ = str(item.get("copyright") or "")
    source = str(item.get("source") or "")
    # Support both camelCase (dateAdded) and snake_case (date_added).
    date_added = str(
        item.get("dateAdded") or item.get("date_added") or ""
    )

    # id — use existing UUID if valid; otherwise generate stable UUID from content.
    raw_id = item.get("id") or ""
    if raw_id:
        try:
            song_id = str(uuid.UUID(str(raw_id)))
        except ValueError:
            # Non-UUID string id → derive stable UUID via uuid5 from content.
            fingerprint = f"{title}\x00{author}\x00{source}"
            song_id = str(uuid.uuid5(_SONG_NAMESPACE, fingerprint))
    else:
        # No id at all → derive stable UUID from title+author+source fingerprint.
        fingerprint = f"{title}\x00{author}\x00{source}"
        song_id = str(uuid.uuid5(_SONG_NAMESPACE, fingerprint))

    return {
        "id": song_id,
        "title": title,
        "author": author,
        "lyrics": lyrics,
        "copyright": copyright_,
        "source": source,
        "date_added": date_added,
    }


def _upsert_song(conn, row: dict) -> bool:
    """Insert song; return True if a new row was created, False if skipped."""
    sql = """
        INSERT INTO songs (
            id,
            title,
            author,
            lyrics,
            copyright,
            source,
            date_added
        ) VALUES (
            %(id)s::uuid,
            %(title)s,
            %(author)s,
            %(lyrics)s,
            %(copyright)s,
            %(source)s,
            %(date_added)s
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
        description="Import legacy song_database.json into Postgres."
    )
    parser.add_argument(
        "--json-path",
        default="data/song_database.json",
        help="Path to song_database.json (default: data/song_database.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate only — no DB writes.",
    )
    args = parser.parse_args()

    result = import_songs_from_json(args.json_path, dry_run=args.dry_run)
    label = "[DRY RUN] " if result["dry_run"] else ""
    print(f"{label}imported={result['imported']}  skipped={result['skipped']}")
    for err in result["errors"]:
        print(f"  ERROR: {err}", file=sys.stderr)
    if result["errors"]:
        sys.exit(1)
