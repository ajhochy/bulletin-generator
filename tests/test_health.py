"""
tests/test_health.py — Unit tests for GET /api/health endpoint.

No live PostgreSQL or HTTP server required — DB and migration helpers are mocked.

The test file stubs out the `cgi` module (removed in Python 3.13+) before
importing server.py so that the module loads cleanly on all supported Python
versions.
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

# ── Import server after patching cgi ─────────────────────────────────────────
import server  # noqa: E402  (must follow sys.modules patch)


# ── Test helper ───────────────────────────────────────────────────────────────

def _make_handler():
    """
    Return a Handler instance with _send_json mocked so we can inspect what
    payload and status code the endpoint would return without needing a real
    socket or HTTP connection.
    """
    handler = server.Handler.__new__(server.Handler)
    handler._send_json = MagicMock()
    return handler


def _sent(handler):
    """Return (data_dict, status_code) from the captured _send_json call."""
    assert handler._send_json.called, "_send_json was never called"
    args = handler._send_json.call_args
    data = args[0][0]
    # status defaults to 200 if not supplied as positional or keyword arg
    if len(args[0]) > 1:
        status = args[0][1]
    else:
        status = args[1].get("status", 200) if args[1] else 200
    return data, status


# ── Desktop mode ──────────────────────────────────────────────────────────────

class TestHealthDesktopMode:
    def _call(self, version="1.2.3"):
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", True), \
             patch.object(server, "APP_MODE", "desktop"), \
             patch.object(server, "APP_VERSION", version):
            handler._handle_health()
        return handler

    def test_returns_http_200(self):
        handler = self._call()
        _, status = _sent(handler)
        assert status == 200

    def test_status_is_healthy(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert data["status"] == "healthy"

    def test_mode_field(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert data["mode"] == "desktop"

    def test_version_field(self):
        handler = self._call(version="9.9.9")
        data, _ = _sent(handler)
        assert data["version"] == "9.9.9"

    def test_no_database_field(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert "database" not in data


# ── Server mode — healthy DB ──────────────────────────────────────────────────

class TestHealthServerModeHealthy:
    def _call(self, applied=1, latest="v001_initial_schema"):
        db_result = {"connected": True, "error": None}
        mig_result = {"applied": applied, "latest": latest}
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(server, "APP_MODE", "server"), \
             patch.object(server, "APP_VERSION", "2.0.0"), \
             patch("db.health_check", return_value=db_result), \
             patch("migrations.runner.get_migration_status", return_value=mig_result):
            handler._handle_health()
        return handler

    def test_returns_http_200(self):
        handler = self._call()
        _, status = _sent(handler)
        assert status == 200

    def test_status_healthy(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert data["status"] == "healthy"

    def test_mode_and_version(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert data["mode"] == "server"
        assert data["version"] == "2.0.0"

    def test_database_connected_true(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert data["database"]["connected"] is True

    def test_database_error_none(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert data["database"]["error"] is None

    def test_migrations_applied_count(self):
        handler = self._call(applied=1, latest="v001_initial_schema")
        data, _ = _sent(handler)
        assert data["database"]["migrations_applied"] == 1
        assert data["database"]["latest_migration"] == "v001_initial_schema"

    def test_zero_migrations_applied(self):
        handler = self._call(applied=0, latest=None)
        data, _ = _sent(handler)
        assert data["database"]["migrations_applied"] == 0
        assert data["database"]["latest_migration"] is None


# ── Server mode — unhealthy DB ────────────────────────────────────────────────

class TestHealthServerModeUnhealthy:
    def _call(self, error_msg="connection refused"):
        db_result = {"connected": False, "error": error_msg}
        mig_result = {"applied": None, "latest": None, "error": error_msg}
        handler = _make_handler()
        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(server, "APP_MODE", "server"), \
             patch.object(server, "APP_VERSION", "2.0.0"), \
             patch("db.health_check", return_value=db_result), \
             patch("migrations.runner.get_migration_status", return_value=mig_result):
            handler._handle_health()
        return handler

    def test_returns_http_503(self):
        handler = self._call()
        _, status = _sent(handler)
        assert status == 503

    def test_status_unhealthy(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert data["status"] == "unhealthy"

    def test_connected_false(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert data["database"]["connected"] is False

    def test_error_message_propagated(self):
        handler = self._call("connection refused")
        data, _ = _sent(handler)
        assert data["database"]["error"] == "connection refused"

    def test_migrations_applied_is_none(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert data["database"]["migrations_applied"] is None

    def test_latest_migration_is_none(self):
        handler = self._call()
        data, _ = _sent(handler)
        assert data["database"]["latest_migration"] is None
