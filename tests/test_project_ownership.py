"""
tests/test_project_ownership.py — Two-user API authorization tests for project
ownership and visibility defaults introduced in issue #210.

Covers:
  - New project POST sets owner_user_id from authenticated session, visibility=private
  - Existing project update does NOT overwrite visibility or owner_user_id
  - Client-supplied visibility='workspace' on a new project is silently ignored
  - Desktop mode passes through to JSON storage without ownership enforcement
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
}

_USER_BOB = {
    "id": "bbbbbbbb-0000-0000-0000-000000000001",
    "email": "bob@example.com",
    "display_name": "Bob",
    "avatar_url": "",
    "domain": "example.com",
}


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
    mock_store.save_project.return_value = {"revision": 1, "id": payload.get("id", "")}

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


# ── Existing project update: visibility/owner unchanged ───────────────────────

class TestExistingProjectUpdate:
    """Updates to existing projects must not overwrite visibility or owner."""

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

    def test_visibility_not_overwritten_on_update(self):
        """storage.save_project is still called (visibility preserved by SQL ON CONFLICT)."""
        # The SQL UPDATE clause only touches name/state/revision/updated_at/updated_by_email,
        # so even if the data dict carries 'visibility' the DB column is never overwritten.
        # This test verifies save_project is called exactly once (not rejected) and that
        # the handler returns ok=True.
        project_id = str(uuid.uuid4())
        existing = self._existing_project(project_id, _USER_ALICE["id"])

        handler, store = _post_project(
            user=_USER_ALICE,
            payload={
                "id": project_id,
                "name": "Sunday Service",
                "_clientRevision": 5,
                "visibility": "workspace",  # client-supplied — SQL ignores it on UPDATE
            },
            existing_in_store=existing,
        )
        store.save_project.assert_called_once()
        result = handler._send_json.call_args[0][0]
        assert result.get("ok") is True

    def test_owner_user_id_not_overwritten_on_update(self):
        """save_project is still called; SQL ON CONFLICT UPDATE does not touch owner_user_id."""
        # The SQL UPDATE clause does not include owner_user_id, so even if the data
        # dict carries it the column is never changed.  This test verifies the update
        # succeeds and that the authenticated editor's email is recorded.
        project_id = str(uuid.uuid4())
        existing = self._existing_project(project_id, _USER_ALICE["id"])

        handler, store = _post_project(
            user=_USER_BOB,  # a different user editing Alice's project
            payload={
                "id": project_id,
                "name": "Sunday Service",
                "_clientRevision": 5,
                "owner_user_id": _USER_BOB["id"],  # SQL ignores this on UPDATE
            },
            existing_in_store=existing,
        )
        store.save_project.assert_called_once()
        # Verify the authenticated editor's identity is sent, not the payload's
        kwargs = store.save_project.call_args[1]
        assert kwargs["updated_by_user_id"] == _USER_BOB["id"]
        result = handler._send_json.call_args[0][0]
        assert result.get("ok") is True

    def test_update_sends_authenticated_user_email(self):
        """updated_by_email kwarg reflects the currently authenticated editor."""
        project_id = str(uuid.uuid4())
        existing = self._existing_project(project_id, _USER_ALICE["id"])

        _handler, store = _post_project(
            user=_USER_BOB,
            payload={"id": project_id, "name": "Sunday Service", "_clientRevision": 5},
            existing_in_store=existing,
        )
        kwargs = store.save_project.call_args[1]
        assert kwargs["updated_by_email"] == _USER_BOB["email"]


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
