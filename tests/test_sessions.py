"""
tests/test_sessions.py — Unit tests for session management in auth.py and
the /api/me and /auth/logout routes in server.py.

No live network, database, or HTTP server required.  All external calls are
mocked via unittest.mock.

Compatibility note: stubs out the ``cgi`` module before importing server.py
so these tests run on Python 3.13+ where cgi was removed.
"""

import hashlib
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ── Project root on sys.path ──────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Python 3.13+ compatibility shim ──────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

# ── Imports ───────────────────────────────────────────────────────────────────

import auth    # noqa: E402
import server  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_conn(fetchone_return=None):
    """Return a mock DB connection/cursor pair."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fetchone_return

    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__  = MagicMock(return_value=False)
    return mock_conn


def _make_handler():
    """Return a Handler instance with network-level methods mocked out."""
    handler = server.Handler.__new__(server.Handler)
    handler._send_json      = MagicMock()
    handler.send_response   = MagicMock()
    handler.send_header     = MagicMock()
    handler.end_headers     = MagicMock()
    handler._cors_headers   = MagicMock()
    handler.wfile           = MagicMock()
    handler.server          = MagicMock()
    handler.server.server_address = ("127.0.0.1", 8080)
    handler.headers         = {}
    return handler


# ── create_session ────────────────────────────────────────────────────────────

class TestCreateSession:
    """auth.create_session() should insert a hashed token and return the plain token."""

    def test_returns_string_token(self):
        mock_conn = _make_mock_conn()
        with patch("db.transaction", return_value=mock_conn):
            token = auth.create_session("user-uuid-1")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_is_hex(self):
        mock_conn = _make_mock_conn()
        with patch("db.transaction", return_value=mock_conn):
            token = auth.create_session("user-uuid-1")
        # secrets.token_hex(32) produces 64 hex chars
        assert len(token) == 64
        int(token, 16)  # should not raise

    def test_inserts_row_into_sessions(self):
        mock_conn = _make_mock_conn()
        with patch("db.transaction", return_value=mock_conn):
            auth.create_session("user-uuid-1")
        assert mock_conn.execute.called
        sql = mock_conn.execute.call_args[0][0]
        assert "INSERT INTO sessions" in sql

    def test_stores_hash_not_plain_token(self):
        mock_conn = _make_mock_conn()
        with patch("db.transaction", return_value=mock_conn):
            token = auth.create_session("user-uuid-1")

        args = mock_conn.execute.call_args[0][1]
        stored_hash = args[0]
        expected_hash = hashlib.sha256(token.encode()).hexdigest()
        assert stored_hash == expected_hash

    def test_stored_user_id_matches(self):
        mock_conn = _make_mock_conn()
        with patch("db.transaction", return_value=mock_conn):
            auth.create_session("my-user-uuid")

        args = mock_conn.execute.call_args[0][1]
        assert args[1] == "my-user-uuid"

    def test_each_call_returns_different_token(self):
        mock_conn = _make_mock_conn()
        with patch("db.transaction", return_value=mock_conn):
            token1 = auth.create_session("user-uuid-1")
            token2 = auth.create_session("user-uuid-1")
        assert token1 != token2


# ── get_session_user ──────────────────────────────────────────────────────────

class TestGetSessionUser:
    """auth.get_session_user() returns a user dict for valid sessions and None otherwise."""

    _USER_ROW = ("uuid-42", "alice@example.com", "Alice", "https://example.com/a.jpg", "example.com")

    def test_returns_user_dict_for_valid_token(self):
        mock_conn = _make_mock_conn(fetchone_return=self._USER_ROW)
        with patch("db.transaction", return_value=mock_conn):
            user = auth.get_session_user("valid-token")
        assert user is not None
        assert user["id"] == "uuid-42"
        assert user["email"] == "alice@example.com"
        assert user["display_name"] == "Alice"
        assert user["avatar_url"] == "https://example.com/a.jpg"
        assert user["domain"] == "example.com"

    def test_returns_none_for_expired_or_missing_token(self):
        mock_conn = _make_mock_conn(fetchone_return=None)
        with patch("db.transaction", return_value=mock_conn):
            result = auth.get_session_user("nonexistent-token")
        assert result is None

    def test_queries_with_hashed_token(self):
        mock_conn = _make_mock_conn(fetchone_return=self._USER_ROW)
        plain_token = "my-plain-token"
        expected_hash = hashlib.sha256(plain_token.encode()).hexdigest()

        with patch("db.transaction", return_value=mock_conn):
            auth.get_session_user(plain_token)

        args = mock_conn.execute.call_args[0][1]
        assert args[0] == expected_hash

    def test_sql_joins_sessions_and_users(self):
        mock_conn = _make_mock_conn(fetchone_return=self._USER_ROW)
        with patch("db.transaction", return_value=mock_conn):
            auth.get_session_user("any-token")
        sql = mock_conn.execute.call_args[0][0]
        assert "sessions" in sql
        assert "users" in sql
        assert "expires_at" in sql

    def test_id_is_stringified(self):
        """UUID returned from DB should be converted to str."""
        import uuid
        row = (uuid.UUID("12345678-1234-5678-1234-567812345678"),
               "bob@example.com", "Bob", "", "example.com")
        mock_conn = _make_mock_conn(fetchone_return=row)
        with patch("db.transaction", return_value=mock_conn):
            user = auth.get_session_user("token")
        assert isinstance(user["id"], str)


# ── delete_session ────────────────────────────────────────────────────────────

class TestDeleteSession:
    """auth.delete_session() should delete by hashed token."""

    def test_deletes_row(self):
        mock_conn = _make_mock_conn()
        with patch("db.transaction", return_value=mock_conn):
            auth.delete_session("some-token")
        assert mock_conn.execute.called
        sql = mock_conn.execute.call_args[0][0]
        assert "DELETE FROM sessions" in sql

    def test_deletes_by_hash(self):
        mock_conn = _make_mock_conn()
        plain_token = "plain-token-value"
        expected_hash = hashlib.sha256(plain_token.encode()).hexdigest()

        with patch("db.transaction", return_value=mock_conn):
            auth.delete_session(plain_token)

        args = mock_conn.execute.call_args[0][1]
        assert args[0] == expected_hash

    def test_returns_none(self):
        mock_conn = _make_mock_conn()
        with patch("db.transaction", return_value=mock_conn):
            result = auth.delete_session("token")
        assert result is None


# ── get_request_user ──────────────────────────────────────────────────────────

class TestGetRequestUser:
    """auth.get_request_user() parses the Cookie header and returns user or None."""

    _USER = {
        "id": "uid-1",
        "email": "user@example.com",
        "display_name": "User",
        "avatar_url": "",
        "domain": "example.com",
    }

    def test_returns_user_for_valid_cookie(self):
        with patch.object(auth, "get_session_user", return_value=self._USER) as mock_gsu:
            result = auth.get_request_user("bg_session=my-token; other=val")
        assert result == self._USER
        mock_gsu.assert_called_once_with("my-token")

    def test_returns_none_for_missing_bg_session(self):
        result = auth.get_request_user("other=value; another=123")
        assert result is None

    def test_returns_none_for_empty_cookie_header(self):
        result = auth.get_request_user("")
        assert result is None

    def test_returns_none_for_none_cookie_header(self):
        result = auth.get_request_user(None)
        assert result is None

    def test_returns_none_when_session_expired(self):
        with patch.object(auth, "get_session_user", return_value=None):
            result = auth.get_request_user("bg_session=expired-token")
        assert result is None

    def test_parses_token_with_surrounding_whitespace(self):
        with patch.object(auth, "get_session_user", return_value=self._USER) as mock_gsu:
            auth.get_request_user("  bg_session  =  trimmed-token  ")
        mock_gsu.assert_called_once_with("trimmed-token")

    def test_ignores_malformed_cookie_parts(self):
        """Parts without '=' should not crash."""
        with patch.object(auth, "get_session_user", return_value=self._USER) as mock_gsu:
            result = auth.get_request_user("garbage; bg_session=tok; morejunk")
        assert result == self._USER
        mock_gsu.assert_called_once_with("tok")


# ── /api/me route ─────────────────────────────────────────────────────────────

class TestApiMeRoute:
    """/api/me should return 401 when unauthenticated, user dict when authenticated."""

    _USER = {
        "id":           "uid-99",
        "email":        "me@example.com",
        "display_name": "Me User",
        "avatar_url":   "https://example.com/me.jpg",
        "domain":       "example.com",
    }

    def test_returns_desktop_response_in_desktop_mode(self):
        handler = _make_handler()
        handler.headers = {}
        with patch.object(server, "IS_DESKTOP", True):
            handler._handle_api_me()
        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args[0][0]
        assert payload["mode"] == "desktop"
        assert payload["user"] is None

    def test_returns_401_when_unauthenticated_in_server_mode(self):
        handler = _make_handler()
        handler.headers = {"Cookie": ""}
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            handler._handle_api_me()
        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        assert args[1] == 401

    def test_returns_401_when_no_cookie(self):
        handler = _make_handler()
        handler.headers = {}
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            handler._handle_api_me()
        args = handler._send_json.call_args[0]
        assert args[1] == 401

    def test_returns_user_when_authenticated(self):
        handler = _make_handler()
        handler.headers = {"Cookie": "bg_session=valid-token"}
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=self._USER):
            handler._handle_api_me()
        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args[0][0]
        assert payload["mode"] == "server"
        user = payload["user"]
        assert user["id"] == "uid-99"
        assert user["email"] == "me@example.com"
        assert user["displayName"] == "Me User"
        assert user["avatarUrl"] == "https://example.com/me.jpg"
        assert user["domain"] == "example.com"

    def test_authenticated_response_has_no_display_name_key(self):
        """The response key should be camelCase displayName, not display_name."""
        handler = _make_handler()
        handler.headers = {"Cookie": "bg_session=t"}
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=self._USER):
            handler._handle_api_me()
        payload = handler._send_json.call_args[0][0]
        assert "displayName" in payload["user"]
        assert "display_name" not in payload["user"]


# ── /auth/logout route ────────────────────────────────────────────────────────

class TestAuthLogoutRoute:
    """POST /auth/logout should delete the session and clear the cookie."""

    def test_returns_200(self):
        handler = _make_handler()
        handler.headers = {"Cookie": "bg_session=my-token"}
        with patch("auth.delete_session"):
            handler._handle_auth_logout()
        handler.send_response.assert_called_once_with(200)

    def test_calls_delete_session_with_token(self):
        handler = _make_handler()
        handler.headers = {"Cookie": "bg_session=my-token"}
        with patch("auth.delete_session") as mock_del:
            handler._handle_auth_logout()
        mock_del.assert_called_once_with("my-token")

    def test_clears_cookie(self):
        handler = _make_handler()
        handler.headers = {"Cookie": "bg_session=my-token"}
        with patch("auth.delete_session"):
            handler._handle_auth_logout()
        cookie_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Set-Cookie"
        ]
        assert cookie_calls, "No Set-Cookie header was set"
        cookie_value = cookie_calls[0][0][1]
        assert "bg_session=" in cookie_value
        assert "Max-Age=0" in cookie_value

    def test_returns_ok_true_body(self):
        handler = _make_handler()
        handler.headers = {"Cookie": "bg_session=tok"}
        with patch("auth.delete_session"):
            handler._handle_auth_logout()
        write_calls = handler.wfile.write.call_args_list
        assert write_calls
        body = write_calls[0][0][0]
        import json
        payload = json.loads(body)
        assert payload == {"ok": True}

    def test_handles_missing_cookie_gracefully(self):
        """Logout with no cookie should not raise."""
        handler = _make_handler()
        handler.headers = {}
        with patch("auth.delete_session") as mock_del:
            handler._handle_auth_logout()
        mock_del.assert_not_called()
        handler.send_response.assert_called_once_with(200)

    def test_handles_delete_session_exception_gracefully(self):
        """DB errors during session deletion should not bubble up as 500."""
        handler = _make_handler()
        handler.headers = {"Cookie": "bg_session=tok"}
        with patch("auth.delete_session", side_effect=RuntimeError("DB down")):
            handler._handle_auth_logout()  # should not raise
        handler.send_response.assert_called_once_with(200)
