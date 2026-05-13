"""
storage.py — Storage abstraction boundary.

Routes call these methods; the implementation routes to JSON files (desktop)
or Postgres (server mode).  This module never imports server.py directly —
it re-implements the minimal read/write helpers it needs.

Usage:
    from storage import get_storage
    store = get_storage()
    projects = store.list_projects()
"""

from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Minimal JSON helpers (mirrors server._read_json / _write_json)
# ---------------------------------------------------------------------------

def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    """Atomic write: write to .tmp then rename."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Base class / protocol
# ---------------------------------------------------------------------------

class StorageBackend(ABC):
    """Abstract storage interface.  All route handlers talk to this interface;
    the concrete implementation (JSON or Postgres) is chosen at startup."""

    # ── Projects ──────────────────────────────────────────────────────────────

    @abstractmethod
    def list_projects(self) -> list:
        """Return the full list of project dicts."""
        ...

    @abstractmethod
    def get_project(self, project_id: str) -> dict | None:
        """Return a single project dict by id, or None if not found."""
        ...

    @abstractmethod
    def save_project(self, data: dict) -> dict:
        """Upsert a project.  ``data`` must contain an ``id`` key.  Returns the saved project."""
        ...

    @abstractmethod
    def delete_project(self, project_id: str) -> bool:
        """Delete a project by id.  Returns True if it existed."""
        ...

    # ── Settings ──────────────────────────────────────────────────────────────

    @abstractmethod
    def get_settings(self) -> dict:
        """Return the settings dict."""
        ...

    @abstractmethod
    def save_settings(self, data: dict) -> dict:
        """Persist the settings dict.  Returns the saved settings."""
        ...

    # ── Announcements ─────────────────────────────────────────────────────────

    @abstractmethod
    def list_announcements(self) -> list:
        """Return the full list of announcement dicts."""
        ...

    @abstractmethod
    def save_announcements(self, data: list) -> list:
        """Persist the full announcements list.  Returns the saved list."""
        ...

    # ── Songs ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def list_songs(self) -> list:
        """Return the full song-database list."""
        ...

    @abstractmethod
    def save_songs(self, data: list) -> list:
        """Persist the full song-database list.  Returns the saved list."""
        ...

    # ── Templates ─────────────────────────────────────────────────────────────

    @abstractmethod
    def list_templates(self) -> list:
        """Return user-defined (non-built-in) template dicts."""
        ...

    @abstractmethod
    def save_templates(self, data: list) -> list:
        """Persist the full templates list.  Returns the saved list."""
        ...


# ---------------------------------------------------------------------------
# JSON implementation (desktop mode)
# ---------------------------------------------------------------------------

class JsonStorageBackend(StorageBackend):
    """Delegates all storage to JSON files in *data_dir*.

    Thread-safety: a single ``threading.Lock`` serialises all writes,
    matching the behaviour of server.py's ``_lock``.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._lock = threading.Lock()

        self._projects_file      = self._data_dir / "projects.json"
        self._announcements_file = self._data_dir / "announcements.json"
        self._settings_file      = self._data_dir / "settings.json"
        self._songs_file         = self._data_dir / "song_database.json"
        self._templates_file     = self._data_dir / "templates.json"

    # ── Projects ──────────────────────────────────────────────────────────────

    def list_projects(self) -> list:
        with self._lock:
            return _read_json(self._projects_file, [])

    def get_project(self, project_id: str) -> dict | None:
        with self._lock:
            projects = _read_json(self._projects_file, [])
        for p in projects:
            if isinstance(p, dict) and p.get("id") == project_id:
                return p
        return None

    def save_project(self, data: dict) -> dict:
        if "id" not in data:
            raise ValueError("project data must contain an 'id' key")
        with self._lock:
            projects = _read_json(self._projects_file, [])
            for i, p in enumerate(projects):
                if isinstance(p, dict) and p.get("id") == data["id"]:
                    projects[i] = data
                    break
            else:
                projects.append(data)
            _write_json(self._projects_file, projects)
        return data

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            projects = _read_json(self._projects_file, [])
            new_projects = [p for p in projects if not (isinstance(p, dict) and p.get("id") == project_id)]
            existed = len(new_projects) < len(projects)
            if existed:
                _write_json(self._projects_file, new_projects)
        return existed

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> dict:
        with self._lock:
            return _read_json(self._settings_file, {})

    def save_settings(self, data: dict) -> dict:
        with self._lock:
            _write_json(self._settings_file, data)
        return data

    # ── Announcements ─────────────────────────────────────────────────────────

    def list_announcements(self) -> list:
        with self._lock:
            return _read_json(self._announcements_file, [])

    def save_announcements(self, data: list) -> list:
        with self._lock:
            _write_json(self._announcements_file, data)
        return data

    # ── Songs ─────────────────────────────────────────────────────────────────

    def list_songs(self) -> list:
        with self._lock:
            return _read_json(self._songs_file, [])

    def save_songs(self, data: list) -> list:
        with self._lock:
            _write_json(self._songs_file, data)
        return data

    # ── Templates ─────────────────────────────────────────────────────────────

    def list_templates(self) -> list:
        with self._lock:
            return _read_json(self._templates_file, [])

    def save_templates(self, data: list) -> list:
        with self._lock:
            _write_json(self._templates_file, data)
        return data


# ---------------------------------------------------------------------------
# Postgres stub (server mode — filled in by issues #196-#201)
# ---------------------------------------------------------------------------

class PostgresStorageBackend(StorageBackend):
    """Postgres-backed storage for multi-user server deployments.

    Project methods are fully implemented.  All other methods raise
    ``NotImplementedError`` until the remaining issues (#197-#201) land.
    """

    # ── Projects ──────────────────────────────────────────────────────────────

    def list_projects(self) -> list:
        """Return all projects ordered by updated_at DESC."""
        from db import transaction, from_jsonb  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                """
                SELECT id, name, owner_user_id, visibility, state, revision,
                       created_at, updated_at, created_by_email, updated_by_email,
                       imported_from_json
                FROM projects
                ORDER BY updated_at DESC
                """
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [_pg_row_to_project(dict(zip(cols, row))) for row in rows]

    def get_project(self, project_id: str) -> dict | None:
        """Return a single project dict by id, or None if not found."""
        from db import transaction  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                """
                SELECT id, name, owner_user_id, visibility, state, revision,
                       created_at, updated_at, created_by_email, updated_by_email,
                       imported_from_json
                FROM projects
                WHERE id = %s::uuid
                """,
                (project_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cursor.description]
        return _pg_row_to_project(dict(zip(cols, row)))

    def save_project(self, data: dict) -> dict:
        """Upsert a project and return the persisted dict.

        * On INSERT  — revision defaults to 1.
        * On UPDATE  — revision is incremented by 1.
        ``data`` must contain an ``id`` key (UUID string).
        """
        if "id" not in data:
            raise ValueError("project data must contain an 'id' key")

        import json as _json  # noqa: PLC0415
        from db import transaction  # noqa: PLC0415

        project_id = data["id"]
        name = str(data.get("name") or "")
        state_json = _json.dumps(data, ensure_ascii=False)
        created_by_email = str(data.get("createdBy") or "")
        updated_by_email = str(data.get("updatedBy") or "")
        created_at = data.get("createdAt") or None
        updated_at = data.get("updatedAt") or None

        with transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (
                    id, name, owner_user_id, visibility, state, revision,
                    created_at, updated_at, created_by_email, updated_by_email,
                    imported_from_json
                ) VALUES (
                    %(id)s::uuid, %(name)s, NULL, 'workspace', %(state)s::jsonb, 1,
                    COALESCE(%(created_at)s::timestamptz, now()),
                    COALESCE(%(updated_at)s::timestamptz, now()),
                    %(created_by_email)s, %(updated_by_email)s, FALSE
                )
                ON CONFLICT (id) DO UPDATE SET
                    name             = EXCLUDED.name,
                    state            = EXCLUDED.state,
                    revision         = projects.revision + 1,
                    updated_at       = COALESCE(EXCLUDED.updated_at, now()),
                    updated_by_email = EXCLUDED.updated_by_email
                RETURNING id, name, owner_user_id, visibility, state, revision,
                          created_at, updated_at, created_by_email, updated_by_email,
                          imported_from_json
                """,
                {
                    "id": project_id,
                    "name": name,
                    "state": state_json,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "created_by_email": created_by_email,
                    "updated_by_email": updated_by_email,
                },
            )
            row = cursor.fetchone()
            cols = [d[0] for d in cursor.description]
        return _pg_row_to_project(dict(zip(cols, row)))

    def delete_project(self, project_id: str) -> bool:
        """Delete a project by id; return True if it existed."""
        from db import transaction  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM projects WHERE id = %s::uuid",
                (project_id,),
            )
        return cursor.rowcount == 1

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> dict:
        raise NotImplementedError("PostgresStorageBackend.get_settings not yet implemented")

    def save_settings(self, data: dict) -> dict:
        raise NotImplementedError("PostgresStorageBackend.save_settings not yet implemented")

    # ── Announcements ─────────────────────────────────────────────────────────

    def list_announcements(self) -> list:
        raise NotImplementedError("PostgresStorageBackend.list_announcements not yet implemented")

    def save_announcements(self, data: list) -> list:
        raise NotImplementedError("PostgresStorageBackend.save_announcements not yet implemented")

    # ── Songs ─────────────────────────────────────────────────────────────────

    def list_songs(self) -> list:
        raise NotImplementedError("PostgresStorageBackend.list_songs not yet implemented")

    def save_songs(self, data: list) -> list:
        raise NotImplementedError("PostgresStorageBackend.save_songs not yet implemented")

    # ── Templates ─────────────────────────────────────────────────────────────

    def list_templates(self) -> list:
        raise NotImplementedError("PostgresStorageBackend.list_templates not yet implemented")

    def save_templates(self, data: list) -> list:
        raise NotImplementedError("PostgresStorageBackend.save_templates not yet implemented")


# ---------------------------------------------------------------------------
# Postgres row → project dict helper
# ---------------------------------------------------------------------------

def _pg_row_to_project(row: dict) -> dict:
    """Convert a raw Postgres row dict into the project dict shape expected by the frontend.

    The ``state`` column holds the full project payload as JSONB.  We return
    that payload merged with a few top-level fields that callers depend on
    (``id``, ``name``, ``revision``) so callers can trust those keys even if
    the stored state blob is missing them.
    """
    from db import from_jsonb  # noqa: PLC0415

    state = from_jsonb(row.get("state")) or {}
    if not isinstance(state, dict):
        state = {}

    # Merge DB-authoritative fields on top of the stored state blob.
    state["id"] = str(row["id"])
    state["name"] = row.get("name") or state.get("name") or ""
    state["revision"] = row.get("revision") or state.get("revision") or 1

    # Surface timestamps and attribution as camelCase keys matching the legacy format.
    if row.get("created_at"):
        state.setdefault("createdAt", _ts(row["created_at"]))
    if row.get("updated_at"):
        state["updatedAt"] = _ts(row["updated_at"])
    if row.get("created_by_email"):
        state.setdefault("createdBy", row["created_by_email"])
    if row.get("updated_by_email"):
        state["updatedBy"] = row["updated_by_email"]

    return state


def _ts(value) -> str:
    """Convert a datetime (or string) to ISO-8601 string."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_storage(data_dir: Path | None = None) -> StorageBackend:
    """Return the appropriate storage backend for the current APP_MODE.

    ``data_dir`` is required when ``APP_MODE=desktop`` (or when the default
    desktop data directory cannot be inferred).  If omitted the factory reads
    ``DATA_DIR`` from the environment / standard platform paths to match
    server.py behaviour.

    When ``APP_MODE=server`` a ``PostgresStorageBackend`` is returned.
    """
    app_mode = os.environ.get("APP_MODE", "desktop").strip().lower()
    is_desktop = app_mode == "desktop"

    if is_desktop:
        if data_dir is None:
            import sys
            import platform
            if getattr(sys, "frozen", False):
                if platform.system() == "Darwin":
                    data_dir = Path.home() / "Library" / "Application Support" / "BulletinGenerator"
                elif platform.system() == "Windows":
                    data_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "BulletinGenerator"
                else:
                    data_dir = Path.home() / ".bulletin-generator"
            else:
                data_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "data"
        return JsonStorageBackend(Path(data_dir))

    return PostgresStorageBackend()
