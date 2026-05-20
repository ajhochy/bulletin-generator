"""
tests/test_project_visibility.py — Access control for project list/load/save/delete routes.

Covers:
  Unit tests for storage access-control helpers:
    - can_read_project: workspace, private-own, private-other, legacy (no owner)
    - can_write_project: mirrors can_read
    - can_delete_project: owner-only; legacy and non-owner → False
    - list_projects_for_user: returns workspace + own private + legacy private

  API route tests (two-user scenarios):
    List:
      - User A sees their private project; User B does not
      - Both users see workspace projects
    Load (GET /api/projects?id=):
      - User A can load their private project
      - User B gets 403/404 on User A's private project
      - Both users can load workspace projects
    Save (POST /api/projects):
      - User A can save their private project
      - User B gets 403 saving User A's private project
      - Both users can save a workspace project
    Delete (DELETE /api/projects/{id}):
      - User A can delete their own private project
      - User B gets 403 deleting User A's private project
      - Owner gets 403 deleting a workspace project they don't own
        (workspace project owned by the other user)
      - Neither user can delete a legacy (no-owner) workspace project → 403
      - Legacy private project (no owner) → 403 on delete
"""

from __future__ import annotations

import json
import sys
import types
import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

# ── Project root on sys.path ──────────────────────────────────────────────────

sys.path.insert(0, str(__file__).replace("/tests/test_project_visibility.py", ""))

# ── Python 3.13+ compatibility shim ──────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

# ── Imports ───────────────────────────────────────────────────────────────────

import server  # noqa: E402
import storage  # noqa: E402
from storage import can_read_project, can_write_project, can_delete_project  # noqa: E402


# ── Test users ────────────────────────────────────────────────────────────────

_USER_ALICE = {
    "id": "aaaaaaaa-0000-0000-0000-000000000001",
    "email": "alice@example.com",
    "display_name": "Alice",
    "avatar_url": "",
    "domain": "example.com",
}

_USER_BOB = {
    "id": "bbbbbbbb-0000-0000-0000-000000000002",
    "email": "bob@example.com",
    "display_name": "Bob",
    "avatar_url": "",
    "domain": "example.com",
}


# ── Project factory ────────────────────────────────────────────────────────────

def _project(project_id: str, owner_user_id, visibility: str = "private") -> dict:
    return {
        "id": project_id,
        "name": "Sunday Service",
        "owner_user_id": owner_user_id,
        "visibility": visibility,
        "revision": 1,
    }


# ── Handler factory ────────────────────────────────────────────────────────────

def _make_handler(path: str, cookie: str = "bg_session=tok", body: bytes = b""):
    handler = server.Handler.__new__(server.Handler)
    handler._send_json = MagicMock()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    handler.server = MagicMock()
    handler.server.server_address = ("127.0.0.1", 8080)
    handler.path = path
    handler.headers = {
        "Cookie": cookie,
        "Content-Length": str(len(body)),
        "Content-Type": "application/json",
    }
    handler.rfile = BytesIO(body)
    return handler


def _status(handler) -> int:
    """Extract HTTP status from the last _send_json call."""
    args = handler._send_json.call_args[0]
    return args[1] if len(args) > 1 else 200


# ===========================================================================
# Unit tests: access control helpers
# ===========================================================================

class TestCanReadProject:
    def test_workspace_visible_to_all(self):
        p = _project("p1", _USER_ALICE["id"], "workspace")
        assert can_read_project(p, _USER_BOB["id"]) is True

    def test_private_visible_to_owner(self):
        p = _project("p1", _USER_ALICE["id"], "private")
        assert can_read_project(p, _USER_ALICE["id"]) is True

    def test_private_not_visible_to_other(self):
        p = _project("p1", _USER_ALICE["id"], "private")
        assert can_read_project(p, _USER_BOB["id"]) is False

    def test_legacy_no_owner_visible_to_all(self):
        p = _project("p1", None, "private")
        assert can_read_project(p, _USER_BOB["id"]) is True

    def test_legacy_workspace_no_owner_visible_to_all(self):
        p = _project("p1", None, "workspace")
        assert can_read_project(p, _USER_BOB["id"]) is True


class TestCanWriteProject:
    """can_write_project mirrors can_read_project."""

    def test_workspace_writable_by_all(self):
        p = _project("p1", _USER_ALICE["id"], "workspace")
        assert can_write_project(p, _USER_BOB["id"]) is True

    def test_private_writable_by_owner(self):
        p = _project("p1", _USER_ALICE["id"], "private")
        assert can_write_project(p, _USER_ALICE["id"]) is True

    def test_private_not_writable_by_other(self):
        p = _project("p1", _USER_ALICE["id"], "private")
        assert can_write_project(p, _USER_BOB["id"]) is False

    def test_legacy_no_owner_writable_by_all(self):
        p = _project("p1", None, "private")
        assert can_write_project(p, _USER_BOB["id"]) is True


class TestCanDeleteProject:
    def test_owner_can_delete_own_private(self):
        p = _project("p1", _USER_ALICE["id"], "private")
        assert can_delete_project(p, _USER_ALICE["id"]) is True

    def test_non_owner_cannot_delete_private(self):
        p = _project("p1", _USER_ALICE["id"], "private")
        assert can_delete_project(p, _USER_BOB["id"]) is False

    def test_owner_cannot_delete_workspace_they_do_not_own(self):
        # workspace project owned by Alice — Bob cannot delete
        p = _project("p1", _USER_ALICE["id"], "workspace")
        assert can_delete_project(p, _USER_BOB["id"]) is False

    def test_owner_can_delete_workspace_project_they_own(self):
        p = _project("p1", _USER_ALICE["id"], "workspace")
        assert can_delete_project(p, _USER_ALICE["id"]) is True

    def test_legacy_no_owner_not_deletable(self):
        p = _project("p1", None, "private")
        assert can_delete_project(p, _USER_ALICE["id"]) is False

    def test_legacy_workspace_no_owner_not_deletable(self):
        p = _project("p1", None, "workspace")
        assert can_delete_project(p, _USER_ALICE["id"]) is False


# ===========================================================================
# Unit tests: PostgresStorageBackend.list_projects_for_user
# ===========================================================================

class TestListProjectsForUser:
    """list_projects_for_user uses a SQL filter; we verify the query fires with
    the right user_id by mocking the db transaction."""

    def _run(self, rows, cols, user_id):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_cursor.description = [(c,) for c in cols]

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_cursor

        from unittest.mock import patch as _patch
        from contextlib import contextmanager

        @contextmanager
        def fake_transaction():
            yield mock_conn

        backend = storage.PostgresStorageBackend()
        with _patch("db.transaction", fake_transaction), \
             _patch("db.from_jsonb", side_effect=lambda x: x if isinstance(x, dict) else {}):
            return backend.list_projects_for_user(user_id), mock_conn

    def test_query_includes_user_id_param(self):
        cols = ["id", "name", "owner_user_id", "visibility", "state",
                "revision", "created_at", "updated_at",
                "created_by_email", "updated_by_email", "imported_from_json"]
        _result, mock_conn = self._run([], cols, _USER_ALICE["id"])
        call_args = mock_conn.execute.call_args
        params = call_args[0][1]  # positional second arg (dict)
        assert params.get("user_id") == _USER_ALICE["id"]

    def test_returns_empty_list_when_no_rows(self):
        cols = ["id", "name", "owner_user_id", "visibility", "state",
                "revision", "created_at", "updated_at",
                "created_by_email", "updated_by_email", "imported_from_json"]
        result, _ = self._run([], cols, _USER_ALICE["id"])
        assert result == []


# ===========================================================================
# API route tests: GET /api/projects (list)
# ===========================================================================

class TestGetProjectsList:
    """Server-mode list endpoint uses list_projects(user_id=...) for filtering."""

    def _call_list(self, user, projects_returned):
        handler = _make_handler("/api/projects")
        mock_store = MagicMock()
        mock_store.list_projects.return_value = projects_returned
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=user), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_projects()
        return handler, mock_store

    def test_list_calls_store_with_user_id(self):
        _handler, store = self._call_list(_USER_ALICE, [])
        store.list_projects.assert_called_once_with(user_id=_USER_ALICE["id"])

    def test_list_returns_projects_from_store(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"])
        handler, _store = self._call_list(_USER_ALICE, [prj])
        body = handler._send_json.call_args[0][0]
        assert "projects" in body
        assert len(body["projects"]) == 1
        assert body["projects"][0]["id"] == pid

    def test_list_returns_200(self):
        handler, _store = self._call_list(_USER_ALICE, [])
        assert _status(handler) == 200

    def test_unauthenticated_list_returns_401(self):
        handler = _make_handler("/api/projects")
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            handler._handle_get_projects()
        assert _status(handler) == 401


# ===========================================================================
# API route tests: GET /api/projects?id=... (single project load)
# ===========================================================================

class TestGetProjectSingle:
    """GET /api/projects?id=<id> enforces can_read_project."""

    def _call_get(self, user, project_id, project_in_db):
        path = f"/api/projects?id={project_id}"
        handler = _make_handler(path)
        mock_store = MagicMock()
        mock_store.get_project.return_value = project_in_db
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=user), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_get_projects()
        return handler, mock_store

    def test_owner_can_load_private_project(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"], "private")
        handler, _store = self._call_get(_USER_ALICE, pid, prj)
        assert _status(handler) == 200
        body = handler._send_json.call_args[0][0]
        assert "project" in body

    def test_non_owner_cannot_load_private_project(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"], "private")
        handler, _store = self._call_get(_USER_BOB, pid, prj)
        assert _status(handler) == 403

    def test_both_users_can_load_workspace_project(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"], "workspace")
        for user in (_USER_ALICE, _USER_BOB):
            handler, _store = self._call_get(user, pid, prj)
            assert _status(handler) == 200, f"Expected 200 for {user['email']}"

    def test_missing_project_returns_404(self):
        pid = str(uuid.uuid4())
        handler, _store = self._call_get(_USER_ALICE, pid, None)
        assert _status(handler) == 404

    def test_legacy_no_owner_readable_by_all(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, None, "private")
        handler, _store = self._call_get(_USER_BOB, pid, prj)
        assert _status(handler) == 200


# ===========================================================================
# API route tests: POST /api/projects (save/update)
# ===========================================================================

class TestPostProjectsSave:
    """Save enforces can_write_project for existing projects."""

    def _call_save(self, user, project_id, existing_project, client_rev=1):
        payload = {
            "id": project_id,
            "name": "Updated",
            "_clientRevision": client_rev,
        }
        body = json.dumps(payload).encode()
        handler = _make_handler("/api/projects", body=body)
        mock_store = MagicMock()
        mock_store.get_project.return_value = existing_project
        if existing_project is not None:
            saved = dict(existing_project, revision=(existing_project.get("revision", 1) + 1))
            # Existing projects use the transactional save path.
            mock_store.save_project_transactional.return_value = saved
        else:
            mock_store.save_project.return_value = {"id": project_id, "revision": 1}
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=user), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_post_projects()
        return handler, mock_store

    def test_owner_can_save_private_project(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"], "private")
        handler, store = self._call_save(_USER_ALICE, pid, prj)
        assert _status(handler) == 200
        store.save_project_transactional.assert_called_once()

    def test_non_owner_cannot_save_private_project(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"], "private")
        handler, store = self._call_save(_USER_BOB, pid, prj)
        assert _status(handler) == 403
        store.save_project_transactional.assert_not_called()
        store.save_project.assert_not_called()

    def test_both_users_can_save_workspace_project(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"], "workspace")
        for user in (_USER_ALICE, _USER_BOB):
            handler, store = self._call_save(user, pid, prj)
            assert _status(handler) == 200, f"Expected 200 for {user['email']}"
            store.save_project_transactional.assert_called_once()

    def test_new_project_always_allowed(self):
        """A brand-new project (not yet in DB) is always allowed for any user."""
        pid = str(uuid.uuid4())
        body = json.dumps({"id": pid, "name": "New"}).encode()
        handler = _make_handler("/api/projects", body=body)
        mock_store = MagicMock()
        mock_store.get_project.return_value = None  # not found → new
        mock_store.save_project.return_value = _project(pid, _USER_BOB["id"])
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=_USER_BOB), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_post_projects()
        assert _status(handler) == 200
        # New projects use the non-transactional path
        mock_store.save_project.assert_called_once()
        mock_store.save_project_transactional.assert_not_called()

    def test_unauthenticated_save_returns_401(self):
        pid = str(uuid.uuid4())
        body = json.dumps({"id": pid, "name": "X"}).encode()
        handler = _make_handler("/api/projects", body=body)
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            handler._handle_post_projects()
        assert _status(handler) == 401

    def test_legacy_no_owner_private_writable_by_all(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, None, "private")
        handler, store = self._call_save(_USER_BOB, pid, prj)
        assert _status(handler) == 200
        store.save_project_transactional.assert_called_once()


# ===========================================================================
# API route tests: DELETE /api/projects/{id}
# ===========================================================================

class TestDeleteProject:
    """Delete enforces can_delete_project."""

    def _call_delete(self, user, project_id, existing_project):
        path = f"/api/projects/{project_id}"
        handler = _make_handler(path)
        mock_store = MagicMock()
        mock_store.get_project.return_value = existing_project
        mock_store.delete_project.return_value = True
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=user), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_delete_project()
        return handler, mock_store

    def test_owner_can_delete_own_private_project(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"], "private")
        handler, store = self._call_delete(_USER_ALICE, pid, prj)
        assert _status(handler) == 200
        store.delete_project.assert_called_once_with(pid)

    def test_non_owner_cannot_delete_private_project(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"], "private")
        handler, store = self._call_delete(_USER_BOB, pid, prj)
        assert _status(handler) == 403
        store.delete_project.assert_not_called()

    def test_non_owner_cannot_delete_workspace_project(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"], "workspace")
        handler, store = self._call_delete(_USER_BOB, pid, prj)
        assert _status(handler) == 403
        store.delete_project.assert_not_called()

    def test_owner_can_delete_workspace_project_they_own(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, _USER_ALICE["id"], "workspace")
        handler, store = self._call_delete(_USER_ALICE, pid, prj)
        assert _status(handler) == 200
        store.delete_project.assert_called_once_with(pid)

    def test_legacy_private_no_owner_not_deletable(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, None, "private")
        handler, store = self._call_delete(_USER_ALICE, pid, prj)
        assert _status(handler) == 403
        store.delete_project.assert_not_called()

    def test_legacy_workspace_no_owner_not_deletable(self):
        pid = str(uuid.uuid4())
        prj = _project(pid, None, "workspace")
        handler, store = self._call_delete(_USER_ALICE, pid, prj)
        assert _status(handler) == 403
        store.delete_project.assert_not_called()

    def test_missing_project_returns_404(self):
        pid = str(uuid.uuid4())
        handler, store = self._call_delete(_USER_ALICE, pid, None)
        assert _status(handler) == 404
        store.delete_project.assert_not_called()

    def test_unauthenticated_delete_returns_401(self):
        pid = str(uuid.uuid4())
        path = f"/api/projects/{pid}"
        handler = _make_handler(path)
        with patch.object(server, "IS_DESKTOP", False), \
             patch("auth.get_request_user", return_value=None):
            handler._handle_delete_project()
        assert _status(handler) == 401
