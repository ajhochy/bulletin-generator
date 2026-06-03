from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

import server  # noqa: E402


USER = {
    "id": "aaaaaaaa-0000-0000-0000-000000000001",
    "user_id": "aaaaaaaa-0000-0000-0000-000000000001",
    "email": "alice@example.com",
    "display_name": "Alice",
    "avatar_url": "",
    "workspace_id": "bbbbbbbb-0000-0000-0000-000000000001",
    "role": "admin",
    "claims": {"sub": "aaaaaaaa-0000-0000-0000-000000000001", "email": "alice@example.com"},
}


def _make_handler(path: str = "/api/me", authorization: str = ""):
    handler = server.Handler.__new__(server.Handler)
    handler._send_json = MagicMock()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    handler.server = MagicMock()
    handler.server.server_address = ("127.0.0.1", 8080)
    handler.path = path
    handler.headers = {"Authorization": authorization, "Content-Length": "0"}
    return handler


class TestRequireAuth:
    def test_no_token_returns_401(self):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.authenticate_authorization_header", return_value=(401, None)):
            result = handler._require_auth()
        assert result is None
        handler._send_json.assert_called_once_with({"error": "Authentication required"}, 401)

    def test_invalid_or_expired_token_returns_401(self):
        handler = _make_handler(authorization="Bearer bad")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.authenticate_authorization_header", return_value=(401, None)):
            handler._require_auth()
        assert handler._send_json.call_args[0][1] == 401

    def test_valid_token_without_membership_returns_403(self):
        handler = _make_handler(authorization="Bearer valid")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.authenticate_authorization_header", return_value=(403, None)):
            result = handler._require_auth()
        assert result is None
        handler._send_json.assert_called_once_with({"error": "Workspace membership required"}, 403)

    def test_valid_token_returns_user(self):
        handler = _make_handler(authorization="Bearer valid")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.authenticate_authorization_header", return_value=(200, USER)):
            result = handler._require_auth()
        assert result == USER
        handler._send_json.assert_not_called()

    def test_authorization_header_is_passed_to_auth_module(self):
        handler = _make_handler(authorization="Bearer token-123")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.authenticate_authorization_header", return_value=(200, USER)) as authn:
            handler._require_auth()
        authn.assert_called_once_with("Bearer token-123")

    def test_desktop_mode_returns_synthetic_user(self):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", True):
            result = handler._require_auth()
        assert result["email"] == "desktop"
        assert result["role"] == "desktop"


class TestApiMe:
    def test_api_me_returns_identity_for_authenticated_request(self):
        handler = _make_handler(path="/api/me", authorization="Bearer valid")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.authenticate_authorization_header", return_value=(200, USER)):
            handler._handle_api_me()
        handler._send_json.assert_called_once_with({
            "mode": "server",
            "user_id": USER["id"],
            "email": USER["email"],
            "workspace_id": USER["workspace_id"],
            "role": USER["role"],
        })

    def test_api_me_no_token_returns_401(self):
        handler = _make_handler(path="/api/me")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.authenticate_authorization_header", return_value=(401, None)):
            handler._handle_api_me()
        assert handler._send_json.call_args[0][1] == 401

    def test_api_me_no_membership_returns_403(self):
        handler = _make_handler(path="/api/me", authorization="Bearer valid")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.authenticate_authorization_header", return_value=(403, None)):
            handler._handle_api_me()
        assert handler._send_json.call_args[0][1] == 403

    def test_api_me_desktop_response_is_unchanged(self):
        handler = _make_handler(path="/api/me")
        with patch.object(server, "IS_DESKTOP", True):
            handler._handle_api_me()
        handler._send_json.assert_called_once_with({"mode": "desktop", "user": None})


class TestScopedStorage:
    def test_storage_for_user_passes_workspace_and_claims(self):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", False), \
             patch("storage.get_storage", return_value=MagicMock()) as get_storage:
            handler._storage_for_user(USER)
        get_storage.assert_called_once_with(
            workspace_id=USER["workspace_id"],
            user_claims=USER["claims"],
        )

    def test_bulk_project_revisions_requires_auth(self):
        handler = _make_handler(path="/api/projects/revisions")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.authenticate_authorization_header", return_value=(401, None)):
            handler._handle_get_project_revisions()
        assert handler._send_json.call_args[0][1] == 401

    def test_bulk_project_revisions_uses_scoped_project_list(self):
        handler = _make_handler(path="/api/projects/revisions", authorization="Bearer valid")
        store = MagicMock()
        store.list_projects.return_value = [{"id": "p1", "revision": 3}]
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.authenticate_authorization_header", return_value=(200, USER)), \
             patch("storage.get_storage", return_value=store) as get_storage:
            handler._handle_get_project_revisions()
        get_storage.assert_called_once_with(
            workspace_id=USER["workspace_id"],
            user_claims=USER["claims"],
        )
        store.list_projects.assert_called_once_with(user_id=USER["id"])
        assert handler._send_json.call_args[0][0]["projects"][0]["id"] == "p1"
