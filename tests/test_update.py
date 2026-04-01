"""
Tests for server.py update routes (#87).
Covers: _apply_update_server, _handle_update_status
"""
import json
import os
import sys
import urllib.error
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent.parent))

import server


# ── Minimal Handler stub ───────────────────────────────────────────────────────
# We don't want to spin up a real HTTP server. We just need an object
# that has the handler methods and captures what _send_json was called with.

class StubHandler:
    """Minimal stand-in for server.Handler that captures _send_json calls."""

    def __init__(self):
        self._responses = []  # list of (body_dict, status_code)

    def _send_json(self, body, status=200):
        self._responses.append((body, status))

    # Bind the real methods from server.Handler
    _apply_update_server = server.Handler._apply_update_server
    _handle_update_status = server.Handler._handle_update_status


# ── _apply_update_server ──────────────────────────────────────────────────────

class TestApplyUpdateServer:
    def _make_handler(self):
        h = StubHandler()
        return h

    def _mock_urlopen_ok(self, body_text=""):
        """Context manager mock that returns a successful response."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = body_text.encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return patch("urllib.request.urlopen", return_value=mock_resp)

    def test_success_returns_ok_true(self):
        h = self._make_handler()
        with self._mock_urlopen_ok("Triggered"):
            h._apply_update_server()
        body, status = h._responses[0]
        assert body["ok"] is True
        assert status == 200

    def test_success_message_mentions_restart(self):
        h = self._make_handler()
        with self._mock_urlopen_ok():
            h._apply_update_server()
        body, _ = h._responses[0]
        assert "restart" in body["message"].lower() or "pull" in body["message"].lower()

    def test_success_includes_watchtower_response(self):
        h = self._make_handler()
        with self._mock_urlopen_ok("Scheduled"):
            h._apply_update_server()
        body, _ = h._responses[0]
        assert body.get("watchtowerResponse") == "Scheduled"

    def test_http_error_returns_502_with_manual_fallback(self):
        h = self._make_handler()
        err = urllib.error.HTTPError(
            url="http://watchtower/v1/update",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=BytesIO(b"bad token"),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            h._apply_update_server()
        body, status = h._responses[0]
        assert status == 502
        assert "403" in body["error"]
        assert "manualFallback" in body
        assert "docker compose" in body["manualFallback"]

    def test_url_error_returns_502_with_manual_fallback(self):
        h = self._make_handler()
        err = urllib.error.URLError(reason="Connection refused")
        with patch("urllib.request.urlopen", side_effect=err):
            h._apply_update_server()
        body, status = h._responses[0]
        assert status == 502
        assert "Watchtower" in body["error"] or "watchtower" in body["error"].lower()
        assert "manualFallback" in body
        assert "docker compose" in body["manualFallback"]

    def test_generic_exception_returns_500_with_manual_fallback(self):
        h = self._make_handler()
        with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            h._apply_update_server()
        body, status = h._responses[0]
        assert status == 500
        assert "manualFallback" in body

    def test_http_error_includes_response_body_detail(self):
        h = self._make_handler()
        err = urllib.error.HTTPError(
            url="http://watchtower/v1/update",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(b"invalid token"),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            h._apply_update_server()
        body, _ = h._responses[0]
        assert "detail" in body


# ── _handle_update_status ─────────────────────────────────────────────────────

class TestHandleUpdateStatus:
    def _make_handler(self):
        return StubHandler()

    def test_returns_watchtower_url(self):
        h = self._make_handler()
        h._handle_update_status()
        body, status = h._responses[0]
        assert status == 200
        assert "watchtowerUrl" in body

    def test_returns_token_as_bool(self):
        h = self._make_handler()
        h._handle_update_status()
        body, _ = h._responses[0]
        # Token should be True/False, not the actual token value
        assert isinstance(body["watchtowerToken"], bool)

    def test_returns_mode(self):
        h = self._make_handler()
        h._handle_update_status()
        body, _ = h._responses[0]
        assert body["mode"] in ("server", "desktop")

    def test_returns_docker_info(self):
        h = self._make_handler()
        h._handle_update_status()
        body, _ = h._responses[0]
        assert "dockerCliAvailable" in body
        assert "dockerSocketExists" in body

    def test_docker_socket_false_when_not_in_container(self):
        h = self._make_handler()
        _real_exists = os.path.exists
        with patch("os.path.exists", side_effect=lambda p: False if "docker.sock" in str(p) else _real_exists(p)):
            h._handle_update_status()
        body, _ = h._responses[0]
        assert body["dockerSocketExists"] is False
