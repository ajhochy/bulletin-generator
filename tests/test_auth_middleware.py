from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

import auth  # noqa: E402
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


# ---------------------------------------------------------------------------
# First-login provisioning (Issue 008)
# ---------------------------------------------------------------------------

_PROVISIONED_MEMBERSHIP = {
    "workspace_id": "cccccccc-0000-0000-0000-000000000001",
    "role": "editor",
    "email": "bob@allowlisted.org",
    "display_name": "",
    "avatar_url": "",
}

_PROVISIONED_USER = {
    "id": "dddddddd-0000-0000-0000-000000000001",
    "user_id": "dddddddd-0000-0000-0000-000000000001",
    "email": "bob@allowlisted.org",
    "display_name": "",
    "avatar_url": "",
    "workspace_id": "cccccccc-0000-0000-0000-000000000001",
    "role": "editor",
    "claims": {
        "sub": "dddddddd-0000-0000-0000-000000000001",
        "email": "bob@allowlisted.org",
    },
}


class TestFirstLoginProvisioning:
    """Tests for domain-allow-list auto-provisioning on first login (issue 008)."""

    def test_first_login_allow_listed_domain_gets_workspace(self):
        """New user whose domain is allow-listed gets auto-provisioned as editor."""
        claims = {
            "sub": "dddddddd-0000-0000-0000-000000000001",
            "email": "bob@allowlisted.org",
            "exp": 9999999999,
        }
        # resolve_workspace_membership returns None (no prior row), then
        # provision_first_login returns the new membership.
        with (
            patch("auth._verify_supabase_jwt", return_value=claims),
            patch("auth.resolve_workspace_membership", return_value=None) as resolve,
            patch("auth.provision_first_login", return_value=_PROVISIONED_MEMBERSHIP) as provision,
        ):
            status, identity = auth.authenticate_authorization_header("Bearer sometoken")

        assert status == 200
        assert identity is not None
        assert identity["workspace_id"] == _PROVISIONED_MEMBERSHIP["workspace_id"]
        assert identity["role"] == "editor"
        resolve.assert_called_once_with("dddddddd-0000-0000-0000-000000000001")
        provision.assert_called_once_with(
            "dddddddd-0000-0000-0000-000000000001", "bob@allowlisted.org"
        )

    def test_first_login_unlisted_domain_gets_403(self):
        """New user whose domain is NOT on any allow-list still gets 403."""
        claims = {
            "sub": "eeeeeeee-0000-0000-0000-000000000001",
            "email": "eve@notallowed.example",
            "exp": 9999999999,
        }
        with (
            patch("auth._verify_supabase_jwt", return_value=claims),
            patch("auth.resolve_workspace_membership", return_value=None),
            patch("auth.provision_first_login", return_value=None) as provision,
        ):
            status, identity = auth.authenticate_authorization_header("Bearer sometoken")

        assert status == 403
        assert identity is None
        provision.assert_called_once_with(
            "eeeeeeee-0000-0000-0000-000000000001", "eve@notallowed.example"
        )

    def test_existing_member_skips_provisioning(self):
        """A user who already has a membership row is never sent to provisioning."""
        claims = {
            "sub": "aaaaaaaa-0000-0000-0000-000000000001",
            "email": "alice@example.com",
            "exp": 9999999999,
        }
        existing_membership = {
            "workspace_id": "bbbbbbbb-0000-0000-0000-000000000001",
            "role": "admin",
            "email": "alice@example.com",
            "display_name": "Alice",
            "avatar_url": "",
        }
        with (
            patch("auth._verify_supabase_jwt", return_value=claims),
            patch("auth.resolve_workspace_membership", return_value=existing_membership),
            patch("auth.provision_first_login") as provision,
        ):
            status, identity = auth.authenticate_authorization_header("Bearer sometoken")

        assert status == 200
        assert identity is not None
        assert identity["role"] == "admin"
        # provision_first_login must NOT be called when membership already exists
        provision.assert_not_called()
