"""
tests/test_import_settings.py — Unit tests for migrations/import_settings.py.

All Postgres interactions are mocked; no live database required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))
# The module under test lives in migrations/
sys.path.insert(0, str(Path(__file__).parent.parent / "migrations"))

from import_settings import (
    import_settings_from_json,
    ORG_KEYS,
    OAUTH_KEYS,
    USER_KEYS,
    _upsert_org_setting,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

#: A fixture dict containing every known settings key.
ALL_SETTINGS: dict = {
    # Org keys
    "churchName": "Grace Church",
    "staffData": [{"name": "Pastor Bob", "role": "Pastor", "email": "bob@example.org"}],
    "servingTeamFilter": "Worship Team",
    "typeFormats": {"song": {"titleBold": True}},
    "docTemplate": "standard",
    "giveOnlineUrl": "https://example.org/give",
    "calUrls": ["https://example.org/cal.ics"],
    "calExclude": ["Holiday"],
    "googleDriveFolderId": "1AbCdEfGhIj",
    # OAuth tokens (bundled into org_settings["oauth_tokens"])
    "pcoAccessToken": "pco-access-111",
    "pcoRefreshToken": "pco-refresh-222",
    "googleAccessToken": "google-access-333",
    "googleRefreshToken": "google-refresh-444",
    # User-level keys (not written in this release)
    "editorDisplayName": "Alice",
}


@pytest.fixture
def settings_file(tmp_path):
    """Return a factory that writes a settings dict to a temp JSON file."""
    def _make(data: dict) -> Path:
        p = tmp_path / "settings.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p
    return _make


def _make_mock_transaction(insert_results: list[bool] | None = None):
    """Return a (ctx, conn) pair where conn.execute() returns mocked cursors.

    *insert_results* controls the rowcount sequence for successive execute() calls.
    If None, all inserts return rowcount=1 (success).
    """
    results = insert_results or []
    call_index = [0]

    def execute_side_effect(sql, params=None):
        cursor = MagicMock()
        idx = call_index[0]
        if idx < len(results):
            cursor.rowcount = 1 if results[idx] else 0
        else:
            cursor.rowcount = 1  # default: success
        call_index[0] += 1
        return cursor

    conn = MagicMock()
    conn.execute.side_effect = execute_side_effect

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, conn


# ---------------------------------------------------------------------------
# Full fixture: all known keys present → correct counts
# ---------------------------------------------------------------------------

class TestAllKeys:
    """Import a settings dict that contains every known key."""

    def test_all_org_keys_imported(self, settings_file):
        path = settings_file(ALL_SETTINGS)
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(path))

        # ORG_KEYS (9) + 1 oauth_tokens bundle = 10 org rows written
        assert result["org_keys_imported"] == len(ORG_KEYS) + 1  # +1 for oauth bundle

    def test_user_keys_not_written(self, settings_file):
        """User keys are counted but not written in this release."""
        path = settings_file(ALL_SETTINGS)
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(path))

        assert result["user_keys_imported"] == 0

    def test_no_errors(self, settings_file):
        path = settings_file(ALL_SETTINGS)
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(path))

        assert result["skipped"] == 0
        assert result["dry_run"] is False

    def test_execute_called_for_each_org_row(self, settings_file):
        """One execute() call per org key + one for the oauth_tokens bundle."""
        path = settings_file(ALL_SETTINGS)
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            import_settings_from_json(str(path))

        expected_calls = len(ORG_KEYS) + 1  # +1 for oauth bundle
        assert conn.execute.call_count == expected_calls

    def test_oauth_tokens_bundled_under_single_key(self, settings_file):
        """All four OAuth tokens appear inside a single 'oauth_tokens' DB row."""
        path = settings_file(ALL_SETTINGS)
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            import_settings_from_json(str(path))

        # Find the call where key='oauth_tokens'
        oauth_calls = [
            c for c in conn.execute.call_args_list
            if "oauth_tokens" in str(c.args[1] if c.args else c.kwargs)
        ]
        assert len(oauth_calls) == 1

        # The value parameter should contain all four token keys
        call_params = oauth_calls[0].args[1]  # positional param dict
        value_str = call_params["value"]
        bundle = json.loads(value_str)
        for token_key in OAUTH_KEYS:
            assert token_key in bundle


# ---------------------------------------------------------------------------
# Idempotency: re-run → ON CONFLICT DO NOTHING → skipped
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Re-running the import should produce skipped=N, org_keys_imported=0."""

    def test_all_skipped_on_rerun(self, settings_file):
        path = settings_file(ALL_SETTINGS)
        n_rows = len(ORG_KEYS) + 1  # +1 for oauth bundle
        # All rowcount=0 simulates ON CONFLICT DO NOTHING
        ctx, conn = _make_mock_transaction([False] * n_rows)

        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(path))

        assert result["org_keys_imported"] == 0
        assert result["skipped"] == n_rows

    def test_mixed_new_and_existing(self, settings_file):
        """One key already exists; rest are new."""
        path = settings_file(ALL_SETTINGS)
        n_rows = len(ORG_KEYS) + 1
        # First row skipped (already exists), rest imported
        results = [False] + [True] * (n_rows - 1)
        ctx, conn = _make_mock_transaction(results)

        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(path))

        assert result["org_keys_imported"] == n_rows - 1
        assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# Dry run: no DB writes
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_no_transaction_opened(self, settings_file):
        path = settings_file(ALL_SETTINGS)

        with patch("import_settings.transaction") as mock_tx:
            result = import_settings_from_json(str(path), dry_run=True)
            mock_tx.assert_not_called()

        assert result["dry_run"] is True

    def test_dry_run_returns_would_be_counts(self, settings_file):
        path = settings_file(ALL_SETTINGS)

        with patch("import_settings.transaction") as mock_tx:
            result = import_settings_from_json(str(path), dry_run=True)

        expected_org = len(ORG_KEYS) + 1  # +1 for oauth bundle
        assert result["org_keys_imported"] == expected_org
        # User keys counted in dry run too
        assert result["user_keys_imported"] == len(USER_KEYS)

    def test_dry_run_empty_settings(self, settings_file):
        path = settings_file({})

        with patch("import_settings.transaction") as mock_tx:
            result = import_settings_from_json(str(path), dry_run=True)
            mock_tx.assert_not_called()

        assert result["org_keys_imported"] == 0
        assert result["user_keys_imported"] == 0


# ---------------------------------------------------------------------------
# Missing / partial keys
# ---------------------------------------------------------------------------

class TestMissingOptionalKeys:
    def test_empty_settings_no_error(self, settings_file):
        path = settings_file({})
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(path))

        assert result["org_keys_imported"] == 0
        assert result["skipped"] == 0
        assert result["user_keys_imported"] == 0

    def test_only_church_name(self, settings_file):
        path = settings_file({"churchName": "Hope Church"})
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(path))

        assert result["org_keys_imported"] == 1
        assert result["skipped"] == 0

    def test_partial_oauth_tokens(self, settings_file):
        """Only some OAuth tokens present → they still go into oauth_tokens bundle."""
        path = settings_file({"pcoAccessToken": "abc", "pcoRefreshToken": "def"})
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(path))

        # Only one row: oauth_tokens bundle
        assert result["org_keys_imported"] == 1

    def test_only_user_keys_no_db_writes(self, settings_file):
        """Only user-level keys → nothing written to DB."""
        path = settings_file({"editorDisplayName": "Bob"})
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(path))

        assert result["org_keys_imported"] == 0
        assert conn.execute.call_count == 0

    def test_missing_file_returns_zero_counts(self, tmp_path):
        result = import_settings_from_json(str(tmp_path / "nonexistent.json"))
        assert result == {
            "org_keys_imported": 0,
            "user_keys_imported": 0,
            "skipped": 0,
            "dry_run": False,
        }

    def test_unknown_keys_ignored(self, settings_file):
        """Keys not in ORG_KEYS / OAUTH_KEYS / USER_KEYS are silently ignored."""
        path = settings_file({"churchName": "Zion", "unknownKey": "value", "anotherUnknown": 42})
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(path))

        assert result["org_keys_imported"] == 1  # only churchName


# ---------------------------------------------------------------------------
# SQL correctness: ON CONFLICT DO NOTHING clause
# ---------------------------------------------------------------------------

class TestSqlCorrectness:
    def test_on_conflict_do_nothing_in_sql(self, settings_file):
        path = settings_file({"churchName": "Grace"})
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            import_settings_from_json(str(path))

        executed_sql = conn.execute.call_args_list[0].args[0]
        assert "ON CONFLICT" in executed_sql
        assert "DO NOTHING" in executed_sql

    def test_key_passed_as_param(self, settings_file):
        path = settings_file({"churchName": "Grace"})
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            import_settings_from_json(str(path))

        params = conn.execute.call_args_list[0].args[1]
        assert params["key"] == "churchName"

    def test_value_serialised_as_json(self, settings_file):
        path = settings_file({"staffData": [{"name": "Jane"}]})
        ctx, conn = _make_mock_transaction()

        with patch("import_settings.transaction", return_value=ctx):
            import_settings_from_json(str(path))

        params = conn.execute.call_args_list[0].args[1]
        # value must be a JSON string (for ::jsonb cast)
        parsed = json.loads(params["value"])
        assert parsed == [{"name": "Jane"}]


# ---------------------------------------------------------------------------
# _upsert_org_setting unit test
# ---------------------------------------------------------------------------

class TestUpsertOrgSetting:
    def test_returns_true_on_insert(self):
        cursor = MagicMock()
        cursor.rowcount = 1
        conn = MagicMock()
        conn.execute.return_value = cursor

        result = _upsert_org_setting(conn, "churchName", "Grace")
        assert result is True

    def test_returns_false_on_conflict(self):
        cursor = MagicMock()
        cursor.rowcount = 0
        conn = MagicMock()
        conn.execute.return_value = cursor

        result = _upsert_org_setting(conn, "churchName", "Grace")
        assert result is False

    def test_sql_contains_org_settings_table(self):
        cursor = MagicMock()
        cursor.rowcount = 1
        conn = MagicMock()
        conn.execute.return_value = cursor

        _upsert_org_setting(conn, "giveOnlineUrl", "https://example.org/give")
        executed_sql = conn.execute.call_args.args[0]
        assert "org_settings" in executed_sql


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_invalid_json_raises_value_error(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json {{", encoding="utf-8")

        with pytest.raises(ValueError, match="Failed to read"):
            import_settings_from_json(str(bad))

    def test_non_object_json_raises_value_error(self, tmp_path):
        bad = tmp_path / "array.json"
        bad.write_text('["not", "an", "object"]', encoding="utf-8")

        with pytest.raises(ValueError, match="Expected a JSON object"):
            import_settings_from_json(str(bad))
