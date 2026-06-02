"""
tests/test_collab_regression.py — Consolidated collab-v1 auth/visibility regression suite.

Verifies the entire collab-v1 auth and visibility contract in a single runnable file:

  Section 1: Unauthenticated access in server mode
    - Protected GET/POST/DELETE routes → 401
    - /api/health → 200 (no auth required)
    - /api/me (unauthenticated) → 401
    - /auth/google/login → 302 redirect

  Section 2: Desktop mode — no auth required
    - GET /api/projects, /api/announcements, /api/settings → 200
    - GET /api/me → 200 with mode="desktop"

  Section 3: Private project data isolation
    - User A's private project: User B GET → 403
    - User A's private project: User B POST → 403
    - User A's private project: User B DELETE → 403
    - Workspace project: User B GET → 200
    - Workspace project: User B POST → 200

  Section 4: Shared data in server mode (authenticated)
    - GET /api/announcements → 200 with list
    - POST /api/announcements → 200
    - GET /api/songs → 200 with list
    - GET /api/settings → 200 with dict

No live network, database, or HTTP server required.
"""

from __future__ import annotations

import json
import sys
import types
import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

# ── Project root on sys.path ──────────────────────────────────────────────────

sys.path.insert(0, str(__file__).replace("/tests/test_collab_regression.py", ""))

# ── Python 3.13+ compatibility shim ──────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

# ── Imports ───────────────────────────────────────────────────────────────────

import server  # noqa: E402


# ===========================================================================
# Test helpers
# ===========================================================================

def mock_user(email: str = "user@example.com", id: str | None = None) -> dict:
    """Return a fake user dict for use in auth patches."""
    return {
        "id": id or str(uuid.uuid4()),
        "email": email,
        "display_name": email.split("@")[0].capitalize(),
        "avatar_url": "",
        "domain": email.split("@")[-1],
    }


def mock_project(
    project_id: str | None = None,
    visibility: str = "workspace",
    owner_id: str | None = None,
) -> dict:
    """Return a fake project dict."""
    return {
        "id": project_id or str(uuid.uuid4()),
        "name": "Sunday Service",
        "owner_user_id": owner_id,
        "visibility": visibility,
        "revision": 1,
    }


def _make_handler(path: str, cookie: str = "", body: bytes = b"") -> server.Handler:
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
    handler.headers = {
        "Cookie": cookie,
        "Content-Length": str(len(body)),
        "Content-Type": "application/json",
    }
    handler.rfile = BytesIO(body)
    return handler


def _status(handler: server.Handler) -> int:
    """Extract HTTP status code from the last _send_json call (default 200)."""
    if not handler._send_json.called:
        return 0
    args = handler._send_json.call_args[0]
    return args[1] if len(args) > 1 else 200


def _response_body(handler: server.Handler) -> dict:
    """Extract the response dict from the last _send_json call."""
    return handler._send_json.call_args[0][0]


def _call_unauthed_get(method_name: str, path: str) -> server.Handler:
    """Call a GET handler in server mode without authentication."""
    handler = _make_handler(path)
    with patch.object(server, "IS_DESKTOP", False), \
         patch("auth.get_request_user", return_value=None):
        getattr(handler, method_name)()
    return handler


def _call_unauthed_post(method_name: str, path: str) -> server.Handler:
    """Call a POST handler in server mode without authentication."""
    handler = _make_handler(path, body=b"{}")
    with patch.object(server, "IS_DESKTOP", False), \
         patch("auth.get_request_user", return_value=None):
        getattr(handler, method_name)()
    return handler


def _call_desktop_get(method_name: str, path: str) -> server.Handler:
    """Call a GET handler in desktop mode (no session required)."""
    handler = _make_handler(path)
    with patch.object(server, "IS_DESKTOP", True), \
         patch("server._read_json", return_value=[]):
        getattr(handler, method_name)()
    return handler


def _call_authed_get(
    method_name: str,
    path: str,
    user: dict,
    store_mock: MagicMock | None = None,
) -> server.Handler:
    """Call a GET handler in server mode with a valid session."""
    handler = _make_handler(path, cookie="bg_session=valid-token")
    store = store_mock or MagicMock()
    with patch.object(server, "IS_DESKTOP", False), \
         patch("auth.get_request_user", return_value=user), \
         patch("storage.get_storage", return_value=store):
        getattr(handler, method_name)()
    return handler


def _call_authed_post(
    method_name: str,
    path: str,
    user: dict,
    body: bytes,
    store_mock: MagicMock | None = None,
) -> server.Handler:
    """Call a POST handler in server mode with a valid session."""
    handler = _make_handler(path, cookie="bg_session=valid-token", body=body)
    store = store_mock or MagicMock()
    with patch.object(server, "IS_DESKTOP", False), \
         patch("auth.get_request_user", return_value=user), \
         patch("storage.get_storage", return_value=store):
        getattr(handler, method_name)()
    return handler


# ===========================================================================
# Section 1: Unauthenticated access in server mode
# ===========================================================================

class TestUnauthenticatedServerMode:
    """
    Every protected API route must reject unauthenticated server-mode requests
    with 401.  /api/health must remain open.  /auth/google/login must redirect.
    """

    # ── Protected GET routes ─────────────────────────────────────────────────

    def test_get_projects_unauthenticated_returns_401(self):
        h = _call_unauthed_get("_handle_get_projects", "/api/projects")
        assert _status(h) == 401, "Private data must not leak to unauthenticated callers"

    def test_get_announcements_unauthenticated_returns_401(self):
        h = _call_unauthed_get("_handle_get_announcements", "/api/announcements")
        assert _status(h) == 401

    def test_get_songs_unauthenticated_returns_401(self):
        h = _call_unauthed_get("_handle_get_songs", "/api/songs")
        assert _status(h) == 401

    def test_get_settings_unauthenticated_returns_401(self):
        h = _call_unauthed_get("_handle_get_settings", "/api/settings")
        assert _status(h) == 401

    def test_get_bootstrap_unauthenticated_returns_401(self):
        h = _call_unauthed_get("_handle_bootstrap", "/api/bootstrap")
        assert _status(h) == 401

    def test_get_templates_unauthenticated_returns_401(self):
        h = _call_unauthed_get("_handle_get_templates", "/api/templates")
        assert _status(h) == 401

    # ── Protected POST routes ────────────────────────────────────────────────

    def test_post_projects_unauthenticated_returns_401(self):
        h = _call_unauthed_post("_handle_post_projects", "/api/projects")
        assert _status(h) == 401

    def test_post_announcements_unauthenticated_returns_401(self):
        h = _call_unauthed_post("_handle_post_announcements", "/api/announcements")
        assert _status(h) == 401

    def test_post_settings_unauthenticated_returns_401(self):
        h = _call_unauthed_post("_handle_post_settings", "/api/settings")
        assert _status(h) == 401

    def test_post_songs_unauthenticated_returns_401(self):
        h = _call_unauthed_post("_handle_post_songs", "/api/songs")
        assert _status(h) == 401

    def test_post_templates_unauthenticated_returns_401(self):
        h = _call_unauthed_post("_handle_post_templates", "/api/templates")
        assert _status(h) == 401

    def test_post_pdf_unauthenticated_returns_401(self):
        h = _call_unauthed_post("_handle_pdf", "/api/pdf")
        assert _status(h) == 401

    # ── Protected DELETE routes ──────────────────────────────────────────────

    def test_delete_project_unauthenticated_returns_401(self):
        pid = str(uuid.uuid4())
        h = _call_unauthed_get("_handle_delete_project", f"/api/projects/{pid}")
        assert _status(h) == 401

    # ── /api/health — always open ────────────────────────────────────────────

    def test_health_returns_200_without_auth(self):
        """GET /api/health must never require authentication."""
        handler = _make_handler("/api/health")
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
        assert _status(handler) != 401, "/api/health must be publicly accessible"
        handler._send_json.assert_called_once()

    # ── /api/me — unauthenticated → 401 ─────────────────────────────────────

    def test_api_me_unauthenticated_returns_401(self):
        """GET /api/me must return 401 (not 500) when no session is present."""
        handler = _make_handler("/api/me")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            handler._handle_api_me()
        assert _status(handler) == 401, "/api/me must return 401, not 500 or 200"

    # ── /auth/google/login — redirect, not 401 ───────────────────────────────

    def test_auth_google_login_redirects(self):
        """GET /auth/google/login must issue a redirect (302), not a 401 error."""
        handler = _make_handler("/auth/google/login")
        import auth as _auth_module
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.build_auth_login_url", return_value="https://accounts.google.com/o/oauth2/auth?foo=bar"):
            handler._handle_auth_google_login()
        # Must have called send_response(302), never _send_json with a 401
        handler.send_response.assert_called_once_with(302)
        # _send_json should NOT have been called (or must not be 401)
        if handler._send_json.called:
            assert _status(handler) != 401, "/auth/google/login must redirect, not error"


# ===========================================================================
# Section 2: Desktop mode — no auth required
# ===========================================================================

class TestDesktopModeNoAuthRequired:
    """
    In desktop mode every protected route must pass through without requiring
    a session cookie.  Tests fail if desktop mode accidentally requires login.
    """

    def test_desktop_get_projects_returns_200(self):
        """GET /api/projects in desktop mode must not require login."""
        handler = _make_handler("/api/projects")
        mock_store = MagicMock()
        mock_store.list_projects.return_value = []
        with patch.object(server, "IS_DESKTOP", True), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_projects()
        assert _status(handler) != 401, "Desktop mode must not require authentication"
        assert "projects" in _response_body(handler)

    def test_desktop_get_announcements_returns_200(self):
        """GET /api/announcements in desktop mode must not require login."""
        handler = _make_handler("/api/announcements")
        mock_store = MagicMock()
        mock_store.list_announcements.return_value = []
        with patch.object(server, "IS_DESKTOP", True), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_announcements()
        assert _status(handler) != 401

    def test_desktop_get_settings_returns_200(self):
        """GET /api/settings in desktop mode must not require login."""
        handler = _make_handler("/api/settings")
        mock_store = MagicMock()
        mock_store.get_settings.return_value = {}
        with patch.object(server, "IS_DESKTOP", True), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_settings()
        assert _status(handler) != 401
        assert isinstance(_response_body(handler), dict)

    def test_desktop_get_songs_returns_200(self):
        """GET /api/songs in desktop mode must not require login."""
        handler = _make_handler("/api/songs")
        mock_store = MagicMock()
        mock_store.list_songs.return_value = []
        with patch.object(server, "IS_DESKTOP", True), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_songs()
        assert _status(handler) != 401

    def test_desktop_api_me_returns_desktop_mode(self):
        """GET /api/me in desktop mode must return mode='desktop' without auth."""
        handler = _make_handler("/api/me")
        with patch.object(server, "IS_DESKTOP", True):
            handler._handle_api_me()
        assert _status(handler) != 401, "Desktop /api/me must not require login"
        body = _response_body(handler)
        assert body.get("mode") == "desktop", "Desktop /api/me must include mode='desktop'"

    def test_desktop_get_projects_no_cookie_still_works(self):
        """Desktop mode must work with an empty Cookie header (no session at all)."""
        handler = _make_handler("/api/projects", cookie="")  # explicitly no cookie
        mock_store = MagicMock()
        mock_store.list_projects.return_value = []
        with patch.object(server, "IS_DESKTOP", True), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_projects()
        assert _status(handler) != 401, "Desktop mode must never require a cookie"


# ===========================================================================
# Section 3: Private project data isolation
# ===========================================================================

class TestPrivateProjectIsolation:
    """
    Private data must not leak across users.  User B must never read, write,
    or delete User A's private projects.  Workspace projects are shared.
    """

    _USER_A = mock_user("alice@example.com", id="aaaaaaaa-0000-0000-0000-000000000001")
    _USER_B = mock_user("bob@example.com",   id="bbbbbbbb-0000-0000-0000-000000000002")

    # ── GET (load) ───────────────────────────────────────────────────────────

    def _call_get_project(self, user: dict, project: dict) -> server.Handler:
        path = f"/api/projects?id={project['id']}"
        handler = _make_handler(path, cookie="bg_session=tok")
        mock_store = MagicMock()
        mock_store.get_project.return_value = project
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=user), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_projects()
        return handler

    def test_user_b_cannot_read_user_a_private_project(self):
        """Private project data must not leak to other users."""
        prj = mock_project(visibility="private", owner_id=self._USER_A["id"])
        h = self._call_get_project(self._USER_B, prj)
        assert _status(h) in (403, 404), \
            f"User B must not access User A's private project (got {_status(h)})"

    def test_user_a_can_read_own_private_project(self):
        """Owner must be able to access their own private project."""
        prj = mock_project(visibility="private", owner_id=self._USER_A["id"])
        h = self._call_get_project(self._USER_A, prj)
        assert _status(h) == 200

    def test_user_b_can_read_workspace_project(self):
        """Workspace projects must be visible to all authenticated users."""
        prj = mock_project(visibility="workspace", owner_id=self._USER_A["id"])
        h = self._call_get_project(self._USER_B, prj)
        assert _status(h) == 200, \
            f"Workspace project must be accessible to all users (got {_status(h)})"

    # ── POST (save) ──────────────────────────────────────────────────────────

    def _call_save_project(self, user: dict, project: dict) -> server.Handler:
        payload = {"id": project["id"], "name": "Updated", "_clientRevision": 1}
        body = json.dumps(payload).encode()
        handler = _make_handler("/api/projects", cookie="bg_session=tok", body=body)
        mock_store = MagicMock()
        mock_store.get_project.return_value = project
        saved = dict(project, revision=2)
        mock_store.save_project_transactional.return_value = saved
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=user), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_post_projects()
        return handler

    def test_user_b_cannot_save_user_a_private_project(self):
        """Writing another user's private project must be blocked."""
        prj = mock_project(visibility="private", owner_id=self._USER_A["id"])
        h = self._call_save_project(self._USER_B, prj)
        assert _status(h) == 403, \
            f"User B must not save User A's private project (got {_status(h)})"

    def test_user_a_can_save_own_private_project(self):
        prj = mock_project(visibility="private", owner_id=self._USER_A["id"])
        h = self._call_save_project(self._USER_A, prj)
        assert _status(h) == 200

    def test_user_b_can_save_workspace_project(self):
        prj = mock_project(visibility="workspace", owner_id=self._USER_A["id"])
        h = self._call_save_project(self._USER_B, prj)
        assert _status(h) == 200, \
            f"User B must be able to save workspace projects (got {_status(h)})"

    # ── DELETE ───────────────────────────────────────────────────────────────

    def _call_delete_project(self, user: dict, project: dict) -> server.Handler:
        path = f"/api/projects/{project['id']}"
        handler = _make_handler(path, cookie="bg_session=tok")
        mock_store = MagicMock()
        mock_store.get_project.return_value = project
        mock_store.delete_project.return_value = True
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=user), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_delete_project()
        return handler

    def test_user_b_cannot_delete_user_a_private_project(self):
        """Deleting another user's private project must be blocked."""
        prj = mock_project(visibility="private", owner_id=self._USER_A["id"])
        h = self._call_delete_project(self._USER_B, prj)
        assert _status(h) == 403, \
            f"User B must not delete User A's private project (got {_status(h)})"

    def test_user_a_can_delete_own_private_project(self):
        prj = mock_project(visibility="private", owner_id=self._USER_A["id"])
        h = self._call_delete_project(self._USER_A, prj)
        assert _status(h) == 200

    def test_user_b_cannot_delete_workspace_project_owned_by_a(self):
        """Non-owner must not be able to delete a workspace project."""
        prj = mock_project(visibility="workspace", owner_id=self._USER_A["id"])
        h = self._call_delete_project(self._USER_B, prj)
        assert _status(h) == 403


# ===========================================================================
# Section 4: Shared data in server mode (authenticated)
# ===========================================================================

class TestSharedDataAuthenticated:
    """
    Shared data APIs (announcements, songs, settings) must return well-formed
    responses to authenticated server-mode users.
    """

    _AUTHED_USER = mock_user("editor@example.com")

    def test_get_announcements_authenticated_returns_list(self):
        """GET /api/announcements must return a list for authenticated users."""
        mock_store = MagicMock()
        mock_store.list_announcements.return_value = [{"id": "ann-1", "text": "Welcome"}]
        handler = _make_handler("/api/announcements", cookie="bg_session=tok")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=self._AUTHED_USER), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_announcements()
        assert _status(handler) != 401
        body = _response_body(handler)
        assert isinstance(body, list), f"Expected list, got {type(body)}"

    def test_post_announcements_authenticated_saves_data(self):
        """POST /api/announcements must save data for authenticated users."""
        anns = [{"id": "ann-1", "text": "Sunday potluck after service"}]
        body_bytes = json.dumps(anns).encode()
        mock_store = MagicMock()
        handler = _make_handler("/api/announcements", cookie="bg_session=tok", body=body_bytes)
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=self._AUTHED_USER), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_post_announcements()
        assert _status(handler) != 401
        mock_store.save_announcements.assert_called_once_with(anns)
        assert _response_body(handler).get("ok") is True

    def test_get_songs_authenticated_returns_list(self):
        """GET /api/songs must return a list for authenticated users."""
        mock_store = MagicMock()
        mock_store.list_songs.return_value = [{"title": "Amazing Grace", "ccli": "12345"}]
        handler = _make_handler("/api/songs", cookie="bg_session=tok")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=self._AUTHED_USER), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_songs()
        assert _status(handler) != 401
        body = _response_body(handler)
        assert isinstance(body, list), f"Expected list, got {type(body)}"

    def test_get_settings_authenticated_returns_dict(self):
        """GET /api/settings must return a dict for authenticated users."""
        mock_store = MagicMock()
        mock_store.get_settings.return_value = {"churchName": "Visalia CRC", "pageSize": "letter"}
        handler = _make_handler("/api/settings", cookie="bg_session=tok")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=self._AUTHED_USER), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_settings()
        assert _status(handler) != 401
        body = _response_body(handler)
        assert isinstance(body, dict), f"Expected dict, got {type(body)}"

    def test_shared_data_not_user_scoped(self):
        """Announcements and songs are workspace-wide — any user sees the same data."""
        shared_songs = [
            {"title": "How Great Thou Art"},
            {"title": "In Christ Alone"},
        ]
        user_a = mock_user("alice@example.com")
        user_b = mock_user("bob@example.com")

        for user in (user_a, user_b):
            mock_store = MagicMock()
            mock_store.list_songs.return_value = shared_songs
            handler = _make_handler("/api/songs", cookie="bg_session=tok")
            with patch.object(server, "IS_DESKTOP", False), \
                 patch("auth.get_request_user", return_value=user), \
                 patch("storage.get_storage", return_value=mock_store):
                handler._handle_get_songs()
            body = _response_body(handler)
            assert len(body) == 2, \
                f"User {user['email']} must see all shared songs (got {len(body)})"
