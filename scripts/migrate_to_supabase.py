"""
scripts/migrate_to_supabase.py — Workspace seeding and data migration.

Reads legacy JSON files from a configurable source directory and migrates them
into the Supabase multi-tenant schema for a single workspace.

Target workspace (hard-coded for the Visalia CRC staging migration):
    name:  Visalia CRC
    slug:  visaliacrc
    id:    614505d2-0f12-4c00-afb1-9077a0dc94fe

Tables written:
    projects           — one row per project (ON CONFLICT (id) DO NOTHING)
    project_revisions  — one initial revision per newly inserted project
    announcements      — one row per announcement (ON CONFLICT (id) DO NOTHING)
    songs              — one row per song (ON CONFLICT (id) DO NOTHING)
    templates          — one row per template (ON CONFLICT (id) DO NOTHING)
    workspace_settings — one upsert for the whole settings blob (includes
                         volunteerRoles migrated from volunteer-roles.json)

Usage::

    # Dry-run (default — no DB writes):
    python scripts/migrate_to_supabase.py --source /Volumes/docker/bulletingenerator

    # Execute (writes to staging DB):
    python scripts/migrate_to_supabase.py --source /Volumes/docker/bulletingenerator --execute

Environment variables required for --execute:
    SUPABASE_SERVICE_ROLE_URL  — preferred (service_role bypasses RLS)
    DATABASE_URL               — fallback (must be DB-owner credentials)
    APP_MODE=server            — required by db.py; set in .env

Data-safety rules:
    * Dry-run is the DEFAULT; --execute is an explicit opt-in.
    * The service_role URL is never logged.
    * No source file is modified.
    * ON CONFLICT DO NOTHING ensures idempotency — re-running is safe.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants — Visalia CRC workspace
# ---------------------------------------------------------------------------

WORKSPACE_ID = "614505d2-0f12-4c00-afb1-9077a0dc94fe"

# ---------------------------------------------------------------------------
# UUID helpers
# ---------------------------------------------------------------------------

# Namespaces for stable UUID5 derivation (keep consistent with migrations/).
_PROJECT_NS = uuid.NAMESPACE_DNS
_ANN_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
_SONG_NS = uuid.UUID("c0ffee00-d400-4db0-0000-000000000000")
_TPL_NS = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")


def _stable_uuid(raw_id: str, namespace: uuid.UUID) -> str:
    """Return a stable UUID5 derived from *raw_id* using *namespace*."""
    return str(uuid.uuid5(namespace, raw_id))


def _coerce_uuid(raw_id: Any, namespace: uuid.UUID) -> str:
    """Return a valid UUID string from *raw_id*.

    * If *raw_id* is a valid UUID: return it normalised.
    * If *raw_id* is a non-UUID string: derive a stable UUID5 so re-runs
      produce the same value.
    * If *raw_id* is falsy: return a fresh random UUID (one-off).
    """
    if not raw_id:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(str(raw_id)))
    except ValueError:
        return _stable_uuid(str(raw_id), namespace)


# ---------------------------------------------------------------------------
# Source data readers
# ---------------------------------------------------------------------------

def _read_json(path: Path, expected_type: type) -> tuple[Any, str | None]:
    """Read *path* as JSON.  Returns (data, error_message).  error is None on success."""
    if not path.exists():
        return expected_type(), None  # missing file → empty default, no error

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return expected_type(), f"Failed to read {path}: {exc}"

    if not isinstance(data, expected_type):
        return expected_type(), (
            f"{path.name}: expected {expected_type.__name__}, got {type(data).__name__}"
        )

    return data, None


# ---------------------------------------------------------------------------
# Row parsers
# ---------------------------------------------------------------------------

def _parse_project(item: dict, idx: int) -> dict:
    """Normalise a legacy project dict into a DB-ready row."""
    if not isinstance(item, dict):
        raise ValueError(f"expected a dict at index {idx}, got {type(item).__name__}")

    project_id = _coerce_uuid(item.get("id"), _PROJECT_NS)
    name = str(item.get("name") or "")
    state = item  # full JSON blob → state column
    revision = int(item.get("revision") or 1)
    created_at = item.get("createdAt") or None
    updated_at = item.get("updatedAt") or None

    return {
        "id": project_id,
        "name": name,
        "state": state,
        "revision": revision,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _parse_announcement(item: dict, idx: int) -> dict:
    """Normalise a legacy announcement dict into a DB-ready row."""
    if not isinstance(item, dict):
        raise ValueError(f"expected a dict at index {idx}, got {type(item).__name__}")

    title = str(item.get("title") or "")
    body = str(item.get("body") or "")
    # Preserve the full legacy dict in state; drop nothing.
    state = {k: v for k, v in item.items() if k not in ("title", "body")}

    raw_id = item.get("id") or ""
    if raw_id:
        ann_id = _coerce_uuid(raw_id, _ANN_NS)
    else:
        # Derive stable UUID from title+body fingerprint.
        ann_id = _stable_uuid(f"{title}\x00{body}", _ANN_NS)

    return {
        "id": ann_id,
        "title": title,
        "body": body,
        "state": state,
    }


def _parse_song(item: dict, idx: int) -> dict:
    """Normalise a legacy song dict into a DB-ready row."""
    if not isinstance(item, dict):
        raise ValueError(f"expected a dict at index {idx}, got {type(item).__name__}")

    title = str(item.get("title") or "")
    # Preserve the full legacy dict in the data column.
    data = item

    raw_id = item.get("id") or ""
    if raw_id:
        song_id = _coerce_uuid(raw_id, _SONG_NS)
    else:
        author = str(item.get("author") or "")
        source = str(item.get("source") or "")
        song_id = _stable_uuid(f"{title}\x00{author}\x00{source}", _SONG_NS)

    return {
        "id": song_id,
        "title": title,
        "data": data,
    }


# ---------------------------------------------------------------------------
# Settings extractor
# ---------------------------------------------------------------------------

# Keys to include in workspace_settings (everything except OAuth tokens, which
# contain secrets and are excluded from the migration).
_SETTINGS_INCLUDE = {
    "churchName",
    "staffData",
    "servingTeamFilter",
    "typeFormats",
    "docTemplate",
    "giveOnlineUrl",
    "calUrls",
    "calExclude",
    "googleDriveFolderId",
}

_SETTINGS_EXCLUDE = {
    "pcoAccessToken",
    "pcoRefreshToken",
    "googleAccessToken",
    "googleRefreshToken",
}


def _extract_settings(raw: dict) -> dict:
    """Return the subset of *raw* settings that belong in workspace_settings.

    OAuth tokens are excluded from migration (they are secrets and should be
    re-issued for the multi-tenant deployment).
    """
    return {k: v for k, v in raw.items() if k not in _SETTINGS_EXCLUDE}


# ---------------------------------------------------------------------------
# Dry-run summary helpers
# ---------------------------------------------------------------------------

def _print_dry_run_summary(
    projects: list[dict],
    announcements: list[dict],
    songs: list[dict],
    templates: list[dict],
    settings: dict,
    errors: list[str],
) -> None:
    """Print dry-run counts and a preview of the first 3 project names."""
    print()
    print("=== migrate_to_supabase.py  [DRY RUN] ===")
    print()
    print(f"  Source workspace : {WORKSPACE_ID}  (Visalia CRC)")
    print()
    print(f"  projects          : {len(projects):>6} rows would be inserted")
    print(f"  project_revisions : {len(projects):>6} initial revisions would be inserted")
    print(f"  announcements     : {len(announcements):>6} rows would be inserted")
    print(f"  songs             : {len(songs):>6} rows would be inserted")
    print(f"  templates         : {len(templates):>6} rows would be inserted")

    settings_row = 1 if settings else 0
    volunteer_roles_count = len(settings.get('volunteerRoles', []))
    print(f"  workspace_settings: {settings_row:>6} row would be upserted"
          + (f"  (volunteerRoles: {volunteer_roles_count} entries)" if volunteer_roles_count else ""))
    print()

    if projects:
        print("  First 3 project names:")
        for p in projects[:3]:
            name = p.get("name") or "(no name)"
            print(f"    - {name}")
        print()

    if errors:
        print(f"  Parse errors ({len(errors)}):")
        for err in errors:
            print(f"    ERROR: {err}")
        print()

    print("  Re-run with --execute to write to the database.")
    print()


def _print_execute_summary(
    projects_imported: int,
    projects_skipped: int,
    announcements_imported: int,
    announcements_skipped: int,
    songs_imported: int,
    songs_skipped: int,
    templates_imported: int,
    templates_skipped: int,
    settings_upserted: bool,
    errors: list[str],
) -> None:
    """Print a summary after a --execute run."""
    print()
    print("=== migrate_to_supabase.py  [EXECUTE] ===")
    print()
    print(f"  projects          : {projects_imported:>6} imported  "
          f"{projects_skipped:>6} skipped")
    print(f"  announcements     : {announcements_imported:>6} imported  "
          f"{announcements_skipped:>6} skipped")
    print(f"  songs             : {songs_imported:>6} imported  "
          f"{songs_skipped:>6} skipped")
    print(f"  templates         : {templates_imported:>6} imported  "
          f"{templates_skipped:>6} skipped")
    settings_label = "upserted" if settings_upserted else "no settings file"
    print(f"  workspace_settings: {settings_label}")
    print()

    if errors:
        print(f"  Parse/write errors ({len(errors)}):")
        for err in errors:
            print(f"    ERROR: {err}")
        print()


# ---------------------------------------------------------------------------
# DB write helpers  (used only with --execute)
# ---------------------------------------------------------------------------

def _upsert_project(conn, row: dict, workspace_id: str) -> bool:
    """Insert project row; return True if a new row was created."""
    sql = """
        INSERT INTO projects (
            id,
            workspace_id,
            name,
            owner_user_id,
            visibility,
            state,
            revision,
            created_at,
            updated_at
        ) VALUES (
            %(id)s,
            %(workspace_id)s::uuid,
            %(name)s,
            NULL,
            'workspace',
            %(state)s::jsonb,
            %(revision)s,
            COALESCE(%(created_at)s::timestamptz, now()),
            COALESCE(%(updated_at)s::timestamptz, now())
        )
        ON CONFLICT (id) DO NOTHING
    """
    cursor = conn.execute(sql, {
        "id": row["id"],
        "workspace_id": workspace_id,
        "name": row["name"],
        "state": json.dumps(row["state"], ensure_ascii=False),
        "revision": row["revision"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    })
    return cursor.rowcount == 1


def _insert_project_revision(conn, row: dict, workspace_id: str) -> None:
    """Insert the initial revision snapshot for a newly imported project."""
    sql = """
        INSERT INTO project_revisions (
            id,
            project_id,
            workspace_id,
            revision_number,
            state,
            summary,
            created_at,
            created_by_user_id
        ) VALUES (
            gen_random_uuid(),
            %(project_id)s,
            %(workspace_id)s::uuid,
            %(revision_number)s,
            %(state)s::jsonb,
            'Imported from projects.json',
            COALESCE(%(created_at)s::timestamptz, now()),
            NULL
        )
        ON CONFLICT DO NOTHING
    """
    conn.execute(sql, {
        "project_id": row["id"],
        "workspace_id": workspace_id,
        "revision_number": row["revision"],
        "state": json.dumps(row["state"], ensure_ascii=False),
        "created_at": row.get("updated_at") or row.get("created_at"),
    })


def _upsert_announcement(conn, row: dict, workspace_id: str) -> bool:
    """Insert announcement row; return True if a new row was created."""
    sql = """
        INSERT INTO announcements (
            id,
            workspace_id,
            title,
            body,
            state,
            created_at,
            updated_at,
            created_by_user_id
        ) VALUES (
            %(id)s::uuid,
            %(workspace_id)s::uuid,
            %(title)s,
            %(body)s,
            %(state)s::jsonb,
            now(),
            now(),
            NULL
        )
        ON CONFLICT (id) DO NOTHING
    """
    cursor = conn.execute(sql, {
        "id": row["id"],
        "workspace_id": workspace_id,
        "title": row["title"],
        "body": row["body"],
        "state": json.dumps(row["state"], ensure_ascii=False),
    })
    return cursor.rowcount == 1


def _upsert_song(conn, row: dict, workspace_id: str) -> bool:
    """Insert song row; return True if a new row was created."""
    sql = """
        INSERT INTO songs (
            id,
            workspace_id,
            title,
            data,
            created_at,
            updated_at
        ) VALUES (
            %(id)s::uuid,
            %(workspace_id)s::uuid,
            %(title)s,
            %(data)s::jsonb,
            now(),
            now()
        )
        ON CONFLICT (id) DO NOTHING
    """
    cursor = conn.execute(sql, {
        "id": row["id"],
        "workspace_id": workspace_id,
        "title": row["title"],
        "data": json.dumps(row["data"], ensure_ascii=False),
    })
    return cursor.rowcount == 1


def _parse_template(item: dict, idx: int) -> dict:
    """Normalise a legacy template dict into a DB-ready row."""
    if not isinstance(item, dict):
        raise ValueError(f"expected a dict at index {idx}, got {type(item).__name__}")
    raw_id = item.get("id") or ""
    tpl_id = _coerce_uuid(raw_id, _TPL_NS)
    name = str(item.get("name") or "")
    is_default = bool(item.get("builtIn", False))
    return {"id": tpl_id, "name": name, "is_default": is_default, "template_data": item}


def _upsert_template(conn, row: dict, workspace_id: str) -> bool:
    """Insert template row; return True if a new row was created."""
    sql = """
        INSERT INTO templates (
            id, workspace_id, name, template_data, is_default, created_at, updated_at
        ) VALUES (
            %(id)s::uuid, %(workspace_id)s::uuid, %(name)s,
            %(template_data)s::jsonb, %(is_default)s, now(), now()
        )
        ON CONFLICT (id) DO NOTHING
    """
    cursor = conn.execute(sql, {
        "id": row["id"],
        "workspace_id": workspace_id,
        "name": row["name"],
        "template_data": json.dumps(row["template_data"], ensure_ascii=False),
        "is_default": row["is_default"],
    })
    return cursor.rowcount == 1


def _upsert_workspace_settings(conn, settings: dict, workspace_id: str) -> None:
    """Upsert the workspace_settings row (one row per workspace)."""
    sql = """
        INSERT INTO workspace_settings (workspace_id, settings)
        VALUES (%(workspace_id)s::uuid, %(settings)s::jsonb)
        ON CONFLICT (workspace_id) DO UPDATE
          SET settings = workspace_settings.settings || EXCLUDED.settings
    """
    conn.execute(sql, {
        "workspace_id": workspace_id,
        "settings": json.dumps(settings, ensure_ascii=False),
    })


# ---------------------------------------------------------------------------
# Main migration logic
# ---------------------------------------------------------------------------

def migrate(source_dir: str, execute: bool = False) -> int:
    """Run the migration.

    Parameters
    ----------
    source_dir:
        Path to the directory containing legacy JSON files.
    execute:
        When False (default) dry-run only — no DB writes.
        When True, write to the staging Supabase DB via admin_transaction().

    Returns
    -------
    Exit code: 0 on success, 1 on errors.
    """
    src = Path(source_dir).resolve()
    errors: list[str] = []

    # ── 1. Read source files ──────────────────────────────────────────────────
    projects_raw, err = _read_json(src / "projects.json", list)
    if err:
        errors.append(err)
        projects_raw = []

    announcements_raw, err = _read_json(src / "announcements.json", list)
    if err:
        errors.append(err)
        announcements_raw = []

    songs_raw, err = _read_json(src / "song_database.json", list)
    if err:
        errors.append(err)
        songs_raw = []

    settings_raw, err = _read_json(src / "settings.json", dict)
    if err:
        errors.append(err)
        settings_raw = {}

    volunteer_roles_raw, err = _read_json(src / "volunteer-roles.json", list)
    if err:
        errors.append(err)
        volunteer_roles_raw = []

    templates_raw, err = _read_json(src / "templates.json", list)
    if err:
        errors.append(err)
        templates_raw = []

    # ── 2. Parse rows ─────────────────────────────────────────────────────────
    projects: list[dict] = []
    for idx, item in enumerate(projects_raw):
        try:
            projects.append(_parse_project(item, idx))
        except Exception as exc:
            errors.append(f"projects[{idx}]: {exc}")

    announcements: list[dict] = []
    for idx, item in enumerate(announcements_raw):
        try:
            announcements.append(_parse_announcement(item, idx))
        except Exception as exc:
            errors.append(f"announcements[{idx}]: {exc}")

    songs: list[dict] = []
    for idx, item in enumerate(songs_raw):
        try:
            songs.append(_parse_song(item, idx))
        except Exception as exc:
            errors.append(f"songs[{idx}]: {exc}")

    templates: list[dict] = []
    for idx, item in enumerate(templates_raw):
        try:
            templates.append(_parse_template(item, idx))
        except Exception as exc:
            errors.append(f"templates[{idx}]: {exc}")

    settings = _extract_settings(settings_raw) if settings_raw else {}

    # Merge volunteerRoles from volunteer-roles.json into the settings blob.
    # This is idempotent: the upsert uses JSONB || merge, so re-running with
    # the same data is safe.
    if volunteer_roles_raw:
        settings['volunteerRoles'] = volunteer_roles_raw

    # ── 3. Dry-run: print and exit ────────────────────────────────────────────
    if not execute:
        _print_dry_run_summary(projects, announcements, songs, templates, settings, errors)
        return 1 if errors else 0

    # ── 4. Execute: write to DB ───────────────────────────────────────────────
    # Import db.admin_transaction at call time so the module can be imported
    # without a DB connection (e.g. during unit tests or dry-run use).
    try:
        import sys as _sys
        import os as _os
        # Ensure project root is on sys.path for db.py import.
        _repo_root = str(Path(__file__).parent.parent)
        if _repo_root not in _sys.path:
            _sys.path.insert(0, _repo_root)
        from db import admin_transaction  # type: ignore[import]
    except Exception as exc:
        print(
            f"ERROR: cannot import admin_transaction from db.py: {exc}\n"
            "       Set APP_MODE=server and ensure psycopg is installed.",
            file=sys.stderr,
        )
        return 1

    projects_imported = projects_skipped = 0
    announcements_imported = announcements_skipped = 0
    songs_imported = songs_skipped = 0
    templates_imported = templates_skipped = 0
    settings_upserted = False

    try:
        with admin_transaction() as conn:
            # Projects
            for row in projects:
                try:
                    inserted = _upsert_project(conn, row, WORKSPACE_ID)
                    if inserted:
                        _insert_project_revision(conn, row, WORKSPACE_ID)
                        projects_imported += 1
                    else:
                        projects_skipped += 1
                except Exception as exc:
                    errors.append(f"project {row.get('id', '?')}: {exc}")

            # Announcements
            for row in announcements:
                try:
                    inserted = _upsert_announcement(conn, row, WORKSPACE_ID)
                    if inserted:
                        announcements_imported += 1
                    else:
                        announcements_skipped += 1
                except Exception as exc:
                    errors.append(f"announcement {row.get('id', '?')}: {exc}")

            # Songs
            for row in songs:
                try:
                    inserted = _upsert_song(conn, row, WORKSPACE_ID)
                    if inserted:
                        songs_imported += 1
                    else:
                        songs_skipped += 1
                except Exception as exc:
                    errors.append(f"song {row.get('id', '?')}: {exc}")

            # Templates
            for row in templates:
                try:
                    inserted = _upsert_template(conn, row, WORKSPACE_ID)
                    if inserted:
                        templates_imported += 1
                    else:
                        templates_skipped += 1
                except Exception as exc:
                    errors.append(f"template {row.get('id', '?')}: {exc}")

            # Settings
            if settings:
                try:
                    _upsert_workspace_settings(conn, settings, WORKSPACE_ID)
                    settings_upserted = True
                except Exception as exc:
                    errors.append(f"workspace_settings: {exc}")

    except Exception as exc:
        print(f"ERROR: database transaction failed: {exc}", file=sys.stderr)
        return 1

    _print_execute_summary(
        projects_imported, projects_skipped,
        announcements_imported, announcements_skipped,
        songs_imported, songs_skipped,
        templates_imported, templates_skipped,
        settings_upserted,
        errors,
    )

    return 1 if errors else 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate legacy Bulletin Generator JSON data into the Supabase "
            "multi-tenant schema for the Visalia CRC workspace.\n\n"
            "Dry-run is the DEFAULT; pass --execute to write to the database."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        required=True,
        help=(
            "Path to the directory containing legacy JSON files: "
            "projects.json, announcements.json, song_database.json, settings.json."
        ),
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Parse and validate only — no DB writes. This is the DEFAULT.",
    )
    parser.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        help=(
            "Write to the staging Supabase DB via admin_transaction(). "
            "Requires SUPABASE_SERVICE_ROLE_URL (or DATABASE_URL) and APP_MODE=server."
        ),
    )
    args = parser.parse_args(argv)

    sys.exit(migrate(args.source, execute=not args.dry_run))


if __name__ == "__main__":
    main()
