"""Unit tests for _SupabaseRestSettings (issue #294).

Tests that the class reads/writes workspace_settings via the Supabase REST API
using a caller JWT + anon key, without requiring DATABASE_URL.

All network calls are mocked via ``unittest.mock.patch`` on
``urllib.request.urlopen`` so these tests run in CI without any live Supabase
project.  No fixtures or DB required.
"""
import json
import os
import sys
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import server
from server import _SupabaseRestSettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_SUPABASE_URL = "https://example.supabase.co"
_FAKE_ANON_KEY = "anon-key-abc123"
_FAKE_JWT = "header.payload.sig"
_FAKE_WORKSPACE_ID = "ws-0001"


def _env_patch(**extra):
    """Return a patch.dict for os.environ with required Supabase vars."""
    base = {
        "SUPABASE_URL": _FAKE_SUPABASE_URL,
        "SUPABASE_ANON_KEY": _FAKE_ANON_KEY,
    }
    base.update(extra)
    return patch.dict(os.environ, base)


def _make_urlopen_response(body: dict | list) -> MagicMock:
    """Return a mock urlopen context-manager whose .read() returns *body* as JSON bytes."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# _ok() gating
# ---------------------------------------------------------------------------

class TestSupabaseRestSettingsOk:
    """_ok() must be False when any required piece is missing."""

    def test_ok_true_when_all_present(self):
        with _env_patch():
            inst = _SupabaseRestSettings(_FAKE_JWT)
            assert inst._ok() is True

    def test_ok_false_when_no_jwt(self):
        with _env_patch():
            inst = _SupabaseRestSettings("")
            assert inst._ok() is False

    def test_ok_false_when_no_supabase_url(self):
        with patch.dict(os.environ, {"SUPABASE_ANON_KEY": _FAKE_ANON_KEY}, clear=False), \
             patch.dict(os.environ, {}, clear=False):
            # Remove SUPABASE_URL
            env = {k: v for k, v in os.environ.items() if k != "SUPABASE_URL"}
            env["SUPABASE_ANON_KEY"] = _FAKE_ANON_KEY
            with patch.dict(os.environ, env, clear=True):
                inst = _SupabaseRestSettings(_FAKE_JWT)
                assert inst._ok() is False

    def test_ok_false_when_no_anon_key(self):
        env = {"SUPABASE_URL": _FAKE_SUPABASE_URL}
        with patch.dict(os.environ, env, clear=True):
            inst = _SupabaseRestSettings(_FAKE_JWT)
            assert inst._ok() is False

    def test_get_settings_returns_empty_dict_when_not_ok(self):
        """get_settings() must return {} (no raise) when env vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            inst = _SupabaseRestSettings(_FAKE_JWT)
            result = inst.get_settings()
        assert result == {}

    def test_save_settings_returns_data_unchanged_when_not_ok(self):
        """save_settings() must return the data unchanged (no raise) when env vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            inst = _SupabaseRestSettings(_FAKE_JWT)
            data = {"pcoAccessToken": "tok"}
            result = inst.save_settings(data)
        assert result == data


# ---------------------------------------------------------------------------
# get_settings()
# ---------------------------------------------------------------------------

class TestGetSettings:
    def test_parses_settings_from_rest_response(self):
        """get_settings() should return the ``settings`` dict from the first row."""
        settings_data = {"pcoAccessToken": "abc", "pcoRefreshToken": "xyz"}
        row = {"workspace_id": _FAKE_WORKSPACE_ID, "settings": settings_data}
        mock_resp = _make_urlopen_response([row])

        with _env_patch(), patch("urllib.request.urlopen", return_value=mock_resp):
            inst = _SupabaseRestSettings(_FAKE_JWT)
            result = inst.get_settings()

        assert result == settings_data

    def test_caches_workspace_id_from_row(self):
        """get_settings() should populate self._workspace_id from the row."""
        row = {"workspace_id": _FAKE_WORKSPACE_ID, "settings": {"k": "v"}}
        mock_resp = _make_urlopen_response([row])

        with _env_patch(), patch("urllib.request.urlopen", return_value=mock_resp):
            inst = _SupabaseRestSettings(_FAKE_JWT)
            inst.get_settings()

        assert inst._workspace_id == _FAKE_WORKSPACE_ID

    def test_returns_empty_dict_on_empty_row_list(self):
        """get_settings() should return {} when the REST response is an empty list."""
        mock_resp = _make_urlopen_response([])

        with _env_patch(), patch("urllib.request.urlopen", return_value=mock_resp):
            inst = _SupabaseRestSettings(_FAKE_JWT)
            result = inst.get_settings()

        assert result == {}

    def test_returns_empty_dict_on_network_error(self):
        """get_settings() must return {} (no raise) when urlopen raises."""
        err = urllib.error.URLError("connection refused")

        with _env_patch(), patch("urllib.request.urlopen", side_effect=err):
            inst = _SupabaseRestSettings(_FAKE_JWT)
            result = inst.get_settings()

        assert result == {}

    def test_get_url_contains_workspace_settings_path(self):
        """The GET request URL must target /rest/v1/workspace_settings."""
        row = {"workspace_id": _FAKE_WORKSPACE_ID, "settings": {}}
        mock_resp = _make_urlopen_response([row])
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            return mock_resp

        with _env_patch(), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            inst = _SupabaseRestSettings(_FAKE_JWT)
            inst.get_settings()

        assert "/rest/v1/workspace_settings" in captured["url"]
        assert captured["method"] == "GET"


# ---------------------------------------------------------------------------
# save_settings()
# ---------------------------------------------------------------------------

class TestSaveSettings:
    def _make_pre_cached_instance(self):
        """Return an instance with _workspace_id already cached (skips fetch)."""
        with _env_patch():
            inst = _SupabaseRestSettings(_FAKE_JWT)
            inst._workspace_id = _FAKE_WORKSPACE_ID
            return inst

    def test_patch_url_contains_workspace_id_filter(self):
        """save_settings() PATCH URL must include ``workspace_id=eq.<id>``."""
        data = {"pcoAccessToken": "newtoken"}
        updated_row = {"workspace_id": _FAKE_WORKSPACE_ID, "settings": data}
        mock_resp = _make_urlopen_response([updated_row])
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["body"] = req.data
            return mock_resp

        with _env_patch(), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            inst = self._make_pre_cached_instance()
            inst.save_settings(data)

        assert f"workspace_id=eq.{_FAKE_WORKSPACE_ID}" in captured["url"]
        assert captured["method"] == "PATCH"

    def test_patch_body_contains_settings_key(self):
        """save_settings() body must be ``{"settings": data}``."""
        data = {"pcoAccessToken": "tok", "googleRefreshToken": "grt"}
        updated_row = {"workspace_id": _FAKE_WORKSPACE_ID, "settings": data}
        mock_resp = _make_urlopen_response([updated_row])
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            return mock_resp

        with _env_patch(), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            inst = self._make_pre_cached_instance()
            inst.save_settings(data)

        assert captured["body"] == {"settings": data}

    def test_returns_updated_settings_from_patch_response(self):
        """save_settings() should return the settings dict from the PATCH response row."""
        data = {"pcoAccessToken": "fresh"}
        updated_row = {"workspace_id": _FAKE_WORKSPACE_ID, "settings": data}
        mock_resp = _make_urlopen_response([updated_row])

        with _env_patch(), patch("urllib.request.urlopen", return_value=mock_resp):
            inst = self._make_pre_cached_instance()
            result = inst.save_settings(data)

        assert result == data

    def test_returns_data_unchanged_on_network_error(self):
        """save_settings() must return *data* unchanged (no raise) on a network error."""
        data = {"pcoAccessToken": "tok"}
        err = urllib.error.URLError("timeout")

        with _env_patch(), patch("urllib.request.urlopen", side_effect=err):
            inst = self._make_pre_cached_instance()
            result = inst.save_settings(data)

        assert result == data

    def test_fetches_workspace_id_if_not_cached(self):
        """save_settings() should call _fetch_row() when _workspace_id is not cached."""
        data = {"pcoAccessToken": "tok"}
        fetch_row = {"workspace_id": _FAKE_WORKSPACE_ID, "settings": {}}
        patch_row = {"workspace_id": _FAKE_WORKSPACE_ID, "settings": data}
        responses = iter([
            _make_urlopen_response([fetch_row]),
            _make_urlopen_response([patch_row]),
        ])

        def fake_urlopen(req, timeout=None):
            return next(responses)

        with _env_patch(), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            inst = _SupabaseRestSettings(_FAKE_JWT)
            # _workspace_id is NOT pre-set — must fetch it
            result = inst.save_settings(data)

        assert inst._workspace_id == _FAKE_WORKSPACE_ID
        assert result == data

    def test_returns_data_when_workspace_id_unresolvable(self):
        """save_settings() returns *data* unchanged when workspace_id cannot be resolved."""
        data = {"pcoAccessToken": "tok"}
        # Both the cached _workspace_id and _fetch_row return nothing
        mock_resp = _make_urlopen_response([])  # empty list → no workspace_id

        with _env_patch(), patch("urllib.request.urlopen", return_value=mock_resp):
            inst = _SupabaseRestSettings(_FAKE_JWT)
            result = inst.save_settings(data)

        assert result == data
