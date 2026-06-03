"""
migrations/import_fonts.py — Inventory font files from disk into the Postgres
``fonts`` metadata table.

Scans ``data/fonts/user/`` and ``data/fonts/cache/`` for font files and
upserts a metadata row per font into the ``fonts`` table.  Font binaries are
**not** moved; the existing ``/fonts/user/*`` and ``/fonts/cache/*`` serving
paths continue to work unchanged.

Font file extensions recognised: .woff, .woff2, .ttf, .otf, .css

Slug
    Derived from the subdirectory name (one subdir per font family).

Family
    Human-readable form of the slug: dashes replaced with spaces, title-cased.

Source
    ``"user"`` for fonts in ``data/fonts/user/``, ``"cache"`` for
    ``data/fonts/cache/``.

css_url
    Relative URL to the CSS file, e.g. ``/fonts/user/<slug>/font.css``.
    Populated only when a ``font.css`` file exists (or is generated on the
    fly by the server for user fonts).  For user fonts the URL is always
    set because server.py generates the CSS dynamically.  For cache fonts it
    is set only when the file exists on disk.

file_path
    Absolute path to the first (alphabetically) font binary found in the
    directory.  Empty string when only a CSS file exists without binaries.

upload_metadata
    Empty dict ``{}`` in v1 — reserved for future upload provenance.

cached_at
    mtime of the first font binary as an ISO-8601 UTC timestamp.  ``NULL``
    when no binary is found.

Usage (CLI)::

    python -m migrations.import_fonts --user-dir data/fonts/user --cache-dir data/fonts/cache
    python -m migrations.import_fonts --user-dir data/fonts/user --cache-dir data/fonts/cache --dry-run

Programmatic usage::

    from migrations.import_fonts import import_fonts_from_directories
    result = import_fonts_from_directories("data/fonts/user", "data/fonts/cache")
    # result == {
    #     "user_imported": 2,
    #     "cache_imported": 1,
    #     "skipped": 0,
    #     "errors": [],
    #     "dry_run": False,
    # }
"""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Font binary extensions that trigger a metadata row.
FONT_BINARY_EXTS: frozenset[str] = frozenset({".woff", ".woff2", ".ttf", ".otf"})

#: Namespace UUID for stable UUID5 generation (slug + source fingerprint).
_FONT_NAMESPACE = uuid.UUID("f0f7f0f7-f0f7-f0f7-f0f7-f0f7f0f7f0f7")

# ---------------------------------------------------------------------------
# Lazy DB import — ``transaction`` only available in server mode.
# ---------------------------------------------------------------------------

try:
    from db import transaction  # type: ignore[import]
except Exception:  # desktop mode or psycopg not installed
    transaction = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_font_directory(directory: str, source: str) -> list[dict]:
    """Scan *directory* for font families and return a list of metadata dicts.

    Each subdirectory of *directory* that contains at least one font binary
    (.woff, .woff2, .ttf, .otf) **or** a ``font.css`` file is returned as
    one entry.  Entries without binaries have an empty ``file_path`` and
    ``cached_at=None``.

    Missing or non-directory *directory* → returns ``[]`` without error.

    Parameters
    ----------
    directory:
        Absolute or relative path to the font root (e.g. ``data/fonts/user``).
    source:
        Logical origin: ``"user"`` or ``"cache"``.

    Returns
    -------
    list of dicts with keys:
        slug, family, source, css_url, file_path, upload_metadata, cached_at
    """
    root = Path(directory)
    results: list[dict] = []

    if not root.exists() or not root.is_dir():
        return results

    for family_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        slug = family_dir.name
        family = _family_from_slug(slug)
        css_url = f"/fonts/{source}/{slug}/font.css"

        # Gather font binaries.
        binaries = sorted(
            f for f in family_dir.iterdir()
            if f.is_file() and f.suffix.lower() in FONT_BINARY_EXTS
        )

        has_css = (family_dir / "font.css").exists()

        # Skip directories that have neither binaries nor a CSS file.
        if not binaries and not has_css:
            continue

        # For source=="user" the CSS is generated dynamically by server.py even
        # without a static file, so we always populate css_url.  For "cache"
        # we only set it when the file actually exists.
        if source == "cache" and not has_css:
            css_url = ""

        file_path = str(binaries[0]) if binaries else ""
        cached_at: str | None = None
        if binaries:
            mtime = binaries[0].stat().st_mtime
            cached_at = datetime.datetime.fromtimestamp(
                mtime, tz=datetime.timezone.utc
            ).isoformat()

        results.append({
            "slug": slug,
            "family": family,
            "source": source,
            "css_url": css_url,
            "file_path": file_path,
            "upload_metadata": {},
            "cached_at": cached_at,
        })

    return results


def import_fonts_from_directories(
    user_dir: str,
    cache_dir: str,
    dry_run: bool = False,
) -> dict:
    """Scan *user_dir* and *cache_dir* and upsert font metadata into Postgres.

    Behaviour
    ---------
    * Missing directory → reported in result counts as 0, no crash.
    * Each font is upserted with ``ON CONFLICT (slug) DO NOTHING`` so
      re-running is safe and existing rows are not overwritten.
    * ``dry_run=True`` scans directories but performs no DB writes.
    * Individual upsert errors are caught per-font and listed in ``errors``
      so one bad entry does not abort the whole import.

    Parameters
    ----------
    user_dir:
        Path to the user-uploaded fonts directory (e.g. ``data/fonts/user``).
    cache_dir:
        Path to the Google Fonts cache directory (e.g. ``data/fonts/cache``).
    dry_run:
        When ``True`` the function scans directories but writes nothing to DB.

    Returns
    -------
    dict with keys:
        user_imported (int), cache_imported (int), skipped (int),
        errors (list[str]), dry_run (bool).
    """
    result: dict[str, Any] = {
        "user_imported": 0,
        "cache_imported": 0,
        "skipped": 0,
        "errors": [],
        "dry_run": dry_run,
    }

    user_fonts = scan_font_directory(user_dir, "user")
    cache_fonts = scan_font_directory(cache_dir, "cache")

    if dry_run:
        result["user_imported"] = len(user_fonts)
        result["cache_imported"] = len(cache_fonts)
        return result

    # ── Write to DB ───────────────────────────────────────────────────────────
    if transaction is None:
        raise RuntimeError(
            "Database is not available (desktop mode or psycopg not installed). "
            "Run import_fonts_from_directories only in server mode."
        )

    with transaction() as conn:
        for font in user_fonts:
            try:
                inserted = _upsert_font(conn, font)
                if inserted:
                    result["user_imported"] += 1
                else:
                    result["skipped"] += 1
            except Exception as exc:
                result["errors"].append(
                    f"user font '{font.get('slug')}': {exc}"
                )

        for font in cache_fonts:
            try:
                inserted = _upsert_font(conn, font)
                if inserted:
                    result["cache_imported"] += 1
                else:
                    result["skipped"] += 1
            except Exception as exc:
                result["errors"].append(
                    f"cache font '{font.get('slug')}': {exc}"
                )

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _family_from_slug(slug: str) -> str:
    """Convert a slug like ``open-sans`` to ``Open Sans``."""
    return " ".join(part.capitalize() for part in slug.replace("-", " ").split())


def _font_uuid(slug: str, source: str) -> str:
    """Generate a stable UUID5 from slug + source."""
    return str(uuid.uuid5(_FONT_NAMESPACE, f"{slug}\x00{source}"))


def _upsert_font(conn, font: dict) -> bool:
    """Insert a font metadata row; return True if a new row was created.

    Uses ``ON CONFLICT (slug) DO NOTHING`` so re-runs are safe.
    """
    font_id = _font_uuid(font["slug"], font["source"])
    cached_at_sql = font["cached_at"]  # ISO string or None

    sql = """
        INSERT INTO fonts (
            id,
            slug,
            family,
            source,
            css_url,
            file_path,
            upload_metadata,
            cached_at
        ) VALUES (
            %(id)s::uuid,
            %(slug)s,
            %(family)s,
            %(source)s,
            %(css_url)s,
            %(file_path)s,
            %(upload_metadata)s::jsonb,
            %(cached_at)s::timestamptz
        )
        ON CONFLICT (slug) DO NOTHING
    """
    cursor = conn.execute(
        sql,
        {
            "id": font_id,
            "slug": font["slug"],
            "family": font["family"],
            "source": font["source"],
            "css_url": font["css_url"],
            "file_path": font["file_path"],
            "upload_metadata": json.dumps(font.get("upload_metadata") or {}),
            "cached_at": cached_at_sql,
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
        description="Inventory font files from disk into the Postgres fonts table."
    )
    parser.add_argument(
        "--user-dir",
        default="data/fonts/user",
        help="Path to user-uploaded fonts directory (default: data/fonts/user)",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/fonts/cache",
        help="Path to Google Fonts cache directory (default: data/fonts/cache)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan directories only — no DB writes.",
    )
    args = parser.parse_args()

    result = import_fonts_from_directories(
        args.user_dir, args.cache_dir, dry_run=args.dry_run
    )
    label = "[DRY RUN] " if result["dry_run"] else ""
    print(
        f"{label}user_imported={result['user_imported']}  "
        f"cache_imported={result['cache_imported']}  "
        f"skipped={result['skipped']}"
    )
    for err in result["errors"]:
        print(f"  ERROR: {err}", file=sys.stderr)
    if result["errors"]:
        sys.exit(1)
