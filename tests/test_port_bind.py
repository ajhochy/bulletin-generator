"""Contract tests for issue #279: sidecar exits clearly when the port is already in use.

Before this fix, a bind-time OSError bubbled as a raw traceback and Electron
showed the user an opaque "Exit code 1" dialog.  After the fix, run_server()
catches EADDRINUSE / WSAEADDRINUSE, prints a distinct human-readable message to
stderr, and exits with code 3 — without printing a traceback.

These tests are wired into the CI ``python`` job (ci.yml) and into
scripts/run_ai_workflow.py CI_PYTEST_TARGETS so they run on every PR.

The tests must be HERMETIC: run_server() does several pre-bind steps
(``_validate_server_config`` — which sys.exit(1)s without DATABASE_URL —,
``run_migrations``, ``run_schema_migrations``, ``os.chdir``) before it ever
constructs the HTTP server. CI's ``python`` job has no ``.env`` / DATABASE_URL,
so we neutralise those pre-bind steps (force desktop mode + stub the file/DB
initialisers) so only the bind path under test is exercised.
"""

import errno
import io
import sys
from contextlib import ExitStack
from unittest.mock import patch

import pytest


def _neutralise_prebind(stack: ExitStack):
    """Patch run_server()'s pre-bind steps to no-ops so the test is hermetic.

    Forcing IS_DESKTOP=True makes _validate_server_config() return early (no
    DATABASE_URL requirement) and skips the ``if not IS_DESKTOP:
    run_schema_migrations()`` block. run_migrations / _initialize_local_file /
    os.chdir are stubbed so the test touches no files and no DB.
    """
    import server  # noqa: PLC0415
    stack.enter_context(patch.object(server, "IS_DESKTOP", True))
    stack.enter_context(patch.object(server, "run_migrations", lambda: None))
    stack.enter_context(patch.object(server, "_initialize_local_file", lambda *a, **k: None))
    stack.enter_context(patch("os.chdir", lambda *a, **k: None))
    return server


class TestPortBindError:
    """issue-279: run_server() bind-error path."""

    def _make_oserror(self, code):
        e = OSError()
        e.errno = code
        return e

    def _run_server_with_bind_error(self, err):
        """Call server.run_server() with ThreadingHTTPServer monkeypatched to
        raise *err*. Returns (SystemExit code, captured stderr)."""
        stderr_capture = io.StringIO()
        with ExitStack() as stack:
            server = _neutralise_prebind(stack)
            stack.enter_context(patch("http.server.ThreadingHTTPServer", side_effect=err))
            stack.enter_context(patch.object(sys, "stderr", stderr_capture))
            with pytest.raises(SystemExit) as exc_info:
                server.run_server(port=19765)
            return exc_info.value.code, stderr_capture.getvalue()

    def test_c1_exits_with_nonzero_code_on_eaddrinuse(self):
        """issue-279-c1: EADDRINUSE → SystemExit with nonzero code."""
        code, _ = self._run_server_with_bind_error(self._make_oserror(errno.EADDRINUSE))
        assert code != 0, f"Expected nonzero exit code, got {code}"

    def test_c2_exits_with_code_3_on_eaddrinuse(self):
        """issue-279-c2: exit code is exactly 3 (sentinel for port-in-use)."""
        code, _ = self._run_server_with_bind_error(self._make_oserror(errno.EADDRINUSE))
        assert code == 3, f"Expected exit code 3, got {code}"

    def test_c3_distinct_message_in_stderr(self):
        """issue-279-c3: stderr contains the distinct 'already in use' message."""
        _, stderr = self._run_server_with_bind_error(self._make_oserror(errno.EADDRINUSE))
        assert "already in use" in stderr.lower(), \
            f"Expected 'already in use' in stderr, got: {stderr!r}"

    def test_c4_message_mentions_port(self):
        """issue-279-c4: stderr message includes the port number."""
        _, stderr = self._run_server_with_bind_error(self._make_oserror(errno.EADDRINUSE))
        assert "19765" in stderr, f"Expected port 19765 in stderr, got: {stderr!r}"

    def test_c5_no_raw_traceback_in_stderr(self):
        """issue-279-c5: stderr does NOT contain a raw Python traceback."""
        _, stderr = self._run_server_with_bind_error(self._make_oserror(errno.EADDRINUSE))
        assert "Traceback (most recent call last)" not in stderr, \
            f"Unexpected raw traceback in stderr: {stderr!r}"

    def test_c6_other_oserror_reraises(self):
        """issue-279-c6: an OSError that is NOT EADDRINUSE re-raises (not swallowed)."""
        other_err = self._make_oserror(errno.EACCES)  # Permission denied
        with ExitStack() as stack:
            server = _neutralise_prebind(stack)
            stack.enter_context(patch("http.server.ThreadingHTTPServer", side_effect=other_err))
            with pytest.raises(OSError) as exc_info:
                server.run_server(port=19765)
            assert exc_info.value is other_err

    def test_c7_wsaeaddrinuse_exits_cleanly(self):
        """issue-279-c7: Windows WSAEADDRINUSE (10048) also exits with code 3."""
        code, stderr = self._run_server_with_bind_error(self._make_oserror(10048))
        assert code == 3
        assert "already in use" in stderr.lower()
