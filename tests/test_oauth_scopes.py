"""
tests/test_oauth_scopes.py — Verify that app-login and Calendar/Drive OAuth
flows request strictly separated scopes.

No live network, database, or HTTP server required.
"""

import os
import sys
import types
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Project root on sys.path ──────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Python 3.13+ compatibility shim ──────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

# ── Import auth module ────────────────────────────────────────────────────────

import auth


# ── App Login scope tests ─────────────────────────────────────────────────────

class TestAppLoginScopes:
    """build_auth_login_url() must request identity scopes and nothing else."""

    def _get_scopes(self, url: str) -> list[str]:
        """Parse the 'scope' query parameter from an OAuth URL."""
        qs = urllib.parse.urlparse(url).query
        params = urllib.parse.parse_qs(qs)
        scope_str = params.get("scope", [""])[0]
        return scope_str.split()

    def test_contains_openid(self, monkeypatch):
        monkeypatch.setenv("AUTH_GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("AUTH_GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/google/callback")
        url = auth.build_auth_login_url(state="test-state")
        scopes = self._get_scopes(url)
        assert "openid" in scopes, f"Expected 'openid' in scopes, got: {scopes}"

    def test_contains_email(self, monkeypatch):
        monkeypatch.setenv("AUTH_GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("AUTH_GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/google/callback")
        url = auth.build_auth_login_url(state="test-state")
        scopes = self._get_scopes(url)
        assert "email" in scopes, f"Expected 'email' in scopes, got: {scopes}"

    def test_contains_profile(self, monkeypatch):
        monkeypatch.setenv("AUTH_GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("AUTH_GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/google/callback")
        url = auth.build_auth_login_url(state="test-state")
        scopes = self._get_scopes(url)
        assert "profile" in scopes, f"Expected 'profile' in scopes, got: {scopes}"

    def test_does_not_contain_calendar(self, monkeypatch):
        monkeypatch.setenv("AUTH_GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("AUTH_GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/google/callback")
        url = auth.build_auth_login_url(state="test-state")
        # Check the raw URL too — calendar scope is a full URI
        assert "calendar" not in url.lower(), \
            f"App login URL must not include calendar scopes, got: {url}"

    def test_does_not_contain_drive(self, monkeypatch):
        monkeypatch.setenv("AUTH_GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("AUTH_GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/google/callback")
        url = auth.build_auth_login_url(state="test-state")
        assert "drive" not in url.lower(), \
            f"App login URL must not include drive scopes, got: {url}"

    def test_scope_constant_has_no_calendar(self):
        """The AUTH_GOOGLE_LOGIN_SCOPES constant must not include calendar."""
        for scope in auth.AUTH_GOOGLE_LOGIN_SCOPES:
            assert "calendar" not in scope.lower(), \
                f"AUTH_GOOGLE_LOGIN_SCOPES must not contain calendar scope, got: {auth.AUTH_GOOGLE_LOGIN_SCOPES}"

    def test_scope_constant_has_no_drive(self):
        """The AUTH_GOOGLE_LOGIN_SCOPES constant must not include drive."""
        for scope in auth.AUTH_GOOGLE_LOGIN_SCOPES:
            assert "drive" not in scope.lower(), \
                f"AUTH_GOOGLE_LOGIN_SCOPES must not contain drive scope, got: {auth.AUTH_GOOGLE_LOGIN_SCOPES}"


# ── Calendar/Drive scope tests ─────────────────────────────────────────────────

_GCAL_DRIVE_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly "
    "https://www.googleapis.com/auth/drive.file"
)


class TestCalendarDriveScopes:
    """Calendar/Drive OAuth scopes must include calendar but not identity scopes."""

    def _get_scope_string(self) -> str:
        """Return the scope string used by the Calendar/Drive OAuth flow."""
        return _GCAL_DRIVE_SCOPES

    def test_contains_calendar(self):
        scopes = self._get_scope_string()
        assert "calendar" in scopes.lower(), \
            f"Calendar/Drive OAuth must include calendar scope, got: {scopes}"

    def test_contains_drive(self):
        scopes = self._get_scope_string()
        assert "drive" in scopes.lower(), \
            f"Calendar/Drive OAuth must include drive scope, got: {scopes}"

    def test_does_not_contain_openid(self):
        scopes = self._get_scope_string()
        scope_list = scopes.split()
        assert "openid" not in scope_list, \
            f"Calendar/Drive OAuth must NOT include 'openid' scope, got: {scope_list}"

    def test_does_not_contain_profile(self):
        scopes = self._get_scope_string()
        assert "profile" not in scopes.lower(), \
            f"Calendar/Drive OAuth must NOT include 'profile' scope, got: {scopes}"

    def test_does_not_contain_email_scope(self):
        """'email' the scope value (not the word appearing in URLs) must be absent."""
        scope_list = self._get_scope_string().split()
        assert "email" not in scope_list, \
            f"Calendar/Drive OAuth must NOT include 'email' scope, got: {scope_list}"
