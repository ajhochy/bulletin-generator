"""
tests/test_fonts.py — Unit tests for font upload / list / delete round-trip.

Covers:
  - storage.py JsonStorageBackend: save_font writes to local FS, delete_font removes it
  - storage.py PostgresStorageBackend: save_font calls Supabase Storage REST API +
    INSERT, delete_font calls Storage DELETE + DB DELETE
  - _supabase_storage_url: builds correct URL from SUPABASE_URL env var
  - _supabase_storage_upload / _supabase_storage_delete: correct HTTP calls
  - server.py _handle_post_fonts / _handle_get_fonts / _handle_delete_font in
    server mode (via Handler mocks)

No live database or Supabase project required — all Storage/DB calls are mocked.
"""

from __future__ import annotations

import json
import sys
import types
import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ── Path setup ──────────────────────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Python 3.13+ compatibility shim ──────────────────────────────────────────

if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

# ── Imports ───────────────────────────────────────────────────────────────────

import storage  # noqa: E402
from storage import (  # noqa: E402
    JsonStorageBackend,
    PostgresStorageBackend,
    _supabase_storage_url,
    _supabase_storage_upload,
    _supabase_storage_delete,
)


# ===========================================================================
# Helpers
# ===========================================================================

FAKE_WORKSPACE_ID = str(uuid.uuid4())
FAKE_FONT_ID = str(uuid.uuid4())
FONT_BYTES = b"WOFF2_FONT_BINARY_DATA"
SUPABASE_URL = "https://test-ref.supabase.co"
SERVICE_ROLE_KEY = "test-service-role-key"


def _mock_urlopen_success(status=200, body=b'{"Key": "workspace-fonts/test.woff2"}'):
    """Return a mock urllib response context manager."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _make_pg_transaction(rows=None, rowcount=1):
    """Return a mock transaction context manager for PostgresStorageBackend._transaction."""
    cursor = MagicMock()
    cursor.fetchone.return_value = rows[0] if rows else None
    cursor.fetchall.return_value = rows or []
    cursor.rowcount = rowcount
    cursor.description = []  # no columns by default
    conn = MagicMock()
    conn.execute.return_value = cursor

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, conn, cursor


# ===========================================================================
# _supabase_storage_url
# ===========================================================================

class TestSupabaseStorageUrl:
    def test_returns_correct_url(self):
        with patch.dict("os.environ", {"SUPABASE_URL": SUPABASE_URL}):
            url = _supabase_storage_url("workspace-fonts/abc/font.woff2")
        assert url == f"{SUPABASE_URL}/storage/v1/object/public/workspace-fonts/abc/font.woff2"

    def test_empty_when_supabase_url_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            url = _supabase_storage_url("workspace-fonts/abc/font.woff2")
        assert url == ""

    def test_empty_when_storage_path_empty(self):
        with patch.dict("os.environ", {"SUPABASE_URL": SUPABASE_URL}):
            url = _supabase_storage_url("")
        assert url == ""

    def test_strips_trailing_slash_from_supabase_url(self):
        with patch.dict("os.environ", {"SUPABASE_URL": SUPABASE_URL + "/"}):
            url = _supabase_storage_url("bucket/obj")
        assert "//" not in url.replace("https://", "")


# ===========================================================================
# _supabase_storage_upload
# ===========================================================================

class TestSupabaseStorageUpload:
    def _env(self):
        return {"SUPABASE_URL": SUPABASE_URL, "SUPABASE_SERVICE_ROLE_KEY": SERVICE_ROLE_KEY}

    def test_makes_post_request(self):
        resp = _mock_urlopen_success()
        with patch.dict("os.environ", self._env()), \
             patch("urllib.request.urlopen", return_value=resp) as mock_open:
            _supabase_storage_upload("workspace-fonts/ws/font.woff2", FONT_BYTES, "font/woff2")
        mock_open.assert_called_once()

    def test_authorization_header(self):
        resp = _mock_urlopen_success()
        captured_req = {}
        def fake_urlopen(req, timeout=None):
            captured_req["req"] = req
            return resp
        with patch.dict("os.environ", self._env()), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _supabase_storage_upload("workspace-fonts/ws/font.woff2", FONT_BYTES, "font/woff2")
        assert captured_req["req"].get_header("Authorization") == f"Bearer {SERVICE_ROLE_KEY}"

    def test_content_type_header(self):
        resp = _mock_urlopen_success()
        captured_req = {}
        def fake_urlopen(req, timeout=None):
            captured_req["req"] = req
            return resp
        with patch.dict("os.environ", self._env()), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _supabase_storage_upload("workspace-fonts/ws/font.woff2", FONT_BYTES, "font/woff2")
        assert captured_req["req"].get_header("Content-type") == "font/woff2"

    def test_upsert_header(self):
        resp = _mock_urlopen_success()
        captured_req = {}
        def fake_urlopen(req, timeout=None):
            captured_req["req"] = req
            return resp
        with patch.dict("os.environ", self._env()), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _supabase_storage_upload("workspace-fonts/ws/font.woff2", FONT_BYTES, "font/woff2")
        assert captured_req["req"].get_header("X-upsert") == "true"

    def test_returns_public_url(self):
        resp = _mock_urlopen_success()
        with patch.dict("os.environ", self._env()), \
             patch("urllib.request.urlopen", return_value=resp):
            url = _supabase_storage_upload("workspace-fonts/ws/font.woff2", FONT_BYTES, "font/woff2")
        assert url == f"{SUPABASE_URL}/storage/v1/object/public/workspace-fonts/ws/font.woff2"

    def test_raises_when_supabase_url_missing(self):
        with patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": SERVICE_ROLE_KEY}, clear=True):
            with pytest.raises(RuntimeError, match="SUPABASE_URL"):
                _supabase_storage_upload("bucket/file.woff2", FONT_BYTES, "font/woff2")

    def test_raises_when_service_role_key_missing(self):
        with patch.dict("os.environ", {"SUPABASE_URL": SUPABASE_URL}, clear=True):
            with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_ROLE_KEY"):
                _supabase_storage_upload("bucket/file.woff2", FONT_BYTES, "font/woff2")

    def test_raises_on_network_error(self):
        import urllib.error
        with patch.dict("os.environ", self._env()), \
             patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(RuntimeError, match="Storage upload failed"):
                _supabase_storage_upload("bucket/file.woff2", FONT_BYTES, "font/woff2")


# ===========================================================================
# _supabase_storage_delete
# ===========================================================================

class TestSupabaseStorageDelete:
    def _env(self):
        return {"SUPABASE_URL": SUPABASE_URL, "SUPABASE_SERVICE_ROLE_KEY": SERVICE_ROLE_KEY}

    def test_makes_delete_request(self):
        resp = _mock_urlopen_success()
        with patch.dict("os.environ", self._env()), \
             patch("urllib.request.urlopen", return_value=resp) as mock_open:
            _supabase_storage_delete("workspace-fonts/ws/font.woff2")
        mock_open.assert_called_once()

    def test_delete_target_is_bucket_endpoint(self):
        resp = _mock_urlopen_success()
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["req"] = req
            return resp
        with patch.dict("os.environ", self._env()), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _supabase_storage_delete("workspace-fonts/ws/font.woff2")
        # URL should target the bucket, not the full object path.
        assert captured["req"].full_url == f"{SUPABASE_URL}/storage/v1/object/workspace-fonts"

    def test_delete_body_contains_prefixes(self):
        resp = _mock_urlopen_success()
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["req"] = req
            return resp
        with patch.dict("os.environ", self._env()), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _supabase_storage_delete("workspace-fonts/ws/font.woff2")
        body = json.loads(captured["req"].data.decode("utf-8"))
        assert body == {"prefixes": ["ws/font.woff2"]}

    def test_raises_on_invalid_path(self):
        with patch.dict("os.environ", self._env()):
            with pytest.raises(RuntimeError, match="Invalid storage_path"):
                _supabase_storage_delete("no-slash-here")

    def test_raises_when_env_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError):
                _supabase_storage_delete("workspace-fonts/ws/font.woff2")


# ===========================================================================
# JsonStorageBackend.save_font / delete_font  (desktop mode)
# ===========================================================================

class TestJsonStorageBackendFonts:
    def test_save_font_writes_file(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        result = backend.save_font("Open Sans", "opensans.woff2", FONT_BYTES, "font/woff2")
        dest = tmp_path / "fonts" / "user" / "open-sans" / "opensans.woff2"
        assert dest.exists()
        assert dest.read_bytes() == FONT_BYTES

    def test_save_font_returns_id_name_url(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        result = backend.save_font("Open Sans", "opensans.woff2", FONT_BYTES, "font/woff2")
        assert result["id"] == "open-sans"
        assert result["name"] == "Open Sans"
        assert result["url"] == "/fonts/user/open-sans/font.css"

    def test_save_font_safe_filename(self, tmp_path):
        """Filename with unusual chars is sanitised before writing."""
        backend = JsonStorageBackend(tmp_path)
        backend.save_font("My Font", "my font!!.woff2", FONT_BYTES, "font/woff2")
        slug_dir = tmp_path / "fonts" / "user" / "my-font"
        files = list(slug_dir.iterdir())
        assert len(files) == 1
        assert " " not in files[0].name

    def test_save_font_creates_dirs(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_font("Roboto", "roboto.ttf", FONT_BYTES, "font/truetype")
        assert (tmp_path / "fonts" / "user" / "roboto").is_dir()

    def test_delete_font_removes_directory(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_font("Roboto", "roboto.woff2", FONT_BYTES, "font/woff2")
        removed = backend.delete_font("roboto")
        assert removed is True
        assert not (tmp_path / "fonts" / "user" / "roboto").exists()

    def test_delete_font_missing_returns_false(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        result = backend.delete_font("does-not-exist")
        assert result is False

    def test_save_then_list_round_trip(self, tmp_path):
        backend = JsonStorageBackend(tmp_path)
        backend.save_font("Lato", "lato.woff2", FONT_BYTES, "font/woff2")
        fonts = backend.list_fonts()
        assert any(f["slug"] == "lato" for f in fonts)


# ===========================================================================
# PostgresStorageBackend.save_font  (server mode, mocked Storage + DB)
# ===========================================================================

class TestPostgresStorageBackendSaveFont:
    def _env(self):
        return {
            "SUPABASE_URL": SUPABASE_URL,
            "SUPABASE_SERVICE_ROLE_KEY": SERVICE_ROLE_KEY,
            "APP_MODE": "server",
        }

    def test_save_font_calls_storage_upload(self):
        backend = PostgresStorageBackend(workspace_id=FAKE_WORKSPACE_ID)
        ctx, conn, cursor = _make_pg_transaction(rows=[(FAKE_FONT_ID,)])
        cursor.description = [("id",)]

        with patch.dict("os.environ", self._env()), \
             patch.object(backend, "_transaction", return_value=ctx), \
             patch("storage._supabase_storage_upload", return_value=f"{SUPABASE_URL}/storage/v1/object/public/workspace-fonts/{FAKE_WORKSPACE_ID}/font.woff2") as mock_upload:
            backend.save_font("Open Sans", "opensans.woff2", FONT_BYTES, "font/woff2")

        mock_upload.assert_called_once_with(
            f"workspace-fonts/{FAKE_WORKSPACE_ID}/opensans.woff2",
            FONT_BYTES,
            "font/woff2",
        )

    def test_save_font_inserts_db_row(self):
        backend = PostgresStorageBackend(workspace_id=FAKE_WORKSPACE_ID)
        ctx, conn, cursor = _make_pg_transaction(rows=[(FAKE_FONT_ID,)])
        cursor.description = [("id",)]
        storage_url = f"{SUPABASE_URL}/storage/v1/object/public/workspace-fonts/{FAKE_WORKSPACE_ID}/opensans.woff2"

        with patch.dict("os.environ", self._env()), \
             patch.object(backend, "_transaction", return_value=ctx), \
             patch("storage._supabase_storage_upload", return_value=storage_url):
            backend.save_font("Open Sans", "opensans.woff2", FONT_BYTES, "font/woff2")

        conn.execute.assert_called_once()
        sql = conn.execute.call_args[0][0]
        assert "INSERT INTO fonts" in sql
        assert "RETURNING id" in sql

    def test_save_font_returns_id_name_url(self):
        backend = PostgresStorageBackend(workspace_id=FAKE_WORKSPACE_ID)
        ctx, conn, cursor = _make_pg_transaction(rows=[(FAKE_FONT_ID,)])
        cursor.description = [("id",)]
        storage_url = f"{SUPABASE_URL}/storage/v1/object/public/workspace-fonts/{FAKE_WORKSPACE_ID}/opensans.woff2"

        with patch.dict("os.environ", self._env()), \
             patch.object(backend, "_transaction", return_value=ctx), \
             patch("storage._supabase_storage_upload", return_value=storage_url):
            result = backend.save_font("Open Sans", "opensans.woff2", FONT_BYTES, "font/woff2")

        assert result["id"] == FAKE_FONT_ID
        assert result["name"] == "Open Sans"
        assert result["url"] == storage_url

    def test_save_font_raises_without_workspace_id(self):
        backend = PostgresStorageBackend(workspace_id=None)
        with pytest.raises(RuntimeError, match="workspace_id"):
            backend.save_font("Font", "font.woff2", FONT_BYTES, "font/woff2")

    def test_storage_path_includes_workspace_id(self):
        """The Storage path must be workspace-scoped for isolation."""
        backend = PostgresStorageBackend(workspace_id=FAKE_WORKSPACE_ID)
        ctx, conn, cursor = _make_pg_transaction(rows=[(FAKE_FONT_ID,)])
        cursor.description = [("id",)]

        with patch.dict("os.environ", self._env()), \
             patch.object(backend, "_transaction", return_value=ctx), \
             patch("storage._supabase_storage_upload", return_value="https://x") as mock_upload:
            backend.save_font("Font", "font.woff2", FONT_BYTES, "font/woff2")

        path_arg = mock_upload.call_args[0][0]
        assert path_arg.startswith(f"workspace-fonts/{FAKE_WORKSPACE_ID}/")


# ===========================================================================
# PostgresStorageBackend.delete_font  (server mode, mocked Storage + DB)
# ===========================================================================

class TestPostgresStorageBackendDeleteFont:
    def _env(self):
        return {
            "SUPABASE_URL": SUPABASE_URL,
            "SUPABASE_SERVICE_ROLE_KEY": SERVICE_ROLE_KEY,
            "APP_MODE": "server",
        }

    def test_delete_font_returns_true_when_found(self):
        backend = PostgresStorageBackend(workspace_id=FAKE_WORKSPACE_ID)
        storage_path = f"workspace-fonts/{FAKE_WORKSPACE_ID}/font.woff2"

        # First execute call returns storage_path row; second execute (DELETE) returns nothing.
        cursor_select = MagicMock()
        cursor_select.fetchone.return_value = (storage_path,)
        cursor_delete = MagicMock()
        cursor_delete.fetchone.return_value = None
        conn = MagicMock()
        conn.execute.side_effect = [cursor_select, cursor_delete]
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch.dict("os.environ", self._env()), \
             patch.object(backend, "_transaction", return_value=ctx), \
             patch("storage._supabase_storage_delete") as mock_del:
            result = backend.delete_font(FAKE_FONT_ID)

        assert result is True
        mock_del.assert_called_once_with(storage_path)

    def test_delete_font_returns_false_when_not_found(self):
        backend = PostgresStorageBackend(workspace_id=FAKE_WORKSPACE_ID)

        cursor_select = MagicMock()
        cursor_select.fetchone.return_value = None
        conn = MagicMock()
        conn.execute.return_value = cursor_select
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch.dict("os.environ", self._env()), \
             patch.object(backend, "_transaction", return_value=ctx), \
             patch("storage._supabase_storage_delete") as mock_del:
            result = backend.delete_font(FAKE_FONT_ID)

        assert result is False
        mock_del.assert_not_called()

    def test_delete_font_raises_without_workspace_id(self):
        backend = PostgresStorageBackend(workspace_id=None)
        with pytest.raises(RuntimeError, match="workspace_id"):
            backend.delete_font(FAKE_FONT_ID)

    def test_storage_delete_error_logs_but_returns_true(self):
        """Storage delete failure is logged but does not prevent a True return."""
        backend = PostgresStorageBackend(workspace_id=FAKE_WORKSPACE_ID)
        storage_path = f"workspace-fonts/{FAKE_WORKSPACE_ID}/font.woff2"

        cursor_select = MagicMock()
        cursor_select.fetchone.return_value = (storage_path,)
        cursor_delete = MagicMock()
        conn = MagicMock()
        conn.execute.side_effect = [cursor_select, cursor_delete]
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch.dict("os.environ", self._env()), \
             patch.object(backend, "_transaction", return_value=ctx), \
             patch("storage._supabase_storage_delete", side_effect=RuntimeError("network")):
            result = backend.delete_font(FAKE_FONT_ID)

        # DB row was deleted; Storage failure is soft (already logged).
        assert result is True


# ===========================================================================
# server.py handler tests — server mode font routes
# ===========================================================================

import server  # noqa: E402 (after sys.path insert)


def _make_handler():
    handler = server.Handler.__new__(server.Handler)
    handler._send_json = MagicMock()
    handler._send_bytes = MagicMock()
    return handler


def _sent(handler):
    assert handler._send_json.called, "_send_json was never called"
    args = handler._send_json.call_args
    data = args[0][0]
    status = args[0][1] if len(args[0]) > 1 else (args[1].get("status", 200) if args[1] else 200)
    return data, status


def _mock_user(workspace_id=None):
    return {
        "id": str(uuid.uuid4()),
        "email": "user@example.com",
        "workspace_id": workspace_id or FAKE_WORKSPACE_ID,
        "claims": {"sub": str(uuid.uuid4())},
    }


class TestHandleGetFontsServerMode:
    def _call(self, fonts):
        handler = _make_handler()
        user = _mock_user()
        mock_store = MagicMock()
        mock_store.list_fonts.return_value = fonts

        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(handler, "_require_auth", return_value=user), \
             patch.object(handler, "_storage_for_user", return_value=mock_store):
            handler._handle_get_fonts()
        return handler

    def test_returns_200_with_user_list(self):
        fonts = [{"id": FAKE_FONT_ID, "name": "Open Sans", "url": "https://x/font.woff2",
                  "slug": "open-sans", "family": "Open Sans", "source": "user"}]
        handler = self._call(fonts)
        data, status = _sent(handler)
        assert status == 200
        assert "user" in data
        assert len(data["user"]) == 1

    def test_user_font_has_id_name_url_keys(self):
        fonts = [{"id": FAKE_FONT_ID, "name": "Open Sans", "url": "https://x/font.woff2",
                  "slug": "open-sans", "family": "Open Sans", "source": "user"}]
        handler = self._call(fonts)
        data, _ = _sent(handler)
        font = data["user"][0]
        assert "id" in font
        assert "name" in font
        assert "url" in font

    def test_cached_is_empty_list_in_server_mode(self):
        handler = self._call([])
        data, _ = _sent(handler)
        assert data["cached"] == []

    def test_empty_fonts_returns_empty_user_list(self):
        handler = self._call([])
        data, _ = _sent(handler)
        assert data["user"] == []


class TestHandlePostFontsServerMode:
    def _call_with_store(self, store_result, font_data=None, filename="font.woff2"):
        handler = _make_handler()
        user = _mock_user()
        if font_data is None:
            font_data = FONT_BYTES

        # Patch cgi.FieldStorage
        field = MagicMock()
        field.filename = filename
        field.file = BytesIO(font_data)
        form = MagicMock()
        form.__contains__ = MagicMock(side_effect=lambda k: k in {"file"})
        form.__getitem__ = MagicMock(return_value=field)
        mock_cgi_fs = MagicMock(return_value=form)

        mock_store = MagicMock()
        mock_store.save_font.return_value = store_result

        handler.headers = {"Content-Type": "multipart/form-data; boundary=---X",
                           "Content-Length": str(len(font_data))}
        handler.rfile = BytesIO(font_data)

        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(handler, "_require_auth", return_value=user), \
             patch.object(handler, "_storage_for_user", return_value=mock_store), \
             patch("server.cgi.FieldStorage", mock_cgi_fs):
            handler._handle_post_fonts()
        return handler, mock_store

    def test_returns_200_ok(self):
        result = {"id": FAKE_FONT_ID, "name": "Font", "url": "https://x/font.woff2"}
        handler, _ = self._call_with_store(result)
        data, status = _sent(handler)
        assert status == 200
        assert data["ok"] is True

    def test_response_contains_id_name_url(self):
        result = {"id": FAKE_FONT_ID, "name": "Open Sans", "url": "https://x/opensans.woff2"}
        handler, _ = self._call_with_store(result)
        data, _ = _sent(handler)
        font = data["font"]
        assert font["id"] == FAKE_FONT_ID
        assert font["name"] == "Open Sans"
        assert font["url"] == "https://x/opensans.woff2"

    def test_calls_store_save_font(self):
        result = {"id": FAKE_FONT_ID, "name": "Font", "url": "https://x/font.woff2"}
        _, mock_store = self._call_with_store(result)
        mock_store.save_font.assert_called_once()

    def test_save_font_error_returns_500(self):
        handler = _make_handler()
        user = _mock_user()

        field = MagicMock()
        field.filename = "font.woff2"
        field.file = BytesIO(FONT_BYTES)
        form = MagicMock()
        form.__contains__ = MagicMock(side_effect=lambda k: k in {"file"})
        form.__getitem__ = MagicMock(return_value=field)

        mock_store = MagicMock()
        mock_store.save_font.side_effect = RuntimeError("Storage upload failed")

        handler.headers = {"Content-Type": "multipart/form-data; boundary=---X",
                           "Content-Length": "22"}
        handler.rfile = BytesIO(FONT_BYTES)

        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(handler, "_require_auth", return_value=user), \
             patch.object(handler, "_storage_for_user", return_value=mock_store), \
             patch("server.cgi.FieldStorage", MagicMock(return_value=form)):
            handler._handle_post_fonts()

        _, status = _sent(handler)
        assert status == 500


class TestHandleDeleteFontServerMode:
    def _call(self, font_id, found=True):
        handler = _make_handler()
        user = _mock_user()
        handler.path = f"/api/fonts/{font_id}"

        mock_store = MagicMock()
        mock_store.delete_font.return_value = found

        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(handler, "_require_auth", return_value=user), \
             patch.object(handler, "_storage_for_user", return_value=mock_store):
            handler._handle_delete_font()
        return handler, mock_store

    def test_returns_200_when_found(self):
        handler, _ = self._call(FAKE_FONT_ID, found=True)
        data, status = _sent(handler)
        assert status == 200
        assert data["ok"] is True

    def test_returns_404_when_not_found(self):
        handler, _ = self._call(FAKE_FONT_ID, found=False)
        _, status = _sent(handler)
        assert status == 404

    def test_calls_delete_font_with_id(self):
        _, mock_store = self._call(FAKE_FONT_ID, found=True)
        mock_store.delete_font.assert_called_once_with(FAKE_FONT_ID)

    def test_missing_id_returns_400(self):
        handler = _make_handler()
        user = _mock_user()
        handler.path = "/api/fonts/"

        mock_store = MagicMock()
        with patch.object(server, "IS_DESKTOP", False), \
             patch.object(handler, "_require_auth", return_value=user), \
             patch.object(handler, "_storage_for_user", return_value=mock_store):
            handler._handle_delete_font()

        _, status = _sent(handler)
        assert status == 400
