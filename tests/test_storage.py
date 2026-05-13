"""
Tests for storage.py — the storage abstraction layer.

Covers:
  - get_storage() returns JsonStorageBackend in desktop mode
  - get_storage() returns PostgresStorageBackend in server mode
  - JsonStorageBackend round-trips for all resource types
  - PostgresStorageBackend raises NotImplementedError for every method
"""

import os
import sys
import pytest
from pathlib import Path

# Ensure project root is on the path so storage.py can be imported.
sys.path.insert(0, str(Path(__file__).parent.parent))

import storage as storage_module
from storage import (
    get_storage,
    JsonStorageBackend,
    PostgresStorageBackend,
    StorageBackend,
)


# ── Factory: backend selection by APP_MODE ─────────────────────────────────────

class TestGetStorage:
    def test_desktop_mode_returns_json_backend(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_MODE", "desktop")
        backend = get_storage(data_dir=tmp_path)
        assert isinstance(backend, JsonStorageBackend)

    def test_server_mode_returns_postgres_backend(self, monkeypatch):
        monkeypatch.setenv("APP_MODE", "server")
        backend = get_storage()
        assert isinstance(backend, PostgresStorageBackend)

    def test_default_mode_returns_json_backend(self, tmp_path, monkeypatch):
        """APP_MODE defaults to 'desktop' when not set."""
        monkeypatch.delenv("APP_MODE", raising=False)
        backend = get_storage(data_dir=tmp_path)
        assert isinstance(backend, JsonStorageBackend)

    def test_json_backend_is_storage_backend(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_MODE", "desktop")
        backend = get_storage(data_dir=tmp_path)
        assert isinstance(backend, StorageBackend)

    def test_postgres_backend_is_storage_backend(self, monkeypatch):
        monkeypatch.setenv("APP_MODE", "server")
        backend = get_storage()
        assert isinstance(backend, StorageBackend)


# ── JsonStorageBackend round-trip tests ───────────────────────────────────────

class TestJsonStorageBackendProjects:
    def test_list_projects_empty_by_default(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        assert backend.list_projects() == []

    def test_save_and_get_project(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        project = {"id": "proj-1", "title": "Sunday Service"}
        saved = backend.save_project(project)
        assert saved == project
        assert backend.get_project("proj-1") == project

    def test_save_returns_saved_project(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        project = {"id": "proj-2", "title": "Easter"}
        result = backend.save_project(project)
        assert result == project

    def test_list_projects_after_save(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_project({"id": "a", "title": "A"})
        backend.save_project({"id": "b", "title": "B"})
        ids = [p["id"] for p in backend.list_projects()]
        assert ids == ["a", "b"]

    def test_save_project_updates_existing(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_project({"id": "proj-1", "title": "Original"})
        backend.save_project({"id": "proj-1", "title": "Updated"})
        projects = backend.list_projects()
        assert len(projects) == 1
        assert projects[0]["title"] == "Updated"

    def test_get_project_missing_returns_none(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        assert backend.get_project("nonexistent") is None

    def test_delete_project_returns_true_when_found(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_project({"id": "proj-1", "title": "To Delete"})
        assert backend.delete_project("proj-1") is True
        assert backend.get_project("proj-1") is None

    def test_delete_project_returns_false_when_missing(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        assert backend.delete_project("ghost") is False

    def test_delete_project_removes_only_target(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_project({"id": "keep", "title": "Keep"})
        backend.save_project({"id": "remove", "title": "Remove"})
        backend.delete_project("remove")
        assert [p["id"] for p in backend.list_projects()] == ["keep"]

    def test_save_project_requires_id(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        with pytest.raises(ValueError, match="id"):
            backend.save_project({"title": "No ID"})

    def test_projects_file_is_atomic(self, tmp_path):
        """No .tmp file should remain after a save."""
        backend = JsonStorageBackend(tmp_path)
        backend.save_project({"id": "x", "title": "X"})
        assert not (tmp_path / "projects.tmp").exists()
        assert (tmp_path / "projects.json").exists()


class TestJsonStorageBackendSettings:
    def test_get_settings_empty_by_default(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        assert backend.get_settings() == {}

    def test_save_and_get_settings(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        settings = {"churchName": "Grace Church", "pcoEnabled": True}
        result = backend.save_settings(settings)
        assert result == settings
        assert backend.get_settings() == settings

    def test_save_settings_overwrites(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_settings({"v": 1})
        backend.save_settings({"v": 2})
        assert backend.get_settings()["v"] == 2

    def test_save_settings_returns_saved(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        data = {"key": "value"}
        assert backend.save_settings(data) == data


class TestJsonStorageBackendAnnouncements:
    def test_list_announcements_empty_by_default(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        assert backend.list_announcements() == []

    def test_save_and_list_announcements(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        anns = [{"id": "ann-1", "text": "Potluck Sunday"}]
        result = backend.save_announcements(anns)
        assert result == anns
        assert backend.list_announcements() == anns

    def test_save_announcements_returns_list(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        data = [{"id": "a"}]
        assert backend.save_announcements(data) == data

    def test_save_announcements_replaces_all(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_announcements([{"id": "old"}])
        backend.save_announcements([{"id": "new1"}, {"id": "new2"}])
        assert [a["id"] for a in backend.list_announcements()] == ["new1", "new2"]


class TestJsonStorageBackendSongs:
    def test_list_songs_empty_by_default(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        assert backend.list_songs() == []

    def test_save_and_list_songs(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        songs = [{"title": "Amazing Grace", "author": "Newton"}]
        result = backend.save_songs(songs)
        assert result == songs
        assert backend.list_songs() == songs

    def test_save_songs_returns_list(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        data = [{"title": "How Great Thou Art"}]
        assert backend.save_songs(data) == data

    def test_save_songs_replaces_all(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_songs([{"title": "Old Song"}])
        backend.save_songs([{"title": "Song A"}, {"title": "Song B"}])
        assert [s["title"] for s in backend.list_songs()] == ["Song A", "Song B"]


class TestJsonStorageBackendTemplates:
    def test_list_templates_empty_by_default(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        assert backend.list_templates() == []

    def test_save_and_list_templates(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        templates = [{"id": "tmpl-1", "name": "Classic"}]
        result = backend.save_templates(templates)
        assert result == templates
        assert backend.list_templates() == templates

    def test_save_templates_returns_list(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        data = [{"id": "t"}]
        assert backend.save_templates(data) == data

    def test_save_templates_replaces_all(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_templates([{"id": "old"}])
        backend.save_templates([{"id": "new"}])
        assert [t["id"] for t in backend.list_templates()] == ["new"]


# ── PostgresStorageBackend — unimplemented methods still raise ────────────────

class TestPostgresStorageBackendNotImplemented:
    """Non-project methods on PostgresStorageBackend must raise NotImplementedError.

    Project methods are implemented in #196 and tested in
    tests/test_import_projects.py (mocked DB).
    """

    @pytest.fixture
    def pg(self):
        return PostgresStorageBackend()

    def test_get_settings(self, pg):
        with pytest.raises(NotImplementedError):
            pg.get_settings()

    def test_save_settings(self, pg):
        with pytest.raises(NotImplementedError):
            pg.save_settings({})

    def test_list_announcements(self, pg):
        with pytest.raises(NotImplementedError):
            pg.list_announcements()

    def test_save_announcements(self, pg):
        with pytest.raises(NotImplementedError):
            pg.save_announcements([])

    def test_list_songs(self, pg):
        with pytest.raises(NotImplementedError):
            pg.list_songs()

    def test_save_songs(self, pg):
        with pytest.raises(NotImplementedError):
            pg.save_songs([])

    def test_list_templates(self, pg):
        with pytest.raises(NotImplementedError):
            pg.list_templates()

    def test_save_templates(self, pg):
        with pytest.raises(NotImplementedError):
            pg.save_templates([])
