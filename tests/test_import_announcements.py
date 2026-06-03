"""
tests/test_import_announcements.py — Unit tests for migrations/import_announcements.py.

All Postgres interactions are mocked; no live database required.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

# The module under test lives in migrations/; add that to the path too.
sys.path.insert(0, str(Path(__file__).parent.parent / "migrations"))

from import_announcements import import_announcements_from_json, _parse_announcement

# Reuse the same namespace as the module for consistency checks.
_ANN_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def announcements_file(tmp_path):
    """Return a factory that writes a list of announcements to a temp JSON file."""
    def _make(announcements: list) -> Path:
        p = tmp_path / "announcements.json"
        p.write_text(json.dumps(announcements), encoding="utf-8")
        return p
    return _make


def _mock_transaction(inserted_rows: list[bool]):
    """Build a mock ``transaction()`` context manager.

    *inserted_rows* is a list of booleans (one per announcement): True means
    INSERT succeeded (rowcount=1), False means ON CONFLICT DO NOTHING (rowcount=0).
    """
    call_index = [0]

    def side_effect(sql, params=None):
        cursor = MagicMock()
        idx = call_index[0]
        cursor.rowcount = 1 if (idx < len(inserted_rows) and inserted_rows[idx]) else 0
        call_index[0] += 1
        return cursor

    conn = MagicMock()
    conn.execute.side_effect = side_effect

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, conn


# ---------------------------------------------------------------------------
# Happy-path: three normal announcements → all imported
# ---------------------------------------------------------------------------

class TestImportThreeNormalAnnouncements:
    ANNOUNCEMENTS = [
        {
            "id": str(uuid.uuid4()),
            "title": "VBS Registration Open",
            "body": "Sign up online at example.com",
            "url": "https://example.com/vbs",
            "ordering": 0,
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Potluck Sunday",
            "body": "Bring a dish to share after service.",
            "url": "",
            "ordering": 1,
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Youth Group Retreat",
            "body": "Registration deadline is May 20.",
            "ordering": 2,
        },
    ]

    def test_returns_three_imported(self, announcements_file):
        path = announcements_file(self.ANNOUNCEMENTS)
        ctx, conn = _mock_transaction([True, True, True])

        with patch("import_announcements.transaction", return_value=ctx):
            result = import_announcements_from_json(str(path))

        assert result["imported"] == 3
        assert result["skipped"] == 0
        assert result["errors"] == []
        assert result["dry_run"] is False

    def test_upsert_called_for_each_announcement(self, announcements_file):
        path = announcements_file(self.ANNOUNCEMENTS)
        ctx, conn = _mock_transaction([True, True, True])

        with patch("import_announcements.transaction", return_value=ctx):
            import_announcements_from_json(str(path))

        assert conn.execute.call_count == 3

    def test_conflict_do_nothing_in_sql(self, announcements_file):
        """The INSERT SQL must include ON CONFLICT (id) DO NOTHING."""
        path = announcements_file(self.ANNOUNCEMENTS[:1])
        ctx, conn = _mock_transaction([True])

        with patch("import_announcements.transaction", return_value=ctx):
            import_announcements_from_json(str(path))

        upsert_sql = conn.execute.call_args_list[0].args[0]
        assert "ON CONFLICT" in upsert_sql
        assert "DO NOTHING" in upsert_sql


# ---------------------------------------------------------------------------
# Empty array → 0 imported, no error
# ---------------------------------------------------------------------------

class TestEmptyArray:
    def test_empty_array_returns_zero_counts(self, announcements_file):
        path = announcements_file([])
        ctx, conn = _mock_transaction([])

        with patch("import_announcements.transaction", return_value=ctx):
            result = import_announcements_from_json(str(path))

        assert result["imported"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_empty_array_no_db_calls(self, announcements_file):
        path = announcements_file([])
        ctx, conn = _mock_transaction([])

        with patch("import_announcements.transaction", return_value=ctx):
            import_announcements_from_json(str(path))

        conn.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Missing optional fields (no url, no id) → handled gracefully
# ---------------------------------------------------------------------------

class TestMissingOptionalFields:
    def test_missing_url_defaults_to_empty_string(self):
        row = _parse_announcement({"title": "Hello", "body": "World"}, 0)
        assert row["url"] == ""

    def test_missing_id_generates_stable_uuid_from_content(self):
        item = {"title": "Stable Title", "body": "Stable Body"}
        row1 = _parse_announcement(item, 0)
        row2 = _parse_announcement(item, 0)
        # Same content → same UUID every time.
        assert row1["id"] == row2["id"]
        # Must be a valid UUID.
        uuid.UUID(row1["id"])

    def test_missing_id_different_content_gives_different_uuid(self):
        row_a = _parse_announcement({"title": "A", "body": "B"}, 0)
        row_b = _parse_announcement({"title": "X", "body": "Y"}, 0)
        assert row_a["id"] != row_b["id"]

    def test_missing_ordering_uses_list_index(self):
        row = _parse_announcement({"title": "No Order"}, 5)
        assert row["ordering"] == 5

    def test_missing_body_defaults_to_empty_string(self):
        row = _parse_announcement({"title": "Title Only"}, 0)
        assert row["body"] == ""

    def test_missing_title_defaults_to_empty_string(self):
        row = _parse_announcement({}, 0)
        assert row["title"] == ""

    def test_import_succeeds_with_no_optional_fields(self, announcements_file):
        path = announcements_file([{"title": "Minimal"}])
        ctx, conn = _mock_transaction([True])

        with patch("import_announcements.transaction", return_value=ctx):
            result = import_announcements_from_json(str(path))

        assert result["imported"] == 1
        assert result["errors"] == []

    def test_non_uuid_id_generates_stable_uuid(self):
        """Legacy string ids (e.g. 'ann_001') produce a stable UUID v5."""
        row1 = _parse_announcement({"id": "ann_001", "title": "T"}, 0)
        row2 = _parse_announcement({"id": "ann_001", "title": "T"}, 0)
        assert row1["id"] == row2["id"]
        uuid.UUID(row1["id"])


# ---------------------------------------------------------------------------
# Re-run → 0 imported (ON CONFLICT DO NOTHING)
# ---------------------------------------------------------------------------

class TestRerun:
    ANNOUNCEMENT = {
        "id": str(uuid.uuid4()),
        "title": "Already Imported",
        "body": "This was imported before.",
    }

    def test_second_run_counts_as_skipped(self, announcements_file):
        path = announcements_file([self.ANNOUNCEMENT])
        # rowcount=0 simulates ON CONFLICT DO NOTHING
        ctx, conn = _mock_transaction([False])

        with patch("import_announcements.transaction", return_value=ctx):
            result = import_announcements_from_json(str(path))

        assert result["imported"] == 0
        assert result["skipped"] == 1
        assert result["errors"] == []

    def test_mixed_new_and_existing(self, announcements_file):
        """One new + one already-imported → imported=1, skipped=1."""
        announcements = [
            {"id": str(uuid.uuid4()), "title": "New"},
            {"id": str(uuid.uuid4()), "title": "Already There"},
        ]
        path = announcements_file(announcements)
        ctx, conn = _mock_transaction([True, False])

        with patch("import_announcements.transaction", return_value=ctx):
            result = import_announcements_from_json(str(path))

        assert result["imported"] == 1
        assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# dry_run=True → no DB writes
# ---------------------------------------------------------------------------

class TestDryRun:
    ANNOUNCEMENTS = [
        {"id": str(uuid.uuid4()), "title": "Alpha", "body": "Body A"},
        {"id": str(uuid.uuid4()), "title": "Beta", "body": "Body B"},
    ]

    def test_dry_run_returns_would_be_count(self, announcements_file):
        path = announcements_file(self.ANNOUNCEMENTS)

        with patch("import_announcements.transaction") as mock_tx:
            result = import_announcements_from_json(str(path), dry_run=True)
            mock_tx.assert_not_called()

        assert result["dry_run"] is True
        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_dry_run_does_not_open_transaction(self, announcements_file):
        path = announcements_file(self.ANNOUNCEMENTS)

        with patch("import_announcements.transaction") as mock_tx:
            import_announcements_from_json(str(path), dry_run=True)

        mock_tx.assert_not_called()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_missing_file_returns_zero_counts(self, tmp_path):
        result = import_announcements_from_json(str(tmp_path / "nonexistent.json"))
        assert result == {"imported": 0, "skipped": 0, "errors": [], "dry_run": False}

    def test_malformed_top_level_not_list(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"not": "a list"}', encoding="utf-8")

        result = import_announcements_from_json(str(bad))
        assert result["imported"] == 0
        assert len(result["errors"]) == 1
        assert "Expected a JSON array" in result["errors"][0]

    def test_invalid_json_file(self, tmp_path):
        bad = tmp_path / "corrupt.json"
        bad.write_text("not valid json {{", encoding="utf-8")

        result = import_announcements_from_json(str(bad))
        assert len(result["errors"]) == 1
        assert "Failed to read" in result["errors"][0]

    def test_malformed_item_skips_with_error(self, announcements_file):
        """A non-dict entry in the array records an error but doesn't abort."""
        announcements = [
            "not a dict",
            {"id": str(uuid.uuid4()), "title": "Valid"},
        ]
        path = announcements_file(announcements)
        ctx, conn = _mock_transaction([True])

        with patch("import_announcements.transaction", return_value=ctx):
            result = import_announcements_from_json(str(path))

        assert result["imported"] == 1
        assert len(result["errors"]) == 1
        assert "index 0" in result["errors"][0]

    def test_valid_uuid_id_preserved(self):
        """A well-formed UUID id is kept as-is."""
        ann_id = str(uuid.uuid4())
        row = _parse_announcement({"id": ann_id, "title": "T"}, 0)
        assert row["id"] == ann_id

    def test_ordering_explicit_value_preserved(self):
        row = _parse_announcement({"title": "T", "ordering": 42}, 0)
        assert row["ordering"] == 42
