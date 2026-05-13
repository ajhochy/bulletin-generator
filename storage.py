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

    All methods raise ``NotImplementedError`` until the Postgres
    implementations are wired in by subsequent issues (#196-#201).
    """

    # ── Projects ──────────────────────────────────────────────────────────────

    def list_projects(self) -> list:
        raise NotImplementedError("PostgresStorageBackend.list_projects not yet implemented")

    def get_project(self, project_id: str) -> dict | None:
        raise NotImplementedError("PostgresStorageBackend.get_project not yet implemented")

    def save_project(self, data: dict) -> dict:
        raise NotImplementedError("PostgresStorageBackend.save_project not yet implemented")

    def delete_project(self, project_id: str) -> bool:
        raise NotImplementedError("PostgresStorageBackend.delete_project not yet implemented")

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
