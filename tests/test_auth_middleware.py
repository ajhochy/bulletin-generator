"""
tests/test_auth_middleware.py — Tests for auth middleware on protected routes.

Verifies that:
- Unauthenticated server-mode requests to protected routes return 401.
- Authenticated server-mode requests pass through to the handler.
- Desktop mode passes through without requiring a session.
- Unprotected routes (/api/health, /api/me) always pass through.

No live network, database, or HTTP server required.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Project root on sys.path ──────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Python 3.13+ compatibility shim ──────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

# ── Imports ───────────────────────────────────────────────────────────────────

import server  # noqa: E402

# ── Helpers ───────────────────────────────────────────────────────────────────

_FAKE_USER = {
    "id": "user-uuid-1",
    "email": "test@visaliacrc.com",
    "display_name": "Test User",
    "avatar_url": "",
    "domain": "visaliacrc.com",
}

_DESKTOP_USER = {
    "id": None,
    "email": "desktop",
    "display_name": "Desktop User",
    "domain": "local",
}


def _make_handler(cookie: str = "", path: str = "/"):
    """Return a minimal Handler instance with network methods mocked out."""
    handler = server.Handler.__new__(server.Handler)
    handler._send_json = MagicMock()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    handler.server = MagicMock()
    handler.server.server_address = ("127.0.0.1", 8080)
    handler.path = path
    handler.headers = {"Cookie": cookie}
    return handler


# ── _get_authenticated_user ───────────────────────────────────────────────────

class TestGetAuthenticatedUser:
    """_get_authenticated_user() returns a synthetic user in desktop mode."""

    def test_desktop_mode_returns_desktop_user(self):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", True):
            user = handler._get_authenticated_user()
        assert user is not None
        assert user["email"] == "desktop"
        assert user["domain"] == "local"

    def test_server_mode_no_cookie_returns_none(self):
        handler = _make_handler(cookie="")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            user = handler._get_authenticated_user()
        assert user is None

    def test_server_mode_valid_cookie_returns_user(self):
        handler = _make_handler(cookie="bg_session=valid-token")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=_FAKE_USER):
            user = handler._get_authenticated_user()
        assert user is not None
        assert user["email"] == "test@visaliacrc.com"

    def test_server_mode_passes_cookie_header_to_auth(self):
        """auth.get_request_user should receive the raw Cookie header value."""
        handler = _make_handler(cookie="bg_session=mytoken; other=x")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=_FAKE_USER) as mock_gru:
            handler._get_authenticated_user()
        mock_gru.assert_called_once_with("bg_session=mytoken; other=x")


# ── _require_auth ─────────────────────────────────────────────────────────────

class TestRequireAuth:
    """_require_auth() sends 401 when unauthenticated, returns user otherwise."""

    def test_sends_401_when_unauthenticated_in_server_mode(self):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            result = handler._require_auth()
        assert result is None
        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        assert args[1] == 401

    def test_returns_user_when_authenticated(self):
        handler = _make_handler(cookie="bg_session=tok")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=_FAKE_USER):
            result = handler._require_auth()
        assert result == _FAKE_USER
        handler._send_json.assert_not_called()

    def test_returns_desktop_user_in_desktop_mode(self):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", True):
            result = handler._require_auth()
        assert result is not None
        assert result["email"] == "desktop"
        handler._send_json.assert_not_called()

    def test_401_error_message_content(self):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            handler._require_auth()
        payload = handler._send_json.call_args[0][0]
        assert "error" in payload
        assert "Authentication" in payload["error"] or "authentication" in payload["error"].lower()


# ── Unauthenticated GET routes in server mode → 401 ──────────────────────────

class TestUnauthenticatedGetRoutes:
    """Unauthenticated server-mode GET requests to protected routes return 401."""

    def _call_unauthed(self, handler_method: str, path: str = "/"):
        handler = _make_handler(path=path)
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            getattr(handler, handler_method)()
        return handler

    def test_get_projects_returns_401(self):
        h = self._call_unauthed("_handle_get_projects", "/api/projects")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_get_announcements_returns_401(self):
        h = self._call_unauthed("_handle_get_announcements", "/api/announcements")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_get_settings_returns_401(self):
        h = self._call_unauthed("_handle_get_settings", "/api/settings")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_get_songs_returns_401(self):
        h = self._call_unauthed("_handle_get_songs", "/api/songs")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_bootstrap_returns_401(self):
        h = self._call_unauthed("_handle_bootstrap", "/api/bootstrap")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_get_templates_returns_401(self):
        h = self._call_unauthed("_handle_get_templates", "/api/templates")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_get_fonts_returns_401(self):
        h = self._call_unauthed("_handle_get_fonts", "/api/fonts")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_check_update_returns_401(self):
        h = self._call_unauthed("_handle_check_update", "/api/admin/check-update")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_update_status_returns_401(self):
        h = self._call_unauthed("_handle_update_status", "/api/admin/update-status")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_proxy_pco_returns_401(self):
        h = self._call_unauthed("_proxy_pco", "/pco-proxy/services/v2/service_types")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_cal_returns_401(self):
        h = self._call_unauthed("_handle_cal", "/cal")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_google_calendars_returns_401(self):
        h = self._call_unauthed("_handle_google_calendars", "/api/google-calendars")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401


# ── Authenticated GET routes in server mode → pass through ───────────────────

class TestAuthenticatedGetRoutes:
    """Authenticated requests pass through to the handler logic."""

    def _call_authed(self, handler_method: str, path: str = "/", **read_json_returns):
        handler = _make_handler(cookie="bg_session=valid", path=path)
        mock_store = MagicMock()
        mock_store.list_projects.return_value = read_json_returns.get("return_value", [])
        mock_store.list_songs.return_value = read_json_returns.get("return_value", [])
        mock_store.get_settings.return_value = read_json_returns.get("return_value", {})
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=_FAKE_USER), \
             patch("server._read_json", return_value=read_json_returns.get("return_value", [])), \
             patch("storage.get_storage", return_value=mock_store):
            getattr(handler, handler_method)()
        return handler

    def test_get_projects_passes_through(self):
        h = self._call_authed("_handle_get_projects", "/api/projects", return_value=[])
        # _send_json should be called with the projects payload, not a 401
        h._send_json.assert_called_once()
        args = h._send_json.call_args[0]
        # Default status=200
        assert args[1] != 401 if len(args) > 1 else True
        assert "projects" in args[0]

    def test_get_songs_passes_through(self):
        h = self._call_authed("_handle_get_songs", "/api/songs", return_value=[])
        h._send_json.assert_called_once()
        # Not a 401
        call_args = h._send_json.call_args
        if len(call_args[0]) > 1:
            assert call_args[0][1] != 401
        # Status keyword
        if "status" in call_args[1]:
            assert call_args[1]["status"] != 401

    def test_get_settings_passes_through(self):
        h = self._call_authed("_handle_get_settings", "/api/settings", return_value={})
        h._send_json.assert_called_once()
        call_args = h._send_json.call_args[0]
        assert isinstance(call_args[0], dict)
        if len(call_args) > 1:
            assert call_args[1] != 401


# ── Desktop mode → always passes through ─────────────────────────────────────

class TestDesktopModePassthrough:
    """Desktop mode should bypass auth and pass through to handler logic."""

    def _call_desktop(self, handler_method: str, path: str = "/"):
        handler = _make_handler(cookie="", path=path)
        with patch.object(server, "IS_DESKTOP", True), \
             patch("server._read_json", return_value=[]):
            getattr(handler, handler_method)()
        return handler

    def test_desktop_get_projects_passes_through(self):
        h = self._call_desktop("_handle_get_projects", "/api/projects")
        h._send_json.assert_called_once()
        args = h._send_json.call_args[0]
        assert "projects" in args[0]
        # No 401
        assert len(args) < 2 or args[1] != 401

    def test_desktop_get_songs_passes_through(self):
        h = self._call_desktop("_handle_get_songs", "/api/songs")
        h._send_json.assert_called_once()
        args = h._send_json.call_args[0]
        assert len(args) < 2 or args[1] != 401

    def test_desktop_get_settings_passes_through(self):
        h = self._call_desktop("_handle_get_settings", "/api/settings")
        h._send_json.assert_called_once()
        args = h._send_json.call_args[0]
        assert len(args) < 2 or args[1] != 401

    def test_desktop_get_announcements_passes_through(self):
        h = self._call_desktop("_handle_get_announcements", "/api/announcements")
        h._send_json.assert_called_once()
        args = h._send_json.call_args[0]
        assert len(args) < 2 or args[1] != 401


# ── Unprotected routes always pass through ────────────────────────────────────

class TestUnprotectedRoutes:
    """/api/health and /api/me should not require authentication."""

    def test_health_passes_through_no_auth(self):
        """GET /api/health should respond without checking for a session."""
        handler = _make_handler(path="/api/health")
        with patch.object(server, "IS_DESKTOP", True):
            # Desktop path is simpler — no db import needed
            handler._handle_health()
        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        assert args[1] != 401 if len(args) > 1 else True
        assert "status" in args[0]

    def test_health_server_mode_passes_through(self):
        """GET /api/health in server mode should always respond (no auth guard)."""
        handler = _make_handler(path="/api/health")
        mock_db = MagicMock()
        mock_db.health_check.return_value = {"connected": True}

        mock_migration = MagicMock()
        mock_migration.get_migration_status.return_value = {"applied": 5, "latest": "005"}

        with patch.object(server, "IS_DESKTOP", False), \
             patch.dict("sys.modules", {
                 "db": mock_db,
                 "migrations.runner": mock_migration,
             }):
            handler._handle_health()

        handler._send_json.assert_called_once()
        # Should not be 401
        call_args = handler._send_json.call_args[0]
        assert len(call_args) < 2 or call_args[1] != 401

    def test_api_me_no_session_returns_401_not_bypassed(self):
        """GET /api/me returns 401 when unauthenticated — this is intentional
        (it's the login-check endpoint, not a protected data endpoint)."""
        handler = _make_handler(path="/api/me")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            handler._handle_api_me()
        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        assert args[1] == 401

    def test_api_me_desktop_mode_returns_desktop_response(self):
        """GET /api/me in desktop mode should return desktop info without auth."""
        handler = _make_handler(path="/api/me")
        with patch.object(server, "IS_DESKTOP", True):
            handler._handle_api_me()
        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        # Should be 200 (no explicit status arg) and contain mode key
        assert args[0].get("mode") == "desktop"


# ── Unauthenticated POST routes in server mode → 401 ─────────────────────────

class TestUnauthenticatedPostRoutes:
    """Unauthenticated server-mode POST requests to protected routes return 401."""

    def _call_unauthed_post(self, handler_method: str, path: str = "/"):
        handler = _make_handler(path=path)
        # Provide a dummy Content-Length so _read_body_json returns None gracefully
        handler.headers["Content-Length"] = "0"
        handler.rfile = MagicMock()
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            getattr(handler, handler_method)()
        return handler

    def test_post_projects_returns_401(self):
        h = self._call_unauthed_post("_handle_post_projects", "/api/projects")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_post_announcements_returns_401(self):
        h = self._call_unauthed_post("_handle_post_announcements", "/api/announcements")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_post_settings_returns_401(self):
        h = self._call_unauthed_post("_handle_post_settings", "/api/settings")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_post_songs_returns_401(self):
        h = self._call_unauthed_post("_handle_post_songs", "/api/songs")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_post_templates_returns_401(self):
        h = self._call_unauthed_post("_handle_post_templates", "/api/templates")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_post_pdf_returns_401(self):
        h = self._call_unauthed_post("_handle_pdf", "/api/pdf")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_apply_update_returns_401(self):
        h = self._call_unauthed_post("_handle_apply_update", "/api/admin/apply-update")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401


# ── Unauthenticated DELETE routes in server mode → 401 ───────────────────────

class TestUnauthenticatedDeleteRoutes:
    """Unauthenticated server-mode DELETE requests to protected routes return 401."""

    def _call_unauthed_delete(self, handler_method: str, path: str):
        handler = _make_handler(path=path)
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            getattr(handler, handler_method)()
        return handler

    def test_delete_project_returns_401(self):
        h = self._call_unauthed_delete("_handle_delete_project", "/api/projects/some-id")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_delete_template_returns_401(self):
        h = self._call_unauthed_delete("_handle_delete_template", "/api/templates/my-tpl")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401

    def test_delete_font_returns_401(self):
        h = self._call_unauthed_delete("_handle_delete_font", "/api/fonts/open-sans")
        h._send_json.assert_called_once()
        assert h._send_json.call_args[0][1] == 401
