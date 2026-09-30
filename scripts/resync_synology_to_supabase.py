"""
scripts/resync_synology_to_supabase.py — Cutover re-sync (Synology JSON → Supabase).

One-off operator tool to make the Supabase Visalia CRC workspace authoritative
with the *current* Synology JSON-mode data, where Synology WINS on conflict.

This differs from scripts/migrate_to_supabase.py (which is insert-only,
ON CONFLICT DO NOTHING, and keys projects by a derived UUID5). The live Electron
app stores projects under their RAW ``proj_*`` text id, so this script:

  * keys projects by their raw Synology id (matches the live app → no duplicates),
  * UPSERTS (Synology wins) instead of skipping,
  * removes the stale seed rows that would otherwise duplicate the re-imported
    projects, while preserving an explicit keep-list,
  * assigns a real owner so the projects are editable under RLS.

Reconciliation rules (decided with the operator 2026-06-09):
  projects           replace: delete (existing − synology − keep), then upsert
                     the 37 Synology projects under raw proj_* ids, owner = AJ,
                     visibility = 'workspace'. Keep-list preserved untouched.
  project_revisions  one initial snapshot per imported project (idempotent).
  songs              union/upsert — Synology wins on conflict, Supabase-only kept.
  announcements      union/upsert — Synology wins on conflict, Supabase-only kept.
  templates          union/upsert — Synology wins on conflict, Supabase-only kept.
  workspace_settings REPLACE the blob with Synology settings (+ volunteerRoles),
                     OAuth tokens excluded.

Source of truth: /Volumes/docker/bulletingenerator/app/data  (read-only — never
modified by this script).

Usage::

    set -a && source .env && set +a   # provides DATABASE_URL (postgres owner)

    # 0. Back up current Supabase workspace state (safe; read + local write):
    APP_MODE=server .venv/bin/python scripts/resync_synology_to_supabase.py --backup

    # 1. Dry-run (DEFAULT — no DB writes):
    APP_MODE=server .venv/bin/python scripts/resync_synology_to_supabase.py

    # 2. Execute (auto-backs-up first, then writes in ONE transaction):
    APP_MODE=server .venv/bin/python scripts/resync_synology_to_supabase.py --execute

Data-safety rules:
  * Dry-run is the DEFAULT; --execute is an explicit opt-in.
  * --execute always takes a fresh backup before touching anything.
  * All writes run inside a single admin_transaction() — all-or-nothing.
  * No Synology source file is modified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── path wiring ────────────────────────────────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
for _p in (str(_SCRIPTS_DIR), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Reuse the tested row parsers from the original migration script.
from migrate_to_supabase import (  # type: ignore[import]  # noqa: E402
    _read_json,
    _parse_announcement,
    _parse_song,
    _parse_template,
    _extract_settings,
)

# ── constants (Visalia CRC) ──────────────────────────────────────────────────
WORKSPACE_ID = "614505d2-0f12-4c00-afb1-9077a0dc94fe"
# AJ Hochhalter (workspace owner). Imported projects are owned by AJ now; an
# ownership transfer to info@visaliacrc.com is a documented follow-up step that
# runs after she first signs in (her auth.users row does not exist yet).
OWNER_USER_ID = "74b48104-31b5-4100-9dc1-45935404e916"

DEFAULT_SOURCE = "/Volumes/docker/bulletingenerator/app/data"

# Supabase-only projects created in the Electron app that the operator chose to
# KEEP (not delete) during the replace. Verified 2026-06-09.
KEEP_PROJECT_IDS = {
    "proj_1780527262376_ar1kci",  # Lake Service - June 7, 2026 Bulletin
    "proj_1780592008290_ran4jm",  # Lake Service - June 7, 2026 Bulletin — copy
    "proj_1780528089304_kyyw5t",  # Lake Service - June 7, 2026 Bulletin v2
}


# ── project parser (RAW id, unlike migrate_to_supabase) ──────────────────────
def _parse_project_raw(item: dict, idx: int) -> dict:
    """Normalise a Synology project into a DB row, keeping the RAW proj_* id.

    The whole wrapper object (``{id, name, state:{...}, createdAt, updatedAt}``)
    becomes the ``state`` jsonb column — this matches the shape the live Electron
    app stores (verified against an app-created project).
    """
    if not isinstance(item, dict):
        raise ValueError(f"project[{idx}]: expected dict, got {type(item).__name__}")
    raw_id = str(item.get("id") or "").strip()
    if not raw_id:
        raise ValueError(f"project[{idx}]: missing id")
    return {
        "id": raw_id,
        "name": str(item.get("name") or ""),
        "state": item,
        "revision": int(item.get("revision") or 1),
        "created_at": item.get("createdAt") or None,
        "updated_at": item.get("updatedAt") or None,
    }


# ── source loading ───────────────────────────────────────────────────────────
def load_sources(src: Path) -> dict:
    errors: list[str] = []

    projects_raw, err = _read_json(src / "projects.json", list)
    if err:
        errors.append(err); projects_raw = []
    announcements_raw, err = _read_json(src / "announcements.json", list)
    if err:
        errors.append(err); announcements_raw = []
    songs_raw, err = _read_json(src / "song_database.json", list)
    if err:
        errors.append(err); songs_raw = []
    templates_raw, err = _read_json(src / "templates.json", list)
    if err:
        errors.append(err); templates_raw = []
    settings_raw, err = _read_json(src / "settings.json", dict)
    if err:
        errors.append(err); settings_raw = {}
    volunteer_roles_raw, err = _read_json(src / "volunteer-roles.json", list)
    if err:
        errors.append(err); volunteer_roles_raw = []

    projects, announcements, songs, templates = [], [], [], []
    for i, it in enumerate(projects_raw):
        try: projects.append(_parse_project_raw(it, i))
        except Exception as e: errors.append(f"projects[{i}]: {e}")
    for i, it in enumerate(announcements_raw):
        try: announcements.append(_parse_announcement(it, i))
        except Exception as e: errors.append(f"announcements[{i}]: {e}")
    for i, it in enumerate(songs_raw):
        try: songs.append(_parse_song(it, i))
        except Exception as e: errors.append(f"songs[{i}]: {e}")
    for i, it in enumerate(templates_raw):
        try: templates.append(_parse_template(it, i))
        except Exception as e: errors.append(f"templates[{i}]: {e}")

    settings = _extract_settings(settings_raw) if settings_raw else {}
    if volunteer_roles_raw:
        settings["volunteerRoles"] = volunteer_roles_raw

    return {
        "projects": projects,
        "announcements": announcements,
        "songs": songs,
        "templates": templates,
        "settings": settings,
        "errors": errors,
    }


# ── backup (read Supabase → local JSON) ──────────────────────────────────────
_BACKUP_TABLES = [
    "projects",
    "project_revisions",
    "announcements",
    "songs",
    "templates",
    "workspace_settings",
]


def backup_workspace(conn, out_dir: Path) -> dict:
    """Dump every workspace row to JSON files. Returns {table: rowcount}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for table in _BACKUP_TABLES:
        cur = conn.execute(
            f"SELECT COALESCE(json_agg(t)::text, '[]') "
            f"FROM (SELECT * FROM {table} WHERE workspace_id = %s) t",
            (WORKSPACE_ID,),
        )
        text = cur.fetchone()[0]
        (out_dir / f"{table}.json").write_text(text, encoding="utf-8")
        counts[table] = len(json.loads(text))
    (out_dir / "_manifest.json").write_text(
        json.dumps({"workspace_id": WORKSPACE_ID, "tables": counts}, indent=2),
        encoding="utf-8",
    )
    return counts


# ── plan computation ─────────────────────────────────────────────────────────
def compute_project_plan(conn, projects: list[dict]) -> dict:
    cur = conn.execute(
        "SELECT id FROM projects WHERE workspace_id = %s", (WORKSPACE_ID,)
    )
    existing = {r[0] for r in cur.fetchall()}
    syn_ids = {p["id"] for p in projects}
    keep = set(KEEP_PROJECT_IDS)
    to_delete = sorted(existing - syn_ids - keep)
    return {
        "existing": sorted(existing),
        "syn_ids": sorted(syn_ids),
        "to_delete": to_delete,
        "to_upsert": sorted(syn_ids),
        "kept": sorted(existing & keep),
    }


# ── DB writes ────────────────────────────────────────────────────────────────
def _upsert_project(conn, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO projects (
            id, workspace_id, name, owner_user_id, visibility, state, revision,
            created_at, updated_at, created_by_user_id, updated_by_user_id
        ) VALUES (
            %(id)s, %(ws)s::uuid, %(name)s, %(owner)s::uuid, 'workspace',
            %(state)s::jsonb, %(rev)s,
            COALESCE(%(created)s::timestamptz, now()),
            COALESCE(%(updated)s::timestamptz, now()),
            %(owner)s::uuid, %(owner)s::uuid
        )
        ON CONFLICT (id) DO UPDATE SET
            workspace_id       = EXCLUDED.workspace_id,
            name               = EXCLUDED.name,
            owner_user_id      = EXCLUDED.owner_user_id,
            visibility         = EXCLUDED.visibility,
            state              = EXCLUDED.state,
            revision           = EXCLUDED.revision,
            updated_at         = EXCLUDED.updated_at,
            updated_by_user_id = EXCLUDED.updated_by_user_id
        """,
        {
            "id": row["id"], "ws": WORKSPACE_ID, "name": row["name"],
            "owner": OWNER_USER_ID,
            "state": json.dumps(row["state"], ensure_ascii=False),
            "rev": row["revision"],
            "created": row["created_at"], "updated": row["updated_at"],
        },
    )


def _insert_initial_revision(conn, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO project_revisions (
            id, project_id, workspace_id, revision_number, state, summary,
            created_at, created_by_user_id
        )
        SELECT gen_random_uuid(), %(pid)s, %(ws)s::uuid, %(rev)s, %(state)s::jsonb,
               'Imported from Synology app/data (cutover re-sync)', now(), %(owner)s::uuid
        WHERE NOT EXISTS (
            SELECT 1 FROM project_revisions
            WHERE project_id = %(pid)s AND revision_number = %(rev)s
        )
        """,
        {
            "pid": row["id"], "ws": WORKSPACE_ID, "rev": row["revision"],
            "state": json.dumps(row["state"], ensure_ascii=False),
            "owner": OWNER_USER_ID,
        },
    )


def _upsert_song(conn, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO songs (id, workspace_id, title, data, created_at, updated_at)
        VALUES (%(id)s::uuid, %(ws)s::uuid, %(title)s, %(data)s::jsonb, now(), now())
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title, data = EXCLUDED.data, updated_at = now()
        """,
        {"id": row["id"], "ws": WORKSPACE_ID, "title": row["title"],
         "data": json.dumps(row["data"], ensure_ascii=False)},
    )


def _upsert_announcement(conn, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO announcements (
            id, workspace_id, title, body, state, created_at, updated_at, created_by_user_id
        ) VALUES (
            %(id)s::uuid, %(ws)s::uuid, %(title)s, %(body)s, %(state)s::jsonb,
            now(), now(), %(owner)s::uuid
        )
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title, body = EXCLUDED.body,
            state = EXCLUDED.state, updated_at = now()
        """,
        {"id": row["id"], "ws": WORKSPACE_ID, "title": row["title"],
         "body": row["body"], "state": json.dumps(row["state"], ensure_ascii=False),
         "owner": OWNER_USER_ID},
    )


def _upsert_template(conn, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO templates (
            id, workspace_id, name, template_data, is_default, created_at, updated_at
        ) VALUES (
            %(id)s::uuid, %(ws)s::uuid, %(name)s, %(td)s::jsonb, %(def)s, now(), now()
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name, template_data = EXCLUDED.template_data,
            is_default = EXCLUDED.is_default, updated_at = now()
        """,
        {"id": row["id"], "ws": WORKSPACE_ID, "name": row["name"],
         "td": json.dumps(row["template_data"], ensure_ascii=False),
         "def": row["is_default"]},
    )


def _replace_workspace_settings(conn, settings: dict) -> None:
    conn.execute(
        """
        INSERT INTO workspace_settings (workspace_id, settings)
        VALUES (%(ws)s::uuid, %(s)s::jsonb)
        ON CONFLICT (workspace_id) DO UPDATE SET settings = EXCLUDED.settings
        """,
        {"ws": WORKSPACE_ID, "s": json.dumps(settings, ensure_ascii=False)},
    )


# ── reporting ────────────────────────────────────────────────────────────────
def print_dry_run(src: Path, data: dict, plan: dict) -> None:
    s = data["settings"]
    print()
    print("=== resync_synology_to_supabase.py  [DRY RUN — no DB writes] ===")
    print(f"  source     : {src}")
    print(f"  workspace  : {WORKSPACE_ID}")
    print(f"  owner      : {OWNER_USER_ID}  (AJ — transfer to secretary later)")
    print()
    print("  PROJECTS (replace, keep-list preserved):")
    print(f"    existing in Supabase : {len(plan['existing'])}")
    print(f"    Synology to upsert   : {len(plan['to_upsert'])}")
    print(f"    will DELETE          : {len(plan['to_delete'])}")
    print(f"    kept (Lake Service)  : {len(plan['kept'])}  {plan['kept']}")
    print(f"    final project count  : {len(plan['to_upsert']) + len(plan['kept'])}")
    print()
    print("  UNION/UPSERT (Synology wins; Supabase-only rows preserved):")
    print(f"    songs                : {len(data['songs'])} upserts")
    print(f"    announcements        : {len(data['announcements'])} upserts")
    print(f"    templates            : {len(data['templates'])} upserts")
    print()
    vr = len(s.get("volunteerRoles", [])) if isinstance(s, dict) else 0
    staff = len(s.get("staffData", [])) if isinstance(s, dict) else 0
    print(f"  WORKSPACE_SETTINGS replace: {len(s)} keys "
          f"(staff={staff}, volunteerRoles={vr}); OAuth tokens excluded")
    print()
    if plan["to_delete"]:
        print("  Projects to DELETE (seed/stale rows being replaced):")
        for pid in plan["to_delete"]:
            print(f"    - {pid}")
        print()
    if data["errors"]:
        print(f"  PARSE ERRORS ({len(data['errors'])}):")
        for e in data["errors"]:
            print(f"    ! {e}")
        print()
    print("  Re-run with --execute to write (a backup is taken first).")
    print()


# ── execute ──────────────────────────────────────────────────────────────────
def execute(conn, data: dict, plan: dict) -> dict:
    # 1. delete replaced project rows (revisions first — FK), keep-list preserved
    if plan["to_delete"]:
        conn.execute(
            "DELETE FROM project_revisions WHERE workspace_id = %s AND project_id = ANY(%s)",
            (WORKSPACE_ID, plan["to_delete"]),
        )
        conn.execute(
            "DELETE FROM projects WHERE workspace_id = %s AND id = ANY(%s)",
            (WORKSPACE_ID, plan["to_delete"]),
        )
    # 2. upsert Synology projects + initial revision
    for row in data["projects"]:
        _upsert_project(conn, row)
        _insert_initial_revision(conn, row)
    # 3. union upserts
    for row in data["songs"]:
        _upsert_song(conn, row)
    for row in data["announcements"]:
        _upsert_announcement(conn, row)
    for row in data["templates"]:
        _upsert_template(conn, row)
    # 4. replace settings
    if data["settings"]:
        _replace_workspace_settings(conn, data["settings"])

    # verification counts (within same tx, pre-commit)
    counts = {}
    for t in ("projects", "songs", "announcements", "templates"):
        counts[t] = conn.execute(
            f"SELECT count(*) FROM {t} WHERE workspace_id = %s", (WORKSPACE_ID,)
        ).fetchone()[0]
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=DEFAULT_SOURCE,
                    help=f"Synology data dir (default: {DEFAULT_SOURCE})")
    ap.add_argument("--backup-root", default="/Volumes/docker/bulletingenerator/backups",
                    help="Where to write the Supabase backup dir.")
    ap.add_argument("--backup", action="store_true",
                    help="Only back up current Supabase workspace state, then exit.")
    ap.add_argument("--execute", action="store_true",
                    help="Write to Supabase (auto-backs-up first). Default is dry-run.")
    args = ap.parse_args(argv)

    src = Path(args.source).resolve()
    if not src.exists():
        print(f"ERROR: source dir not found: {src}", file=sys.stderr)
        return 1

    data = load_sources(src)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

    # --backup only
    if args.backup:
        from db import admin_transaction  # noqa: PLC0415
        out = Path(args.backup_root) / f"supabase-precutover-{stamp}"
        with admin_transaction() as conn:
            counts = backup_workspace(conn, out)
        print(f"Backup written to: {out}")
        for t, n in counts.items():
            print(f"  {t:20} {n:>6} rows")
        return 0

    # dry-run (default): connect read-only to compute the project plan
    from db import admin_transaction  # noqa: PLC0415
    if not args.execute:
        with admin_transaction() as conn:
            plan = compute_project_plan(conn, data["projects"])
            # roll back the (read-only) tx explicitly — no writes happened
            conn.rollback()
        print_dry_run(src, data, plan)
        return 1 if data["errors"] else 0

    # --execute
    if data["errors"]:
        print("Refusing to execute: source parse errors present:", file=sys.stderr)
        for e in data["errors"]:
            print(f"  ! {e}", file=sys.stderr)
        return 1

    out = Path(args.backup_root) / f"supabase-precutover-{stamp}"
    with admin_transaction() as conn:
        bcounts = backup_workspace(conn, out)
        print(f"[backup] written to {out}: " +
              ", ".join(f"{t}={n}" for t, n in bcounts.items()))
        plan = compute_project_plan(conn, data["projects"])
        counts = execute(conn, data, plan)
        # admin_transaction commits on clean exit
    print()
    print("=== EXECUTE complete (committed) ===")
    print(f"  projects deleted : {len(plan['to_delete'])}")
    print(f"  projects kept    : {len(plan['kept'])}")
    print(f"  post-write workspace counts:")
    for t, n in counts.items():
        print(f"    {t:20} {n:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
