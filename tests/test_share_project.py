"""
tests/test_share_project.py — API tests for POST /api/projects/{id}/share

Covers:
  - Owner shares private project → 200, visibility='workspace'
  - Non-owner tries to share → 403
  - Sharing already-workspace project → 200 (idempotent)
  - Legacy imported project (no owner) → any authenticated user can share → 200
  - Not found → 404
  - Desktop mode → 404
  - Unauthenticated → 401
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

sys.path.insert(0, str(__file__).replace("/tests/test_share_project.py", ""))

# ── Python 3.13+ compatibility shim ──────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

# ── Imports ───────────────────────────────────────────────────────────────────

import server  # noqa: E402


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


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_handler(path: str = "/api/projects/some-id/share", cookie: str = "bg_session=tok"):
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
        "Content-Length": "0",
    }
    handler.rfile = BytesIO(b"")
    return handler


def _call_share(
    project_id: str,
    user,
    existing_project,
    shared_project=None,
    is_desktop: bool = False,
):
    """
    Call _handle_share_project() and return (handler, mock_store).

    *user* — authenticated user dict, or None to simulate unauthenticated.
    *existing_project* — what store.get_project() returns.
    *shared_project* — what store.share_project_to_workspace() returns
                       (defaults to existing_project with visibility='workspace').
    """
    path = f"/api/projects/{project_id}/share"
    handler = _make_handler(path=path)

    if shared_project is None and existing_project is not None:
        shared_project = dict(existing_project, visibility="workspace")

    mock_store = MagicMock()
    mock_store.get_project.return_value = existing_project
    mock_store.share_project_to_workspace.return_value = shared_project

    with patch.object(server, "IS_DESKTOP", is_desktop), \
         patch("auth.get_request_user", return_value=user), \
         patch("storage.get_storage", return_value=mock_store):
        handler._handle_share_project()

    return handler, mock_store


def _project(project_id, owner_user_id, visibility="private"):
    return {
        "id": project_id,
        "name": "Sunday Service",
        "owner_user_id": owner_user_id,
        "visibility": visibility,
        "revision": 3,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestShareProjectOwnerSuccess:
    """Owner sharing their private project succeeds."""

    def test_returns_ok_true(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        handler, _store = _call_share(project_id, _USER_ALICE, existing)

        handler._send_json.assert_called_once()
        body = handler._send_json.call_args[0][0]
        assert body.get("ok") is True

    def test_response_includes_project(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        handler, _store = _call_share(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert "project" in body
        assert body["project"]["visibility"] == "workspace"

    def test_share_project_to_workspace_called(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        _handler, store = _call_share(project_id, _USER_ALICE, existing)

        store.share_project_to_workspace.assert_called_once_with(project_id)

    def test_status_code_is_200(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        handler, _store = _call_share(project_id, _USER_ALICE, existing)

        # Default status for _send_json with no explicit code is 200.
        args = handler._send_json.call_args[0]
        kwargs = handler._send_json.call_args[1] if handler._send_json.call_args[1] else {}
        status = kwargs.get("status", args[1] if len(args) > 1 else 200)
        assert status == 200


class TestShareProjectNonOwnerForbidden:
    """Non-owner trying to share another user's private project is rejected."""

    def test_returns_403(self):
        project_id = str(uuid.uuid4())
        # Project is owned by Alice
        existing = _project(project_id, _USER_ALICE["id"])
        # Bob tries to share it
        handler, _store = _call_share(project_id, _USER_BOB, existing)

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 403

    def test_share_storage_not_called_for_non_owner(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        _handler, store = _call_share(project_id, _USER_BOB, existing)

        store.share_project_to_workspace.assert_not_called()

    def test_error_message_in_response(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        handler, _store = _call_share(project_id, _USER_BOB, existing)

        body = handler._send_json.call_args[0][0]
        assert "error" in body


class TestShareProjectIdempotent:
    """Sharing an already-workspace project succeeds (idempotent)."""

    def test_workspace_project_returns_ok(self):
        project_id = str(uuid.uuid4())
        # Project is already workspace-visible, owned by Alice
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _store = _call_share(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert body.get("ok") is True

    def test_storage_share_called_even_if_already_workspace(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        _handler, store = _call_share(project_id, _USER_ALICE, existing)

        store.share_project_to_workspace.assert_called_once_with(project_id)


class TestShareProjectLegacyImport:
    """Legacy imported projects (no owner) can be shared by any authenticated user."""

    def test_any_user_can_share_legacy_project(self):
        project_id = str(uuid.uuid4())
        # No owner — legacy imported project
        existing = _project(project_id, owner_user_id=None)
        handler, _store = _call_share(project_id, _USER_BOB, existing)

        body = handler._send_json.call_args[0][0]
        assert body.get("ok") is True

    def test_share_storage_called_for_legacy_project(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, owner_user_id=None)
        _handler, store = _call_share(project_id, _USER_BOB, existing)

        store.share_project_to_workspace.assert_called_once_with(project_id)


class TestShareProjectNotFound:
    """Sharing a non-existent project returns 404."""

    def test_returns_404_when_project_missing(self):
        project_id = str(uuid.uuid4())
        handler, _store = _call_share(project_id, _USER_ALICE, existing_project=None)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 404

    def test_share_storage_not_called_when_not_found(self):
        project_id = str(uuid.uuid4())
        _handler, store = _call_share(project_id, _USER_ALICE, existing_project=None)

        store.share_project_to_workspace.assert_not_called()


class TestShareProjectDesktopMode:
    """Desktop mode returns 404 for the share endpoint."""

    def test_desktop_returns_404(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, owner_user_id=None)
        handler, _store = _call_share(
            project_id, _USER_ALICE, existing, is_desktop=True
        )

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 404

    def test_desktop_share_storage_not_called(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, owner_user_id=None)
        _handler, store = _call_share(
            project_id, _USER_ALICE, existing, is_desktop=True
        )
        store.share_project_to_workspace.assert_not_called()


class TestShareProjectUnauthenticated:
    """Unauthenticated requests are rejected with 401."""

    def test_unauthenticated_returns_401(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        handler, _store = _call_share(
            project_id, user=None, existing_project=existing
        )

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 401

    def test_unauthenticated_share_storage_not_called(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        _handler, store = _call_share(
            project_id, user=None, existing_project=existing
        )
        store.share_project_to_workspace.assert_not_called()


class TestShareProjectRouteDispatch:
    """Verify that the POST /api/projects/{id}/share route is dispatched correctly."""

    def test_share_route_dispatched_via_post_routes(self):
        """_handle_post_projects_sub must dispatch /api/projects/{id}/share."""
        project_id = str(uuid.uuid4())
        path = f"/api/projects/{project_id}/share"
        handler = _make_handler(path=path)
        handler._handle_share_project = MagicMock()

        handler._handle_post_projects_sub()

        handler._handle_share_project.assert_called_once()

    def test_unknown_sub_route_returns_404(self):
        """Unknown sub-route under /api/projects/ returns 404."""
        project_id = str(uuid.uuid4())
        path = f"/api/projects/{project_id}/unknown-action"
        handler = _make_handler(path=path)

        handler._handle_post_projects_sub()

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 404
