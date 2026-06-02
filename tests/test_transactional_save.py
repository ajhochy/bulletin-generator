"""
tests/test_transactional_save.py — Transactional project save with optimistic
revision checks.

Covers:
  storage.py — PostgresStorageBackend.save_project_transactional():
    - Successful save: rowcount=1, revision snapshot inserted, returns updated project
    - Stale revision: rowcount=0, ConflictError raised with server project state
    - Missing _clientRevision (None): treated as 0, raises ConflictError when DB revision > 0
    - Project not found: ConflictError raised with minimal project dict

  storage.py — ConflictError:
    - Has .project attribute with server-side project dict

  storage.py — StorageBackend.save_project_transactional() default:
    - JSON backend falls back to save_project() (no revision check)

  server.py — POST /api/projects (server mode, existing project):
    - Successful save: returns {"ok": True, "revision": N}
    - Conflict: returns 409 with conflict metadata
    - New project: uses non-transactional path, revision not checked

  server.py — POST /api/projects (desktop mode):
    - Uses JSON file path, not the transactional path
"""

from __future__ import annotations

import json
import sys
import types
import uuid
from io import BytesIO
from unittest.mock import MagicMock, call, patch

import pytest

# ── Project root on sys.path ───────────────────────────────────────────────────

sys.path.insert(0, str(__file__).replace("/tests/test_transactional_save.py", ""))

# ── Python 3.13+ cgi shim ──────────────────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_project(project_id: str, revision: int, **extra) -> dict:
    return {
        "id": project_id,
        "name": "Sunday Service",
        "revision": revision,
        "updated_at": "2026-05-20T10:00:00+00:00",
        "updated_by_email": "alice@example.com",
        "updatedAt": "2026-05-20T10:00:00+00:00",
        "updatedBy": "alice@example.com",
        **extra,
    }


# =============================================================================
# ConflictError
# =============================================================================

class TestConflictError:
    def test_has_project_attribute(self):
        from storage import ConflictError
        project = _make_project("p1", revision=7)
        err = ConflictError(project)
        assert err.project is project

    def test_message_mentions_revision(self):
        from storage import ConflictError
        project = _make_project("p1", revision=7)
        err = ConflictError(project)
        assert "7" in str(err)

    def test_is_exception(self):
        from storage import ConflictError
        assert issubclass(ConflictError, Exception)


# =============================================================================
# PostgresStorageBackend.save_project_transactional — unit tests (no real DB)
# =============================================================================

class TestSaveProjectTransactionalUnit:
    """Test the Postgres transactional save in isolation by mocking db.transaction."""

    _PROJECT_ID = str(uuid.uuid4())

    def _pg_row(self, revision: int) -> dict:
        """Build a minimal Postgres row dict for _pg_row_to_project()."""
        now_str = "2026-05-20T10:00:00+00:00"
        return {
            "id": uuid.UUID(self._PROJECT_ID),
            "name": "Sunday Service",
            "owner_user_id": None,
            "visibility": "workspace",
            "state": json.dumps({"id": self._PROJECT_ID, "name": "Sunday Service"}),
            "revision": revision,
            "created_at": None,
            "updated_at": None,
            "created_by_email": "alice@example.com",
            "updated_by_email": "alice@example.com",
            "imported_from_json": False,
        }

    def _make_cursor(self, row_dict: dict | None, *, rowcount: int = 1):
        """Return a mock cursor that mimics psycopg2 cursor behaviour."""
        cursor = MagicMock()
        if row_dict is not None:
            row_tuple = tuple(row_dict.values())
            cursor.fetchone.return_value = row_tuple
            cursor.description = [(k,) for k in row_dict]
            cursor.rowcount = rowcount
        else:
            cursor.fetchone.return_value = None
            cursor.description = []
            cursor.rowcount = 0
        return cursor

    def _make_prev_cursor(self):
        """Return a mock cursor for the prev-state SELECT (first execute call)."""
        cursor = MagicMock()
        prev_json = json.dumps({"id": self._PROJECT_ID, "name": "Sunday Service"})
        cursor.fetchone.return_value = (prev_json,)
        return cursor

    def _make_conn(self, update_row, *, conflict_server_row=None):
        """Build a mock connection where execute() returns different cursors per call.

        execute() call order in save_project_transactional:
          1. SELECT state FROM projects  (prev-state fetch for summary generation)
          2. UPDATE projects ... RETURNING  (the main transactional save)
          3a. INSERT INTO project_revisions  (success path)
          3b. SELECT ... FROM projects  (conflict path — fetch server state)
        """
        conn = MagicMock()
        prev_cursor = self._make_prev_cursor()
        update_cursor = self._make_cursor(update_row)
        snapshot_cursor = MagicMock()
        snapshot_cursor.rowcount = 1

        if conflict_server_row is not None:
            server_cursor = self._make_cursor(conflict_server_row)
            # prev state SELECT + UPDATE (None) + SELECT server state
            conn.execute.side_effect = [prev_cursor, update_cursor, server_cursor]
        else:
            # prev state SELECT + UPDATE + INSERT snapshot
            conn.execute.side_effect = [prev_cursor, update_cursor, snapshot_cursor]
        return conn

    def _patch_transaction(self, conn):
        """Return a context manager patch for db.transaction that yields conn."""
        from contextlib import contextmanager

        @contextmanager
        def _fake_transaction():
            yield conn

        return patch("storage.PostgresStorageBackend.save_project_transactional.__wrapped__", None), \
               patch("db.transaction", _fake_transaction)

    # -- Successful save -------------------------------------------------------

    def test_successful_save_returns_updated_project(self):
        from storage import PostgresStorageBackend, ConflictError

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service", "items": []}
        updated_row = self._pg_row(revision=4)  # revision already incremented by DB
        conn = self._make_conn(update_row=updated_row)

        from contextlib import contextmanager

        @contextmanager
        def _fake_tx():
            yield conn

        backend = PostgresStorageBackend()
        with patch("db.transaction", _fake_tx):
            result = backend.save_project_transactional(
                project_data,
                client_revision=3,
                updated_by_email="alice@example.com",
                updated_by_user_id=None,
                updated_by_name="Alice",
            )

        assert result["id"] == self._PROJECT_ID
        assert result["revision"] == 4

    def test_successful_save_inserts_revision_snapshot(self):
        from storage import PostgresStorageBackend

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        updated_row = self._pg_row(revision=6)
        conn = self._make_conn(update_row=updated_row)

        from contextlib import contextmanager

        @contextmanager
        def _fake_tx():
            yield conn

        backend = PostgresStorageBackend()
        with patch("db.transaction", _fake_tx):
            backend.save_project_transactional(
                project_data,
                client_revision=5,
                updated_by_email="bob@example.com",
            )

        # conn.execute should have been called three times:
        # SELECT prev state + UPDATE + INSERT snapshot
        assert conn.execute.call_count == 3
        # The third call should insert into project_revisions
        third_call_sql = conn.execute.call_args_list[2][0][0]
        assert "project_revisions" in third_call_sql

    def test_successful_save_snapshot_uses_new_revision(self):
        from storage import PostgresStorageBackend

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        updated_row = self._pg_row(revision=10)
        conn = self._make_conn(update_row=updated_row)

        from contextlib import contextmanager

        @contextmanager
        def _fake_tx():
            yield conn

        backend = PostgresStorageBackend()
        with patch("db.transaction", _fake_tx):
            backend.save_project_transactional(
                project_data,
                client_revision=9,
                updated_by_email="carol@example.com",
                updated_by_name="Carol",
            )

        snapshot_params = conn.execute.call_args_list[2][0][1]
        assert snapshot_params["revision"] == 10
        assert snapshot_params["saved_by_email"] == "carol@example.com"
        assert snapshot_params["saved_by_name"] == "Carol"

    # -- Stale revision --------------------------------------------------------

    def test_stale_revision_raises_conflict_error(self):
        from storage import PostgresStorageBackend, ConflictError

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        server_row = self._pg_row(revision=5)
        conn = self._make_conn(update_row=None, conflict_server_row=server_row)

        from contextlib import contextmanager

        @contextmanager
        def _fake_tx():
            yield conn

        backend = PostgresStorageBackend()
        with pytest.raises(ConflictError) as exc_info:
            with patch("db.transaction", _fake_tx):
                backend.save_project_transactional(
                    project_data,
                    client_revision=3,  # stale — server is at 5
                )

        assert exc_info.value.project["revision"] == 5

    def test_conflict_error_project_contains_id(self):
        from storage import PostgresStorageBackend, ConflictError

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        server_row = self._pg_row(revision=8)
        conn = self._make_conn(update_row=None, conflict_server_row=server_row)

        from contextlib import contextmanager

        @contextmanager
        def _fake_tx():
            yield conn

        backend = PostgresStorageBackend()
        with pytest.raises(ConflictError) as exc_info:
            with patch("db.transaction", _fake_tx):
                backend.save_project_transactional(project_data, client_revision=7)

        assert exc_info.value.project["id"] == self._PROJECT_ID

    # -- Missing client revision -----------------------------------------------

    def test_missing_client_revision_treated_as_zero(self):
        """None client_revision → effective_client_rev=0 → always conflicts if DB revision > 0."""
        from storage import PostgresStorageBackend, ConflictError

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        server_row = self._pg_row(revision=1)
        conn = self._make_conn(update_row=None, conflict_server_row=server_row)

        from contextlib import contextmanager

        @contextmanager
        def _fake_tx():
            yield conn

        backend = PostgresStorageBackend()
        with pytest.raises(ConflictError):
            with patch("db.transaction", _fake_tx):
                backend.save_project_transactional(project_data, client_revision=None)

        # Verify the UPDATE (second call, after prev-state SELECT) was called with revision=0
        update_params = conn.execute.call_args_list[1][0][1]
        assert update_params["client_revision"] == 0

    # -- Project not found ─────────────────────────────────────────────────────

    def test_project_not_found_raises_conflict_error(self):
        """If the project doesn't exist in DB, ConflictError is raised."""
        from storage import PostgresStorageBackend, ConflictError

        project_data = {"id": self._PROJECT_ID, "name": "Sunday Service"}

        conn = MagicMock()
        # Prev-state SELECT returns None (project not yet in DB)
        prev_cursor = MagicMock()
        prev_cursor.fetchone.return_value = None

        # UPDATE returns None (no row)
        update_cursor = MagicMock()
        update_cursor.fetchone.return_value = None
        update_cursor.description = []

        # SELECT server state also returns None (project gone)
        server_cursor = MagicMock()
        server_cursor.fetchone.return_value = None
        server_cursor.description = []

        conn.execute.side_effect = [prev_cursor, update_cursor, server_cursor]

        from contextlib import contextmanager

        @contextmanager
        def _fake_tx():
            yield conn

        backend = PostgresStorageBackend()
        with pytest.raises(ConflictError) as exc_info:
            with patch("db.transaction", _fake_tx):
                backend.save_project_transactional(project_data, client_revision=1)

        # Should still have an id so caller can build a response
        assert exc_info.value.project["id"] == self._PROJECT_ID

    # -- ValueError for missing id ─────────────────────────────────────────────

    def test_missing_id_raises_value_error(self):
        from storage import PostgresStorageBackend

        backend = PostgresStorageBackend()
        with pytest.raises(ValueError, match="id"):
            backend.save_project_transactional({"name": "no id"}, client_revision=1)


# =============================================================================
# JsonStorageBackend.save_project_transactional — default fallback
# =============================================================================

class TestJsonBackendTransactionalFallback:
    """JSON backend should fall back to save_project() — no revision check."""

    def test_json_backend_saves_without_conflict_check(self, tmp_path):
        from storage import JsonStorageBackend

        backend = JsonStorageBackend(tmp_path)
        project = {"id": "p-json-1", "name": "Desktop Service", "revision": 3}
        backend.save_project(project)

        # Transactional save with a stale revision should NOT raise — JSON backend
        # delegates to save_project() which has no revision awareness.
        result = backend.save_project_transactional(
            {"id": "p-json-1", "name": "Updated Service", "revision": 3},
            client_revision=1,  # stale, but JSON backend ignores it
        )
        assert result["name"] == "Updated Service"

    def test_json_backend_returns_saved_data(self, tmp_path):
        from storage import JsonStorageBackend

        backend = JsonStorageBackend(tmp_path)
        project = {"id": "p-json-2", "name": "Service"}
        result = backend.save_project_transactional(project, client_revision=0)
        assert result["id"] == "p-json-2"


# =============================================================================
# POST /api/projects — server mode integration (mocked storage)
# =============================================================================

class TestPostProjectsServerMode:
    """Integration tests for the POST /api/projects route in server mode.

    The storage layer is fully mocked so no database is required.
    """

    _USER = {
        "id": str(uuid.uuid4()),
        "email": "alice@example.com",
        "display_name": "Alice",
    }
    _PROJECT_ID = str(uuid.uuid4())

    def _make_handler(self, body: bytes, monkeypatch):
        """Return a server.Handler-like object wired for a POST /api/projects request."""
        import server as server_module

        monkeypatch.setenv("APP_MODE", "server")
        # Reload module-level IS_DESKTOP flag.
        server_module.IS_DESKTOP = False

        from server import Handler

        handler = MagicMock(spec=Handler)
        handler.path = "/api/projects"
        handler.headers = {"Content-Length": str(len(body)), "Content-Type": "application/json"}
        handler.rfile = BytesIO(body)

        responses = []

        def _send_json(data, status=200):
            responses.append((status, data))

        handler._send_json = _send_json
        handler._require_auth = MagicMock(return_value=self._USER)
        handler._read_body_json = MagicMock(return_value=json.loads(body))

        # Attach the real method bound to our mock handler.
        import types as _types

        handler._handle_post_projects = _types.MethodType(
            Handler._handle_post_projects, handler
        )
        return handler, responses

    def _existing_project(self, revision: int) -> dict:
        return _make_project(
            self._PROJECT_ID,
            revision=revision,
            visibility="workspace",
            owner_user_id=self._USER["id"],
        )

    # -- Successful save -------------------------------------------------------

    def test_successful_save_returns_ok_and_revision(self, monkeypatch):
        import server as server_module

        project_payload = {
            "id": self._PROJECT_ID,
            "name": "Sunday Service",
            "_clientRevision": 4,
        }
        body = json.dumps(project_payload).encode()
        handler, responses = self._make_handler(body, monkeypatch)

        existing = self._existing_project(revision=4)
        saved = {**existing, "revision": 5}

        mock_store = MagicMock()
        mock_store.get_project.return_value = existing
        mock_store.save_project_transactional.return_value = saved

        with patch("storage.get_storage", return_value=mock_store), \
             patch("storage.ConflictError", __import__("storage").ConflictError), \
             patch.object(server_module, "IS_DESKTOP", False):
            handler._handle_post_projects()

        assert len(responses) == 1
        status, data = responses[0]
        assert status == 200
        assert data["ok"] is True
        assert data["revision"] == 5

    def test_successful_save_calls_transactional_with_client_revision(self, monkeypatch):
        import server as server_module

        project_payload = {
            "id": self._PROJECT_ID,
            "name": "Sunday Service",
            "_clientRevision": 7,
        }
        body = json.dumps(project_payload).encode()
        handler, responses = self._make_handler(body, monkeypatch)

        existing = self._existing_project(revision=7)
        saved = {**existing, "revision": 8}

        mock_store = MagicMock()
        mock_store.get_project.return_value = existing
        mock_store.save_project_transactional.return_value = saved

        with patch("storage.get_storage", return_value=mock_store), \
             patch("storage.ConflictError", __import__("storage").ConflictError), \
             patch.object(server_module, "IS_DESKTOP", False):
            handler._handle_post_projects()

        call_kwargs = mock_store.save_project_transactional.call_args
        assert call_kwargs.kwargs.get("client_revision") == 7 or \
               (call_kwargs.args and call_kwargs.args[1] == 7)

    # -- Conflict (stale revision) ─────────────────────────────────────────────

    def test_conflict_returns_409(self, monkeypatch):
        import server as server_module
        from storage import ConflictError

        project_payload = {
            "id": self._PROJECT_ID,
            "name": "Sunday Service",
            "_clientRevision": 3,
        }
        body = json.dumps(project_payload).encode()
        handler, responses = self._make_handler(body, monkeypatch)

        existing = self._existing_project(revision=5)
        server_project = self._existing_project(revision=5)

        mock_store = MagicMock()
        mock_store.get_project.return_value = existing
        mock_store.save_project_transactional.side_effect = ConflictError(server_project)

        with patch("storage.get_storage", return_value=mock_store), \
             patch("storage.ConflictError", ConflictError), \
             patch.object(server_module, "IS_DESKTOP", False):
            handler._handle_post_projects()

        assert len(responses) == 1
        status, data = responses[0]
        assert status == 409

    def test_conflict_response_contains_metadata(self, monkeypatch):
        import server as server_module
        from storage import ConflictError

        project_payload = {
            "id": self._PROJECT_ID,
            "name": "Sunday Service",
            "_clientRevision": 3,
        }
        body = json.dumps(project_payload).encode()
        handler, responses = self._make_handler(body, monkeypatch)

        server_project = self._existing_project(revision=7)
        existing = self._existing_project(revision=7)

        mock_store = MagicMock()
        mock_store.get_project.return_value = existing
        mock_store.save_project_transactional.side_effect = ConflictError(server_project)

        with patch("storage.get_storage", return_value=mock_store), \
             patch("storage.ConflictError", ConflictError), \
             patch.object(server_module, "IS_DESKTOP", False):
            handler._handle_post_projects()

        status, data = responses[0]
        assert status == 409
        assert data["conflict"] is True
        assert data["serverRevision"] == 7
        assert "serverUpdatedAt" in data
        assert "serverUpdatedBy" in data

    # -- New project: non-transactional path ───────────────────────────────────

    def test_new_project_uses_nontransactional_save(self, monkeypatch):
        import server as server_module

        new_id = str(uuid.uuid4())
        project_payload = {"id": new_id, "name": "New Service", "_clientRevision": 0}
        body = json.dumps(project_payload).encode()
        handler, responses = self._make_handler(body, monkeypatch)

        saved = {"id": new_id, "name": "New Service", "revision": 1}
        mock_store = MagicMock()
        mock_store.get_project.return_value = None  # does not exist yet → new project
        mock_store.save_project.return_value = saved

        with patch("storage.get_storage", return_value=mock_store), \
             patch("storage.ConflictError", __import__("storage").ConflictError), \
             patch.object(server_module, "IS_DESKTOP", False):
            handler._handle_post_projects()

        # save_project should be called, NOT save_project_transactional
        assert mock_store.save_project.call_count == 1
        assert mock_store.save_project_transactional.call_count == 0

        status, data = responses[0]
        assert status == 200
        assert data["ok"] is True

    # -- Missing _clientRevision ───────────────────────────────────────────────

    def test_missing_client_revision_passed_as_none(self, monkeypatch):
        """When _clientRevision is absent from payload, None is passed to transactional save."""
        import server as server_module
        from storage import ConflictError

        project_payload = {"id": self._PROJECT_ID, "name": "Sunday Service"}
        body = json.dumps(project_payload).encode()
        handler, responses = self._make_handler(body, monkeypatch)

        existing = self._existing_project(revision=3)
        # Simulate that the missing revision triggers a conflict
        mock_store = MagicMock()
        mock_store.get_project.return_value = existing
        mock_store.save_project_transactional.side_effect = ConflictError(existing)

        with patch("storage.get_storage", return_value=mock_store), \
             patch("storage.ConflictError", ConflictError), \
             patch.object(server_module, "IS_DESKTOP", False):
            handler._handle_post_projects()

        # Verify None was passed as client_revision
        call_kwargs = mock_store.save_project_transactional.call_args
        passed_rev = call_kwargs.kwargs.get("client_revision") or \
                     (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
        assert passed_rev is None

        status, _ = responses[0]
        assert status == 409


# =============================================================================
# POST /api/projects — desktop mode (JSON file path unchanged)
# =============================================================================

class TestPostProjectsDesktopMode:
    """Desktop mode must use the JSON file path, not the transactional save."""

    _PROJECT_ID = str(uuid.uuid4())

    def test_desktop_mode_does_not_call_transactional_save(self, tmp_path, monkeypatch):
        """In desktop mode, save_project_transactional must never be called."""
        import server as server_module

        monkeypatch.setenv("APP_MODE", "desktop")
        server_module.IS_DESKTOP = True

        # Seed the projects file with an existing project at revision 2.
        import json as _json
        projects_file = tmp_path / "projects.json"
        existing = {"id": self._PROJECT_ID, "name": "Desktop Service", "revision": 2}
        projects_file.write_text(_json.dumps([existing]))

        original_projects_file = server_module.PROJECTS_FILE
        original_lock = server_module._lock

        monkeypatch.setattr(server_module, "PROJECTS_FILE", projects_file)

        from server import Handler

        project_payload = {
            "id": self._PROJECT_ID,
            "name": "Desktop Service Updated",
            "_clientRevision": 2,
        }
        body = _json.dumps(project_payload).encode()

        handler = MagicMock(spec=Handler)
        handler.path = "/api/projects"
        handler._require_auth = MagicMock(return_value={"id": "u1", "email": "desk@example.com"})
        handler._read_body_json = MagicMock(return_value=_json.loads(body))

        responses = []

        def _send_json(data, status=200):
            responses.append((status, data))

        handler._send_json = _send_json

        import types as _types
        handler._handle_post_projects = _types.MethodType(
            Handler._handle_post_projects, handler
        )

        mock_store = MagicMock()

        with patch("storage.get_storage", return_value=mock_store), \
             patch.object(server_module, "IS_DESKTOP", True):
            handler._handle_post_projects()

        # storage layer must not be touched at all in desktop mode.
        mock_store.save_project_transactional.assert_not_called()
        mock_store.save_project.assert_not_called()

        assert len(responses) == 1
        status, data = responses[0]
        assert status == 200
        assert data["ok"] is True
        assert data["revision"] == 3  # incremented from 2

        monkeypatch.setattr(server_module, "PROJECTS_FILE", original_projects_file)
