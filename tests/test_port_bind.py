"""Contract tests for issue #279: sidecar exits clearly when the port is already in use.

Before this fix, a bind-time OSError bubbled as a raw traceback and Electron
showed the user an opaque "Exit code 1" dialog.  After the fix, run_server()
catches EADDRINUSE / WSAEADDRINUSE, prints a distinct human-readable message to
stderr, and exits with code 3 — without printing a traceback.

These tests are wired into the CI ``python`` job (ci.yml) and into
scripts/run_ai_workflow.py CI_PYTEST_TARGETS so they run on every PR.
"""

import errno
import io
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestPortBindError:
    """issue-279: run_server() bind-error path."""

    def _make_eaddrinuse(self):
        """Return an OSError with EADDRINUSE errno (cross-platform)."""
        e = OSError()
        e.errno = errno.EADDRINUSE
        return e

    def _run_server_with_bind_error(self, err):
        """
        Call server.run_server() with the ThreadingHTTPServer constructor
        monkeypatched to raise *err*.  Captures stderr and the SystemExit code.
        """
        import server  # noqa: PLC0415 — server sets globals at import

        stderr_capture = io.StringIO()

        with patch('http.server.ThreadingHTTPServer', side_effect=err), \
             patch.object(sys, 'stderr', stderr_capture):
            with pytest.raises(SystemExit) as exc_info:
                server.run_server(port=19765)  # arbitrary high port, never actually bound

        return exc_info.value.code, stderr_capture.getvalue()

    def test_c1_exits_with_nonzero_code_on_eaddrinuse(self):
        """issue-279-c1: EADDRINUSE → SystemExit with nonzero code (3)."""
        code, _ = self._run_server_with_bind_error(self._make_eaddrinuse())
        assert code != 0, f"Expected nonzero exit code, got {code}"

    def test_c2_exits_with_code_3_on_eaddrinuse(self):
        """issue-279-c2: exit code is exactly 3 (sentinel for port-in-use)."""
        code, _ = self._run_server_with_bind_error(self._make_eaddrinuse())
        assert code == 3, f"Expected exit code 3, got {code}"

    def test_c3_distinct_message_in_stderr(self):
        """issue-279-c3: stderr contains the distinct 'already in use' message."""
        _, stderr = self._run_server_with_bind_error(self._make_eaddrinuse())
        assert 'already in use' in stderr.lower(), \
            f"Expected 'already in use' in stderr, got: {stderr!r}"

    def test_c4_message_mentions_port(self):
        """issue-279-c4: stderr message includes the port number."""
        _, stderr = self._run_server_with_bind_error(self._make_eaddrinuse())
        assert '19765' in stderr, \
            f"Expected port 19765 in stderr message, got: {stderr!r}"

    def test_c5_no_raw_traceback_in_stderr(self):
        """issue-279-c5: stderr does NOT contain a raw Python traceback."""
        _, stderr = self._run_server_with_bind_error(self._make_eaddrinuse())
        assert 'Traceback (most recent call last)' not in stderr, \
            f"Unexpected raw traceback in stderr: {stderr!r}"

    def test_c6_other_oserror_reraises(self):
        """issue-279-c6: an OSError that is NOT EADDRINUSE re-raises (not swallowed)."""
        import server  # noqa: PLC0415

        other_err = OSError()
        other_err.errno = errno.EACCES  # Permission denied — should not be caught

        with patch('http.server.ThreadingHTTPServer', side_effect=other_err):
            with pytest.raises(OSError) as exc_info:
                server.run_server(port=19765)
        # Must be the original error (not wrapped in SystemExit)
        assert exc_info.value is other_err

    def test_c7_wsaeaddrinuse_exits_cleanly(self):
        """issue-279-c7: Windows WSAEADDRINUSE (10048) also exits with code 3."""
        import server  # noqa: PLC0415

        win_err = OSError()
        win_err.errno = 10048  # WSAEADDRINUSE on Windows

        stderr_capture = io.StringIO()
        with patch('http.server.ThreadingHTTPServer', side_effect=win_err), \
             patch.object(sys, 'stderr', stderr_capture):
            with pytest.raises(SystemExit) as exc_info:
                server.run_server(port=19765)

        assert exc_info.value.code == 3
        assert 'already in use' in stderr_capture.getvalue().lower()
