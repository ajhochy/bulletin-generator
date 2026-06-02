"""
tests/test_storage_routing.py — Route-layer storage routing tests for #221.

Verifies that each migrated route handler calls the storage abstraction
(get_storage()) rather than reading/writing JSON files directly, in both
server and desktop modes.

No live PostgreSQL or HTTP server is required — storage and DB helpers are
fully mocked.  The ``cgi`` module is stubbed before importing server.py so
the test runs cleanly on Python ≥ 3.13.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Compatibility shim for Python ≥ 3.13 (cgi removed) ───────────────────────
if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

import server  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_handler():
    """Return a Handler instance with _send_json and _require_auth mocked."""
    handler = server.Handler.__new__(server.Handler)
    handler._send_json = MagicMock()
    # Simulate a logged-in user
    handler._require_auth = MagicMock(return_value={"id": "user-1", "email": "test@example.com"})
    return handler


def _sent(handler):
    """Return (data_dict, status_code) from the captured _send_json call."""
    assert handler._send_json.called, "_send_json was never called"
    args = handler._send_json.call_args
    data = args[0][0]
    if len(args[0]) > 1:
        status = args[0][1]
    else:
        status = args[1].get("status", 200) if args[1] else 200
    return data, status


def _mock_store(
    announcements=None, songs=None, settings=None, templates=None, fonts=None
):
    """Build a mock store with preset return values."""
    store = MagicMock()
    store.list_announcements.return_value = announcements if announcements is not None else []
    store.list_songs.return_value = songs if songs is not None else []
    store.get_settings.return_value = settings if settings is not None else {}
    store.list_templates.return_value = templates if templates is not None else []
    store.list_fonts.return_value = fonts if fonts is not None else []
    store.save_announcements.return_value = []
    store.save_songs.return_value = []
    store.save_settings.return_value = {}
    store.save_templates.return_value = []
    return store


# ── GET /api/announcements ─────────────────────────────────────────────────────

class TestGetAnnouncementsStorageRouting:
    """_handle_get_announcements must call store.list_announcements()."""

    def _call(self, store, mode="server"):
        handler = _make_handler()
        is_desktop = mode == "desktop"
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch.object(server, "APP_MODE", mode), \
             patch("storage.get_storage", return_value=store):
            handler._handle_get_announcements()
        return handler

    def test_server_mode_calls_list_announcements(self):
        store = _mock_store(announcements=[{"id": "a1", "title": "Test"}])
        self._call(store, mode="server")
        store.list_announcements.assert_called_once()

    def test_server_mode_returns_announcements(self):
        anns = [{"id": "a1", "title": "Test"}]
        store = _mock_store(announcements=anns)
        handler = self._call(store, mode="server")
        data, status = _sent(handler)
        assert data == anns
        assert status == 200

    def test_desktop_mode_calls_list_announcements(self):
        store = _mock_store(announcements=[])
        self._call(store, mode="desktop")
        store.list_announcements.assert_called_once()

    def test_returns_empty_list_when_no_announcements(self):
        store = _mock_store(announcements=[])
        handler = self._call(store, mode="server")
        data, _ = _sent(handler)
        assert data == []


# ── POST /api/announcements ────────────────────────────────────────────────────

class TestPostAnnouncementsStorageRouting:
    """_handle_post_announcements must call store.save_announcements()."""

    def _call(self, store, body, mode="server"):
        import json
        handler = _make_handler()
        handler._read_body_json = MagicMock(return_value=body)
        is_desktop = mode == "desktop"
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch.object(server, "APP_MODE", mode), \
             patch("storage.get_storage", return_value=store):
            handler._handle_post_announcements()
        return handler

    def test_server_mode_calls_save_announcements(self):
        store = _mock_store()
        anns = [{"id": "a1", "title": "Potluck"}]
        self._call(store, anns, mode="server")
        store.save_announcements.assert_called_once_with(anns)

    def test_desktop_mode_calls_save_announcements(self):
        store = _mock_store()
        anns = [{"id": "a1", "title": "Potluck"}]
        self._call(store, anns, mode="desktop")
        store.save_announcements.assert_called_once_with(anns)

    def test_returns_ok_true(self):
        store = _mock_store()
        handler = self._call(store, [], mode="server")
        data, status = _sent(handler)
        assert data == {"ok": True}
        assert status == 200

    def test_rejects_non_list_body(self):
        store = _mock_store()
        handler = self._call(store, {"not": "a list"}, mode="server")
        data, status = _sent(handler)
        assert status == 400
        store.save_announcements.assert_not_called()


# ── GET /api/songs ─────────────────────────────────────────────────────────────

class TestGetSongsStorageRouting:
    """_handle_get_songs must call store.list_songs()."""

    def _call(self, store, mode="server"):
        handler = _make_handler()
        is_desktop = mode == "desktop"
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch.object(server, "APP_MODE", mode), \
             patch("storage.get_storage", return_value=store):
            handler._handle_get_songs()
        return handler

    def test_server_mode_calls_list_songs(self):
        store = _mock_store(songs=[{"title": "Amazing Grace"}])
        self._call(store, mode="server")
        store.list_songs.assert_called_once()

    def test_desktop_mode_calls_list_songs(self):
        store = _mock_store(songs=[])
        self._call(store, mode="desktop")
        store.list_songs.assert_called_once()

    def test_returns_songs_list(self):
        songs = [{"title": "How Great Thou Art"}]
        store = _mock_store(songs=songs)
        handler = self._call(store, mode="server")
        data, status = _sent(handler)
        assert data == songs
        assert status == 200


# ── POST /api/songs ────────────────────────────────────────────────────────────

class TestPostSongsStorageRouting:
    """_handle_post_songs must call store.save_songs()."""

    def _call(self, store, body, mode="server"):
        handler = _make_handler()
        handler._read_body_json = MagicMock(return_value=body)
        is_desktop = mode == "desktop"
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch.object(server, "APP_MODE", mode), \
             patch("storage.get_storage", return_value=store):
            handler._handle_post_songs()
        return handler

    def test_server_mode_calls_save_songs(self):
        store = _mock_store()
        songs = [{"title": "Amazing Grace"}]
        self._call(store, songs, mode="server")
        store.save_songs.assert_called_once_with(songs)

    def test_desktop_mode_calls_save_songs(self):
        store = _mock_store()
        songs = [{"title": "Blessed Assurance"}]
        self._call(store, songs, mode="desktop")
        store.save_songs.assert_called_once_with(songs)

    def test_returns_ok_true(self):
        store = _mock_store()
        handler = self._call(store, [], mode="server")
        data, _ = _sent(handler)
        assert data == {"ok": True}

    def test_rejects_non_list_body(self):
        store = _mock_store()
        handler = self._call(store, "not a list", mode="server")
        data, status = _sent(handler)
        assert status == 400
        store.save_songs.assert_not_called()


# ── GET /api/settings ─────────────────────────────────────────────────────────

class TestGetSettingsStorageRouting:
    """_handle_get_settings must call store.get_settings()."""

    def _call(self, store, mode="server"):
        handler = _make_handler()
        is_desktop = mode == "desktop"
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch.object(server, "APP_MODE", mode), \
             patch("storage.get_storage", return_value=store):
            handler._handle_get_settings()
        return handler

    def test_server_mode_calls_get_settings(self):
        store = _mock_store(settings={"churchName": "Grace"})
        self._call(store, mode="server")
        store.get_settings.assert_called_once()

    def test_desktop_mode_calls_get_settings(self):
        store = _mock_store(settings={})
        self._call(store, mode="desktop")
        store.get_settings.assert_called_once()

    def test_returns_settings_dict(self):
        settings = {"churchName": "Grace Church", "timezone": "US/Pacific"}
        store = _mock_store(settings=settings)
        handler = self._call(store, mode="server")
        data, status = _sent(handler)
        assert data == settings
        assert status == 200


# ── POST /api/settings ────────────────────────────────────────────────────────

class TestPostSettingsStorageRouting:
    """_handle_post_settings must call store.get_settings() and store.save_settings()."""

    def _call(self, store, body, mode="server"):
        handler = _make_handler()
        handler._read_body_json = MagicMock(return_value=body)
        is_desktop = mode == "desktop"
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch.object(server, "APP_MODE", mode), \
             patch("storage.get_storage", return_value=store):
            handler._handle_post_settings()
        return handler

    def test_server_mode_merges_and_saves(self):
        store = _mock_store(settings={"existing": "value"})
        self._call(store, {"newKey": "newValue"}, mode="server")
        store.get_settings.assert_called_once()
        # save_settings should be called with the merged dict
        call_args = store.save_settings.call_args[0][0]
        assert call_args["existing"] == "value"
        assert call_args["newKey"] == "newValue"

    def test_desktop_mode_merges_and_saves(self):
        store = _mock_store(settings={"old": "data"})
        self._call(store, {"new": "field"}, mode="desktop")
        store.save_settings.assert_called_once()

    def test_none_value_removes_key(self):
        store = _mock_store(settings={"removeMe": "value", "keep": "this"})
        self._call(store, {"removeMe": None}, mode="server")
        call_args = store.save_settings.call_args[0][0]
        assert "removeMe" not in call_args
        assert call_args["keep"] == "this"

    def test_returns_ok_true(self):
        store = _mock_store(settings={})
        handler = self._call(store, {}, mode="server")
        data, status = _sent(handler)
        assert data == {"ok": True}

    def test_rejects_non_dict_body(self):
        store = _mock_store()
        handler = self._call(store, ["not", "a", "dict"], mode="server")
        data, status = _sent(handler)
        assert status == 400
        store.save_settings.assert_not_called()


# ── GET /api/templates ────────────────────────────────────────────────────────

class TestGetTemplatesStorageRouting:
    """_handle_get_templates must call store.list_templates()."""

    def _call(self, store, mode="server"):
        handler = _make_handler()
        is_desktop = mode == "desktop"
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch.object(server, "APP_MODE", mode), \
             patch("storage.get_storage", return_value=store):
            handler._handle_get_templates()
        return handler

    def test_server_mode_calls_list_templates(self):
        store = _mock_store(templates=[{"id": "classic", "name": "Classic"}])
        self._call(store, mode="server")
        store.list_templates.assert_called_once()

    def test_desktop_mode_calls_list_templates(self):
        store = _mock_store(templates=[])
        self._call(store, mode="desktop")
        store.list_templates.assert_called_once()

    def test_returns_templates_list(self):
        templates = [{"id": "classic", "name": "Classic", "builtIn": True}]
        store = _mock_store(templates=templates)
        handler = self._call(store, mode="server")
        data, status = _sent(handler)
        assert data == templates
        assert status == 200


# ── POST /api/templates ────────────────────────────────────────────────────────

class TestPostTemplatesStorageRouting:
    """_handle_post_templates must call store.list_templates() and store.save_templates()."""

    _VALID_TEMPLATE = {
        "id": "my-template",
        "name": "My Template",
        "zones": [
            {"id": "z-cover", "binding": "cover", "elements": {}}
        ],
    }

    def _call(self, store, body, mode="server"):
        handler = _make_handler()
        handler._read_body_json = MagicMock(return_value=body)
        is_desktop = mode == "desktop"
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch.object(server, "APP_MODE", mode), \
             patch("storage.get_storage", return_value=store):
            handler._handle_post_templates()
        return handler

    def test_server_mode_saves_template(self):
        store = _mock_store(templates=[])
        self._call(store, dict(self._VALID_TEMPLATE), mode="server")
        store.save_templates.assert_called_once()

    def test_desktop_mode_saves_template(self):
        store = _mock_store(templates=[])
        self._call(store, dict(self._VALID_TEMPLATE), mode="desktop")
        store.save_templates.assert_called_once()

    def test_builtin_template_cannot_be_modified(self):
        existing = {"id": "my-template", "name": "My Template", "builtIn": True}
        store = _mock_store(templates=[existing])
        handler = self._call(store, dict(self._VALID_TEMPLATE), mode="server")
        data, status = _sent(handler)
        assert status == 403
        store.save_templates.assert_not_called()

    def test_new_template_appended(self):
        store = _mock_store(templates=[])
        self._call(store, dict(self._VALID_TEMPLATE), mode="server")
        saved_list = store.save_templates.call_args[0][0]
        assert any(t.get("name") == "My Template" for t in saved_list)

    def test_existing_template_updated(self):
        existing = {"id": "my-template", "name": "Old Name", "builtIn": False,
                    "zones": [{"id": "z-cover", "binding": "cover", "elements": {}}]}
        store = _mock_store(templates=[existing])
        updated = dict(self._VALID_TEMPLATE)
        updated["name"] = "New Name"
        self._call(store, updated, mode="server")
        saved_list = store.save_templates.call_args[0][0]
        assert saved_list[0]["name"] == "New Name"

    def test_returns_ok_true(self):
        store = _mock_store(templates=[])
        handler = self._call(store, dict(self._VALID_TEMPLATE), mode="server")
        data, status = _sent(handler)
        assert data == {"ok": True}


# ── DELETE /api/templates/<id> ────────────────────────────────────────────────

class TestDeleteTemplateStorageRouting:
    """_handle_delete_template must use store.list_templates() / store.save_templates()."""

    def _call(self, store, template_id, mode="server"):
        handler = _make_handler()
        handler.path = f"/api/templates/{template_id}"
        is_desktop = mode == "desktop"
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch.object(server, "APP_MODE", mode), \
             patch("storage.get_storage", return_value=store):
            handler._handle_delete_template()
        return handler

    def test_server_mode_deletes_template(self):
        store = _mock_store(templates=[{"id": "my-tmpl", "name": "Mine", "builtIn": False}])
        self._call(store, "my-tmpl", mode="server")
        store.save_templates.assert_called_once()
        saved = store.save_templates.call_args[0][0]
        assert not any(t["id"] == "my-tmpl" for t in saved)

    def test_desktop_mode_deletes_template(self):
        store = _mock_store(templates=[{"id": "my-tmpl", "name": "Mine", "builtIn": False}])
        self._call(store, "my-tmpl", mode="desktop")
        store.save_templates.assert_called_once()

    def test_builtin_template_cannot_be_deleted(self):
        store = _mock_store(templates=[{"id": "classic", "name": "Classic", "builtIn": True}])
        handler = self._call(store, "classic", mode="server")
        data, status = _sent(handler)
        assert status == 403
        store.save_templates.assert_not_called()

    def test_returns_ok_true_after_delete(self):
        store = _mock_store(templates=[{"id": "my-tmpl", "name": "Mine", "builtIn": False}])
        handler = self._call(store, "my-tmpl", mode="server")
        data, status = _sent(handler)
        assert data == {"ok": True}

    def test_missing_id_returns_400(self):
        store = _mock_store(templates=[])
        handler = self._call(store, "", mode="server")
        data, status = _sent(handler)
        assert status == 400


# ── GET /api/bootstrap ────────────────────────────────────────────────────────

class TestBootstrapStorageRouting:
    """_handle_bootstrap must use store.get_settings() and store.list_songs()."""

    def _call(self, store, mode="server"):
        handler = _make_handler()
        is_desktop = mode == "desktop"
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch.object(server, "APP_MODE", mode), \
             patch("storage.get_storage", return_value=store), \
             patch.object(server, "_public_config", return_value={"appMode": mode}):
            handler._handle_bootstrap()
        return handler

    def test_server_mode_calls_get_settings(self):
        store = _mock_store(settings={"churchName": "Grace"}, songs=[])
        self._call(store, mode="server")
        store.get_settings.assert_called()

    def test_server_mode_calls_list_songs(self):
        store = _mock_store(settings={}, songs=[{"title": "Grace"}])
        self._call(store, mode="server")
        store.list_songs.assert_called()

    def test_desktop_mode_calls_get_settings(self):
        store = _mock_store(settings={}, songs=[])
        self._call(store, mode="desktop")
        store.get_settings.assert_called()

    def test_desktop_mode_calls_list_songs(self):
        store = _mock_store(settings={}, songs=[])
        self._call(store, mode="desktop")
        store.list_songs.assert_called()

    def test_bootstrap_response_shape(self):
        settings = {"churchName": "Grace Church"}
        songs = [{"title": "Amazing Grace"}]
        store = _mock_store(settings=settings, songs=songs)
        handler = self._call(store, mode="server")
        data, status = _sent(handler)
        assert status == 200
        assert data["settings"] == settings
        assert data["songDb"] == songs
        assert "config" in data

    def test_bootstrap_settings_from_storage_not_json_file(self):
        """Verify settings come from the store, not a mocked JSON file."""
        settings = {"pcoAccessToken": "token-from-db"}
        store = _mock_store(settings=settings, songs=[])
        handler = self._call(store, mode="server")
        data, _ = _sent(handler)
        assert data["settings"]["pcoAccessToken"] == "token-from-db"


# ── GET /api/fonts ────────────────────────────────────────────────────────────

class TestGetFontsStorageRouting:
    """In server mode, _handle_get_fonts must use store.list_fonts()."""

    def _call_server(self, store):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(server, "APP_MODE", "server"), \
             patch("storage.get_storage", return_value=store):
            handler._handle_get_fonts()
        return handler

    def _call_desktop(self, store):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", True), \
             patch.object(server, "APP_MODE", "desktop"), \
             patch.object(handler, "_list_user_fonts", return_value=[]), \
             patch.object(handler, "_list_cached_fonts", return_value=[]):
            handler._handle_get_fonts()
        return handler

    def test_server_mode_calls_list_fonts(self):
        store = _mock_store(fonts=[])
        self._call_server(store)
        store.list_fonts.assert_called_once()

    def test_server_mode_splits_user_and_cached(self):
        fonts = [
            {"slug": "open-sans", "family": "Open Sans", "source": "user", "css_url": "/fonts/user/open-sans/font.css"},
            {"slug": "roboto", "family": "Roboto", "source": "google", "css_url": "/fonts/cache/roboto/font.css"},
        ]
        store = _mock_store(fonts=fonts)
        handler = self._call_server(store)
        data, _ = _sent(handler)
        assert len(data["user"]) == 1
        assert data["user"][0]["slug"] == "open-sans"
        assert len(data["cached"]) == 1
        assert data["cached"][0]["slug"] == "roboto"

    def test_desktop_mode_uses_filesystem_methods(self):
        """Desktop mode must NOT call store.list_fonts()."""
        store = _mock_store()
        self._call_desktop(store)
        store.list_fonts.assert_not_called()

    def test_server_mode_returns_dict_with_user_and_cached(self):
        store = _mock_store(fonts=[])
        handler = self._call_server(store)
        data, status = _sent(handler)
        assert status == 200
        assert "user" in data
        assert "cached" in data
