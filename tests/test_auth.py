"""
tests/test_auth.py — Unit tests for auth.py and the /auth/google/* routes.

No live network, database, or HTTP server required.  All external calls are
mocked via unittest.mock.

Compatibility note: stubs out the ``cgi`` module before importing server.py
so these tests run on Python 3.13+ where cgi was removed.
"""

import base64
import json
import os
import sys
import types
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ── Project root on sys.path ──────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Python 3.13+ compatibility shim ──────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

# ── Imports ───────────────────────────────────────────────────────────────────

import auth   # noqa: E402
import server  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_jwt_payload(claims: dict) -> str:
    """Build a minimal JWT string with a real base64url-encoded payload."""
    header  = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps(claims).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesig"


def _make_handler():
    """Return a Handler instance with network-level methods mocked out."""
    handler = server.Handler.__new__(server.Handler)
    handler._send_json      = MagicMock()
    handler.send_response   = MagicMock()
    handler.send_header     = MagicMock()
    handler.end_headers     = MagicMock()
    handler.server          = MagicMock()
    handler.server.server_address = ("127.0.0.1", 8080)
    return handler


# ── build_auth_login_url ──────────────────────────────────────────────────────

class TestBuildAuthLoginUrl:
    """auth.build_auth_login_url() should produce a correctly formed URL."""

    def _call(self, state="test-state-abc", **env_overrides):
        env = {
            "AUTH_GOOGLE_CLIENT_ID":    "my-client-id",
            "AUTH_GOOGLE_REDIRECT_URI": "http://localhost:8080/auth/google/callback",
            **env_overrides,
        }
        with patch.dict(os.environ, env, clear=False):
            return auth.build_auth_login_url(state)

    def test_returns_google_accounts_url(self):
        url = self._call()
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")

    def test_includes_client_id(self):
        url = self._call()
        assert "client_id=my-client-id" in url

    def test_includes_redirect_uri(self):
        url = self._call()
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fauth%2Fgoogle%2Fcallback" in url

    def test_includes_openid_scope(self):
        url = self._call()
        assert "openid" in url

    def test_includes_email_scope(self):
        url = self._call()
        assert "email" in url

    def test_includes_profile_scope(self):
        url = self._call()
        assert "profile" in url

    def test_includes_state_param(self):
        url = self._call(state="my-random-state")
        assert "my-random-state" in url

    def test_access_type_offline(self):
        url = self._call()
        assert "access_type=offline" in url

    def test_prompt_consent(self):
        url = self._call()
        assert "prompt=consent" in url

    def test_login_scopes_constant(self):
        assert auth.AUTH_GOOGLE_LOGIN_SCOPES == ["openid", "email", "profile"]


# ── exchange_auth_code ────────────────────────────────────────────────────────

class TestExchangeAuthCode:
    """auth.exchange_auth_code() should parse a mocked token response."""

    _CLAIMS = {
        "sub":     "1234567890",
        "email":   "jane@example.com",
        "name":    "Jane Doe",
        "picture": "https://example.com/photo.jpg",
        "hd":      "example.com",
    }

    def _mock_urlopen(self, claims=None):
        """Return a mock urlopen context manager that yields a token response."""
        if claims is None:
            claims = self._CLAIMS
        id_token    = _make_jwt_payload(claims)
        token_resp  = json.dumps({"id_token": id_token, "access_token": "at-xyz"}).encode()
        mock_resp   = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__  = MagicMock(return_value=False)
        mock_resp.read      = MagicMock(return_value=token_resp)
        return mock_resp

    def _env(self):
        return {
            "AUTH_GOOGLE_CLIENT_ID":     "cid",
            "AUTH_GOOGLE_CLIENT_SECRET": "csecret",
            "AUTH_GOOGLE_REDIRECT_URI":  "http://localhost:8080/auth/google/callback",
        }

    def test_returns_claims_dict(self):
        with patch.dict(os.environ, self._env()), \
             patch("urllib.request.urlopen", return_value=self._mock_urlopen()):
            claims = auth.exchange_auth_code("code-abc")
        assert claims["email"] == "jane@example.com"

    def test_returns_name(self):
        with patch.dict(os.environ, self._env()), \
             patch("urllib.request.urlopen", return_value=self._mock_urlopen()):
            claims = auth.exchange_auth_code("code-abc")
        assert claims["name"] == "Jane Doe"

    def test_returns_picture(self):
        with patch.dict(os.environ, self._env()), \
             patch("urllib.request.urlopen", return_value=self._mock_urlopen()):
            claims = auth.exchange_auth_code("code-abc")
        assert claims["picture"] == "https://example.com/photo.jpg"

    def test_returns_sub(self):
        with patch.dict(os.environ, self._env()), \
             patch("urllib.request.urlopen", return_value=self._mock_urlopen()):
            claims = auth.exchange_auth_code("code-abc")
        assert claims["sub"] == "1234567890"

    def test_returns_hd(self):
        with patch.dict(os.environ, self._env()), \
             patch("urllib.request.urlopen", return_value=self._mock_urlopen()):
            claims = auth.exchange_auth_code("code-abc")
        assert claims["hd"] == "example.com"

    def test_raises_value_error_on_missing_id_token(self):
        token_resp = json.dumps({"access_token": "at"}).encode()
        mock_resp  = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__  = MagicMock(return_value=False)
        mock_resp.read      = MagicMock(return_value=token_resp)
        with patch.dict(os.environ, self._env()), \
             patch("urllib.request.urlopen", return_value=mock_resp), \
             pytest.raises(ValueError, match="No id_token"):
            auth.exchange_auth_code("bad-code")

    def test_raises_value_error_on_network_error(self):
        with patch.dict(os.environ, self._env()), \
             patch("urllib.request.urlopen", side_effect=OSError("connection refused")), \
             pytest.raises(ValueError, match="token exchange request failed"):
            auth.exchange_auth_code("code-xyz")

    def test_raises_value_error_on_malformed_jwt(self):
        token_resp = json.dumps({"id_token": "not.a.valid.jwt.parts"}).encode()
        mock_resp  = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__  = MagicMock(return_value=False)
        mock_resp.read      = MagicMock(return_value=token_resp)
        with patch.dict(os.environ, self._env()), \
             patch("urllib.request.urlopen", return_value=mock_resp), \
             pytest.raises(ValueError, match="Malformed id_token"):
            auth.exchange_auth_code("code-bad")


# ── upsert_user ───────────────────────────────────────────────────────────────

class TestUpsertUser:
    """auth.upsert_user() should INSERT new users and UPDATE existing ones."""

    _CLAIMS = {
        "email":   "alice@example.org",
        "name":    "Alice Smith",
        "picture": "https://example.org/alice.jpg",
        "sub":     "999",
    }

    def _make_mock_conn(self, returned_row):
        """Return a mock connection whose execute().fetchone() returns returned_row."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = returned_row

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__  = MagicMock(return_value=False)
        return mock_conn

    def _call(self, claims=None, row=None):
        if claims is None:
            claims = self._CLAIMS
        if row is None:
            row = ("uuid-1", "alice@example.org", "Alice Smith",
                   "https://example.org/alice.jpg", "example.org")
        mock_conn = self._make_mock_conn(row)
        with patch.object(auth, "ALLOWED_DOMAIN", "example.org"), \
             patch("db.transaction", return_value=mock_conn):
            return auth.upsert_user(claims)

    def test_returns_id(self):
        user = self._call()
        assert user["id"] == "uuid-1"

    def test_returns_email(self):
        user = self._call()
        assert user["email"] == "alice@example.org"

    def test_returns_display_name(self):
        user = self._call()
        assert user["display_name"] == "Alice Smith"

    def test_returns_avatar_url(self):
        user = self._call()
        assert user["avatar_url"] == "https://example.org/alice.jpg"

    def test_returns_domain(self):
        user = self._call()
        assert user["domain"] == "example.org"

    def test_raises_if_email_missing(self):
        with pytest.raises(ValueError, match="missing the 'email' field"):
            auth.upsert_user({"name": "No Email"})

    def test_raises_if_email_empty_string(self):
        with pytest.raises(ValueError, match="missing the 'email' field"):
            auth.upsert_user({"email": "", "name": "Empty"})

    def test_domain_extracted_from_email(self):
        row = ("uid-2", "bob@myorg.com", "Bob", "", "myorg.com")
        mock_conn = self._make_mock_conn(row)
        with patch.object(auth, "ALLOWED_DOMAIN", "myorg.com"), \
             patch("db.transaction", return_value=mock_conn):
            user = auth.upsert_user({"email": "bob@myorg.com", "name": "Bob", "picture": ""})
        assert user["domain"] == "myorg.com"

    def test_upsert_sql_called_with_correct_args(self):
        """execute() should be called with the ON CONFLICT upsert SQL."""
        row = ("uid-3", "alice@example.org", "Alice Smith",
               "https://example.org/alice.jpg", "example.org")
        mock_conn = self._make_mock_conn(row)
        with patch.object(auth, "ALLOWED_DOMAIN", "example.org"), \
             patch("db.transaction", return_value=mock_conn):
            auth.upsert_user(self._CLAIMS)

        assert mock_conn.execute.called
        sql_arg = mock_conn.execute.call_args[0][0]
        assert "ON CONFLICT" in sql_arg
        assert "DO UPDATE" in sql_arg

    def test_update_existing_user_returns_updated_values(self):
        """When a user already exists, upsert returns the new display_name."""
        updated_row = ("uuid-1", "alice@example.org", "Alice Updated",
                       "https://example.org/new.jpg", "example.org")
        user = self._call(row=updated_row)
        assert user["display_name"] == "Alice Updated"
        assert user["avatar_url"] == "https://example.org/new.jpg"


# ── /auth/google/login route ──────────────────────────────────────────────────

class TestAuthGoogleLoginRoute:
    """/auth/google/login should redirect to Google in server mode, 404 in desktop."""

    def _call_server_mode(self):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", False), \
             patch.dict(os.environ, {
                 "AUTH_GOOGLE_CLIENT_ID":    "cid",
                 "AUTH_GOOGLE_REDIRECT_URI": "http://localhost:8080/auth/google/callback",
             }):
            handler._handle_auth_google_login()
        return handler

    def test_redirects_302_in_server_mode(self):
        handler = self._call_server_mode()
        handler.send_response.assert_called_once_with(302)

    def test_location_header_points_to_google(self):
        handler = self._call_server_mode()
        location_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Location"
        ]
        assert location_calls, "No Location header was set"
        location = location_calls[0][0][1]
        assert "accounts.google.com" in location

    def test_returns_404_in_desktop_mode(self):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", True):
            handler._handle_auth_google_login()
        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        assert args[1] == 404

    def test_state_stored_in_csrf_dict(self):
        """A CSRF state entry should be added to _auth_login_states."""
        with patch.object(server, "IS_DESKTOP", False), \
             patch.dict(os.environ, {
                 "AUTH_GOOGLE_CLIENT_ID":    "cid",
                 "AUTH_GOOGLE_REDIRECT_URI": "http://localhost:8080/auth/google/callback",
             }):
            server._auth_login_states.clear()
            handler = _make_handler()
            handler._handle_auth_google_login()
            assert len(server._auth_login_states) == 1


# ── /auth/google/callback route ───────────────────────────────────────────────

class TestAuthGoogleCallbackRoute:
    """/auth/google/callback should exchange code, upsert user, set cookie."""

    _CLAIMS = {
        "sub":     "42",
        "email":   "user@example.com",
        "name":    "Test User",
        "picture": "https://example.com/pic.jpg",
    }

    def _setup_state(self, state="valid-state"):
        server._auth_login_states[state] = True

    def _call(self, qs="code=mycode&state=valid-state", is_desktop=False):
        handler = _make_handler()
        handler.path = f"/auth/google/callback?{qs}"
        self._setup_state("valid-state")
        with patch.object(server, "IS_DESKTOP", is_desktop), \
             patch("auth.exchange_auth_code", return_value=self._CLAIMS), \
             patch("auth.upsert_user", return_value={
                 "id": "user-uuid-123",
                 "email": "user@example.com",
                 "display_name": "Test User",
                 "avatar_url": "https://example.com/pic.jpg",
                 "domain": "example.com",
             }), \
             patch("auth.create_session", return_value="fake-session-token"):
            handler._handle_auth_google_callback()
        return handler

    def test_redirects_302_on_success(self):
        handler = self._call()
        handler.send_response.assert_called_once_with(302)

    def test_redirects_to_root_on_success(self):
        handler = self._call()
        location_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Location"
        ]
        assert location_calls[0][0][1] == "/"

    def test_sets_bg_session_cookie(self):
        handler = self._call()
        cookie_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Set-Cookie"
        ]
        assert cookie_calls, "No Set-Cookie header was set"
        cookie_value = cookie_calls[0][0][1]
        assert "bg_session=fake-session-token" in cookie_value

    def test_cookie_is_httponly(self):
        handler = self._call()
        cookie_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Set-Cookie"
        ]
        cookie_value = cookie_calls[0][0][1]
        assert "HttpOnly" in cookie_value

    def test_returns_404_in_desktop_mode(self):
        handler = _make_handler()
        handler.path = "/auth/google/callback?code=x&state=valid-state"
        self._setup_state("valid-state")
        with patch.object(server, "IS_DESKTOP", True):
            handler._handle_auth_google_callback()
        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        assert args[1] == 404

    def test_redirects_on_oauth_error(self):
        handler = _make_handler()
        handler.path = "/auth/google/callback?error=access_denied&state=valid-state"
        self._setup_state("valid-state")
        with patch.object(server, "IS_DESKTOP", False):
            handler._handle_auth_google_callback()
        location_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Location"
        ]
        assert "auth_error=denied" in location_calls[0][0][1]

    def test_redirects_on_missing_code(self):
        handler = _make_handler()
        handler.path = "/auth/google/callback?state=valid-state"
        self._setup_state("valid-state")
        with patch.object(server, "IS_DESKTOP", False):
            handler._handle_auth_google_callback()
        location_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Location"
        ]
        assert "auth_error=denied" in location_calls[0][0][1]

    def test_redirects_on_invalid_state(self):
        handler = _make_handler()
        handler.path = "/auth/google/callback?code=abc&state=bad-state"
        server._auth_login_states.clear()
        with patch.object(server, "IS_DESKTOP", False):
            handler._handle_auth_google_callback()
        location_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Location"
        ]
        assert "auth_error=state_mismatch" in location_calls[0][0][1]

    def test_state_consumed_after_use(self):
        """CSRF state should be removed from the dict once used."""
        self._call(qs="code=mycode&state=valid-state")
        assert "valid-state" not in server._auth_login_states

    def test_redirects_on_exchange_failure(self):
        """A ValueError from exchange_auth_code results in a 403 (domain-rejection path)."""
        handler = _make_handler()
        handler.path = "/auth/google/callback?code=bad&state=valid-state"
        handler.wfile = MagicMock()
        self._setup_state("valid-state")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.exchange_auth_code", side_effect=ValueError("boom")):
            handler._handle_auth_google_callback()
        # ValueError is now caught by the domain-rejection branch → 403
        handler.send_response.assert_called_once_with(403)


# ── validate_domain ───────────────────────────────────────────────────────────

class TestValidateDomain:
    """auth.validate_domain() should accept only the configured allowed domain."""

    def _call(self, email, allowed="visaliacrc.com"):
        with patch.dict(os.environ, {"GOOGLE_WORKSPACE_DOMAIN": allowed}, clear=False):
            # Re-read ALLOWED_DOMAIN from env for each call via the module-level constant.
            # Since the constant is set at import time, patch the attribute directly.
            with patch.object(auth, "ALLOWED_DOMAIN", allowed):
                return auth.validate_domain(email)

    def test_accepted_domain(self):
        assert self._call("person@visaliacrc.com") is True

    def test_rejected_domain(self):
        assert self._call("person@gmail.com") is False

    def test_case_insensitive_uppercase(self):
        assert self._call("USER@VISALIACRC.COM") is True

    def test_whitespace_stripped(self):
        assert self._call("  user@visaliacrc.com  ") is True

    def test_no_at_sign_returns_false(self):
        assert self._call("notanemail") is False

    def test_subdomain_rejected(self):
        assert self._call("user@sub.visaliacrc.com") is False


# ── upsert_user domain enforcement ───────────────────────────────────────────

class TestUpsertUserDomainEnforcement:
    """upsert_user() should raise ValueError for disallowed email domains."""

    def _make_mock_conn(self, returned_row):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = returned_row
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__  = MagicMock(return_value=False)
        return mock_conn

    def test_raises_for_wrong_domain(self):
        with patch.object(auth, "ALLOWED_DOMAIN", "visaliacrc.com"), \
             pytest.raises(ValueError, match="Login restricted"):
            auth.upsert_user({"email": "person@gmail.com", "name": "Person", "picture": ""})

    def test_does_not_raise_for_allowed_domain(self):
        row = ("uid-ok", "person@visaliacrc.com", "Person", "", "visaliacrc.com")
        mock_conn = self._make_mock_conn(row)
        with patch.object(auth, "ALLOWED_DOMAIN", "visaliacrc.com"), \
             patch("db.transaction", return_value=mock_conn):
            user = auth.upsert_user({"email": "person@visaliacrc.com", "name": "Person", "picture": ""})
        assert user["email"] == "person@visaliacrc.com"


# ── callback route: domain rejection returns 403 ──────────────────────────────

class TestCallbackDomainRejection:
    """Callback with a wrong-domain account should return 403 with no cookie."""

    _WRONG_CLAIMS = {
        "sub":     "99",
        "email":   "outsider@gmail.com",
        "name":    "Outsider",
        "picture": "",
    }

    def _setup_state(self, state="valid-state"):
        server._auth_login_states[state] = True

    def _call_with_wrong_domain(self):
        handler = _make_handler()
        handler.path = "/auth/google/callback?code=mycode&state=valid-state"
        handler.wfile = MagicMock()
        self._setup_state("valid-state")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.exchange_auth_code", return_value=self._WRONG_CLAIMS), \
             patch("auth.upsert_user", side_effect=ValueError("Login restricted to @visaliacrc.com accounts")):
            handler._handle_auth_google_callback()
        return handler

    def test_returns_403(self):
        handler = self._call_with_wrong_domain()
        handler.send_response.assert_called_once_with(403)

    def test_no_cookie_set(self):
        handler = self._call_with_wrong_domain()
        cookie_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Set-Cookie"
        ]
        assert not cookie_calls, "Set-Cookie header should not be set on rejection"

    def test_no_redirect(self):
        handler = self._call_with_wrong_domain()
        location_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Location"
        ]
        assert not location_calls, "Location header should not be set on 403"

    def test_response_body_mentions_domain(self):
        handler = self._call_with_wrong_domain()
        write_calls = handler.wfile.write.call_args_list
        assert write_calls, "Response body should be written"
        body = write_calls[0][0][0].decode("utf-8")
        assert "visaliacrc.com" in body

    def test_response_body_has_try_again_link(self):
        handler = self._call_with_wrong_domain()
        body = handler.wfile.write.call_args_list[0][0][0].decode("utf-8")
        assert "/auth/google/login" in body
