"""
Tests for scripts/backup.sh and scripts/restore.sh.

These tests verify script existence, executability, content correctness,
and basic error-handling behaviour without requiring a real Postgres instance.
"""

import os
import stat
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_SH = os.path.join(REPO_ROOT, "scripts", "backup.sh")
RESTORE_SH = os.path.join(REPO_ROOT, "scripts", "restore.sh")
BACKUP_COMPOSE_SH = os.path.join(REPO_ROOT, "scripts", "backup-compose.sh")


# ── Existence and permissions ─────────────────────────────────────────────────


def test_backup_sh_exists():
    assert os.path.isfile(BACKUP_SH), f"scripts/backup.sh not found at {BACKUP_SH}"


def test_backup_sh_is_executable():
    st = os.stat(BACKUP_SH)
    assert st.st_mode & stat.S_IXUSR, "scripts/backup.sh is not executable (chmod +x it)"


def test_restore_sh_exists():
    assert os.path.isfile(RESTORE_SH), f"scripts/restore.sh not found at {RESTORE_SH}"


def test_restore_sh_is_executable():
    st = os.stat(RESTORE_SH)
    assert st.st_mode & stat.S_IXUSR, "scripts/restore.sh is not executable (chmod +x it)"


def test_backup_compose_sh_exists():
    assert os.path.isfile(BACKUP_COMPOSE_SH), (
        f"scripts/backup-compose.sh not found at {BACKUP_COMPOSE_SH}"
    )


def test_backup_compose_sh_is_executable():
    st = os.stat(BACKUP_COMPOSE_SH)
    assert st.st_mode & stat.S_IXUSR, "scripts/backup-compose.sh is not executable"


# ── Content checks ────────────────────────────────────────────────────────────


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def test_backup_sh_uses_pg_dump():
    content = _read(BACKUP_SH)
    assert "pg_dump" in content, "backup.sh must invoke pg_dump"


def test_backup_sh_uses_database_url_env_not_hardcoded():
    content = _read(BACKUP_SH)
    assert "DATABASE_URL" in content, "backup.sh must read DATABASE_URL from the environment"
    # Must not contain a bare postgres:// URI with embedded credentials
    import re

    hardcoded = re.search(r"pg_dump\s+['\"]?postgres://[^$\s]+:[^$\s]+@", content)
    assert hardcoded is None, (
        "backup.sh appears to hardcode credentials in the pg_dump call — "
        "use $DATABASE_URL instead"
    )


def test_backup_sh_checks_database_url_is_set():
    content = _read(BACKUP_SH)
    # Script should guard against an empty DATABASE_URL
    assert "DATABASE_URL" in content
    # Some form of emptiness guard — either -z or :- with an error path
    assert '-z "${DATABASE_URL' in content or "DATABASE_URL:-}" in content, (
        "backup.sh should exit with an error when DATABASE_URL is not set"
    )


def test_restore_sh_uses_pg_restore():
    content = _read(RESTORE_SH)
    assert "pg_restore" in content, "restore.sh must invoke pg_restore"


def test_restore_sh_references_database_url():
    content = _read(RESTORE_SH)
    assert "DATABASE_URL" in content, "restore.sh must read DATABASE_URL from the environment"


def test_restore_sh_uses_clean_flag():
    content = _read(RESTORE_SH)
    assert "--clean" in content, "restore.sh should pass --clean to pg_restore"


def test_backup_sh_copies_fonts():
    content = _read(BACKUP_SH)
    assert "fonts" in content, "backup.sh should handle font directories"


def test_backup_compose_sh_references_docker_compose():
    content = _read(BACKUP_COMPOSE_SH)
    assert "docker compose" in content or "docker-compose" in content, (
        "backup-compose.sh should use docker compose"
    )


def test_backup_compose_sh_passes_database_url_via_e_flag():
    content = _read(BACKUP_COMPOSE_SH)
    # -e DATABASE_URL passes the env var into the container without shell history exposure
    assert "-e DATABASE_URL" in content or '-e "DATABASE_URL' in content, (
        "backup-compose.sh should pass DATABASE_URL via docker compose exec -e flag"
    )


# ── Runtime behaviour (no real DB required) ───────────────────────────────────


def _run_script(script: str, env: dict | None = None, input_text: str | None = None) -> subprocess.CompletedProcess:
    """Run a bash script and return the completed process."""
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["bash", script],
        capture_output=True,
        text=True,
        env=merged_env,
        input=input_text,
    )


def test_backup_sh_exits_nonzero_when_database_url_empty():
    """Script must fail fast when DATABASE_URL is not set."""
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env["DATABASE_URL"] = ""
    result = _run_script(BACKUP_SH, env=env)
    assert result.returncode != 0, (
        "backup.sh should exit non-zero when DATABASE_URL is empty; "
        f"got returncode={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )


def test_backup_sh_prints_error_to_stderr_when_database_url_missing():
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env["DATABASE_URL"] = ""
    result = _run_script(BACKUP_SH, env=env)
    assert "DATABASE_URL" in result.stderr, (
        "backup.sh should mention DATABASE_URL in its error message"
    )


def test_restore_sh_exits_nonzero_when_no_args():
    """restore.sh requires a backup directory argument."""
    result = _run_script(RESTORE_SH)
    assert result.returncode != 0, (
        "restore.sh should exit non-zero when called without arguments"
    )


def test_restore_sh_exits_nonzero_when_database_url_empty(tmp_path):
    """restore.sh must fail fast when DATABASE_URL is not set."""
    # Create a fake backup dir with a db.dump so we get past the path checks
    fake_backup = tmp_path / "20240101_120000"
    fake_backup.mkdir()
    (fake_backup / "db.dump").write_bytes(b"fake")

    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env["DATABASE_URL"] = ""

    result = subprocess.run(
        ["bash", RESTORE_SH, str(fake_backup)],
        capture_output=True,
        text=True,
        env=env,
        input="n\n",  # answer "no" to confirmation prompt if reached
    )
    assert result.returncode != 0, (
        "restore.sh should exit non-zero when DATABASE_URL is empty"
    )


def test_restore_sh_exits_nonzero_when_backup_dir_missing():
    """restore.sh should fail cleanly if the backup directory does not exist."""
    env = {**os.environ, "DATABASE_URL": "postgres://user:pass@localhost/test"}
    result = subprocess.run(
        ["bash", RESTORE_SH, "/nonexistent/backup/path"],
        capture_output=True,
        text=True,
        env=env,
        input="n\n",
    )
    assert result.returncode != 0


def test_restore_sh_exits_nonzero_when_dump_file_missing(tmp_path):
    """restore.sh should fail if db.dump is absent from the backup dir."""
    fake_backup = tmp_path / "20240101_120000"
    fake_backup.mkdir()
    # No db.dump created

    env = {**os.environ, "DATABASE_URL": "postgres://user:pass@localhost/test"}
    result = subprocess.run(
        ["bash", RESTORE_SH, str(fake_backup)],
        capture_output=True,
        text=True,
        env=env,
        input="n\n",
    )
    assert result.returncode != 0
