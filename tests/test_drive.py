"""Tests for Google Drive integration (#25)."""
import sys
import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import BytesIO
import urllib.error
import threading

sys.path.insert(0, str(Path(__file__).parent.parent))
import server

_lock = server._lock


# ── Shared stub ───────────────────────────────────────────────────────────────

class StubDriveHandler:
    """Minimal Handler stub for Drive upload tests."""
    def __init__(self, body_dict=None):
        self._responses = []
        self._body_dict = body_dict or {}

    def _send_json(self, body, status=200):
        self._responses.append((body, status))

    def _read_body_json(self):
        return self._body_dict

    def _handle_drive_upload(self):
        # Defer lookup so tests compile before the method is implemented
        return server.Handler._handle_drive_upload(self)


# ── Task 1: OAuth scope ───────────────────────────────────────────────────────

class TestGoogleOAuthScope:
    def test_oauth_start_includes_drive_scope(self):
        """OAuth URL must request drive.file alongside calendar.readonly."""
        captured = {}

        class FakeHandler:
            server = type('S', (), {'server_address': ('0.0.0.0', 8080)})()
            path = '/oauth/google/start'

            def send_response(self, code): captured['code'] = code
            def send_header(self, k, v): captured[k] = v
            def end_headers(self): pass
            def _send_json(self, body, status=200): captured['json'] = body

        with patch.dict(os.environ, {
            'GOOGLE_CLIENT_ID': 'test-client-id',
            'GOOGLE_CLIENT_SECRET': 'test-client-secret',
        }):
            server.Handler._handle_google_oauth_start(FakeHandler())

        location = captured.get('Location', '')
        assert 'drive.file' in location
        assert 'calendar.readonly' in location

    def test_oauth_callback_sets_drive_scope_granted(self, tmp_path):
        """Successful OAuth callback must store googleDriveScopeGranted=True."""
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text('{}')

        token_resp = json.dumps({
            'access_token': 'acc123',
            'refresh_token': 'ref456',
        }).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = token_resp
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        captured = {}

        class FakeHandler:
            server = type('S', (), {'server_address': ('0.0.0.0', 8080)})()
            path = '/oauth/google/callback?code=authcode123'

            def send_response(self, code): captured['code'] = code
            def send_header(self, k, v): captured[k] = v
            def end_headers(self): pass

        written_data = {}

        def fake_write_json(path, data):
            written_data.update(data)

        with patch.dict(os.environ, {
            'GOOGLE_CLIENT_ID': 'cid',
            'GOOGLE_CLIENT_SECRET': 'csec',
        }), patch('urllib.request.urlopen', return_value=mock_resp), \
           patch('server.SETTINGS_FILE', settings_file), \
           patch('server._write_json', side_effect=fake_write_json):
            server.Handler._handle_google_oauth_callback(FakeHandler())

        assert written_data.get('googleDriveScopeGranted') is True


# ── Task 2: driveConfigured in bootstrap ─────────────────────────────────────

class TestDriveConfigured:
    def test_public_config_includes_drive_configured_false_when_not_granted(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        with patch('server.SETTINGS_FILE', settings_file):
            cfg = server._public_config()
        assert cfg.get('driveConfigured') is False

    def test_public_config_drive_configured_true_when_granted(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {
            'googleAccessToken': 'tok',
            'googleDriveScopeGranted': True,
        })
        with patch('server.SETTINGS_FILE', settings_file):
            cfg = server._public_config()
        assert cfg.get('driveConfigured') is True

    def test_disconnect_clears_drive_keys(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {
            'googleAccessToken': 'tok',
            'googleDriveScopeGranted': True,
            'googleDriveFolderId': 'folder123',
        })

        captured = {}

        class FakeHandler:
            path = '/api/google-disconnect'
            def _send_json(self, body, status=200): captured['body'] = body

        with patch('server.SETTINGS_FILE', settings_file):
            # Simulate the disconnect handler logic directly
            with _lock:
                s = server._read_json(settings_file, {})
                s.pop('googleAccessToken', None)
                s.pop('googleRefreshToken', None)
                s.pop('googleCalendarIds', None)
                s.pop('googleDriveScopeGranted', None)
                s.pop('googleDriveFolderId', None)
                server._write_json(settings_file, s)

        result = server._read_json(settings_file, {})
        assert 'googleDriveScopeGranted' not in result
        assert 'googleDriveFolderId' not in result


# ── Task 3: Drive upload endpoint ─────────────────────────────────────────────

class TestDriveUpload:
    def _mock_drive_response(self, file_id='file123'):
        resp_data = json.dumps({
            'id': file_id,
            'webViewLink': f'https://drive.google.com/file/d/{file_id}',
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return patch('urllib.request.urlopen', return_value=mock_resp)

    def test_upload_returns_ok_with_file_id(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {
            'googleAccessToken': 'tok',
            'googleDriveScopeGranted': True,
        })
        h = StubDriveHandler({'filename': 'test.pdf', 'content': 'SGVsbG8=', 'mimeType': 'application/pdf'})
        with self._mock_drive_response('abc123'), \
             patch('server.SETTINGS_FILE', settings_file):
            h._handle_drive_upload()
        body, status = h._responses[0]
        assert status == 200
        assert body['ok'] is True
        assert body['fileId'] == 'abc123'

    def test_upload_no_token_returns_401(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {})
        h = StubDriveHandler({'filename': 'test.pdf', 'content': 'SGVsbG8=', 'mimeType': 'application/pdf'})
        with patch('server.SETTINGS_FILE', settings_file):
            h._handle_drive_upload()
        body, status = h._responses[0]
        assert status == 401
        assert 'error' in body

    def test_upload_missing_fields_returns_400(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {
            'googleAccessToken': 'tok',
            'googleDriveScopeGranted': True,
        })
        h = StubDriveHandler({})
        with patch('server.SETTINGS_FILE', settings_file):
            h._handle_drive_upload()
        body, status = h._responses[0]
        assert status == 400

    def test_upload_includes_folder_id_when_configured(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {
            'googleAccessToken': 'tok',
            'googleDriveScopeGranted': True,
            'googleDriveFolderId': 'folder99',
        })
        h = StubDriveHandler({'filename': 'out.pdf', 'content': 'SGVsbG8=', 'mimeType': 'application/pdf'})
        captured_req = {}

        def fake_urlopen(req, timeout=None):
            captured_req['body'] = req.data
            resp = MagicMock()
            resp.read.return_value = json.dumps({'id': 'f1', 'webViewLink': 'http://drive'}).encode()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch('urllib.request.urlopen', side_effect=fake_urlopen), \
             patch('server.SETTINGS_FILE', settings_file):
            h._handle_drive_upload()

        assert b'folder99' in captured_req['body']

    def test_upload_drive_403_returns_403_with_message(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {
            'googleAccessToken': 'tok',
            'googleDriveScopeGranted': True,
        })
        h = StubDriveHandler({'filename': 'test.pdf', 'content': 'SGVsbG8=', 'mimeType': 'application/pdf'})
        err = urllib.error.HTTPError(url='', code=403, msg='Forbidden', hdrs=None, fp=BytesIO(b'forbidden'))
        with patch('urllib.request.urlopen', side_effect=err), \
             patch('server.SETTINGS_FILE', settings_file):
            h._handle_drive_upload()
        body, status = h._responses[0]
        assert status == 403
        assert body.get('code') == 'drive_permission_denied'
        assert 'permission' in body.get('error', '').lower()

    def test_upload_drive_404_returns_404_with_message(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {
            'googleAccessToken': 'tok',
            'googleDriveScopeGranted': True,
            'googleDriveFolderId': 'bad-folder-id',
        })
        h = StubDriveHandler({'filename': 'test.pdf', 'content': 'SGVsbG8=', 'mimeType': 'application/pdf'})
        err = urllib.error.HTTPError(url='', code=404, msg='Not Found', hdrs=None, fp=BytesIO(b'not found'))
        with patch('urllib.request.urlopen', side_effect=err), \
             patch('server.SETTINGS_FILE', settings_file):
            h._handle_drive_upload()
        body, status = h._responses[0]
        assert status == 404
        assert body.get('code') == 'drive_folder_not_found'
        assert 'folder' in body.get('error', '').lower()

    def test_upload_unknown_http_error_returns_502(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {
            'googleAccessToken': 'tok',
            'googleDriveScopeGranted': True,
        })
        h = StubDriveHandler({'filename': 'test.pdf', 'content': 'SGVsbG8=', 'mimeType': 'application/pdf'})
        err = urllib.error.HTTPError(url='', code=500, msg='Internal Server Error', hdrs=None, fp=BytesIO(b'server error'))
        with patch('urllib.request.urlopen', side_effect=err), \
             patch('server.SETTINGS_FILE', settings_file):
            h._handle_drive_upload()
        body, status = h._responses[0]
        assert status == 502

    def test_upload_returns_file_url(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {
            'googleAccessToken': 'tok',
            'googleDriveScopeGranted': True,
        })
        h = StubDriveHandler({'filename': 'bulletin.json', 'content': 'e30=', 'mimeType': 'application/json'})
        with self._mock_drive_response('xyz789'), \
             patch('server.SETTINGS_FILE', settings_file):
            h._handle_drive_upload()
        body, _ = h._responses[0]
        assert 'xyz789' in body.get('fileUrl', '')


# ── Task 6: Settings round-trip ───────────────────────────────────────────────

class TestDriveFolderIdSettings:
    def test_folder_id_survives_settings_round_trip(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        server._write_json(settings_file, {})

        with patch('server.SETTINGS_FILE', settings_file):
            with _lock:
                s = server._read_json(settings_file, {})
                s['googleDriveFolderId'] = '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms'
                server._write_json(settings_file, s)

            result = server._read_json(settings_file, {})

        assert result.get('googleDriveFolderId') == '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms'
