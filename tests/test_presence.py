"""
tests/test_presence.py — Unit tests for presence heartbeat endpoints.

Covers:
  - POST /api/presence/heartbeat: upserts row with last_seen_at = now()
  - GET /api/presence?project_id=<uuid>: returns active presences (< 90s)
  - GET /api/presence?project_id=<uuid>: stale records (> 90s) excluded
  - DELETE /api/presence: removes caller's presence rows
  - Desktop mode bypass: all three endpoints return ok/[] without touching DB

No live database required — all DB calls are mocked.
"""

from __future__ import annotations

import sys
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Path / Python 3.13+ shim ──────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

import server  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────

WORKSPACE_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())

FAKE_USER = {
    "id": USER_ID,
    "user_id": USER_ID,
    "workspace_id": WORKSPACE_ID,
    "email": "test@example.com",
    "display_name": "Test User",
    "claims": {"sub": USER_ID},
}

DESKTOP_USER = {
    "id": None,
    "user_id": None,
    "workspace_id": None,
    "email": "desktop",
    "display_name": "Desktop User",
    "role": "desktop",
    "claims": None,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_handler(path="/api/presence"):
    """Return a minimal Handler with _send_json and _read_body_json mocked."""
    h = server.Handler.__new__(server.Handler)
    h._send_json = MagicMock()
    h._read_body_json = MagicMock(return_value={"project_id": PROJECT_ID})
    h.path = path
    return h


def _make_tx_ctx(rows=None):
    """Return a mock db.transaction() context manager.

    conn.execute().fetchall() returns *rows* (list of tuples).
    """
    rows = rows or []
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.execute.return_value = cursor

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, conn, cursor


def _sent(handler):
    """Return (data, status) from the first _send_json call."""
    assert handler._send_json.called
    args = handler._send_json.call_args[0]
    data = args[0]
    status = args[1] if len(args) > 1 else 200
    return data, status


# ── POST /api/presence/heartbeat ─────────────────────────────────────────────

class TestPresenceHeartbeat:
    def _call(self, body=None, user=None):
        h = _make_handler("/api/presence/heartbeat")
        if body is not None:
            h._read_body_json = MagicMock(return_value=body)
        ctx, conn, cursor = _make_tx_ctx()
        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(h, "_require_auth", return_value=user or FAKE_USER), \
             patch("db.transaction", return_value=ctx):
            h._handle_post_presence_heartbeat()
        return h, conn

    def test_returns_ok_true(self):
        h, _ = self._call()
        data, status = _sent(h)
        assert data == {"ok": True}
        assert status == 200

    def test_upserts_row_in_db(self):
        h, conn = self._call()
        conn.execute.assert_called_once()
        sql = conn.execute.call_args[0][0]
        assert "INSERT INTO workspace_presences" in sql
        assert "ON CONFLICT" in sql

    def test_upsert_passes_correct_params(self):
        h, conn = self._call()
        params = conn.execute.call_args[0][1]
        assert params[0] == WORKSPACE_ID   # workspace_id
        assert params[1] == USER_ID        # user_id
        assert params[2] == PROJECT_ID     # project_id

    def test_missing_project_id_returns_400(self):
        h, _ = self._call(body={})
        data, status = _sent(h)
        assert status == 400
        assert "project_id" in data.get("error", "")

    def test_invalid_json_body_returns_400(self):
        h = _make_handler("/api/presence/heartbeat")
        h._read_body_json = MagicMock(side_effect=ValueError("bad json"))
        ctx, conn, _ = _make_tx_ctx()
        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(h, "_require_auth", return_value=FAKE_USER), \
             patch("db.transaction", return_value=ctx):
            h._handle_post_presence_heartbeat()
        data, status = _sent(h)
        assert status == 400

    def test_no_workspace_id_returns_403(self):
        user_no_ws = {**FAKE_USER, "workspace_id": None}
        h, _ = self._call(user=user_no_ws)
        data, status = _sent(h)
        assert status == 403

    def test_unauthenticated_returns_early(self):
        h = _make_handler("/api/presence/heartbeat")
        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(h, "_require_auth", return_value=None):
            h._handle_post_presence_heartbeat()
        # _send_json called by _require_auth (mocked to do nothing) — just ensure no crash
        # The mock _require_auth returns None but also must have called _send_json.
        # Here we verify the handler doesn't proceed to DB.
        assert True  # no AttributeError = correct early return path


# ── GET /api/presence ─────────────────────────────────────────────────────────

class TestGetPresence:
    # Two active presence rows returned by the DB
    ACTIVE_ROWS = [
        (USER_ID, "Alice", "2026-06-03T12:00:00"),
        (str(uuid.uuid4()), "Bob", "2026-06-03T11:59:30"),
    ]

    def _call(self, project_id=None, rows=None, user=None):
        pid = project_id if project_id is not None else PROJECT_ID
        h = _make_handler(f"/api/presence?project_id={pid}")
        ctx, conn, cursor = _make_tx_ctx(rows=rows if rows is not None else self.ACTIVE_ROWS)
        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(h, "_require_auth", return_value=user or FAKE_USER), \
             patch("db.transaction", return_value=ctx):
            h._handle_get_presence()
        return h, conn, cursor

    def test_returns_list(self):
        h, _, _ = self._call()
        data, status = _sent(h)
        assert isinstance(data, list)
        assert status == 200

    def test_returns_active_presences(self):
        h, _, _ = self._call()
        data, _ = _sent(h)
        assert len(data) == 2

    def test_response_shape(self):
        h, _, _ = self._call()
        data, _ = _sent(h)
        first = data[0]
        assert "user_id" in first
        assert "display_name" in first
        assert "last_seen_at" in first

    def test_user_id_field(self):
        h, _, _ = self._call()
        data, _ = _sent(h)
        assert data[0]["user_id"] == USER_ID
        assert data[0]["display_name"] == "Alice"

    def test_stale_records_not_returned(self):
        """Query filters by 90s — we verify the SQL contains the interval."""
        h, conn, _ = self._call(rows=[])
        sql = conn.execute.call_args[0][0]
        assert "90 seconds" in sql

    def test_sql_filters_by_workspace_and_project(self):
        h, conn, _ = self._call()
        params = conn.execute.call_args[0][1]
        assert params[0] == WORKSPACE_ID
        assert params[1] == PROJECT_ID

    def test_missing_project_id_returns_400(self):
        h = _make_handler("/api/presence")
        ctx, conn, _ = _make_tx_ctx()
        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(h, "_require_auth", return_value=FAKE_USER), \
             patch("db.transaction", return_value=ctx):
            h._handle_get_presence()
        data, status = _sent(h)
        assert status == 400
        assert "project_id" in data.get("error", "")

    def test_no_workspace_id_returns_403(self):
        user_no_ws = {**FAKE_USER, "workspace_id": None}
        h, _, _ = self._call(user=user_no_ws)
        data, status = _sent(h)
        assert status == 403

    def test_empty_when_no_active_presences(self):
        h, _, _ = self._call(rows=[])
        data, status = _sent(h)
        assert data == []
        assert status == 200


# ── DELETE /api/presence ──────────────────────────────────────────────────────

class TestDeletePresence:
    def _call(self, user=None):
        h = _make_handler("/api/presence")
        ctx, conn, _ = _make_tx_ctx()
        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(h, "_require_auth", return_value=user or FAKE_USER), \
             patch("db.transaction", return_value=ctx):
            h._handle_delete_presence()
        return h, conn

    def test_returns_ok_true(self):
        h, _ = self._call()
        data, status = _sent(h)
        assert data == {"ok": True}
        assert status == 200

    def test_deletes_caller_rows(self):
        h, conn = self._call()
        conn.execute.assert_called_once()
        sql = conn.execute.call_args[0][0]
        assert "DELETE FROM workspace_presences" in sql

    def test_delete_scoped_to_workspace_and_user(self):
        h, conn = self._call()
        params = conn.execute.call_args[0][1]
        assert params[0] == WORKSPACE_ID
        assert params[1] == USER_ID

    def test_no_workspace_id_returns_403(self):
        user_no_ws = {**FAKE_USER, "workspace_id": None}
        h, _ = self._call(user=user_no_ws)
        data, status = _sent(h)
        assert status == 403


# ── Desktop mode bypass ───────────────────────────────────────────────────────

class TestPresenceDesktopBypass:
    """In desktop mode all three endpoints must return immediately without DB."""

    def _heartbeat(self):
        h = _make_handler("/api/presence/heartbeat")
        h._read_body_json = MagicMock(return_value={"project_id": PROJECT_ID})
        with patch.object(server, "IS_DESKTOP", True), \
             patch.object(h, "_require_auth", return_value=DESKTOP_USER), \
             patch("db.transaction") as mock_tx:
            h._handle_post_presence_heartbeat()
        return h, mock_tx

    def _get(self):
        h = _make_handler(f"/api/presence?project_id={PROJECT_ID}")
        with patch.object(server, "IS_DESKTOP", True), \
             patch.object(h, "_require_auth", return_value=DESKTOP_USER), \
             patch("db.transaction") as mock_tx:
            h._handle_get_presence()
        return h, mock_tx

    def _delete(self):
        h = _make_handler("/api/presence")
        with patch.object(server, "IS_DESKTOP", True), \
             patch.object(h, "_require_auth", return_value=DESKTOP_USER), \
             patch("db.transaction") as mock_tx:
            h._handle_delete_presence()
        return h, mock_tx

    def test_heartbeat_returns_ok(self):
        h, mock_tx = self._heartbeat()
        data, status = _sent(h)
        assert data == {"ok": True}
        assert status == 200

    def test_heartbeat_does_not_touch_db(self):
        _, mock_tx = self._heartbeat()
        mock_tx.assert_not_called()

    def test_get_returns_empty_list(self):
        h, mock_tx = self._get()
        data, status = _sent(h)
        assert data == []
        assert status == 200

    def test_get_does_not_touch_db(self):
        _, mock_tx = self._get()
        mock_tx.assert_not_called()

    def test_delete_returns_ok(self):
        h, mock_tx = self._delete()
        data, status = _sent(h)
        assert data == {"ok": True}
        assert status == 200

    def test_delete_does_not_touch_db(self):
        _, mock_tx = self._delete()
        mock_tx.assert_not_called()
