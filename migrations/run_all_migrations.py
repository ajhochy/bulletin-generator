"""
migrations/run_all_migrations.py — Operator entry point for all legacy JSON imports.

Runs all individual importers in sequence, creates a timestamped backup of the
JSON source files before writing, and prints a human-readable summary table.

Usage::

    python -m migrations.run_all_migrations [--dry-run] [--check] [--data-dir /path/to/data]

Flags
-----
--dry-run
    Parse and validate all JSON files, run each importer with dry_run=True,
    print summary, skip backup. Exits 0.
--check
    Count records in JSON files without connecting to the database at all.
    Even faster than --dry-run; useful for a quick pre-flight sanity check.
--data-dir PATH
    Root of the legacy data directory.  Defaults to ``./data``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Lazy imports of individual importers — guarded so the module can be imported
# without a DB connection (e.g. in --check mode or during unit tests that mock
# these names).  Tests patch these at the module level:
#   patch("migrations.run_all_migrations.import_projects_from_json", ...)
# ---------------------------------------------------------------------------

try:
    from migrations.import_projects import import_projects_from_json
except Exception:
    import_projects_from_json = None  # type: ignore[assignment]

try:
    from migrations.import_settings import import_settings_from_json
except Exception:
    import_settings_from_json = None  # type: ignore[assignment]

try:
    from migrations.import_announcements import import_announcements_from_json
except Exception:
    import_announcements_from_json = None  # type: ignore[assignment]

try:
    from migrations.import_songs import import_songs_from_json
except Exception:
    import_songs_from_json = None  # type: ignore[assignment]

try:
    from migrations.import_templates import import_templates_from_json
except Exception:
    import_templates_from_json = None  # type: ignore[assignment]

try:
    from migrations.import_fonts import import_fonts_from_directories
except Exception:
    import_fonts_from_directories = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_json_records(path: Path) -> int:
    """Return the number of top-level records in a JSON file.

    * Missing file → 0
    * JSON array → len(array)
    * JSON object → len(object.keys())
    * Parse error / not array or object → 0
    """
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return len(data)
    except Exception:
        pass
    return 0


def _count_font_dirs(directory: Path) -> int:
    """Return the number of font family subdirectories in *directory*."""
    if not directory.exists() or not directory.is_dir():
        return 0
    return sum(1 for p in directory.iterdir() if p.is_dir())


def _backup_data(data_dir: Path) -> Path:
    """Copy legacy JSON files and user font directory to a timestamped backup.

    Returns the path to the created backup directory.

    Files copied (silently skipped if missing):
        projects.json, settings.json, announcements.json,
        song_database.json, templates.json, fonts/user/ (directory)
    """
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = data_dir / "backups" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    files_to_backup = [
        "projects.json",
        "settings.json",
        "announcements.json",
        "song_database.json",
        "templates.json",
    ]
    for filename in files_to_backup:
        src = data_dir / filename
        if src.exists():
            shutil.copy2(src, backup_dir / filename)

    user_fonts_src = data_dir / "fonts" / "user"
    if user_fonts_src.exists() and user_fonts_src.is_dir():
        shutil.copytree(user_fonts_src, backup_dir / "fonts" / "user")

    return backup_dir


def _print_summary(results: dict[str, dict], dry_run: bool) -> None:
    """Print a human-readable summary table of importer results."""
    col_w = 16

    label = " [DRY RUN]" if dry_run else ""
    print(f"\nMigration summary{label}")
    print("-" * 60)
    header = f"{'Data type':<{col_w}}  {'imported':>8}  {'skipped':>8}  {'errors':>8}"
    print(header)
    print("-" * 60)

    total_imported = 0
    total_skipped = 0
    total_errors = 0

    for name, res in results.items():
        imported = res.get("imported", 0)
        skipped = res.get("skipped", 0)
        errors = len(res.get("errors", []))

        # fonts returns user_imported + cache_imported instead of a single "imported"
        if "user_imported" in res or "cache_imported" in res:
            imported = res.get("user_imported", 0) + res.get("cache_imported", 0)

        total_imported += imported
        total_skipped += skipped
        total_errors += errors

        print(f"{name:<{col_w}}  {imported:>8}  {skipped:>8}  {errors:>8}")

    print("-" * 60)
    print(f"{'TOTAL':<{col_w}}  {total_imported:>8}  {total_skipped:>8}  {total_errors:>8}")
    print()


def _print_check_summary(counts: dict[str, int]) -> None:
    """Print a pre-flight record count from JSON files (--check mode)."""
    print("\nPre-flight check — JSON record counts (no DB connection)")
    print("-" * 50)
    for label, count in counts.items():
        print(f"  {label:<30} {count:>6}")
    print()


# ---------------------------------------------------------------------------
# Importer execution
# ---------------------------------------------------------------------------

def _run_importers(data_dir: Path, dry_run: bool) -> dict[str, dict]:
    """Run all importers in sequence and return their result dicts."""
    results: dict[str, dict] = {}

    results["projects"] = import_projects_from_json(
        str(data_dir / "projects.json"), dry_run=dry_run
    )
    results["settings"] = import_settings_from_json(
        str(data_dir / "settings.json"), dry_run=dry_run
    )
    results["announcements"] = import_announcements_from_json(
        str(data_dir / "announcements.json"), dry_run=dry_run
    )
    results["songs"] = import_songs_from_json(
        str(data_dir / "song_database.json"), dry_run=dry_run
    )
    results["templates"] = import_templates_from_json(
        str(data_dir / "templates.json"), dry_run=dry_run
    )
    results["fonts"] = import_fonts_from_directories(
        str(data_dir / "fonts" / "user"),
        str(data_dir / "fonts" / "cache"),
        dry_run=dry_run,
    )

    return results


# ---------------------------------------------------------------------------
# Check mode
# ---------------------------------------------------------------------------

def _run_check(data_dir: Path) -> None:
    """Count records in JSON files without touching the DB; print and exit 0."""
    counts = {
        "projects.json": _count_json_records(data_dir / "projects.json"),
        "settings.json (keys)": _count_json_records(data_dir / "settings.json"),
        "announcements.json": _count_json_records(data_dir / "announcements.json"),
        "song_database.json": _count_json_records(data_dir / "song_database.json"),
        "templates.json": _count_json_records(data_dir / "templates.json"),
        "fonts/user/ (families)": _count_font_dirs(data_dir / "fonts" / "user"),
        "fonts/cache/ (families)": _count_font_dirs(data_dir / "fonts" / "cache"),
    }
    _print_check_summary(counts)
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run all legacy JSON import migrations.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count without writing to the database.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Count records in JSON files only — no DB connection at all.",
    )
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="Path to the legacy data directory (default: ./data).",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve()

    # --check is the fastest path: filesystem only, no DB.
    if args.check:
        _run_check(data_dir)
        return  # unreachable; _run_check always exits

    dry_run: bool = args.dry_run

    # Backup before any writes (skipped in dry-run).
    if not dry_run:
        backup_dir = _backup_data(data_dir)
        print(f"Backup created at: {backup_dir}")

    # Run all importers.
    results = _run_importers(data_dir, dry_run=dry_run)

    # Print summary.
    _print_summary(results, dry_run=dry_run)

    # Collect all errors.
    all_errors: list[str] = []
    for name, res in results.items():
        for err in res.get("errors", []):
            all_errors.append(f"[{name}] {err}")

    if all_errors:
        print("Errors:", file=sys.stderr)
        for err in all_errors:
            print(f"  {err}", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print("DRY RUN — no data was written.")

    sys.exit(0)


if __name__ == "__main__":
    main()
