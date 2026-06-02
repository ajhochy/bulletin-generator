"""
tests/test_migrations.py — Unit tests for migrations/runner.py and v001 schema.

No live PostgreSQL required — all DB calls are mocked/stubbed.

Integration test (requires a running Postgres instance):
    DATABASE_URL=postgresql://... APP_MODE=server pytest tests/test_migrations.py -m integration
"""

import os
import sys
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Helpers ───────────────────────────────────────────────────────────────────

def _reload_runner(app_mode="server"):
    """Reload migrations.runner with the given APP_MODE env var."""
    with patch.dict(os.environ, {"APP_MODE": app_mode}):
        import migrations.runner as runner
        importlib.reload(runner)
        # After reload IS_DESKTOP reflects the env at reload time
        return runner


def _patch_get_connection(runner, side_effect):
    """Return a patch context that replaces get_connection on the runner module."""
    return patch.object(runner, "get_connection", side_effect=side_effect)


def _mock_conn(applied_ids=None):
    """Return a mock psycopg3 connection that reports the given applied IDs."""
    conn = MagicMock()
    rows = [(mid,) for mid in (applied_ids or [])]
    conn.execute.return_value.fetchall.return_value = rows
    return conn


# ── v001 SQL completeness ──────────────────────────────────────────────────────

class TestV001Schema:
    """Verify that the v001 DDL mentions every expected table name."""

    EXPECTED_TABLES = [
        "users",
        "sessions",
        "org_settings",
        "user_settings",
        "projects",
        "project_revisions",
        "announcements",
        "songs",
        "templates",
        "fonts",
        "data_migrations",
    ]

    def setup_method(self):
        from migrations import v001_initial_schema
        importlib.reload(v001_initial_schema)
        self.sql = v001_initial_schema.SQL

    def test_sql_is_non_empty(self):
        assert self.sql.strip() != ""

    @pytest.mark.parametrize("table", EXPECTED_TABLES)
    def test_table_present_in_sql(self, table):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in self.sql, (
            f"Expected 'CREATE TABLE IF NOT EXISTS {table}' in v001 SQL"
        )

    def test_run_calls_execute(self):
        from migrations import v001_initial_schema
        importlib.reload(v001_initial_schema)
        conn = MagicMock()
        v001_initial_schema.run(conn)
        conn.execute.assert_called_once_with(v001_initial_schema.SQL)


# ── Runner: desktop mode guard ────────────────────────────────────────────────

class TestRunnerDesktopGuard:
    def test_noop_in_desktop_mode(self):
        runner = _reload_runner(app_mode="desktop")
        # Should return without doing anything (no DB import)
        runner.run_schema_migrations()  # must not raise


# ── Runner: bootstrap ─────────────────────────────────────────────────────────

class TestRunnerBootstrap:
    def test_bootstrap_creates_data_migrations_table(self):
        runner = _reload_runner()
        conn = MagicMock()
        runner._bootstrap(conn)
        conn.execute.assert_called_once()
        sql_arg = conn.execute.call_args[0][0]
        assert "data_migrations" in sql_arg
        assert "CREATE TABLE IF NOT EXISTS" in sql_arg
        conn.commit.assert_called_once()

    def test_applied_ids_returns_set(self):
        runner = _reload_runner()
        conn = _mock_conn(applied_ids=["v001_initial_schema", "v002_foo"])
        result = runner._applied_ids(conn)
        assert result == {"v001_initial_schema", "v002_foo"}

    def test_applied_ids_empty_when_no_rows(self):
        runner = _reload_runner()
        conn = _mock_conn(applied_ids=[])
        assert runner._applied_ids(conn) == set()

    def test_record_applied_inserts_id(self):
        runner = _reload_runner()
        conn = MagicMock()
        runner._record_applied(conn, "v001_initial_schema")
        conn.execute.assert_called_once()
        sql_arg = conn.execute.call_args[0][0]
        params = conn.execute.call_args[0][1]
        assert "INSERT INTO data_migrations" in sql_arg
        assert params == ("v001_initial_schema",)


# ── Runner: full run_schema_migrations flow ───────────────────────────────────

class TestRunSchemaMigrations:
    """
    Tests for run_schema_migrations() using mocked get_connection() so no live
    Postgres is required.
    """

    def _make_connections(self, *conns):
        """Return a side_effect callable that yields connections in order."""
        it = iter(conns)

        def fake_get_connection():
            return next(it)

        return fake_get_connection

    def test_all_pending_applied_on_fresh_db(self):
        """All migrations run when none are recorded yet."""
        runner = _reload_runner(app_mode="server")

        conn_bootstrap = MagicMock()
        conn_read = _mock_conn(applied_ids=[])
        conn_v001 = MagicMock()

        mock_module = MagicMock()

        with patch.object(runner, "MIGRATIONS", [("v001_initial_schema", mock_module)]):
            with patch.object(runner, "get_connection",
                              side_effect=self._make_connections(conn_bootstrap, conn_read, conn_v001)):
                runner.run_schema_migrations()

        mock_module.run.assert_called_once_with(conn_v001)
        conn_v001.commit.assert_called_once()

    def test_already_applied_migration_skipped(self):
        """Migrations already in data_migrations are not re-applied."""
        runner = _reload_runner(app_mode="server")

        conn_bootstrap = MagicMock()
        conn_read = _mock_conn(applied_ids=["v001_initial_schema"])

        mock_module = MagicMock()

        with patch.object(runner, "MIGRATIONS", [("v001_initial_schema", mock_module)]):
            with patch.object(runner, "get_connection",
                              side_effect=self._make_connections(conn_bootstrap, conn_read)):
                runner.run_schema_migrations()

        mock_module.run.assert_not_called()

    def test_failed_migration_raises_and_rolls_back(self):
        """A migration that raises should roll back and propagate RuntimeError."""
        runner = _reload_runner(app_mode="server")

        conn_bootstrap = MagicMock()
        conn_read = _mock_conn(applied_ids=[])
        conn_v001 = MagicMock()

        mock_module = MagicMock()
        mock_module.run.side_effect = Exception("syntax error near 'CREAT'")

        with patch.object(runner, "MIGRATIONS", [("v001_initial_schema", mock_module)]):
            with patch.object(runner, "get_connection",
                              side_effect=self._make_connections(conn_bootstrap, conn_read, conn_v001)):
                with pytest.raises(RuntimeError, match="v001_initial_schema"):
                    runner.run_schema_migrations()

        conn_v001.rollback.assert_called_once()
        conn_v001.commit.assert_not_called()

    def test_idempotent_second_run(self):
        """Second run with all migrations already applied does nothing."""
        runner = _reload_runner(app_mode="server")

        conn_bootstrap = MagicMock()
        conn_read = _mock_conn(applied_ids=["v001_initial_schema"])

        call_count = {"n": 0}
        original_side_effect = self._make_connections(conn_bootstrap, conn_read)

        def counting_get_connection():
            call_count["n"] += 1
            return original_side_effect()

        mock_module = MagicMock()

        with patch.object(runner, "MIGRATIONS", [("v001_initial_schema", mock_module)]):
            with patch.object(runner, "get_connection", side_effect=counting_get_connection):
                runner.run_schema_migrations()

        # Only 2 connections opened (bootstrap + read applied); none for migrations
        assert call_count["n"] == 2
        mock_module.run.assert_not_called()

    def test_record_applied_called_on_success(self):
        """After a successful migration, its ID is inserted into data_migrations."""
        runner = _reload_runner(app_mode="server")

        conn_bootstrap = MagicMock()
        conn_read = _mock_conn(applied_ids=[])
        conn_v001 = MagicMock()

        mock_module = MagicMock()

        with patch.object(runner, "MIGRATIONS", [("v001_initial_schema", mock_module)]):
            with patch.object(runner, "get_connection",
                              side_effect=self._make_connections(conn_bootstrap, conn_read, conn_v001)):
                runner.run_schema_migrations()

        # Find the INSERT INTO data_migrations call on conn_v001
        insert_calls = [
            c for c in conn_v001.execute.call_args_list
            if "INSERT INTO data_migrations" in str(c)
        ]
        assert len(insert_calls) == 1, "Expected exactly one INSERT INTO data_migrations"


# ── Integration marker (skipped unless --run-integration is passed) ────────────

@pytest.mark.integration
class TestIntegration:
    """
    Requires a live Postgres instance.

    Run with:
        DATABASE_URL=postgresql://... APP_MODE=server pytest tests/test_migrations.py -m integration
    """

    def test_fresh_db_creates_all_tables(self):
        from migrations.runner import run_schema_migrations
        import db

        run_schema_migrations()
        with db.transaction() as conn:
            rows = conn.execute(
                "SELECT id FROM data_migrations ORDER BY id"
            ).fetchall()
        ids = [r[0] for r in rows]
        assert "v001_initial_schema" in ids

    def test_second_run_is_idempotent(self):
        from migrations.runner import run_schema_migrations
        import db

        run_schema_migrations()  # first run
        run_schema_migrations()  # second run — must not raise

        with db.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM data_migrations WHERE id = 'v001_initial_schema'"
            ).fetchone()[0]
        assert count == 1
