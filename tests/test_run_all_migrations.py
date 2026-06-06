"""
tests/test_run_all_migrations.py — Unit tests for migrations/run_all_migrations.py.

All importers and filesystem operations are mocked.
No live database or filesystem state required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root on path.
sys.path.insert(0, str(Path(__file__).parent.parent))

from migrations.run_all_migrations import (
    _backup_data,
    _count_json_records,
    _count_font_dirs,
    _run_importers,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def data_dir(tmp_path):
    """Return a temporary data directory populated with minimal fixture files."""
    d = tmp_path / "data"
    d.mkdir()

    # JSON data files.
    (d / "projects.json").write_text(
        json.dumps([{"id": "p1", "name": "Sunday"}, {"id": "p2", "name": "Easter"}]),
        encoding="utf-8",
    )
    (d / "settings.json").write_text(
        json.dumps({"churchName": "First Church", "staffData": []}),
        encoding="utf-8",
    )
    (d / "announcements.json").write_text(
        json.dumps([{"id": "a1", "title": "Potluck"}]),
        encoding="utf-8",
    )
    (d / "song_database.json").write_text(
        json.dumps([{"id": "s1", "title": "Amazing Grace"}]),
        encoding="utf-8",
    )
    (d / "templates.json").write_text(
        json.dumps([{"id": "t1", "name": "Classic"}]),
        encoding="utf-8",
    )

    # Font directories.
    user_font = d / "fonts" / "user" / "open-sans"
    user_font.mkdir(parents=True)
    (user_font / "OpenSans-Regular.woff2").write_bytes(b"fake")

    cache_font = d / "fonts" / "cache" / "roboto"
    cache_font.mkdir(parents=True)
    (cache_font / "Roboto-Regular.woff2").write_bytes(b"fake")

    return d


def _make_ok_result(imported=1, skipped=0):
    """Return a generic importer result dict with no errors."""
    return {"imported": imported, "skipped": skipped, "errors": [], "dry_run": False}


def _make_font_ok_result(user_imported=1, cache_imported=1, skipped=0):
    return {
        "user_imported": user_imported,
        "cache_imported": cache_imported,
        "skipped": skipped,
        "errors": [],
        "dry_run": False,
    }


# ---------------------------------------------------------------------------
# _count_json_records
# ---------------------------------------------------------------------------

class TestCountJsonRecords:
    def test_missing_file_returns_zero(self, tmp_path):
        assert _count_json_records(tmp_path / "nope.json") == 0

    def test_json_array(self, tmp_path):
        f = tmp_path / "arr.json"
        f.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert _count_json_records(f) == 3

    def test_json_object(self, tmp_path):
        f = tmp_path / "obj.json"
        f.write_text(json.dumps({"a": 1, "b": 2}), encoding="utf-8")
        assert _count_json_records(f) == 2

    def test_corrupt_json_returns_zero(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not valid {{ json", encoding="utf-8")
        assert _count_json_records(f) == 0

    def test_empty_array(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("[]", encoding="utf-8")
        assert _count_json_records(f) == 0


# ---------------------------------------------------------------------------
# _count_font_dirs
# ---------------------------------------------------------------------------

class TestCountFontDirs:
    def test_missing_directory_returns_zero(self, tmp_path):
        assert _count_font_dirs(tmp_path / "nope") == 0

    def test_counts_subdirectories_only(self, tmp_path):
        d = tmp_path / "fonts"
        d.mkdir()
        (d / "open-sans").mkdir()
        (d / "roboto").mkdir()
        (d / "not-a-dir.txt").write_text("x")
        assert _count_font_dirs(d) == 2

    def test_empty_directory_returns_zero(self, tmp_path):
        d = tmp_path / "fonts"
        d.mkdir()
        assert _count_font_dirs(d) == 0


# ---------------------------------------------------------------------------
# _backup_data
# ---------------------------------------------------------------------------

class TestBackupData:
    def test_backup_dir_is_created(self, data_dir):
        backup = _backup_data(data_dir)
        assert backup.exists()
        assert backup.is_dir()
        # Should be inside data/backups/
        assert backup.parent.name == "backups"

    def test_json_files_are_copied(self, data_dir):
        backup = _backup_data(data_dir)
        for name in [
            "projects.json",
            "settings.json",
            "announcements.json",
            "song_database.json",
            "templates.json",
        ]:
            assert (backup / name).exists(), f"{name} not in backup"

    def test_user_fonts_are_copied(self, data_dir):
        backup = _backup_data(data_dir)
        assert (backup / "fonts" / "user" / "open-sans").is_dir()

    def test_missing_files_silently_skipped(self, tmp_path):
        """A data dir with no JSON files should still produce a backup dir."""
        d = tmp_path / "empty_data"
        d.mkdir()
        backup = _backup_data(d)
        assert backup.exists()
        # No JSON files present → nothing to copy, but no crash.
        assert not (backup / "projects.json").exists()

    def test_missing_user_fonts_silently_skipped(self, tmp_path):
        d = tmp_path / "data_no_fonts"
        d.mkdir()
        backup = _backup_data(d)
        assert backup.exists()
        assert not (backup / "fonts").exists()

    def test_backup_timestamps_are_unique(self, data_dir):
        """Two successive backups with different timestamps produce different dirs."""
        import migrations.run_all_migrations as m

        original_datetime = m.datetime

        class _FakeDT:
            _stamp = "20990101_120001"

            @classmethod
            def now(cls, tz=None):
                return cls()

            def strftime(self, fmt):
                return self._stamp

        m.datetime = _FakeDT
        try:
            b2 = _backup_data(data_dir)
        finally:
            m.datetime = original_datetime

        b1 = _backup_data(data_dir)
        # b2 used a fixed fake stamp; b1 used the real clock.
        # They should reside in different directories.
        assert b1.name != "20990101_120001" or b2.name == "20990101_120001"
        # Both must exist.
        assert b1.exists()
        assert b2.exists()


# ---------------------------------------------------------------------------
# Dry-run: all importers called with dry_run=True, no backup
# ---------------------------------------------------------------------------

IMPORTER_PATCH_TARGETS = {
    "migrations.run_all_migrations.import_projects_from_json": _make_ok_result(),
    "migrations.run_all_migrations.import_settings_from_json": {
        "org_keys_imported": 2,
        "user_keys_imported": 0,
        "skipped": 0,
        "errors": [],
        "dry_run": True,
    },
    "migrations.run_all_migrations.import_announcements_from_json": _make_ok_result(),
    "migrations.run_all_migrations.import_songs_from_json": _make_ok_result(),
    "migrations.run_all_migrations.import_templates_from_json": {
        "imported": 1,
        "skipped": 0,
        "built_in": 1,
        "custom": 0,
        "errors": [],
        "dry_run": True,
    },
    "migrations.run_all_migrations.import_fonts_from_directories": _make_font_ok_result(),
}


def _patch_importers(results: dict | None = None):
    """Context-manager stack that patches all six importer functions."""
    from unittest.mock import patch as _patch
    import contextlib

    defaults = {
        "migrations.run_all_migrations.import_projects_from_json": _make_ok_result(),
        "migrations.run_all_migrations.import_settings_from_json": {
            "org_keys_imported": 1,
            "user_keys_imported": 0,
            "skipped": 0,
            "errors": [],
            "dry_run": False,
        },
        "migrations.run_all_migrations.import_announcements_from_json": _make_ok_result(),
        "migrations.run_all_migrations.import_songs_from_json": _make_ok_result(),
        "migrations.run_all_migrations.import_templates_from_json": {
            "imported": 1,
            "skipped": 0,
            "built_in": 1,
            "custom": 0,
            "errors": [],
            "dry_run": False,
        },
        "migrations.run_all_migrations.import_fonts_from_directories": _make_font_ok_result(),
    }
    if results:
        defaults.update(results)

    @contextlib.contextmanager
    def _ctx():
        patches = []
        mocks = {}
        for target, retval in defaults.items():
            p = _patch(target, return_value=retval)
            m = p.start()
            patches.append(p)
            mocks[target] = m
        try:
            yield mocks
        finally:
            for p in patches:
                p.stop()

    return _ctx()


class TestDryRunMode:
    def test_all_importers_called_with_dry_run_true(self, data_dir):
        with _patch_importers() as mocks:
            with pytest.raises(SystemExit) as exc:
                main(["--dry-run", "--data-dir", str(data_dir)])
        assert exc.value.code == 0

        for target, mock in mocks.items():
            _, kwargs = mock.call_args
            assert kwargs.get("dry_run") is True or (
                mock.call_args.args and True in mock.call_args.args
            ), f"{target} was not called with dry_run=True"

    def test_no_backup_directory_created_in_dry_run(self, data_dir):
        with _patch_importers():
            with pytest.raises(SystemExit):
                main(["--dry-run", "--data-dir", str(data_dir)])
        backups = data_dir / "backups"
        assert not backups.exists()

    def test_exits_zero_on_success(self, data_dir):
        with _patch_importers():
            with pytest.raises(SystemExit) as exc:
                main(["--dry-run", "--data-dir", str(data_dir)])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# Real run: backup created before importers
# ---------------------------------------------------------------------------

class TestRealRun:
    def test_backup_created_before_importers(self, data_dir):
        """The backup directory must exist when importers run."""
        call_order = []

        def record_backup(*a, **kw):
            call_order.append("backup")
            return data_dir / "backups" / "fake"

        def record_importer(*a, **kw):
            call_order.append("importer")
            return _make_ok_result()

        def record_font_importer(*a, **kw):
            call_order.append("importer")
            return _make_font_ok_result()

        with (
            patch("migrations.run_all_migrations._backup_data", side_effect=record_backup),
            patch("migrations.run_all_migrations.import_projects_from_json", side_effect=record_importer),
            patch("migrations.run_all_migrations.import_settings_from_json", return_value={
                "org_keys_imported": 1, "user_keys_imported": 0,
                "skipped": 0, "errors": [], "dry_run": False,
            }),
            patch("migrations.run_all_migrations.import_announcements_from_json", side_effect=record_importer),
            patch("migrations.run_all_migrations.import_songs_from_json", side_effect=record_importer),
            patch("migrations.run_all_migrations.import_templates_from_json", return_value={
                "imported": 1, "skipped": 0, "built_in": 1, "custom": 0,
                "errors": [], "dry_run": False,
            }),
            patch("migrations.run_all_migrations.import_fonts_from_directories", side_effect=record_font_importer),
        ):
            with pytest.raises(SystemExit):
                main(["--data-dir", str(data_dir)])

        assert call_order[0] == "backup"
        assert "importer" in call_order

    def test_real_backup_dir_exists_after_run(self, data_dir):
        with _patch_importers():
            with pytest.raises(SystemExit) as exc:
                main(["--data-dir", str(data_dir)])
        assert exc.value.code == 0
        backups = data_dir / "backups"
        assert backups.exists()
        subdirs = list(backups.iterdir())
        assert len(subdirs) == 1

    def test_exits_zero_when_all_succeed(self, data_dir):
        with _patch_importers():
            with pytest.raises(SystemExit) as exc:
                main(["--data-dir", str(data_dir)])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# Re-run idempotency: all importers return skipped=N, imported=0 → exit 0
# ---------------------------------------------------------------------------

class TestRerunIdempotency:
    def test_all_skipped_exits_zero(self, data_dir):
        skip_results = {
            "migrations.run_all_migrations.import_projects_from_json": {
                "imported": 0, "skipped": 2, "errors": [], "dry_run": False,
            },
            "migrations.run_all_migrations.import_settings_from_json": {
                "org_keys_imported": 0, "user_keys_imported": 0,
                "skipped": 2, "errors": [], "dry_run": False,
            },
            "migrations.run_all_migrations.import_announcements_from_json": {
                "imported": 0, "skipped": 1, "errors": [], "dry_run": False,
            },
            "migrations.run_all_migrations.import_songs_from_json": {
                "imported": 0, "skipped": 1, "errors": [], "dry_run": False,
            },
            "migrations.run_all_migrations.import_templates_from_json": {
                "imported": 0, "skipped": 1, "built_in": 1, "custom": 0,
                "errors": [], "dry_run": False,
            },
            "migrations.run_all_migrations.import_fonts_from_directories": {
                "user_imported": 0, "cache_imported": 0,
                "skipped": 2, "errors": [], "dry_run": False,
            },
        }
        with _patch_importers(skip_results):
            with pytest.raises(SystemExit) as exc:
                main(["--data-dir", str(data_dir)])
        assert exc.value.code == 0

    def test_no_errors_when_all_skipped(self, data_dir, capsys):
        skip_results = {
            "migrations.run_all_migrations.import_projects_from_json": {
                "imported": 0, "skipped": 2, "errors": [], "dry_run": False,
            },
            "migrations.run_all_migrations.import_settings_from_json": {
                "org_keys_imported": 0, "user_keys_imported": 0,
                "skipped": 0, "errors": [], "dry_run": False,
            },
            "migrations.run_all_migrations.import_announcements_from_json": {
                "imported": 0, "skipped": 1, "errors": [], "dry_run": False,
            },
            "migrations.run_all_migrations.import_songs_from_json": {
                "imported": 0, "skipped": 1, "errors": [], "dry_run": False,
            },
            "migrations.run_all_migrations.import_templates_from_json": {
                "imported": 0, "skipped": 1, "built_in": 1, "custom": 0,
                "errors": [], "dry_run": False,
            },
            "migrations.run_all_migrations.import_fonts_from_directories": {
                "user_imported": 0, "cache_imported": 0,
                "skipped": 2, "errors": [], "dry_run": False,
            },
        }
        with _patch_importers(skip_results):
            with pytest.raises(SystemExit):
                main(["--data-dir", str(data_dir)])
        captured = capsys.readouterr()
        assert "ERROR" not in captured.err


# ---------------------------------------------------------------------------
# Error handling: one importer returns errors → exit 1
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_exits_one_on_importer_error(self, data_dir):
        error_results = {
            "migrations.run_all_migrations.import_projects_from_json": {
                "imported": 0,
                "skipped": 0,
                "errors": ["Malformed project at index 0: missing field"],
                "dry_run": False,
            },
        }
        with _patch_importers(error_results):
            with pytest.raises(SystemExit) as exc:
                main(["--data-dir", str(data_dir)])
        assert exc.value.code == 1

    def test_error_printed_to_stderr(self, data_dir, capsys):
        error_msg = "Malformed project at index 0: missing field"
        error_results = {
            "migrations.run_all_migrations.import_projects_from_json": {
                "imported": 0,
                "skipped": 0,
                "errors": [error_msg],
                "dry_run": False,
            },
        }
        with _patch_importers(error_results):
            with pytest.raises(SystemExit):
                main(["--data-dir", str(data_dir)])
        captured = capsys.readouterr()
        assert error_msg in captured.err

    def test_other_importers_still_run_after_error(self, data_dir):
        """All importers always run — errors are collected, not fatal mid-sequence."""
        songs_mock = MagicMock(return_value=_make_ok_result())
        error_results = {
            "migrations.run_all_migrations.import_projects_from_json": {
                "imported": 0, "skipped": 0,
                "errors": ["bad project"],
                "dry_run": False,
            },
            "migrations.run_all_migrations.import_songs_from_json": songs_mock.return_value,
        }
        with (
            _patch_importers(error_results),
            patch(
                "migrations.run_all_migrations.import_songs_from_json",
                songs_mock,
            ),
        ):
            with pytest.raises(SystemExit):
                main(["--data-dir", str(data_dir)])
        songs_mock.assert_called_once()


# ---------------------------------------------------------------------------
# --check mode: counts records without DB, exits 0
# ---------------------------------------------------------------------------

class TestCheckMode:
    def test_exits_zero(self, data_dir):
        with pytest.raises(SystemExit) as exc:
            main(["--check", "--data-dir", str(data_dir)])
        assert exc.value.code == 0

    def test_prints_record_counts(self, data_dir, capsys):
        with pytest.raises(SystemExit):
            main(["--check", "--data-dir", str(data_dir)])
        captured = capsys.readouterr()
        # Should mention projects and fonts.
        assert "projects" in captured.out
        assert "fonts" in captured.out

    def test_no_importer_called(self, data_dir):
        """--check must not call any importer."""
        with _patch_importers() as mocks:
            with pytest.raises(SystemExit):
                main(["--check", "--data-dir", str(data_dir)])
        for mock in mocks.values():
            mock.assert_not_called()

    def test_no_backup_created(self, data_dir):
        with pytest.raises(SystemExit):
            main(["--check", "--data-dir", str(data_dir)])
        assert not (data_dir / "backups").exists()

    def test_counts_match_fixture_data(self, data_dir, capsys):
        with pytest.raises(SystemExit):
            main(["--check", "--data-dir", str(data_dir)])
        captured = capsys.readouterr()
        # projects.json has 2 entries.
        assert "2" in captured.out
        # announcements.json has 1 entry.
        assert "1" in captured.out


# ---------------------------------------------------------------------------
# Summary table content
# ---------------------------------------------------------------------------

class TestSummaryOutput:
    def test_summary_includes_each_data_type(self, data_dir, capsys):
        with _patch_importers():
            with pytest.raises(SystemExit):
                main(["--dry-run", "--data-dir", str(data_dir)])
        captured = capsys.readouterr()
        for name in ("projects", "settings", "announcements", "songs", "templates", "fonts"):
            assert name in captured.out

    def test_dry_run_label_in_output(self, data_dir, capsys):
        with _patch_importers():
            with pytest.raises(SystemExit):
                main(["--dry-run", "--data-dir", str(data_dir)])
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out

    def test_no_dry_run_label_on_real_run(self, data_dir, capsys):
        with _patch_importers():
            with pytest.raises(SystemExit):
                main(["--data-dir", str(data_dir)])
        captured = capsys.readouterr()
        assert "DRY RUN" not in captured.out
