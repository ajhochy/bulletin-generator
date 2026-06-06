"""
tests/test_storage_assets.py

Unit tests for storage_assets.py:
  - is_base64_data_uri: correctly identifies data URIs
  - _parse_data_uri: extracts binary, MIME, extension
  - upload_image: calls Supabase Storage REST API correctly; returns public URL
  - extract_and_upload_images:
      * uploads base64 fields and replaces with Storage URLs
      * leaves non-base64 fields unchanged
      * falls back to base64 when upload raises (no image lost)
      * is a no-op in desktop mode (missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)
      * is a no-op when workspace_id is None
"""

import base64
import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import storage_assets
from storage_assets import (
    _parse_data_uri,
    extract_and_upload_images,
    is_base64_data_uri,
    upload_image,
)

# ── Minimal valid PNG (1x1 pixel) for test fixtures ───────────────────────────
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAD"
    "hQGAWjR9awAAAABJRU5ErkJggg=="
)
_PNG_B64_URI = "data:image/png;base64," + base64.b64encode(_PNG_BYTES).decode()
_JPEG_B64_URI = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"\x00" * 10).decode()
_STORAGE_URL = "https://example.supabase.co"
_SERVICE_KEY = "fake-service-role-jwt"


class TestIsBase64DataUri(unittest.TestCase):

    def test_valid_png(self):
        self.assertTrue(is_base64_data_uri(_PNG_B64_URI))

    def test_valid_jpeg(self):
        self.assertTrue(is_base64_data_uri(_JPEG_B64_URI))

    def test_http_url_is_not_data_uri(self):
        self.assertFalse(is_base64_data_uri("https://example.com/image.png"))

    def test_supabase_storage_url_is_not_data_uri(self):
        self.assertFalse(is_base64_data_uri(
            "https://abc.supabase.co/storage/v1/object/public/project-assets/ws/p-cover.png"
        ))

    def test_none_is_not_data_uri(self):
        self.assertFalse(is_base64_data_uri(None))

    def test_empty_string_is_not_data_uri(self):
        self.assertFalse(is_base64_data_uri(""))

    def test_non_string_is_not_data_uri(self):
        self.assertFalse(is_base64_data_uri(42))


class TestParseDataUri(unittest.TestCase):

    def test_png_uri(self):
        data, mime, ext = _parse_data_uri(_PNG_B64_URI)
        self.assertEqual(mime, "image/png")
        self.assertEqual(ext, "png")
        self.assertEqual(data, _PNG_BYTES)

    def test_jpeg_uri_gives_jpg_ext(self):
        _, mime, ext = _parse_data_uri(_JPEG_B64_URI)
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(ext, "jpg")

    def test_webp_uri(self):
        uri = "data:image/webp;base64," + base64.b64encode(b"webpdata").decode()
        _, mime, ext = _parse_data_uri(uri)
        self.assertEqual(ext, "webp")

    def test_unknown_mime_gives_bin_ext(self):
        uri = "data:application/octet-stream;base64," + base64.b64encode(b"x").decode()
        _, _, ext = _parse_data_uri(uri)
        self.assertEqual(ext, "bin")

    def test_malformed_uri_raises(self):
        with self.assertRaises(ValueError):
            _parse_data_uri("not-a-data-uri")


class TestUploadImage(unittest.TestCase):

    def _make_fake_response(self):
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read = MagicMock(return_value=b'{"Key": "project-assets/ws/pid-cover.png"}')
        return resp

    def test_returns_public_url(self):
        fake_resp = self._make_fake_response()
        with patch("urllib.request.urlopen", return_value=fake_resp) as mock_open:
            url = upload_image(
                _PNG_BYTES, "image/png",
                "ws-id/project-id-cover.png",
                supabase_url=_STORAGE_URL,
                service_role_key=_SERVICE_KEY,
            )
        expected = (
            f"{_STORAGE_URL}/storage/v1/object/public/project-assets/"
            "ws-id/project-id-cover.png"
        )
        self.assertEqual(url, expected)
        mock_open.assert_called_once()

    def test_sends_correct_headers(self):
        fake_resp = self._make_fake_response()
        captured_req = {}

        def capture_open(req, timeout=None):
            captured_req["req"] = req
            return fake_resp

        with patch("urllib.request.urlopen", side_effect=capture_open):
            upload_image(
                _PNG_BYTES, "image/png",
                "ws/pid-cover.png",
                supabase_url=_STORAGE_URL,
                service_role_key=_SERVICE_KEY,
            )

        req = captured_req["req"]
        self.assertIn(f"Bearer {_SERVICE_KEY}", req.get_header("Authorization"))
        self.assertEqual(req.get_header("Content-type"), "image/png")
        self.assertEqual(req.get_header("X-upsert"), "true")

    def test_raises_without_supabase_url(self):
        with self.assertRaises(RuntimeError):
            upload_image(_PNG_BYTES, "image/png", "ws/p.png",
                         supabase_url="", service_role_key=_SERVICE_KEY)

    def test_raises_without_service_key(self):
        with self.assertRaises(RuntimeError):
            upload_image(_PNG_BYTES, "image/png", "ws/p.png",
                         supabase_url=_STORAGE_URL, service_role_key="")

    def test_propagates_network_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with self.assertRaises(urllib.error.URLError):
                upload_image(
                    _PNG_BYTES, "image/png", "ws/p.png",
                    supabase_url=_STORAGE_URL, service_role_key=_SERVICE_KEY,
                )


class TestExtractAndUploadImages(unittest.TestCase):

    def _make_project(self, cover=None, logo=None):
        return {
            "id": "proj-123",
            "name": "Test Project",
            "coverImageUrl": cover,
            "staffLogoUrl":  logo,
        }

    def _mock_upload(self, public_url_template="{url}/storage/v1/object/public/project-assets/{path}"):
        """Return a side_effect function that echoes back the expected public URL."""
        def _side_effect(data, mime, object_path, *, supabase_url, service_role_key):
            return public_url_template.format(url=supabase_url, path=object_path)
        return _side_effect

    # ── Happy path: base64 → Storage URL ──────────────────────────────────────

    def test_cover_base64_replaced_with_storage_url(self):
        project = self._make_project(cover=_PNG_B64_URI)
        with patch.object(storage_assets, "upload_image", side_effect=self._mock_upload()):
            result = extract_and_upload_images(
                project, "ws-id", "proj-123",
                supabase_url=_STORAGE_URL, service_role_key=_SERVICE_KEY,
            )
        self.assertFalse(is_base64_data_uri(result["coverImageUrl"]))
        self.assertIn("project-assets", result["coverImageUrl"])
        self.assertIn("proj-123-cover", result["coverImageUrl"])

    def test_logo_base64_replaced_with_storage_url(self):
        project = self._make_project(logo=_PNG_B64_URI)
        with patch.object(storage_assets, "upload_image", side_effect=self._mock_upload()):
            result = extract_and_upload_images(
                project, "ws-id", "proj-123",
                supabase_url=_STORAGE_URL, service_role_key=_SERVICE_KEY,
            )
        self.assertFalse(is_base64_data_uri(result["staffLogoUrl"]))
        self.assertIn("proj-123-logo", result["staffLogoUrl"])

    def test_both_images_uploaded(self):
        project = self._make_project(cover=_PNG_B64_URI, logo=_JPEG_B64_URI)
        upload_calls = []

        def track_upload(data, mime, path, *, supabase_url, service_role_key):
            upload_calls.append(path)
            return f"{supabase_url}/storage/v1/object/public/project-assets/{path}"

        with patch.object(storage_assets, "upload_image", side_effect=track_upload):
            extract_and_upload_images(
                project, "ws-id", "proj-123",
                supabase_url=_STORAGE_URL, service_role_key=_SERVICE_KEY,
            )

        paths = " ".join(upload_calls)
        self.assertIn("cover", paths)
        self.assertIn("logo", paths)

    # ── Non-base64 fields are left unchanged ──────────────────────────────────

    def test_existing_storage_url_not_re_uploaded(self):
        existing_url = f"{_STORAGE_URL}/storage/v1/object/public/project-assets/ws/proj-cover.png"
        project = self._make_project(cover=existing_url)
        with patch.object(storage_assets, "upload_image") as mock_upload:
            result = extract_and_upload_images(
                project, "ws-id", "proj-123",
                supabase_url=_STORAGE_URL, service_role_key=_SERVICE_KEY,
            )
        mock_upload.assert_not_called()
        self.assertEqual(result["coverImageUrl"], existing_url)

    def test_none_cover_not_uploaded(self):
        project = self._make_project(cover=None, logo=None)
        with patch.object(storage_assets, "upload_image") as mock_upload:
            result = extract_and_upload_images(
                project, "ws-id", "proj-123",
                supabase_url=_STORAGE_URL, service_role_key=_SERVICE_KEY,
            )
        mock_upload.assert_not_called()
        self.assertIsNone(result["coverImageUrl"])

    # ── Fallback: keep base64 when upload fails ─────────────────────────────

    def test_fallback_to_base64_on_network_error(self):
        project = self._make_project(cover=_PNG_B64_URI)
        with patch.object(storage_assets, "upload_image",
                          side_effect=urllib.error.URLError("network unreachable")):
            result = extract_and_upload_images(
                project, "ws-id", "proj-123",
                supabase_url=_STORAGE_URL, service_role_key=_SERVICE_KEY,
            )
        # The base64 must still be there — image not lost.
        self.assertEqual(result["coverImageUrl"], _PNG_B64_URI)

    def test_fallback_to_base64_on_auth_error(self):
        project = self._make_project(logo=_PNG_B64_URI)
        http_err = urllib.error.HTTPError(
            url="http://x", code=403, msg="Forbidden", hdrs=None, fp=None
        )
        with patch.object(storage_assets, "upload_image", side_effect=http_err):
            result = extract_and_upload_images(
                project, "ws-id", "proj-123",
                supabase_url=_STORAGE_URL, service_role_key=_SERVICE_KEY,
            )
        self.assertEqual(result["staffLogoUrl"], _PNG_B64_URI)

    # ── Desktop / no-config bypass ──────────────────────────────────────────

    def test_desktop_mode_no_supabase_url(self):
        project = self._make_project(cover=_PNG_B64_URI)
        with patch.object(storage_assets, "upload_image") as mock_upload:
            result = extract_and_upload_images(
                project, "ws-id", "proj-123",
                supabase_url="", service_role_key=_SERVICE_KEY,
            )
        mock_upload.assert_not_called()
        self.assertEqual(result["coverImageUrl"], _PNG_B64_URI)

    def test_desktop_mode_no_service_key(self):
        project = self._make_project(cover=_PNG_B64_URI)
        with patch.object(storage_assets, "upload_image") as mock_upload:
            result = extract_and_upload_images(
                project, "ws-id", "proj-123",
                supabase_url=_STORAGE_URL, service_role_key="",
            )
        mock_upload.assert_not_called()
        self.assertEqual(result["coverImageUrl"], _PNG_B64_URI)

    def test_reads_env_vars_when_not_supplied(self):
        """When supabase_url/service_role_key are not passed, reads from env."""
        project = self._make_project(cover=_PNG_B64_URI)
        uploaded_paths = []

        def track(data, mime, path, *, supabase_url, service_role_key):
            uploaded_paths.append(path)
            return f"{supabase_url}/storage/v1/object/public/project-assets/{path}"

        with patch.dict("os.environ", {
            "SUPABASE_URL": _STORAGE_URL,
            "SUPABASE_SERVICE_ROLE_KEY": _SERVICE_KEY,
        }):
            with patch.object(storage_assets, "upload_image", side_effect=track):
                result = extract_and_upload_images(project, "ws-id", "proj-123")

        self.assertTrue(uploaded_paths)
        self.assertFalse(is_base64_data_uri(result["coverImageUrl"]))


class TestStorageIntegrationWithStoragePy(unittest.TestCase):
    """Verify that PostgresStorageBackend calls extract_and_upload_images on save.

    These tests mock the DB (no live Postgres needed) and assert that the
    storage_assets module is wired into save_project and save_project_transactional.
    """

    def _make_backend(self, workspace_id="ws-abc"):
        from storage import PostgresStorageBackend
        return PostgresStorageBackend(workspace_id=workspace_id)

    def _mock_transaction(self):
        """Return a context-manager mock that yields a fake conn."""
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = (
            "proj-1", "Test", None, "workspace",
            '{"id":"proj-1","name":"Test"}', 1,
            None, None, None, None, "ws-abc",
        )
        cursor.description = [
            ("id",), ("name",), ("owner_user_id",), ("visibility",),
            ("state",), ("revision",), ("created_at",), ("updated_at",),
            ("created_by_user_id",), ("updated_by_user_id",), ("workspace_id",),
        ]
        conn.execute.return_value = cursor
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    def test_save_project_calls_extract_and_upload(self):
        backend = self._make_backend()
        calls = []

        def fake_extract(project, workspace_id, project_id, **kwargs):
            calls.append((workspace_id, project_id))
            return project

        with patch("storage.PostgresStorageBackend._transaction",
                   return_value=self._mock_transaction()):
            with patch("storage_assets.extract_and_upload_images",
                       side_effect=fake_extract):
                backend.save_project(
                    {"id": "proj-1", "name": "Test", "coverImageUrl": _PNG_B64_URI}
                )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ("ws-abc", "proj-1"))

    def test_save_project_no_workspace_skips_upload(self):
        """When workspace_id is None, no upload should be attempted."""
        from storage import PostgresStorageBackend
        backend = PostgresStorageBackend(workspace_id=None)

        with patch("storage.PostgresStorageBackend._transaction",
                   return_value=self._mock_transaction()):
            with patch("storage_assets.extract_and_upload_images") as mock_upload:
                backend.save_project({"id": "proj-1", "name": "Test"})

        mock_upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
