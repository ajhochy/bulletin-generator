"""Contract tests for issue 277-A: sidecar boots without DATABASE_URL in electron mode.

db.py's docstring says it mirrors the mode logic in server.py, but it defined
``IS_DESKTOP = _APP_MODE == "desktop"`` — omitting "electron". In electron mode
that made db connection helpers attempt a DATABASE_URL connection instead of
failing fast with the clean "server mode only" RuntimeError. server.py already
treats electron as desktop (server.py:263) and _validate_server_config() bypasses
the DATABASE_URL check for IS_DESKTOP.

These tests pin the acceptance: APP_MODE=electron must be treated as desktop by
db.py so the packaged Electron sidecar boots and never reaches psycopg without a
DATABASE_URL.
"""

import importlib
import os
from unittest.mock import patch

import pytest


def _reload_db_with_mode(mode):
    import db
    with patch.dict(os.environ, {"APP_MODE": mode}, clear=False):
        # Ensure DATABASE_URL absent for the electron-boot scenario
        os.environ.pop("DATABASE_URL", None)
        importlib.reload(db)
    return db


class TestIssue277AElectronDbMode:
    def teardown_method(self):
        # Restore db module to a clean server-mode default for other tests.
        import db
        with patch.dict(os.environ, {"APP_MODE": "server"}):
            importlib.reload(db)

    def test_issue_277_a_c1_electron_is_desktop(self):
        """issue-277-A-c1: APP_MODE=electron → db.IS_DESKTOP is True (mirror server.py)."""
        db = _reload_db_with_mode("electron")
        assert db.IS_DESKTOP is True

    def test_issue_277_a_c2_electron_get_connection_clean_runtimeerror(self):
        """issue-277-A-c2: in electron mode, db.get_connection() raises a clean
        'server mode' RuntimeError rather than attempting a psycopg connection."""
        db = _reload_db_with_mode("electron")
        with pytest.raises(RuntimeError, match="server mode"):
            db.get_connection()

    def test_issue_277_a_c3_electron_transaction_clean_runtimeerror(self):
        """issue-277-A-c3: in electron mode, db.transaction() raises a clean
        'server mode' RuntimeError before touching DATABASE_URL."""
        db = _reload_db_with_mode("electron")
        with pytest.raises(RuntimeError, match="server mode"):
            with db.transaction():
                pass

    def test_issue_277_a_c4_server_mode_unaffected(self):
        """issue-277-A-c4: regression guard — APP_MODE=server still NOT desktop."""
        import db
        with patch.dict(os.environ, {"APP_MODE": "server"}):
            importlib.reload(db)
            assert db.IS_DESKTOP is False
