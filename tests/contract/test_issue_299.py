"""Contract tests for issue #299 — sweep e2e test pollution (_testKey,
_screenshots) from production workspace_settings + prevent recurrence.

These tests encode the issue's acceptance criteria as executable assertions.
They MUST fail on the unmodified codebase and pass once the implementation
lands. No live database, network, or HTTP server is required — the prevention
guard is exercised through the real ``_handle_post_settings`` Handler method
(network methods mocked), and the sweep logic is exercised through the pure
helpers the sweep script exposes.

Mapping to acceptance criteria:
  c1 — prevention: a settings POST carrying ``_``-prefixed keys must NOT
       persist those keys (reserved namespace stripped server-side).
  c2 — sweep detection: the sweep identifies exactly the ``_``-prefixed keys
       in a settings blob and leaves legitimate keys alone.
  c3 — sweep cleaning: cleaning a blob removes every ``_``-prefixed key while
       preserving all other keys byte-identically; dry-run does not mutate.
  c4 — (manual) production row shows no ``_``-prefixed keys after the sweep
       executes.
  c5 — (manual) a full live-lane run leaves the production settings row
       byte-identical (excluding refreshed OAuth tokens).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Python 3.13+ removed the stdlib ``cgi`` module that server.py imports lazily.
if "cgi" not in sys.modules:
    sys.modules["cgi"] = types.ModuleType("cgi")

import server  # noqa: E402


# ---------------------------------------------------------------------------
# Handler test harness (mirrors tests/test_collab_regression.py)
# ---------------------------------------------------------------------------

def _mock_user(email: str = "e2e-live@e2e.bulletin.test") -> dict:
    return {
        "id": "00000000-0000-0000-0000-000000000299",
        "email": email,
        "display_name": "E2E Live",
        "avatar_url": "",
        "domain": email.split("@")[-1],
        "workspace_id": "614505d2-0f12-4c00-afb1-9077a0dc94fe",
    }


def _make_handler(path: str, body: bytes = b"") -> server.Handler:
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
        "Cookie": "bg_session=tok",
        "Content-Length": str(len(body)),
        "Content-Type": "application/json",
    }
    handler.rfile = BytesIO(body)
    return handler


def _post_settings(partial: dict, existing: dict | None = None) -> dict:
    """Drive the real _handle_post_settings and return the dict that was
    actually persisted (the argument passed to store.save_settings)."""
    body = json.dumps(partial).encode()
    handler = _make_handler("/api/settings", body=body)
    mock_store = MagicMock()
    mock_store.get_settings.return_value = dict(existing or {})
    with patch.object(server, "IS_DESKTOP", False), \
         patch("auth.get_request_user", return_value=_mock_user()), \
         patch("storage.get_storage", return_value=mock_store):
        handler._handle_post_settings()
    assert mock_store.save_settings.called, "save_settings was never called"
    return mock_store.save_settings.call_args[0][0]


# ---------------------------------------------------------------------------
# Sweep script loader (script lives outside the importable package tree)
# ---------------------------------------------------------------------------

def _load_sweep_module():
    path = REPO_ROOT / "scripts" / "sweep_settings_test_keys.py"
    if not path.exists():
        pytest.fail(
            f"UNVERIFIED: sweep script not found at {path} — "
            "expected scripts/sweep_settings_test_keys.py"
        )
    spec = importlib.util.spec_from_file_location("sweep_settings_test_keys", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ===========================================================================
# c1 — Prevention guard (unit)
# ===========================================================================

class TestPreventionGuard:
    def test_underscore_keys_are_not_persisted(self):
        """issue-299-c1: a settings POST carrying _testKey/_screenshots must
        not persist those keys into workspace_settings."""
        persisted = _post_settings(
            {"_testKey": "boom", "_screenshots": ["a.png"], "churchName": "Visalia CRC"}
        )
        assert "_testKey" not in persisted, "_testKey leaked into persisted settings"
        assert "_screenshots" not in persisted, "_screenshots leaked into persisted settings"

    def test_legitimate_keys_still_persist(self):
        """issue-299-c1: the guard must not disturb normal settings writes."""
        persisted = _post_settings({"churchName": "Visalia CRC", "docTemplate": "letter"})
        assert persisted.get("churchName") == "Visalia CRC"
        assert persisted.get("docTemplate") == "letter"

    def test_guard_does_not_strip_existing_legit_keys(self):
        """issue-299-c1: merging a clean partial must preserve prior keys."""
        persisted = _post_settings(
            {"docTemplate": "a4"}, existing={"churchName": "Visalia CRC"}
        )
        assert persisted.get("churchName") == "Visalia CRC"
        assert persisted.get("docTemplate") == "a4"


# ===========================================================================
# c2 — Sweep detection (unit)
# ===========================================================================

class TestSweepDetection:
    def test_finds_underscore_prefixed_keys(self):
        """issue-299-c2: the sweep identifies exactly the _-prefixed keys."""
        mod = _load_sweep_module()
        settings = {
            "_testKey": 1,
            "_screenshots": [],
            "churchName": "Visalia CRC",
            "pcoAccessToken": "tok",
        }
        found = set(mod.find_test_keys(settings))
        assert found == {"_testKey", "_screenshots"}

    def test_empty_when_no_test_keys(self):
        """issue-299-c2: a clean blob yields no keys to delete."""
        mod = _load_sweep_module()
        assert mod.find_test_keys({"churchName": "x", "docTemplate": "letter"}) == []


# ===========================================================================
# c3 — Sweep cleaning + dry-run safety (unit)
# ===========================================================================

class TestSweepCleaning:
    def test_clean_removes_only_underscore_keys(self):
        """issue-299-c3: cleaning removes _-prefixed keys, preserves the rest."""
        mod = _load_sweep_module()
        before = {
            "_testKey": 1,
            "_screenshots": ["a.png"],
            "churchName": "Visalia CRC",
            "pcoAccessToken": "tok",
            "volunteerRoles": [{"id": "r1"}],
        }
        cleaned = mod.clean_settings(before)
        assert cleaned == {
            "churchName": "Visalia CRC",
            "pcoAccessToken": "tok",
            "volunteerRoles": [{"id": "r1"}],
        }

    def test_clean_does_not_mutate_input(self):
        """issue-299-c3: dry-run safety — clean_settings must not mutate its arg."""
        mod = _load_sweep_module()
        before = {"_testKey": 1, "churchName": "Visalia CRC"}
        snapshot = json.loads(json.dumps(before))
        mod.clean_settings(before)
        assert before == snapshot, "clean_settings mutated its input"


# ===========================================================================
# c4, c5 — manual (recorded in contract.json; no executable test)
# ===========================================================================
