"""
tests/test_project_revision_endpoint.py — API tests for the lightweight revision endpoint.

Covers GET /api/projects/{id}/revision:
  - Returns correct fields (revision, updated_at, updated_by_email, updated_by_name)
  - 401 for unauthenticated requests
  - 403 for inaccessible (private) projects accessed by a non-owner
  - 404 for missing projects
  - Route dispatched via _handle_get_projects_sub
"""

from __future__ import annotations

import sys
import types
from io import BytesIO
from unittest.mock import MagicMock, patch
import uuid

import pytest

# ── Project root on sys.path ──────────────────────────────────────────────────

sys.path.insert(0, str(__file__).replace("/tests/test_project_revision_endpoint.py", ""))

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_handler(path: str, cookie: str = "bg_session=tok"):
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


def _project(project_id, owner_user_id, visibility="private"):
    return {
        "id": project_id,
        "name": "Sunday Service",
        "owner_user_id": owner_user_id,
        "visibility": visibility,
        "revision": 7,
        "updated_at": "2026-05-20T10:00:00+00:00",
        "updated_by_email": "alice@example.com",
        "updated_by_name": "Alice",
    }


def _call_revision(project_id, user, existing_project):
    """Call _handle_project_revision() and return (handler, mock_store)."""
    path = f"/api/projects/{project_id}/revision"
    handler = _make_handler(path=path)

    mock_store = MagicMock()
    mock_store.get_project.return_value = existing_project

    with patch("auth.get_request_user", return_value=user), \
         patch("storage.get_storage", return_value=mock_store):
        handler._handle_project_revision(project_id)

    return handler, mock_store


# ── Success ───────────────────────────────────────────────────────────────────

class TestProjectRevisionSuccess:
    """GET /api/projects/{id}/revision returns lightweight metadata for authorized users."""

    def test_returns_200(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_revision(project_id, _USER_ALICE, existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 200

    def test_response_has_revision_field(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_revision(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert "revision" in body

    def test_revision_value_is_correct(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_revision(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert body["revision"] == 7

    def test_response_has_updated_at(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_revision(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert body["updated_at"] == "2026-05-20T10:00:00+00:00"

    def test_response_has_updated_by_email(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_revision(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert body["updated_by_email"] == "alice@example.com"

    def test_response_has_updated_by_name(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_revision(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert body["updated_by_name"] == "Alice"

    def test_no_state_in_response(self):
        """The response must not include the state JSONB blob — keep it lightweight."""
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_revision(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert "state" not in body

    def test_owner_can_read_private_project_revision(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="private")
        handler, _ = _call_revision(project_id, _USER_ALICE, existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 200

    def test_non_owner_can_read_workspace_project_revision(self):
        """Bob can read revision metadata for a workspace project."""
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="workspace")
        handler, _ = _call_revision(project_id, _USER_BOB, existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 200

    def test_updated_by_email_falls_back_to_updatedBy(self):
        """Legacy projects without updated_by_email fall back to the updatedBy field."""
        project_id = str(uuid.uuid4())
        existing = {
            "id": project_id,
            "name": "Legacy",
            "owner_user_id": _USER_ALICE["id"],
            "visibility": "workspace",
            "revision": 3,
            "updated_at": "2026-05-20T10:00:00+00:00",
            "updated_by_email": None,
            "updatedBy": "alice@legacy.example.com",
        }
        handler, _ = _call_revision(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert body["updated_by_email"] == "alice@legacy.example.com"

    def test_updated_by_email_empty_string_when_missing(self):
        """updated_by_email returns empty string when no attribution info is available."""
        project_id = str(uuid.uuid4())
        existing = {
            "id": project_id,
            "name": "No attribution",
            "owner_user_id": _USER_ALICE["id"],
            "visibility": "workspace",
            "revision": 1,
            "updated_at": "2026-05-20T10:00:00+00:00",
        }
        handler, _ = _call_revision(project_id, _USER_ALICE, existing)

        body = handler._send_json.call_args[0][0]
        assert body["updated_by_email"] == ""


# ── Auth / Access ─────────────────────────────────────────────────────────────

class TestProjectRevisionAuthAccess:
    """Access control for GET /api/projects/{id}/revision."""

    def test_unauthenticated_returns_401(self):
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"])
        handler, _ = _call_revision(project_id, user=None, existing_project=existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 401

    def test_non_owner_private_project_returns_403(self):
        """Bob cannot read Alice's private project revision."""
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="private")
        handler, _ = _call_revision(project_id, _USER_BOB, existing)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 403

    def test_non_owner_private_project_store_not_queried_for_revision(self):
        """On 403, no further store calls should happen."""
        project_id = str(uuid.uuid4())
        existing = _project(project_id, _USER_ALICE["id"], visibility="private")
        _, store = _call_revision(project_id, _USER_BOB, existing)

        # Only get_project should have been called — nothing else.
        store.get_project.assert_called_once_with(project_id)

    def test_missing_project_returns_404(self):
        project_id = str(uuid.uuid4())
        handler, _ = _call_revision(project_id, _USER_ALICE, existing_project=None)

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 404


# ── Route Dispatch ────────────────────────────────────────────────────────────

class TestProjectRevisionRouteDispatch:
    """Verify that GET /api/projects/{id}/revision is dispatched correctly."""

    def test_revision_route_dispatched_via_get_projects_sub(self):
        project_id = str(uuid.uuid4())
        path = f"/api/projects/{project_id}/revision"
        handler = _make_handler(path=path)
        handler._handle_project_revision = MagicMock()

        handler._handle_get_projects_sub()

        handler._handle_project_revision.assert_called_once_with(project_id)

    def test_history_route_still_dispatched_correctly(self):
        """Adding /revision dispatch must not break existing /history dispatch."""
        project_id = str(uuid.uuid4())
        path = f"/api/projects/{project_id}/history"
        handler = _make_handler(path=path)
        handler._handle_project_history = MagicMock()

        handler._handle_get_projects_sub()

        handler._handle_project_history.assert_called_once_with(project_id)

    def test_unknown_sub_route_returns_404(self):
        project_id = str(uuid.uuid4())
        path = f"/api/projects/{project_id}/unknown"
        handler = _make_handler(path=path)

        handler._handle_get_projects_sub()

        args = handler._send_json.call_args[0]
        status = args[1] if len(args) > 1 else 200
        assert status == 404
