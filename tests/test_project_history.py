"""
tests/test_project_history.py — API tests for project history and restore endpoints.

Covers:
  GET /api/projects/{id}/history:
    - Returns revision list with correct fields
    - Unauthorized user gets 403
    - Not found gets 404
    - Unauthenticated gets 401
    - Route dispatched via _handle_get_projects_sub

  POST /api/projects/{id}/restore:
    - Valid revision restores state as a new revision (200)
    - Stale _clientRevision → 409
    - Target revision not found → 404
    - Non-writer → 403
    - Unauthenticated → 401
    - Missing revision field → 400
    - Project not found → 404
    - Route dispatched via _handle_post_projects_sub
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

sys.path.insert(0, str(__file__).replace("/tests/test_project_history.py", ""))

# ── Python 3.13+ compatibility shim ──────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

# ── Imports ───────────────────────────────────────────────────────────────────

import server  # noqa: E402
from storage import ConflictError  # noqa: E402


# ── Users ─────────────────────────────────────────────────────────────────────

_USER_ALICE = {
    "id": "aaaaaaaa-0000-0000-0000-000000000001",
    "email": "alice@example.com",
    "display_name": "Alice",
    "avatar_url": "",
    "domain": "example.com",
}

_USER_BOB = {
    "id": "bbbbbbbb-0000-0000-0000-000000000001",
    "email": "bob@example.com",
    "display_name": "Bob",
    "avatar_url": "",
    "domain": "example.com",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_handler(path: str, body: bytes = b"", cookie: str = "bg_session=tok"):
    """Return a Handler instance with network-level methods stubbed out."""
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
    }
    handler.rfile = BytesIO(body)
    return handler


def _project(project_id, owner_user_id, visibility="private"):
    return {
        "id": project_id,
        "name": "Sunday Service",
        "owner_user_id": owner_user_id,
        "visibility": visibility,
        "revision": 5,
    }


def _sample_revisions(project_id):
    """Return a sample list of revision metadata dicts (newest first)."""
    return [
        {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "revision": 3,
            "saved_at": "2026-05-20T10:00:00+00:00",
            "saved_by_email": "alice@example.com",
            "saved_by_name": "Alice",
            "summary": "Updated song list",
        },
        {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "revision": 2,
            "saved_at": "2026-05-19T10:00:00+00:00",
            "saved_by_email": "alice@example.com",
            "saved_by_name": "Alice",
            "summary": "Added announcements",
        },
        {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "revision": 1,
            "saved_at": "2026-05-18T10:00:00+00:00",
            "saved_by_email": "alice@example.com",
            "saved_by_name": "Alice",
            "summary": "Initial save",
        },
    ]


def _call_history(project_id, user, existing_project, revisions=None):
    """Call _handle_project_history() and return (handler, mock_store)."""
    path = f"/api/projects/{project_id}/history"
    handler = _make_handler(path=path)

    if revisions is None:
        revisions = _sample_revisions(project_id) if existing_project else []

    mock_store = MagicMock()
    mock_store.get_project.return_value = existing_project
    mock_store.get_project_revisions.return_value = revisions

    with patch("auth.get_request_user", return_value=user), \
         patch("storage.get_storage", return_value=mock_store):
        handler._handle_project_history(project_id)

    return handler, mock_store


_SENTINEL = object()  # sentinel to distinguish "not supplied" from explicit None


def _call_restore(
    project_id,
    user,
    existing_project,
    snapshot=_SENTINEL,
    body_override=None,
    save_result=None,
    conflict_project=None,
):
    """Call _handle_project_restore() and return (handler, mock_store).

    Pass ``snapshot=None`` to simulate a missing target revision.
    Omit ``snapshot`` to get a default snapshot built from existing_project.
    """
    path = f"/api/projects/{project_id}/restore"
    target_revision = 2

    if body_override is None:
        body_payload = {"revision": target_revision, "_clientRevision": 5}
    else:
        body_payload = body_override

    body_bytes = json.dumps(body_payload).encode()
    handler = _make_handler(path=path, body=body_bytes)

    if snapshot is _SENTINEL and existing_project is not None:
        snapshot = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "revision": target_revision,
            "state": dict(existing_project, revision=target_revision),
            "saved_at": "2026-05-19T10:00:00+00:00",
            "saved_by_email": "alice@example.com",
            "saved_by_name": "Alice",
            "summary": "Added announcements",
        }
    elif snapshot is _SENTINEL:
        snapshot = None

    if save_result is None and existing_project is not None:
        save_result = dict(existing_project, revision=6)

    mock_store = MagicMock()
    mock_store.get_project.return_value = existing_project
    mock_store.get_project_revision.return_value = snapshot

    if conflict_project is not None:
        mock_store.save_project_transactional.side_effect = ConflictError(conflict_project)
    else:
        mock_store.save_project_transactional.return_value = save_result

    with patch("auth.get_request_user", return_value=user), \
         patch("storage.get_storage", return_value=mock_store):
        handler._handle_project_restore(project_id)

    return handler, mock_store


# ── History: Success ──────────────────────────────────────────────────────────

class TestProjectHistorySuccess:
    """GET /api/projects/{id}/history returns revision list for authorized users."""

    def test_returns_200(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_history(project_id, _USER_ALICE, existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 200

    def test_response_has_revisions_key(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_history(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert "revisions" in body

    def test_revisions_list_has_correct_fields(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        revisions = _sample_revisions(project_id)
        handler, _ = _call_history(project_id, _USER_ALICE, existing, revisions=revisions)

        body = handler._send_json.call_args[0][0]
        rev = body["revisions"][0]
        for field in ("revision", "saved_at", "saved_by_email", "saved_by_name", "summary"):
            assert field in rev, f"Field '{field}' missing from revision dict"

    def test_revisions_returned_newest_first(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        revisions = _sample_revisions(project_id)
        handler, _ = _call_history(project_id, _USER_ALICE, existing, revisions=revisions)

        body = handler._send_json.call_args[0][0]
        revision_numbers = [r["revision"] for r in body["revisions"]]
        assert revision_numbers == sorted(revision_numbers, reverse=True)

    def test_get_project_revisions_called_with_project_id(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        _, store = _call_history(project_id, _USER_ALICE, existing)

        store.get_project_revisions.assert_called_once_with(project_id)

    def test_owner_can_read_private_project_history(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="private")
        handler, _ = _call_history(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert "revisions" in body

    def test_empty_history_returns_empty_list(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_history(project_id, _USER_ALICE, existing, revisions=[])

        body = handler._send_json.call_args[0][0]
        assert body["revisions"] == []


# ── History: Auth/Access ──────────────────────────────────────────────────────

class TestProjectHistoryAuthAccess:
    """Access control for GET /api/projects/{id}/history."""

    def test_unauthenticated_returns_401(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        handler, _ = _call_history(project_id, user=None, existing_project=existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 401

    def test_unauthorized_user_returns_403(self):
        """Bob cannot read Alice's private project history."""
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="private")
        handler, _ = _call_history(project_id, _USER_BOB, existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 403

    def test_unauthorized_user_revisions_not_fetched(self):
        """Storage revisions should not be fetched for unauthorized users."""
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="private")
        _, store = _call_history(project_id, _USER_BOB, existing)

        store.get_project_revisions.assert_not_called()

    def test_workspace_project_accessible_by_non_owner(self):
        """Bob can read a workspace project's history."""
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_history(project_id, _USER_BOB, existing)

        body = handler._send_json.call_args[0][0]
        assert "revisions" in body

    def test_project_not_found_returns_404(self):
        project_id = str(uuid.uuid4())
        handler, _ = _call_history(project_id, _USER_ALICE, existing_project=None)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 404


# ── History: Route Dispatch ───────────────────────────────────────────────────

class TestProjectHistoryRouteDispatch:
    """Verify that GET /api/projects/{id}/history is dispatched correctly."""

    def test_history_route_dispatched_via_get_projects_sub(self):
        project_id = str(uuid.uuid4())
        path = f"/api/projects/{project_id}/history"
        handler = _make_handler(path=path)
        handler._handle_project_history = MagicMock()

        handler._handle_get_projects_sub()

        handler._handle_project_history.assert_called_once_with(project_id)

    def test_unknown_get_sub_route_returns_404(self):
        project_id = str(uuid.uuid4())
        path = f"/api/projects/{project_id}/unknown-action"
        handler = _make_handler(path=path)

        handler._handle_get_projects_sub()

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 404


# ── Restore: Success ──────────────────────────────────────────────────────────

class TestProjectRestoreSuccess:
    """POST /api/projects/{id}/restore creates a new revision from old state."""

    def test_returns_ok_true(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_restore(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert body.get("ok") is True

    def test_response_includes_project(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_restore(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert "project" in body

    def test_status_code_is_200(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_restore(project_id, _USER_ALICE, existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 200

    def test_save_project_transactional_called(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        _, store = _call_restore(project_id, _USER_ALICE, existing)

        store.save_project_transactional.assert_called_once()

    def test_save_called_with_correct_client_revision(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        body = {"revision": 2, "_clientRevision": 5}
        _, store = _call_restore(project_id, _USER_ALICE, existing, body_override=body)

        call_kwargs = store.save_project_transactional.call_args
        assert call_kwargs[1]["client_revision"] == 5

    def test_save_called_with_user_email(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        _, store = _call_restore(project_id, _USER_ALICE, existing)

        call_kwargs = store.save_project_transactional.call_args
        assert call_kwargs[1]["updated_by_email"] == _USER_ALICE["email"]

    def test_get_project_revision_called_with_correct_args(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        body = {"revision": 2, "_clientRevision": 5}
        _, store = _call_restore(project_id, _USER_ALICE, existing, body_override=body)

        store.get_project_revision.assert_called_once_with(project_id, 2)

    def test_new_revision_is_incremented(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        save_result = dict(existing, revision=6)
        handler, _ = _call_restore(
            project_id, _USER_ALICE, existing, save_result=save_result
        )

        body = handler._send_json.call_args[0][0]
        assert body["project"]["revision"] == 6


# ── Restore: Conflict ─────────────────────────────────────────────────────────

class TestProjectRestoreConflict:
    """Stale _clientRevision returns 409."""

    def test_stale_revision_returns_409(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        current_server = dict(existing, revision=7)
        handler, _ = _call_restore(
            project_id, _USER_ALICE, existing, conflict_project=current_server
        )

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 409

    def test_409_body_includes_server_revision(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        current_server = dict(existing, revision=7)
        handler, _ = _call_restore(
            project_id, _USER_ALICE, existing, conflict_project=current_server
        )

        body = handler._send_json.call_args[0][0]
        assert body.get("serverRevision") == 7

    def test_409_body_has_error_key(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        current_server = dict(existing, revision=7)
        handler, _ = _call_restore(
            project_id, _USER_ALICE, existing, conflict_project=current_server
        )

        body = handler._send_json.call_args[0][0]
        assert "error" in body


# ── Restore: Not Found ────────────────────────────────────────────────────────

class TestProjectRestoreNotFound:
    """404 cases for the restore endpoint."""

    def test_project_not_found_returns_404(self):
        project_id = str(uuid.uuid4())
        handler, _ = _call_restore(project_id, _USER_ALICE, existing_project=None)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 404

    def test_target_revision_not_found_returns_404(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        # snapshot=None simulates the revision not existing
        handler, _ = _call_restore(
            project_id, _USER_ALICE, existing, snapshot=None
        )

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 404

    def test_target_revision_not_found_save_not_called(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        _, store = _call_restore(
            project_id, _USER_ALICE, existing, snapshot=None
        )

        store.save_project_transactional.assert_not_called()


# ── Restore: Auth/Access ──────────────────────────────────────────────────────

class TestProjectRestoreAuthAccess:
    """Access control for POST /api/projects/{id}/restore."""

    def test_unauthenticated_returns_401(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        handler, _ = _call_restore(project_id, user=None, existing_project=existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 401

    def test_non_writer_returns_403(self):
        """Bob cannot restore Alice's private project."""
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="private")
        handler, _ = _call_restore(project_id, _USER_BOB, existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 403

    def test_non_writer_save_not_called(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="private")
        _, store = _call_restore(project_id, _USER_BOB, existing)

        store.save_project_transactional.assert_not_called()


# ── Restore: Bad Request ──────────────────────────────────────────────────────

class TestProjectRestoreBadRequest:
    """400 cases for the restore endpoint."""

    def test_missing_revision_field_returns_400(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_restore(
            project_id, _USER_ALICE, existing,
            body_override={"_clientRevision": 5}
        )

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 400

    def test_invalid_json_body_returns_400(self):
        project_id = str(uuid.uuid4())
        path = f"/api/projects/{project_id}/restore"
        handler = _make_handler(path=path, body=b"not-json")

        mock_store = MagicMock()
        mock_store.get_project.return_value = _project(
            project_id, _USER_ALICE["id"], visibility="workspace"
        )

        with patch("auth.get_request_user", return_value=_USER_ALICE), \
             patch("storage.get_storage", return_value=mock_store):
            handler._handle_project_restore(project_id)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 400

    def test_non_integer_revision_returns_400(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_restore(
            project_id, _USER_ALICE, existing,
            body_override={"revision": "notanumber", "_clientRevision": 5}
        )

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 400


# ── Restore: Route Dispatch ───────────────────────────────────────────────────

class TestProjectRestoreRouteDispatch:
    """Verify that POST /api/projects/{id}/restore is dispatched correctly."""

    def test_restore_route_dispatched_via_post_projects_sub(self):
        project_id = str(uuid.uuid4())
        path = f"/api/projects/{project_id}/restore"
        handler = _make_handler(path=path)
        handler._handle_project_restore = MagicMock()

        handler._handle_post_projects_sub()

        handler._handle_project_restore.assert_called_once_with(project_id)
