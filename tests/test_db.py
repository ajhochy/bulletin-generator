"""
Unit tests for db.py — connection helper, transaction rollback, JSONB helpers.

These tests use mocks/monkeypatching so no live PostgreSQL instance is needed.
"""

import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _import_db_in_server_mode():
    """Import db with APP_MODE=server so IS_DESKTOP is False."""
    import importlib
    with patch.dict(os.environ, {"APP_MODE": "server"}):
        import db
        importlib.reload(db)
        return db


# ── JSONB helpers ─────────────────────────────────────────────────────────────

class TestToFromJsonb:
    def setup_method(self):
        import importlib
        import db
        importlib.reload(db)
        self.db = db

    def test_to_jsonb_dict(self):
        result = self.db.to_jsonb({"key": "value", "num": 42})
        assert json.loads(result) == {"key": "value", "num": 42}

    def test_to_jsonb_list(self):
        result = self.db.to_jsonb([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_to_jsonb_unicode(self):
        result = self.db.to_jsonb({"name": "héllo wörld"})
        parsed = json.loads(result)
        assert parsed["name"] == "héllo wörld"

    def test_from_jsonb_string(self):
        result = self.db.from_jsonb('{"a": 1}')
        assert result == {"a": 1}

    def test_from_jsonb_none(self):
        assert self.db.from_jsonb(None) is None

    def test_from_jsonb_already_dict(self):
        """psycopg3 may return decoded dicts directly for jsonb columns."""
        d = {"already": "decoded"}
        assert self.db.from_jsonb(d) is d

    def test_from_jsonb_already_list(self):
        lst = [1, 2, 3]
        assert self.db.from_jsonb(lst) is lst

    def test_roundtrip(self):
        original = {"items": [{"type": "song", "title": "Amazing Grace"}], "count": 1}
        assert self.db.from_jsonb(self.db.to_jsonb(original)) == original


# ── Desktop-mode guard ────────────────────────────────────────────────────────

class TestDesktopModeGuard:
    def test_get_connection_raises_in_desktop_mode(self, monkeypatch):
        import importlib
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", True)
        with pytest.raises(RuntimeError, match="server mode"):
            db.get_connection()

    def test_transaction_raises_in_desktop_mode(self, monkeypatch):
        import importlib
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", True)
        with pytest.raises(RuntimeError, match="server mode"):
            with db.transaction():
                pass

    def test_health_check_returns_error_in_desktop_mode(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", True)
        result = db.health_check()
        assert result["connected"] is False
        assert "server mode" in result["error"]


# ── get_connection ─────────────────────────────────────────────────────────────

class TestGetConnection:
    def test_raises_when_database_url_not_set(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                db.get_connection()

    def test_raises_when_database_url_empty(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)
        with patch.dict(os.environ, {"DATABASE_URL": "   "}):
            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                db.get_connection()

    def test_calls_psycopg_connect_with_url(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)

        mock_conn = MagicMock()
        mock_psycopg = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        db_url = "postgresql://user:pass@localhost/testdb"
        with patch.dict(os.environ, {"DATABASE_URL": db_url}):
            with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
                conn = db.get_connection()

        # prepare_threshold=None disables prepared statements for the pooler.
        mock_psycopg.connect.assert_called_once_with(db_url, prepare_threshold=None)
        assert conn is mock_conn


# ── transaction() context manager ─────────────────────────────────────────────

class TestTransaction:
    def _make_mock_conn(self):
        conn = MagicMock()
        return conn

    def test_commits_on_success(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)

        mock_conn = self._make_mock_conn()
        with patch.object(db, "get_connection", return_value=mock_conn):
            with db.transaction() as conn:
                assert conn is mock_conn

        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()
        mock_conn.close.assert_called_once()

    def test_rolls_back_on_exception(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)

        mock_conn = self._make_mock_conn()
        with patch.object(db, "get_connection", return_value=mock_conn):
            with pytest.raises(ValueError, match="boom"):
                with db.transaction():
                    raise ValueError("boom")

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

    def test_closes_connection_after_rollback(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)

        mock_conn = self._make_mock_conn()
        with patch.object(db, "get_connection", return_value=mock_conn):
            with pytest.raises(RuntimeError):
                with db.transaction():
                    raise RuntimeError("fail")

        mock_conn.close.assert_called_once()

    def test_closes_connection_on_success(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)

        mock_conn = self._make_mock_conn()
        with patch.object(db, "get_connection", return_value=mock_conn):
            with db.transaction():
                pass

        mock_conn.close.assert_called_once()

    def test_re_raises_original_exception(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)

        mock_conn = self._make_mock_conn()

        class CustomError(Exception):
            pass

        with patch.object(db, "get_connection", return_value=mock_conn):
            with pytest.raises(CustomError):
                with db.transaction():
                    raise CustomError("original")


# ── health_check ──────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_returns_connected_true_on_success(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)

        mock_conn = MagicMock()
        with patch.object(db, "get_connection", return_value=mock_conn):
            result = db.health_check()

        assert result == {"connected": True, "error": None}

    def test_returns_connected_false_on_error(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)

        with patch.object(db, "get_connection", side_effect=RuntimeError("no db")):
            result = db.health_check()

        assert result["connected"] is False
        assert "no db" in result["error"]

    def test_executes_select_1(self, monkeypatch):
        import db
        monkeypatch.setattr(db, "IS_DESKTOP", False)

        mock_conn = MagicMock()
        with patch.object(db, "get_connection", return_value=mock_conn):
            db.health_check()

        mock_conn.execute.assert_called_once_with("SELECT 1")


# ── live DB integration (issue 003): RLS claims + admin bypass ────────────────
# These run only when DATABASE_URL points at a live Supabase project; they skip
# cleanly otherwise, matching tests/test_migrations.py::TestIntegration and the
# RLS isolation suite, so CI without a DB stays green.

import uuid  # noqa: E402

_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


@pytest.mark.skipif(
    not _DATABASE_URL,
    reason="DATABASE_URL not set; db integration tests require a live Supabase project",
)
class TestDbIntegration:
    """Exercises the real claims/admin transaction helpers against staging."""

    def _db(self):
        # Import db in server mode so IS_DESKTOP is False for these tests.
        with patch.dict(os.environ, {"APP_MODE": "server"}):
            import importlib
            import db as _dbmod
            importlib.reload(_dbmod)
            return _dbmod

    def test_health_check_connects(self):
        db = self._db()
        with patch.object(db, "IS_DESKTOP", False):
            result = db.health_check()
        assert result["connected"] is True, result

    def test_transaction_sets_auth_uid(self):
        db = self._db()
        user_id = str(uuid.uuid4())
        with patch.object(db, "IS_DESKTOP", False):
            with db.transaction({"sub": user_id}) as conn:
                got = conn.execute("select (select auth.uid())::text").fetchone()[0]
        assert got == user_id, f"auth.uid() should be {user_id}, got {got}"

    def test_admin_transaction_bypasses_rls(self):
        db = self._db()
        ws_name = f"db_admin_test_{uuid.uuid4().hex}"
        with patch.object(db, "IS_DESKTOP", False):
            # As admin (no claims, no role switch): create + read a workspace row
            # without being a member — only possible if RLS is bypassed.
            with db.admin_transaction() as conn:
                ws_id = conn.execute(
                    "insert into public.workspaces (id, name) values (gen_random_uuid(), %s) returning id",
                    (ws_name,),
                ).fetchone()[0]
                claims = conn.execute(
                    "select current_setting('request.jwt.claims', true)"
                ).fetchone()[0]
                visible = conn.execute(
                    "select count(*) from public.workspaces where id = %s", (ws_id,)
                ).fetchone()[0]
                # cleanup within the same tx
                conn.execute("delete from public.workspaces where id = %s", (ws_id,))
        # Supabase seeds request.jwt.claims with an empty-string default, so an
        # unset claim reads back as None or '' — either means the admin path set
        # no JWT claims (it must not).
        assert not claims, f"admin path must not set request.jwt.claims, got {claims!r}"
        assert visible == 1, "admin path must see the row it inserted (RLS bypassed)"
