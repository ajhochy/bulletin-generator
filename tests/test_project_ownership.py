"""
tests/test_project_ownership.py — API authorization tests for project
ownership, owner-only writes, and ownership transfer (issues #210, #021).

Covers:
  - New project POST sets owner_user_id from authenticated session, visibility=private
  - Existing project update does NOT overwrite visibility or owner_user_id
  - Client-supplied visibility='workspace' on a new project is silently ignored
  - Desktop mode passes through to JSON storage without ownership enforcement
  - Owner can save their own project (200 ok)
  - Non-owner gets 403 when trying to save an existing project
  - _clientRevision is ignored (no ConflictError raised)
  - POST /api/projects/{id}/transfer: owner can transfer, non-owner gets 403,
    non-member gets 400, missing project gets 404
"""

from __future__ import annotations

import json
import sys
import types
import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ── Project root on sys.path ──────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Python 3.13+ compatibility shim ──────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

# ── Imports ───────────────────────────────────────────────────────────────────

import server  # noqa: E402


# ── Fixtures / shared helpers ─────────────────────────────────────────────────

_USER_ALICE = {
    "id": "aaaaaaaa-0000-0000-0000-000000000001",
    "email": "alice@example.com",
    "display_name": "Alice",
    "avatar_url": "",
    "domain": "example.com",
    "workspace_id": "wwwwwwww-0000-0000-0000-000000000001",
}

_USER_BOB = {
    "id": "bbbbbbbb-0000-0000-0000-000000000001",
    "email": "bob@example.com",
    "display_name": "Bob",
    "avatar_url": "",
    "domain": "example.com",
    "workspace_id": "wwwwwwww-0000-0000-0000-000000000001",
}

_WORKSPACE_ID = "wwwwwwww-0000-0000-0000-000000000001"


def _make_handler(body: bytes = b"", path: str = "/api/projects", cookie: str = "bg_session=tok"):
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


def _post_project(user: dict, payload: dict, existing_in_store=None):
    """
    Call _handle_post_projects() in server mode as *user* with *payload*.

    *existing_in_store* — what store.get_project() returns (None = new project).

    Returns (handler, mock_store) after the call.
    """
    body = json.dumps(payload).encode()
    handler = _make_handler(body=body)

    mock_store = MagicMock()
    mock_store.get_project.return_value = existing_in_store
    project_id = payload.get("id", "")
    # Both new and existing projects now use save_project() (issue 021).
    saved_revision = (existing_in_store.get("revision") or 1) + 1 if existing_in_store else 1
    mock_store.save_project.return_value = {"revision": saved_revision, "id": project_id}

    with patch.object(server, "IS_DESKTOP", False), \
         patch("auth.get_request_user", return_value=user), \
         patch("storage.get_storage", return_value=mock_store):
        handler._handle_post_projects()

    return handler, mock_store


# ── New project: ownership set from session ───────────────────────────────────

class TestNewProjectOwnership:
    """New projects (no existing row in store) must be owned by the authed user."""

    def test_save_project_called_with_authenticated_user_id(self):
        """owner_user_id in save_project kwarg matches the authenticated user."""
        project_id = str(uuid.uuid4())
        _handler, store = _post_project(
            user=_USER_ALICE,
            payload={"id": project_id, "name": "Sunday Service"},
            existing_in_store=None,  # new project
        )
        store.save_project.assert_called_once()
        kwargs = store.save_project.call_args[1]
        assert kwargs["updated_by_user_id"] == _USER_ALICE["id"]

    def test_save_project_called_with_authenticated_email(self):
        """updated_by_email in save_project kwarg matches the authenticated user."""
        project_id = str(uuid.uuid4())
        _handler, store = _post_project(
            user=_USER_ALICE,
            payload={"id": project_id, "name": "Sunday Service"},
            existing_in_store=None,
        )
        kwargs = store.save_project.call_args[1]
        assert kwargs["updated_by_email"] == _USER_ALICE["email"]

    def test_client_supplied_visibility_removed_for_new_project(self):
        """Client cannot override visibility for new projects — the field is stripped."""
        project_id = str(uuid.uuid4())
        _handler, store = _post_project(
            user=_USER_ALICE,
            payload={"id": project_id, "name": "Test", "visibility": "workspace"},
            existing_in_store=None,
        )
        store.save_project.assert_called_once()
        saved_data = store.save_project.call_args[0][0]  # positional data dict
        assert "visibility" not in saved_data, (
            "Client-supplied visibility must not reach storage for new projects"
        )

    def test_client_supplied_owner_user_id_removed_for_new_project(self):
        """Client cannot set owner_user_id in the payload for new projects."""
        project_id = str(uuid.uuid4())
        _handler, store = _post_project(
            user=_USER_ALICE,
            payload={
                "id": project_id,
                "name": "Test",
                "owner_user_id": _USER_BOB["id"],  # client tries to claim Bob's ownership
            },
            existing_in_store=None,
        )
        saved_data = store.save_project.call_args[0][0]
        assert "owner_user_id" not in saved_data, (
            "Client-supplied owner_user_id must not reach storage for new projects"
        )

    def test_response_is_ok(self):
        """A successful new-project POST returns {"ok": True, ...}."""
        project_id = str(uuid.uuid4())
        handler, _store = _post_project(
            user=_USER_ALICE,
            payload={"id": project_id, "name": "Sunday Service"},
            existing_in_store=None,
        )
        handler._send_json.assert_called_once()
        result = handler._send_json.call_args[0][0]
        assert result.get("ok") is True


# ── Existing project update: owner-only, visibility/owner column preserved ────

class TestExistingProjectUpdate:
    """Updates to existing projects: only the owner may save; SQL UPDATE preserves
    visibility and owner_user_id columns (they are not in the SET clause)."""

    def _existing_project(self, project_id: str, owner_id: str) -> dict:
        return {
            "id": project_id,
            "name": "Sunday Service",
            "owner_user_id": owner_id,
            "visibility": "private",
            "revision": 5,
            "updatedAt": "2026-01-01T00:00:00Z",
            "updatedBy": "alice@example.com",
        }

    def test_owner_can_save_existing_project(self):
        """The project owner's POST returns 200 ok and calls save_project."""
        project_id = str(uuid.uuid4())
        existing = self._existing_project(project_id, _USER_ALICE["id"])

        handler, store = _post_project(
            user=_USER_ALICE,
            payload={"id": project_id, "name": "Sunday Service"},
            existing_in_store=existing,
        )
        store.save_project.assert_called_once()
        result = handler._send_json.call_args[0][0]
        assert result.get("ok") is True

    def test_non_owner_gets_403(self):
        """A non-owner POST to an existing project returns 403."""
        project_id = str(uuid.uuid4())
        existing = self._existing_project(project_id, _USER_ALICE["id"])  # Alice owns it

        handler, store = _post_project(
            user=_USER_BOB,  # Bob is not the owner
            payload={"id": project_id, "name": "Sunday Service"},
            existing_in_store=existing,
        )
        # save_project must NOT be called
        store.save_project.assert_not_called()
        # Response must be 403
        args = handler._send_json.call_args[0]
        assert args[1] == 403
        assert "owner" in args[0]["error"].lower()

    def test_client_revision_ignored(self):
        """_clientRevision in the payload is silently discarded; save proceeds."""
        project_id = str(uuid.uuid4())
        existing = self._existing_project(project_id, _USER_ALICE["id"])

        handler, store = _post_project(
            user=_USER_ALICE,
            payload={"id": project_id, "name": "Sunday Service", "_clientRevision": 99},
            existing_in_store=existing,
        )
        store.save_project.assert_called_once()
        # _clientRevision must not appear in the data passed to save_project
        saved_data = store.save_project.call_args[0][0]
        assert "_clientRevision" not in saved_data
        result = handler._send_json.call_args[0][0]
        assert result.get("ok") is True

    def test_update_sends_authenticated_user_email(self):
        """updated_by_email kwarg reflects the currently authenticated editor."""
        project_id = str(uuid.uuid4())
        existing = self._existing_project(project_id, _USER_ALICE["id"])

        _handler, store = _post_project(
            user=_USER_ALICE,
            payload={"id": project_id, "name": "Sunday Service"},
            existing_in_store=existing,
        )
        kwargs = store.save_project.call_args[1]
        assert kwargs["updated_by_email"] == _USER_ALICE["email"]

    def test_update_sends_authenticated_user_id(self):
        """updated_by_user_id kwarg reflects the authenticated user, not the payload."""
        project_id = str(uuid.uuid4())
        existing = self._existing_project(project_id, _USER_ALICE["id"])

        _handler, store = _post_project(
            user=_USER_ALICE,
            payload={
                "id": project_id,
                "name": "Sunday Service",
                "owner_user_id": _USER_BOB["id"],  # SQL UPDATE ignores this column
            },
            existing_in_store=existing,
        )
        kwargs = store.save_project.call_args[1]
        assert kwargs["updated_by_user_id"] == _USER_ALICE["id"]

    def test_project_with_no_owner_is_allowed(self):
        """A project with owner_user_id=None (legacy import) allows any authenticated user."""
        project_id = str(uuid.uuid4())
        existing = self._existing_project(project_id, owner_id=None)
        existing["owner_user_id"] = None  # explicit None

        handler, store = _post_project(
            user=_USER_BOB,  # Bob is not the owner, but there is no owner
            payload={"id": project_id, "name": "Legacy Project"},
            existing_in_store=existing,
        )
        store.save_project.assert_called_once()
        result = handler._send_json.call_args[0][0]
        assert result.get("ok") is True


# ── Desktop mode: ownership enforcement is skipped ───────────────────────────

class TestDesktopModeOwnership:
    """In desktop mode the server bypasses server-mode ownership logic entirely."""

    def test_desktop_mode_writes_to_json_file(self, tmp_path, monkeypatch):
        """Desktop-mode POST writes to the JSON project file, not Postgres."""
        import server as srv

        project_id = str(uuid.uuid4())
        payload = {"id": project_id, "name": "Desktop Project"}

        projects_file = tmp_path / "projects.json"
        projects_file.write_text("[]")

        body = json.dumps(payload).encode()
        handler = _make_handler(body=body, cookie="")

        with patch.object(srv, "IS_DESKTOP", True), \
             patch.object(srv, "APP_MODE", "desktop"), \
             patch.object(srv, "PROJECTS_FILE", str(projects_file)), \
             patch.object(srv, "_lock", __import__("threading").Lock()), \
             patch.object(srv, "_read_json", lambda path, default: json.loads(projects_file.read_text()) if Path(path) == projects_file else default), \
             patch.object(srv, "_write_json", lambda path, data: projects_file.write_text(json.dumps(data))):
            handler._handle_post_projects()

        handler._send_json.assert_called_once()
        result = handler._send_json.call_args[0][0]
        assert result.get("ok") is True


# ── Transfer endpoint ─────────────────────────────────────────────────────────

def _call_transfer(
    user: dict,
    project_id: str,
    body: dict,
    existing_project=None,
    to_user_is_member: bool = True,
):
    """
    Call _handle_post_transfer_project() in server mode.

    Returns (handler, mock_store).
    """
    raw_body = json.dumps(body).encode()
    path = f"/api/projects/{project_id}/transfer"
    handler = _make_handler(body=raw_body, path=path)

    mock_store = MagicMock()
    mock_store.get_project.return_value = existing_project
    if existing_project is not None:
        mock_store.transfer_project_owner.return_value = {
            **existing_project,
            "owner_user_id": body.get("to_user_id"),
        }

    # Mock the DB membership check.
    membership_row = (body.get("to_user_id"),) if to_user_is_member else None

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = membership_row

    class _FakeCtx:
        def __enter__(self_inner):
            return mock_conn
        def __exit__(self_inner, *a):
            pass

    with patch.object(server, "IS_DESKTOP", False), \
         patch("auth.get_request_user", return_value=user), \
         patch("storage.get_storage", return_value=mock_store), \
         patch("db.admin_transaction", return_value=_FakeCtx()):
        handler._handle_post_transfer_project(project_id)

    return handler, mock_store


class TestTransferProjectOwner:
    """POST /api/projects/{id}/transfer endpoint."""

    def _owned_project(self, project_id: str, owner_id: str) -> dict:
        return {
            "id": project_id,
            "name": "Sunday Service",
            "owner_user_id": owner_id,
            "visibility": "private",
            "revision": 3,
        }

    def test_owner_can_transfer(self):
        """Project owner can transfer ownership to a workspace member."""
        project_id = str(uuid.uuid4())
        existing = self._owned_project(project_id, _USER_ALICE["id"])

        handler, store = _call_transfer(
            user=_USER_ALICE,
            project_id=project_id,
            body={"to_user_id": _USER_BOB["id"]},
            existing_project=existing,
            to_user_is_member=True,
        )

        store.transfer_project_owner.assert_called_once_with(
            project_id,
            from_user_id=_USER_ALICE["id"],
            to_user_id=_USER_BOB["id"],
        )
        result = handler._send_json.call_args[0][0]
        assert result.get("ok") is True
        assert result.get("new_owner") == _USER_BOB["id"]

    def test_non_owner_gets_403(self):
        """A non-owner caller attempting transfer receives 403."""
        project_id = str(uuid.uuid4())
        existing = self._owned_project(project_id, _USER_ALICE["id"])  # Alice owns it

        handler, store = _call_transfer(
            user=_USER_BOB,  # Bob is not the owner
            project_id=project_id,
            body={"to_user_id": _USER_ALICE["id"]},
            existing_project=existing,
            to_user_is_member=True,
        )

        store.transfer_project_owner.assert_not_called()
        args = handler._send_json.call_args[0]
        assert args[1] == 403

    def test_transfer_to_non_member_gets_400(self):
        """Transferring to a user not in the workspace returns 400."""
        project_id = str(uuid.uuid4())
        existing = self._owned_project(project_id, _USER_ALICE["id"])
        stranger_id = str(uuid.uuid4())

        handler, store = _call_transfer(
            user=_USER_ALICE,
            project_id=project_id,
            body={"to_user_id": stranger_id},
            existing_project=existing,
            to_user_is_member=False,  # not a member
        )

        store.transfer_project_owner.assert_not_called()
        args = handler._send_json.call_args[0]
        assert args[1] == 400
        assert "member" in args[0]["error"].lower()

    def test_project_not_found_returns_404(self):
        """Transferring a non-existent project returns 404."""
        project_id = str(uuid.uuid4())

        handler, store = _call_transfer(
            user=_USER_ALICE,
            project_id=project_id,
            body={"to_user_id": _USER_BOB["id"]},
            existing_project=None,  # project doesn't exist
            to_user_is_member=True,
        )

        store.transfer_project_owner.assert_not_called()
        args = handler._send_json.call_args[0]
        assert args[1] == 404

    def test_missing_to_user_id_returns_400(self):
        """Missing to_user_id in the body returns 400."""
        project_id = str(uuid.uuid4())
        existing = self._owned_project(project_id, _USER_ALICE["id"])

        handler, store = _call_transfer(
            user=_USER_ALICE,
            project_id=project_id,
            body={},  # no to_user_id
            existing_project=existing,
            to_user_is_member=True,
        )

        store.transfer_project_owner.assert_not_called()
        args = handler._send_json.call_args[0]
        assert args[1] == 400

    def test_desktop_mode_returns_404(self):
        """Transfer endpoint is not available in desktop mode."""
        project_id = str(uuid.uuid4())
        raw_body = json.dumps({"to_user_id": _USER_BOB["id"]}).encode()
        path = f"/api/projects/{project_id}/transfer"
        handler = _make_handler(body=raw_body, path=path)

        with patch.object(server, "IS_DESKTOP", True):
            handler._handle_post_transfer_project(project_id)

        args = handler._send_json.call_args[0]
        assert args[1] == 404
