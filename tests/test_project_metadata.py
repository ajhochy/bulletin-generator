"""
tests/test_project_metadata.py — Tests for project owner/visibility metadata.

Covers:
  - _pg_row_to_project() surfaces all required metadata fields
  - PostgresStorageBackend.save_project() accepts updated_by_email / updated_by_user_id
  - Imported (imported_from_json=True) projects report visibility='workspace'
  - list_projects() and get_project() return metadata fields
  - JsonStorageBackend.save_project() accepts (and ignores) the attribution kwargs
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

import storage as storage_module
from storage import (
    JsonStorageBackend,
    PostgresStorageBackend,
    _pg_row_to_project,
)


# ---------------------------------------------------------------------------
# _pg_row_to_project — unit tests (no DB required)
# ---------------------------------------------------------------------------

class TestPgRowToProject:
    """Tests for _pg_row_to_project() in isolation."""

    def _make_row(self, **overrides):
        """Return a minimal DB row dict with sensible defaults."""
        uid = str(uuid.uuid4())
        owner_uid = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        row = {
            "id": uid,
            "name": "Sunday Service",
            "owner_user_id": owner_uid,
            "visibility": "private",
            "state": json.dumps({"id": uid, "name": "Sunday Service", "items": []}),
            "revision": 3,
            "created_at": now,
            "updated_at": now,
            "created_by_email": "alice@example.com",
            "updated_by_email": "bob@example.com",
            "imported_from_json": False,
        }
        row.update(overrides)
        return row

    def _call(self, row):
        """Call _pg_row_to_project with a mock for db.from_jsonb."""
        def fake_from_jsonb(value):
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return {}
            return value or {}

        with patch.dict("sys.modules", {"db": MagicMock(from_jsonb=fake_from_jsonb)}):
            return _pg_row_to_project(row)

    # ── Basic scalar fields ────────────────────────────────────────────────────

    def test_id_is_included(self):
        row = self._make_row()
        result = self._call(row)
        assert result["id"] == str(row["id"])

    def test_name_is_included(self):
        row = self._make_row(name="Easter Sunrise")
        result = self._call(row)
        assert result["name"] == "Easter Sunrise"

    def test_revision_is_included(self):
        row = self._make_row(revision=7)
        result = self._call(row)
        assert result["revision"] == 7

    # ── Ownership & visibility ─────────────────────────────────────────────────

    def test_visibility_private(self):
        row = self._make_row(visibility="private")
        result = self._call(row)
        assert result["visibility"] == "private"

    def test_visibility_workspace(self):
        row = self._make_row(visibility="workspace")
        result = self._call(row)
        assert result["visibility"] == "workspace"

    def test_owner_user_id_is_string_when_set(self):
        owner_uid = str(uuid.uuid4())
        row = self._make_row(owner_user_id=owner_uid)
        result = self._call(row)
        assert result["owner_user_id"] == owner_uid

    def test_owner_user_id_is_none_for_legacy_imports(self):
        row = self._make_row(owner_user_id=None)
        result = self._call(row)
        assert result["owner_user_id"] is None

    def test_owner_email_comes_from_created_by_email(self):
        row = self._make_row(created_by_email="alice@example.com")
        result = self._call(row)
        assert result["owner_email"] == "alice@example.com"

    def test_owner_email_is_none_when_created_by_email_empty(self):
        row = self._make_row(created_by_email="")
        result = self._call(row)
        assert result["owner_email"] is None

    def test_imported_from_json_true(self):
        row = self._make_row(imported_from_json=True, visibility="workspace")
        result = self._call(row)
        assert result["imported_from_json"] is True

    def test_imported_from_json_false(self):
        row = self._make_row(imported_from_json=False)
        result = self._call(row)
        assert result["imported_from_json"] is False

    # ── Timestamps & attribution ───────────────────────────────────────────────

    def test_created_at_is_iso_string(self):
        row = self._make_row()
        result = self._call(row)
        assert isinstance(result["created_at"], str)
        assert result["created_at"]  # non-empty

    def test_updated_at_is_iso_string(self):
        row = self._make_row()
        result = self._call(row)
        assert isinstance(result["updated_at"], str)
        assert result["updated_at"]  # non-empty

    def test_created_by_email_is_included(self):
        row = self._make_row(created_by_email="alice@example.com")
        result = self._call(row)
        assert result["created_by_email"] == "alice@example.com"

    def test_updated_by_email_is_included(self):
        row = self._make_row(updated_by_email="bob@example.com")
        result = self._call(row)
        assert result["updated_by_email"] == "bob@example.com"

    # ── camelCase backward-compat keys ────────────────────────────────────────

    def test_camel_case_created_at(self):
        row = self._make_row()
        result = self._call(row)
        assert "createdAt" in result

    def test_camel_case_updated_at(self):
        row = self._make_row()
        result = self._call(row)
        assert "updatedAt" in result

    def test_camel_case_created_by(self):
        row = self._make_row(created_by_email="alice@example.com")
        result = self._call(row)
        assert result.get("createdBy") == "alice@example.com"

    def test_camel_case_updated_by(self):
        row = self._make_row(updated_by_email="bob@example.com")
        result = self._call(row)
        assert result.get("updatedBy") == "bob@example.com"

    # ── Imported / legacy workspace project ───────────────────────────────────

    def test_imported_project_has_workspace_visibility(self):
        """Projects imported from JSON should report visibility='workspace'."""
        row = self._make_row(
            owner_user_id=None,
            imported_from_json=True,
            visibility="workspace",
            created_by_email="",
            updated_by_email="",
        )
        result = self._call(row)
        assert result["visibility"] == "workspace"
        assert result["owner_user_id"] is None
        assert result["imported_from_json"] is True


# ---------------------------------------------------------------------------
# PostgresStorageBackend.save_project() — mocked DB, attribution kwargs
# ---------------------------------------------------------------------------

def _make_pg_save_mock(returned_row: dict):
    """Return a mock transaction context manager that returns *returned_row* from RETURNING."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = tuple(returned_row.values())
    mock_cursor.description = [(col, None) for col in returned_row.keys()]

    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_cursor

    mock_tx = MagicMock()
    mock_tx.__enter__ = MagicMock(return_value=mock_conn)
    mock_tx.__exit__ = MagicMock(return_value=False)

    return mock_tx, mock_conn


class TestPostgresSaveProjectAttribution:
    """save_project() wires caller-supplied attribution into the SQL params."""

    def _saved_params(self, extra_kwargs=None):
        """Call save_project() with a mock DB; return the SQL params dict used."""
        project_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        returned_row = {
            "id": project_id,
            "name": "Test",
            "owner_user_id": None,
            "visibility": "private",
            "state": json.dumps({"id": project_id, "name": "Test"}),
            "revision": 1,
            "created_at": now,
            "updated_at": now,
            "created_by_email": "alice@example.com",
            "updated_by_email": "alice@example.com",
            "imported_from_json": False,
        }

        mock_tx, mock_conn = _make_pg_save_mock(returned_row)

        def fake_from_jsonb(value):
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return {}
            return value or {}

        mock_db = MagicMock()
        mock_db.transaction.return_value = mock_tx
        mock_db.from_jsonb = fake_from_jsonb

        with patch.dict("sys.modules", {"db": mock_db}):
            backend = PostgresStorageBackend()
            kwargs = extra_kwargs or {}
            backend.save_project({"id": project_id, "name": "Test"}, **kwargs)

        # Extract the params dict passed to conn.execute().
        call_args = mock_conn.execute.call_args
        return call_args[0][1]  # positional arg 1 = params dict

    def test_updated_by_email_from_kwarg(self):
        params = self._saved_params({"updated_by_email": "alice@example.com"})
        assert params["updated_by_email"] == "alice@example.com"

    def test_updated_by_email_empty_by_default(self):
        params = self._saved_params()
        assert params["updated_by_email"] == ""

    def test_owner_user_id_from_kwarg(self):
        owner_id = str(uuid.uuid4())
        params = self._saved_params({"updated_by_user_id": owner_id})
        assert params["owner_user_id"] == owner_id

    def test_owner_user_id_none_by_default(self):
        params = self._saved_params()
        assert params["owner_user_id"] is None

    def test_created_by_email_falls_back_to_updated_by_email(self):
        """When data has no createdBy, created_by_email should fall back to updated_by_email."""
        params = self._saved_params({"updated_by_email": "carol@example.com"})
        # created_by_email should be carol@example.com since data has no createdBy
        assert params["created_by_email"] == "carol@example.com"


# ---------------------------------------------------------------------------
# JsonStorageBackend.save_project() — attribution kwargs are accepted (no-op)
# ---------------------------------------------------------------------------

class TestJsonSaveProjectAttributionKwargs:
    def test_accepts_updated_by_email(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        project = {"id": "proj-1", "name": "Test"}
        # Should not raise
        result = backend.save_project(project, updated_by_email="alice@example.com")
        assert result["id"] == "proj-1"

    def test_accepts_updated_by_user_id(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        project = {"id": "proj-2", "name": "Test2"}
        uid = str(uuid.uuid4())
        result = backend.save_project(project, updated_by_user_id=uid)
        assert result["id"] == "proj-2"

    def test_accepts_both_kwargs(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        project = {"id": "proj-3", "name": "Test3"}
        uid = str(uuid.uuid4())
        result = backend.save_project(
            project,
            updated_by_email="alice@example.com",
            updated_by_user_id=uid,
        )
        assert result["id"] == "proj-3"


# ---------------------------------------------------------------------------
# list_projects() metadata shape (mocked Postgres)
# ---------------------------------------------------------------------------

class TestListProjectsMetadata:
    """list_projects() returns dicts that include visibility, owner_email, revision."""

    def _list_via_mock(self, rows):
        """Call list_projects() with mocked DB returning *rows*."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [tuple(r.values()) for r in rows]
        mock_cursor.description = [(col, None) for col in rows[0].keys()] if rows else []

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_cursor

        mock_tx = MagicMock()
        mock_tx.__enter__ = MagicMock(return_value=mock_conn)
        mock_tx.__exit__ = MagicMock(return_value=False)

        def fake_from_jsonb(value):
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return {}
            return value or {}

        mock_db = MagicMock()
        mock_db.transaction.return_value = mock_tx
        mock_db.from_jsonb = fake_from_jsonb

        with patch.dict("sys.modules", {"db": mock_db}):
            backend = PostgresStorageBackend()
            return backend.list_projects()

    def _make_db_row(self, **overrides):
        uid = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        row = {
            "id": uid,
            "name": "Sunday Service",
            "owner_user_id": str(uuid.uuid4()),
            "visibility": "private",
            "state": json.dumps({"id": uid, "name": "Sunday Service"}),
            "revision": 1,
            "created_at": now,
            "updated_at": now,
            "created_by_email": "alice@example.com",
            "updated_by_email": "alice@example.com",
            "imported_from_json": False,
        }
        row.update(overrides)
        return row

    def test_list_includes_visibility(self):
        rows = [self._make_db_row(visibility="private")]
        result = self._list_via_mock(rows)
        assert result[0]["visibility"] == "private"

    def test_list_includes_owner_email(self):
        rows = [self._make_db_row(created_by_email="alice@example.com")]
        result = self._list_via_mock(rows)
        assert result[0]["owner_email"] == "alice@example.com"

    def test_list_includes_revision(self):
        rows = [self._make_db_row(revision=5)]
        result = self._list_via_mock(rows)
        assert result[0]["revision"] == 5

    def test_list_includes_imported_from_json(self):
        rows = [self._make_db_row(imported_from_json=True, visibility="workspace")]
        result = self._list_via_mock(rows)
        assert result[0]["imported_from_json"] is True

    def test_list_legacy_import_has_null_owner_user_id(self):
        rows = [self._make_db_row(owner_user_id=None, imported_from_json=True, visibility="workspace")]
        result = self._list_via_mock(rows)
        assert result[0]["owner_user_id"] is None

    def test_list_includes_updated_by_email(self):
        rows = [self._make_db_row(updated_by_email="bob@example.com")]
        result = self._list_via_mock(rows)
        assert result[0]["updated_by_email"] == "bob@example.com"
