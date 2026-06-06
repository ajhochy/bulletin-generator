"""
tests/test_revision_snapshots.py — Project revision snapshot tests.

Covers:
  storage.py — PostgresStorageBackend.save_project_transactional():
    - Inserts exactly one project_revisions row per save.
    - Snapshot contains all required fields.
    - Two saves produce two distinct revision rows.

  storage.py — PostgresStorageBackend.get_project_revisions():
    - Returns list of revision metadata dicts, DESC by revision.
    - Does not include state in the returned dicts.

  storage.py — PostgresStorageBackend.get_project_revision():
    - Returns full dict including state for a specific revision.
    - Returns None when revision not found.

  storage.py — JsonStorageBackend / StorageBackend stubs:
    - get_project_revisions() returns [].
    - get_project_revision() returns None.

  migrations/import_projects.py:
    - _insert_revision() creates an initial revision row for each imported project.
    - Revision row uses summary='Imported from projects.json'.
"""

from __future__ import annotations

import json
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Project root on sys.path ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "migrations"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALICE_USER_ID = str(uuid.uuid4())


def _pg_project_row(project_id: str, revision: int) -> dict:
    """Build a minimal Postgres row dict for a project RETURNING clause.

    Uses the NEW multi-tenant schema column names (issue 004 / #260):
    created_by_user_id / updated_by_user_id instead of created_by_email etc.,
    id is TEXT (not UUID), workspace_id present.

    Non-None user IDs are used so _pg_enrich_project_row() issues a profiles
    query (the 3rd execute() call), giving 4 total calls in save_project_transactional.
    """
    return {
        "id": project_id,  # TEXT PK in new schema
        "name": "Sunday Service",
        "owner_user_id": None,
        "visibility": "workspace",
        "state": json.dumps({"id": project_id, "name": "Sunday Service"}),
        "revision": revision,
        "created_at": None,
        "updated_at": None,
        "created_by_user_id": _ALICE_USER_ID,  # non-None so enrichment query fires
        "updated_by_user_id": _ALICE_USER_ID,
        "workspace_id": None,
    }


def _make_update_cursor(row_dict: dict | None):
    """Return a mock cursor for the UPDATE ... RETURNING result."""
    cursor = MagicMock()
    if row_dict is not None:
        cursor.fetchone.return_value = tuple(row_dict.values())
        cursor.description = [(k,) for k in row_dict]
    else:
        cursor.fetchone.return_value = None
        cursor.description = []
    return cursor


def _make_prev_state_cursor(project_id: str):
    """Return a mock cursor for the prev-state SELECT before the UPDATE."""
    cursor = MagicMock()
    prev_state_json = json.dumps({"id": project_id, "name": "Sunday Service"})
    cursor.fetchone.return_value = (prev_state_json,)
    return cursor


def _make_profiles_cursor():
    """Return a mock cursor for the profiles enrichment SELECT (after RETURNING).

    _pg_enrich_project_row() SELECTs from public.profiles to get attribution
    emails.  In tests there are no real users so return an empty result.
    """
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    return cursor


def _make_conn_for_save(project_row: dict):
    """Build a mock connection for a successful save_project_transactional call.

    execute() is called four times in order (new multi-tenant schema, issue 004):
      1. SELECT state FROM projects  (fetch prev state for summary generation)
      2. UPDATE projects ... RETURNING  (the main transactional save)
      3. SELECT ... FROM public.profiles  (_pg_enrich_project_row attribution lookup)
      4. INSERT INTO project_revisions  (revision snapshot)
    """
    conn = MagicMock()
    project_id = str(project_row.get("id", ""))
    prev_cursor = _make_prev_state_cursor(project_id)
    update_cursor = _make_update_cursor(project_row)
    profiles_cursor = _make_profiles_cursor()
    snapshot_cursor = MagicMock()
    snapshot_cursor.rowcount = 1
    conn.execute.side_effect = [prev_cursor, update_cursor, profiles_cursor, snapshot_cursor]
    return conn


@contextmanager
def _fake_tx(conn):
    yield conn


# =============================================================================
# save_project_transactional — revision snapshot fields
# =============================================================================

class TestSaveProjectTransactionalRevisionSnapshot:
    """Verify the project_revisions INSERT has all required fields."""

    _PROJECT_ID = str(uuid.uuid4())

    def test_snapshot_inserted_exactly_once_per_save(self):
        """A single successful save must insert exactly one revision row."""
        from storage import PostgresStorageBackend

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        project_row = _pg_project_row(self._PROJECT_ID, revision=2)
        conn = _make_conn_for_save(project_row)

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            backend.save_project_transactional(
                project_data,
                client_revision=1,
                updated_by_email="alice@example.com",
                updated_by_user_id=None,
                updated_by_name="Alice",
            )

        # Four execute calls: SELECT prev state + UPDATE project +
        # SELECT profiles (enrichment) + INSERT project_revisions
        assert conn.execute.call_count == 4
        snapshot_sql = conn.execute.call_args_list[3][0][0]
        assert "project_revisions" in snapshot_sql

    def test_snapshot_includes_uuid_id(self):
        """Snapshot INSERT params must include a valid UUID for ``id``."""
        from storage import PostgresStorageBackend

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        project_row = _pg_project_row(self._PROJECT_ID, revision=3)
        conn = _make_conn_for_save(project_row)

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            backend.save_project_transactional(
                project_data,
                client_revision=2,
                updated_by_email="alice@example.com",
            )

        # Call index 3: INSERT project_revisions (after SELECT prev + UPDATE + SELECT profiles)
        params = conn.execute.call_args_list[3][0][1]
        snap_id = params["snap_id"]
        # Must be parseable as a UUID
        uuid.UUID(snap_id)

    def test_snapshot_includes_project_id(self):
        from storage import PostgresStorageBackend

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        project_row = _pg_project_row(self._PROJECT_ID, revision=4)
        conn = _make_conn_for_save(project_row)

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            backend.save_project_transactional(
                project_data, client_revision=3, updated_by_email="x@example.com"
            )

        params = conn.execute.call_args_list[3][0][1]
        assert params["project_id"] == self._PROJECT_ID

    def test_snapshot_uses_new_incremented_revision(self):
        """The snapshot revision_number must match the DB-returned (incremented) revision."""
        from storage import PostgresStorageBackend

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        project_row = _pg_project_row(self._PROJECT_ID, revision=7)
        conn = _make_conn_for_save(project_row)

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            backend.save_project_transactional(
                project_data, client_revision=6, updated_by_email="bob@example.com"
            )

        # New schema: column is revision_number (not revision)
        params = conn.execute.call_args_list[3][0][1]
        assert params["revision_number"] == 7  # new revision, not client's 6

    def test_snapshot_includes_full_state_json(self):
        """The state param must be the full JSON-serialised project."""
        from storage import PostgresStorageBackend

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service", "items": [1, 2]}
        project_row = _pg_project_row(self._PROJECT_ID, revision=2)
        conn = _make_conn_for_save(project_row)

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            backend.save_project_transactional(
                project_data, client_revision=1, updated_by_email="c@example.com"
            )

        params = conn.execute.call_args_list[3][0][1]
        state = json.loads(params["state"])
        assert state["id"] == self._PROJECT_ID
        assert state["items"] == [1, 2]

    def test_snapshot_includes_created_by_user_id(self):
        """Snapshot INSERT params use created_by_user_id (new schema, issue 004).

        The new project_revisions schema has no saved_by_email / saved_by_name
        columns; attribution is via created_by_user_id FK → profiles.
        """
        from storage import PostgresStorageBackend

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        project_row = _pg_project_row(self._PROJECT_ID, revision=5)
        conn = _make_conn_for_save(project_row)
        user_id = str(uuid.uuid4())

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            backend.save_project_transactional(
                project_data,
                client_revision=4,
                updated_by_user_id=user_id,
                updated_by_name="Carol",
            )

        # New schema: created_by_user_id (not saved_by_email / saved_by_name)
        params = conn.execute.call_args_list[3][0][1]
        assert params["created_by_user_id"] == user_id

    def test_snapshot_summary_is_non_empty_string(self):
        """The summary parameter must be a non-empty string (generated by revisions.py)."""
        from storage import PostgresStorageBackend

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        project_row = _pg_project_row(self._PROJECT_ID, revision=2)
        conn = _make_conn_for_save(project_row)

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)), \
             patch("db.from_jsonb", side_effect=lambda v: json.loads(v) if isinstance(v, str) else v):
            backend.save_project_transactional(
                project_data, client_revision=1, updated_by_email="d@example.com"
            )

        # Summary is passed as a parameter in the snapshot INSERT (4th call, index 3).
        params = conn.execute.call_args_list[3][0][1]
        summary = params["summary"]
        assert isinstance(summary, str)
        assert summary  # non-empty
        assert len(summary) <= 200

    def test_two_saves_produce_two_distinct_revision_rows(self):
        """Each save call must produce exactly one revision INSERT."""
        from storage import PostgresStorageBackend

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}

        # First save: client=1 → DB revision=2
        row1 = _pg_project_row(self._PROJECT_ID, revision=2)
        conn1 = _make_conn_for_save(row1)

        # Second save: client=2 → DB revision=3
        row2 = _pg_project_row(self._PROJECT_ID, revision=3)
        conn2 = _make_conn_for_save(row2)

        backend = PostgresStorageBackend()

        with patch("db.transaction", lambda claims=None: _fake_tx(conn1)):
            backend.save_project_transactional(
                project_data, client_revision=1, updated_by_email="a@example.com"
            )

        with patch("db.transaction", lambda claims=None: _fake_tx(conn2)):
            backend.save_project_transactional(
                project_data, client_revision=2, updated_by_email="a@example.com"
            )

        # Each connection should see exactly 4 execute calls:
        # SELECT prev state + UPDATE project + SELECT profiles + INSERT project_revisions.
        assert conn1.execute.call_count == 4
        assert conn2.execute.call_count == 4

        # New schema: revision_number (not revision) in project_revisions INSERT
        rev1 = conn1.execute.call_args_list[3][0][1]["revision_number"]
        rev2 = conn2.execute.call_args_list[3][0][1]["revision_number"]
        assert rev1 == 2
        assert rev2 == 3
        assert rev1 != rev2


# =============================================================================
# get_project_revisions
# =============================================================================

class TestGetProjectRevisions:
    _PROJECT_ID = str(uuid.uuid4())

    def _make_revisions_cursor(self, rows: list[dict]):
        """Return a mock cursor for the revisions SELECT.

        New schema (issue 004): column is revision_number (not revision),
        created_at (not saved_at), created_by_user_id, saved_by_email and
        saved_by_name come from the profiles LEFT JOIN.
        """
        if not rows:
            cursor = MagicMock()
            cursor.fetchall.return_value = []
            cursor.description = [
                ("id",), ("project_id",), ("revision_number",), ("summary",),
                ("created_at",), ("created_by_user_id",),
                ("saved_by_email",), ("saved_by_name",),
            ]
            return cursor

        cols = list(rows[0].keys())
        cursor = MagicMock()
        cursor.fetchall.return_value = [tuple(r.values()) for r in rows]
        cursor.description = [(c,) for c in cols]
        return cursor

    def _raw_revision_row(self, revision: int) -> dict:
        """Build a raw revision row in the NEW schema column shape (issue 004)."""
        return {
            "id": uuid.uuid4(),
            "project_id": self._PROJECT_ID,  # TEXT in new schema
            "revision_number": revision,  # new column name
            "summary": "",
            "created_at": None,  # new: created_at (not saved_at)
            "created_by_user_id": None,  # new: user FK (not saved_by_email)
            "saved_by_email": "alice@example.com",  # from profiles JOIN
            "saved_by_name": "Alice",  # from profiles JOIN
        }

    def test_returns_list_desc_by_revision(self):
        from storage import PostgresStorageBackend

        raw_rows = [
            self._raw_revision_row(5),
            self._raw_revision_row(3),
            self._raw_revision_row(1),
        ]
        cursor = self._make_revisions_cursor(raw_rows)
        conn = MagicMock()
        conn.execute.return_value = cursor

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            result = backend.get_project_revisions(self._PROJECT_ID)

        assert len(result) == 3
        assert result[0]["revision"] == 5
        assert result[1]["revision"] == 3
        assert result[2]["revision"] == 1

    def test_ids_are_strings(self):
        from storage import PostgresStorageBackend

        raw_rows = [self._raw_revision_row(2)]
        cursor = self._make_revisions_cursor(raw_rows)
        conn = MagicMock()
        conn.execute.return_value = cursor

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            result = backend.get_project_revisions(self._PROJECT_ID)

        assert isinstance(result[0]["id"], str)
        assert isinstance(result[0]["project_id"], str)

    def test_returns_empty_list_when_no_revisions(self):
        from storage import PostgresStorageBackend

        cursor = self._make_revisions_cursor([])
        conn = MagicMock()
        conn.execute.return_value = cursor

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            result = backend.get_project_revisions(self._PROJECT_ID)

        assert result == []

    def test_state_not_present_in_metadata(self):
        """get_project_revisions must not return ``state`` (expensive JSONB)."""
        from storage import PostgresStorageBackend

        raw_rows = [self._raw_revision_row(1)]
        cursor = self._make_revisions_cursor(raw_rows)
        conn = MagicMock()
        conn.execute.return_value = cursor

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            result = backend.get_project_revisions(self._PROJECT_ID)

        assert "state" not in result[0]

    def test_sql_excludes_state_column(self):
        """The SELECT must not include the state column."""
        from storage import PostgresStorageBackend

        cursor = self._make_revisions_cursor([])
        conn = MagicMock()
        conn.execute.return_value = cursor

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)):
            backend.get_project_revisions(self._PROJECT_ID)

        sql = conn.execute.call_args[0][0]
        # Should mention project_revisions but not SELECT state
        assert "project_revisions" in sql
        assert "state" not in sql


# =============================================================================
# get_project_revision (single, with state)
# =============================================================================

class TestGetProjectRevision:
    _PROJECT_ID = str(uuid.uuid4())

    def _raw_full_row(self, revision: int, state: dict) -> dict:
        """Build a raw full revision row in the NEW schema column shape (issue 004).

        New schema: revision_number (not revision), created_at (not saved_at),
        created_by_user_id (not saved_by_user_id).
        saved_by_email / saved_by_name come from the LEFT JOIN on profiles.
        """
        return {
            "id": uuid.uuid4(),
            "project_id": self._PROJECT_ID,  # TEXT in new schema
            "revision_number": revision,  # new column name
            "state": json.dumps(state),
            "created_at": None,  # new: created_at (not saved_at)
            "created_by_user_id": None,  # new: user FK
            "saved_by_email": "alice@example.com",  # from profiles JOIN
            "saved_by_name": "Alice",  # from profiles JOIN
            "summary": "saved from UI",
        }

    def _make_single_cursor(self, row_dict: dict | None):
        cursor = MagicMock()
        if row_dict is not None:
            cursor.fetchone.return_value = tuple(row_dict.values())
            cursor.description = [(k,) for k in row_dict]
        else:
            cursor.fetchone.return_value = None
            cursor.description = [
                ("id",), ("project_id",), ("revision_number",), ("state",),
                ("created_at",), ("created_by_user_id",), ("saved_by_email",),
                ("saved_by_name",), ("summary",),
            ]
        return cursor

    def test_returns_full_state(self):
        from storage import PostgresStorageBackend

        state_payload = {"id": self._PROJECT_ID, "items": [{"type": "song"}]}
        raw = self._raw_full_row(revision=3, state=state_payload)
        cursor = self._make_single_cursor(raw)
        conn = MagicMock()
        conn.execute.return_value = cursor

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)), \
             patch("db.from_jsonb", side_effect=lambda v: json.loads(v) if isinstance(v, str) else v):
            result = backend.get_project_revision(self._PROJECT_ID, 3)

        assert result is not None
        assert result["revision"] == 3
        assert result["state"]["items"] == [{"type": "song"}]

    def test_returns_none_when_not_found(self):
        from storage import PostgresStorageBackend

        cursor = self._make_single_cursor(None)
        conn = MagicMock()
        conn.execute.return_value = cursor

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)), \
             patch("db.from_jsonb", side_effect=lambda v: json.loads(v) if isinstance(v, str) else v):
            result = backend.get_project_revision(self._PROJECT_ID, 999)

        assert result is None

    def test_ids_are_strings(self):
        from storage import PostgresStorageBackend

        raw = self._raw_full_row(revision=1, state={"id": self._PROJECT_ID})
        cursor = self._make_single_cursor(raw)
        conn = MagicMock()
        conn.execute.return_value = cursor

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)), \
             patch("db.from_jsonb", side_effect=lambda v: json.loads(v) if isinstance(v, str) else v):
            result = backend.get_project_revision(self._PROJECT_ID, 1)

        assert isinstance(result["id"], str)
        assert isinstance(result["project_id"], str)

    def test_summary_and_attribution_present(self):
        from storage import PostgresStorageBackend

        raw = self._raw_full_row(revision=2, state={})
        cursor = self._make_single_cursor(raw)
        conn = MagicMock()
        conn.execute.return_value = cursor

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)), \
             patch("db.from_jsonb", side_effect=lambda v: json.loads(v) if isinstance(v, str) else v):
            result = backend.get_project_revision(self._PROJECT_ID, 2)

        assert result["saved_by_email"] == "alice@example.com"
        assert result["saved_by_name"] == "Alice"
        assert result["summary"] == "saved from UI"

    def test_sql_uses_project_id_and_revision_filter(self):
        from storage import PostgresStorageBackend

        cursor = self._make_single_cursor(None)
        conn = MagicMock()
        conn.execute.return_value = cursor

        backend = PostgresStorageBackend()
        with patch("db.transaction", lambda claims=None: _fake_tx(conn)), \
             patch("db.from_jsonb", side_effect=lambda v: v):
            backend.get_project_revision(self._PROJECT_ID, 5)

        sql, params = conn.execute.call_args[0]
        assert "project_revisions" in sql
        assert "project_id" in sql
        assert "revision" in sql
        # New schema uses named params (dict), not positional tuple
        assert isinstance(params, dict)
        assert params["revision_number"] == 5


# =============================================================================
# JsonStorageBackend / StorageBackend stubs
# =============================================================================

class TestJsonBackendRevisionStubs:
    """Desktop JSON backend must return safe empty values for revision queries."""

    def test_get_project_revisions_returns_empty_list(self, tmp_path):
        from storage import JsonStorageBackend

        backend = JsonStorageBackend(tmp_path)
        result = backend.get_project_revisions(str(uuid.uuid4()))
        assert result == []

    def test_get_project_revision_returns_none(self, tmp_path):
        from storage import JsonStorageBackend

        backend = JsonStorageBackend(tmp_path)
        result = backend.get_project_revision(str(uuid.uuid4()), 1)
        assert result is None

    def test_storage_backend_base_get_project_revisions(self, tmp_path):
        """StorageBackend default implementation returns []."""
        from storage import StorageBackend, JsonStorageBackend

        # JsonStorageBackend inherits the default (not overridden), so this also
        # exercises the base class default.
        backend = JsonStorageBackend(tmp_path)
        assert backend.get_project_revisions("any-id") == []

    def test_storage_backend_base_get_project_revision(self, tmp_path):
        """StorageBackend default implementation returns None."""
        from storage import JsonStorageBackend

        backend = JsonStorageBackend(tmp_path)
        assert backend.get_project_revision("any-id", 1) is None


# =============================================================================
# migrations/import_projects.py — initial revision row
# =============================================================================

class TestImportProjectsInitialRevision:
    """Verify import inserts a revision row with the correct summary."""

    _PROJECT_ID = str(uuid.uuid4())

    def _make_ctx(self, project_inserted: bool):
        """Return a (ctx, conn) pair where the project upsert rowcount is controlled."""
        conn = MagicMock()

        def side_effect(sql, params=None):
            cursor = MagicMock()
            if "project_revisions" in sql:
                cursor.rowcount = 1
                return cursor
            # Project upsert
            cursor.rowcount = 1 if project_inserted else 0
            return cursor

        conn.execute.side_effect = side_effect

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx, conn

    def test_import_inserts_revision_row(self, tmp_path):
        """Importing a project must call _insert_revision (project_revisions INSERT)."""
        from import_projects import import_projects_from_json

        projects_file = tmp_path / "projects.json"
        projects_file.write_text(json.dumps([
            {"id": self._PROJECT_ID, "name": "Sunday Service", "revision": 1}
        ]))

        ctx, conn = self._make_ctx(project_inserted=True)

        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(projects_file))

        assert result["imported"] == 1
        revision_calls = [
            c for c in conn.execute.call_args_list
            if "project_revisions" in c.args[0]
        ]
        assert len(revision_calls) == 1

    def test_import_revision_summary_is_imported_from_json(self, tmp_path):
        """The initial revision summary must be 'Imported from projects.json'."""
        from import_projects import import_projects_from_json

        projects_file = tmp_path / "projects.json"
        projects_file.write_text(json.dumps([
            {"id": self._PROJECT_ID, "name": "Sunday Service", "revision": 1}
        ]))

        ctx, conn = self._make_ctx(project_inserted=True)

        with patch("import_projects.transaction", return_value=ctx):
            import_projects_from_json(str(projects_file))

        revision_calls = [
            c for c in conn.execute.call_args_list
            if "project_revisions" in c.args[0]
        ]
        # The summary literal appears in the SQL string itself
        sql = revision_calls[0].args[0]
        assert "Imported from projects.json" in sql

    def test_import_no_revision_when_project_skipped(self, tmp_path):
        """When ON CONFLICT DO NOTHING fires (skipped), no revision row is inserted."""
        from import_projects import import_projects_from_json

        projects_file = tmp_path / "projects.json"
        projects_file.write_text(json.dumps([
            {"id": self._PROJECT_ID, "name": "Sunday Service", "revision": 1}
        ]))

        ctx, conn = self._make_ctx(project_inserted=False)

        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(projects_file))

        assert result["skipped"] == 1
        revision_calls = [
            c for c in conn.execute.call_args_list
            if "project_revisions" in c.args[0]
        ]
        assert len(revision_calls) == 0

    def test_import_revision_uses_project_revision(self, tmp_path):
        """The revision number in the snapshot must match the project's revision field."""
        from import_projects import _parse_project, _insert_revision

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service", "revision": 5}
        row = _parse_project(project_data, 0)
        assert row["revision"] == 5

        conn = MagicMock()
        _insert_revision(conn, row)

        params = conn.execute.call_args[0][1]
        assert params["revision"] == 5

    def test_import_revision_saved_by_email_from_updated_by(self, tmp_path):
        """saved_by_email should use updatedBy (or createdBy as fallback)."""
        from import_projects import _parse_project, _insert_revision

        project_data = {
            "id": self._PROJECT_ID,
            "name": "Sunday Service",
            "revision": 1,
            "updatedBy": "editor@example.com",
            "createdBy": "creator@example.com",
        }
        row = _parse_project(project_data, 0)
        conn = MagicMock()
        _insert_revision(conn, row)

        params = conn.execute.call_args[0][1]
        assert params["saved_by_email"] == "editor@example.com"
