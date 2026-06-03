"""
tests/test_import_projects.py — Unit tests for migrations/import_projects.py.

All Postgres interactions are mocked; no live database required.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

# The module under test lives in migrations/; add that to the path too.
sys.path.insert(0, str(Path(__file__).parent.parent / "migrations"))

from import_projects import import_projects_from_json, _parse_project


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def projects_file(tmp_path):
    """Return a factory that writes a list of projects to a temp JSON file."""
    def _make(projects: list) -> Path:
        p = tmp_path / "projects.json"
        p.write_text(json.dumps(projects), encoding="utf-8")
        return p
    return _make


def _mock_transaction(inserted_rows: list[bool]):
    """Build a mock ``transaction()`` context manager.

    *inserted_rows* is a list of booleans (one per project): True means
    INSERT succeeded (rowcount=1), False means ON CONFLICT DO NOTHING (rowcount=0).
    """
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 1  # default; overridden per-call below

    # Each call to conn.execute() returns a cursor whose rowcount alternates
    # through *inserted_rows* for project upserts.
    call_index = [0]

    def side_effect(sql, params=None):
        cursor = MagicMock()
        # Revision inserts (INSERT INTO project_revisions) always succeed silently.
        if "project_revisions" in sql:
            cursor.rowcount = 1
            return cursor
        # Project upserts consume entries from inserted_rows in order.
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
# Happy-path: two normal projects → both imported
# ---------------------------------------------------------------------------

class TestImportTwoNormalProjects:
    PROJECTS = [
        {
            "id": str(uuid.uuid4()),
            "name": "Sunday Service",
            "createdAt": "2026-01-04T10:00:00.000Z",
            "updatedAt": "2026-01-04T11:00:00.000Z",
            "createdBy": "pastor@example.com",
            "updatedBy": "editor@example.com",
            "revision": 3,
            "state": {"items": []},
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Easter Service",
            "createdAt": "2026-03-15T09:00:00.000Z",
            "updatedAt": "2026-03-15T09:30:00.000Z",
            "revision": 1,
            "state": {"items": [{"type": "section", "title": "GATHERING"}]},
        },
    ]

    def test_returns_two_imported(self, projects_file):
        path = projects_file(self.PROJECTS)
        ctx, conn = _mock_transaction([True, True])

        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(path))

        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == []
        assert result["dry_run"] is False

    def test_upsert_called_for_each_project(self, projects_file):
        path = projects_file(self.PROJECTS)
        ctx, conn = _mock_transaction([True, True])

        with patch("import_projects.transaction", return_value=ctx):
            import_projects_from_json(str(path))

        # 2 project upserts + 2 revision inserts = 4 execute calls
        assert conn.execute.call_count == 4

    def test_revision_insert_called_for_each_imported_project(self, projects_file):
        path = projects_file(self.PROJECTS)
        ctx, conn = _mock_transaction([True, True])

        with patch("import_projects.transaction", return_value=ctx):
            import_projects_from_json(str(path))

        # Check that project_revisions was mentioned in at least 2 calls
        revision_calls = [
            c for c in conn.execute.call_args_list
            if "project_revisions" in c.args[0]
        ]
        assert len(revision_calls) == 2

    def test_imported_from_json_flag_in_sql(self, projects_file):
        """The INSERT SQL must include imported_from_json = TRUE."""
        path = projects_file(self.PROJECTS[:1])
        ctx, conn = _mock_transaction([True])

        with patch("import_projects.transaction", return_value=ctx):
            import_projects_from_json(str(path))

        # First execute call is the project upsert
        upsert_sql = conn.execute.call_args_list[0].args[0]
        assert "imported_from_json" in upsert_sql
        assert "TRUE" in upsert_sql

    def test_visibility_workspace_in_sql(self, projects_file):
        path = projects_file(self.PROJECTS[:1])
        ctx, conn = _mock_transaction([True])

        with patch("import_projects.transaction", return_value=ctx):
            import_projects_from_json(str(path))

        upsert_sql = conn.execute.call_args_list[0].args[0]
        assert "'workspace'" in upsert_sql


# ---------------------------------------------------------------------------
# Project missing `id` → UUID generated
# ---------------------------------------------------------------------------

class TestMissingId:
    PROJECT_NO_ID = {
        "name": "No-ID Project",
        "createdAt": "2026-01-01T00:00:00.000Z",
        "state": {},
    }

    def test_generates_uuid_when_id_missing(self):
        row = _parse_project(self.PROJECT_NO_ID, 0)
        assert "id" in row
        # Should be a valid UUID string
        parsed = uuid.UUID(row["id"])
        assert str(parsed) == row["id"]

    def test_import_succeeds_without_id(self, projects_file):
        path = projects_file([self.PROJECT_NO_ID])
        ctx, conn = _mock_transaction([True])

        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(path))

        assert result["imported"] == 1
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Re-run → skipped (ON CONFLICT DO NOTHING)
# ---------------------------------------------------------------------------

class TestRerun:
    PROJECT = {
        "id": str(uuid.uuid4()),
        "name": "Existing Project",
        "revision": 2,
    }

    def test_second_run_counts_as_skipped(self, projects_file):
        path = projects_file([self.PROJECT])
        # rowcount=0 simulates ON CONFLICT DO NOTHING
        ctx, conn = _mock_transaction([False])

        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(path))

        assert result["imported"] == 0
        assert result["skipped"] == 1
        assert result["errors"] == []

    def test_revision_not_inserted_when_skipped(self, projects_file):
        path = projects_file([self.PROJECT])
        ctx, conn = _mock_transaction([False])

        with patch("import_projects.transaction", return_value=ctx):
            import_projects_from_json(str(path))

        # Only the project upsert; no revision insert
        revision_calls = [
            c for c in conn.execute.call_args_list
            if "project_revisions" in c.args[0]
        ]
        assert len(revision_calls) == 0

    def test_mixed_new_and_existing(self, projects_file):
        """One new + one already-imported → imported=1, skipped=1."""
        projects = [
            {"id": str(uuid.uuid4()), "name": "New"},
            {"id": str(uuid.uuid4()), "name": "Already There"},
        ]
        path = projects_file(projects)
        ctx, conn = _mock_transaction([True, False])

        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(path))

        assert result["imported"] == 1
        assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# dry_run=True → no DB writes
# ---------------------------------------------------------------------------

class TestDryRun:
    PROJECTS = [
        {"id": str(uuid.uuid4()), "name": "Alpha"},
        {"id": str(uuid.uuid4()), "name": "Beta"},
    ]

    def test_dry_run_returns_would_be_count(self, projects_file):
        path = projects_file(self.PROJECTS)

        with patch("import_projects.transaction") as mock_tx:
            result = import_projects_from_json(str(path), dry_run=True)
            mock_tx.assert_not_called()

        assert result["dry_run"] is True
        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_dry_run_does_not_open_transaction(self, projects_file):
        path = projects_file(self.PROJECTS)

        with patch("import_projects.transaction") as mock_tx:
            import_projects_from_json(str(path), dry_run=True)

        mock_tx.assert_not_called()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_missing_file_returns_zero_counts(self, tmp_path):
        result = import_projects_from_json(str(tmp_path / "nonexistent.json"))
        assert result == {"imported": 0, "skipped": 0, "errors": [], "dry_run": False}

    def test_empty_array_returns_zero_counts(self, projects_file):
        path = projects_file([])
        ctx, conn = _mock_transaction([])

        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(path))

        assert result["imported"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_malformed_top_level_not_list(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"not": "a list"}', encoding="utf-8")

        result = import_projects_from_json(str(bad))
        assert result["imported"] == 0
        assert len(result["errors"]) == 1
        assert "Expected a JSON array" in result["errors"][0]

    def test_invalid_json_file(self, tmp_path):
        bad = tmp_path / "corrupt.json"
        bad.write_text("not valid json {{", encoding="utf-8")

        result = import_projects_from_json(str(bad))
        assert len(result["errors"]) == 1
        assert "Failed to read" in result["errors"][0]

    def test_malformed_item_skips_with_error(self, projects_file):
        """A non-dict entry in the array records an error but doesn't abort."""
        projects = [
            "not a dict",
            {"id": str(uuid.uuid4()), "name": "Valid"},
        ]
        path = projects_file(projects)
        ctx, conn = _mock_transaction([True])

        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(path))

        assert result["imported"] == 1
        assert len(result["errors"]) == 1
        assert "index 0" in result["errors"][0]

    def test_missing_optional_fields_uses_defaults(self):
        """Projects with only id should parse without error."""
        pid = str(uuid.uuid4())
        row = _parse_project({"id": pid}, 0)
        assert row["id"] == pid
        assert row["name"] == ""
        assert row["revision"] == 1
        assert row["created_by_email"] == ""
        assert row["updated_by_email"] == ""
        assert row["created_at"] is None
        assert row["updated_at"] is None

    def test_non_uuid_id_generates_stable_uuid(self):
        """Legacy string ids (e.g. 'proj_sunday') produce a stable UUID v5."""
        row1 = _parse_project({"id": "proj_sunday", "name": "Sunday"}, 0)
        row2 = _parse_project({"id": "proj_sunday", "name": "Sunday"}, 0)
        assert row1["id"] == row2["id"]
        # Must be a valid UUID
        uuid.UUID(row1["id"])

    def test_revision_defaults_to_one(self):
        row = _parse_project({"id": str(uuid.uuid4())}, 0)
        assert row["revision"] == 1

    def test_explicit_revision_preserved(self):
        row = _parse_project({"id": str(uuid.uuid4()), "revision": 7}, 0)
        assert row["revision"] == 7
