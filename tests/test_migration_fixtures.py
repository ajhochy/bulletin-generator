"""
tests/test_migration_fixtures.py — Fixture-based migration tests.

Exercises the full migration pipeline using representative real-ish JSON fixtures
in tests/fixtures/.  All Postgres interactions are mocked; no live database required.

Sections
--------
1. Individual importers with fixtures — counts and field preservation
2. Idempotency — second run returns skipped=N, imported=0
3. Dry run — dry_run=True, no DB calls made
4. Full pipeline via run_all_migrations — orchestrator integration
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "migrations"))

from import_projects import import_projects_from_json
from import_settings import import_settings_from_json, ORG_KEYS, OAUTH_KEYS
from import_announcements import import_announcements_from_json
from import_songs import import_songs_from_json
from import_templates import import_templates_from_json
from import_fonts import import_fonts_from_directories
from migrations.run_all_migrations import main


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

def _make_transaction(inserted_flags: list[bool]):
    """Return a (ctx, conn) pair where each execute() call consumes a flag from
    *inserted_flags*: True → rowcount=1 (new row), False → rowcount=0 (conflict).
    Any call beyond the list length returns rowcount=1.
    """
    call_index = [0]

    def _side_effect(sql, params=None):
        cursor = MagicMock()
        idx = call_index[0]
        cursor.rowcount = 1 if (idx >= len(inserted_flags) or inserted_flags[idx]) else 0
        call_index[0] += 1
        return cursor

    conn = MagicMock()
    conn.execute.side_effect = _side_effect

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, conn


def _make_skipped_transaction(n: int):
    """Return a transaction where all *n* upserts hit ON CONFLICT (rowcount=0)."""
    return _make_transaction([False] * n)


# ---------------------------------------------------------------------------
# Section 1: Individual importers with fixture files
# ---------------------------------------------------------------------------

class TestProjectsFixture:
    """import_projects_from_json with tests/fixtures/projects.json (3 projects)."""

    def test_imports_all_three_projects(self):
        ctx, _ = _make_transaction([True, True, True, True, True, True])
        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(FIXTURES / "projects.json"))
        assert result["imported"] == 3
        assert result["errors"] == []

    def test_no_errors(self):
        ctx, _ = _make_transaction([True] * 10)
        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(FIXTURES / "projects.json"))
        assert result["errors"] == []

    def test_skipped_zero_on_first_run(self):
        ctx, _ = _make_transaction([True] * 10)
        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(FIXTURES / "projects.json"))
        assert result["skipped"] == 0

    def test_dry_run_false_in_result(self):
        ctx, _ = _make_transaction([True] * 10)
        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(FIXTURES / "projects.json"))
        assert result["dry_run"] is False

    def test_state_field_preserved_in_upsert_sql(self):
        """The SQL upsert must pass state JSON to DB (song title preserved)."""
        ctx, conn = _make_transaction([True] * 10)
        with patch("import_projects.transaction", return_value=ctx):
            import_projects_from_json(str(FIXTURES / "projects.json"))
        # At least one execute call should contain the song title in its params
        all_params = [
            str(c.args[1]) if len(c.args) > 1 else ""
            for c in conn.execute.call_args_list
        ]
        assert any("Holy Holy Holy" in p for p in all_params)

    def test_revision_preserved_for_full_project(self):
        """The first fixture project has revision=5; that should be passed to DB."""
        ctx, conn = _make_transaction([True] * 10)
        with patch("import_projects.transaction", return_value=ctx):
            import_projects_from_json(str(FIXTURES / "projects.json"))
        # Find the execute call for the first project (the one with revision=5)
        revision_params = [
            str(c.args[1])
            for c in conn.execute.call_args_list
            if "project_revisions" not in c.args[0]
        ]
        assert any("5" in p for p in revision_params)


class TestSettingsFixture:
    """import_settings_from_json with tests/fixtures/settings.json."""

    def test_org_keys_imported_positive(self):
        ctx, _ = _make_transaction([True] * 20)
        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(FIXTURES / "settings.json"))
        assert result["org_keys_imported"] > 0

    def test_oauth_tokens_bundled(self):
        """All four OAuth tokens should be bundled into a single DB row."""
        ctx, conn = _make_transaction([True] * 20)
        with patch("import_settings.transaction", return_value=ctx):
            import_settings_from_json(str(FIXTURES / "settings.json"))
        # Look for the oauth_tokens key in SQL params
        all_params = [
            str(c.args[1]) if len(c.args) > 1 else ""
            for c in conn.execute.call_args_list
        ]
        assert any("oauth_tokens" in p for p in all_params)

    def test_all_org_keys_from_fixture_written(self):
        """Every ORG_KEY present in the fixture should generate an execute call."""
        ctx, conn = _make_transaction([True] * 20)
        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(FIXTURES / "settings.json"))
        fixture_data = json.loads((FIXTURES / "settings.json").read_text())
        present_org_keys = [k for k in ORG_KEYS if k in fixture_data]
        # +1 for the bundled oauth_tokens row
        expected = len(present_org_keys) + 1
        assert result["org_keys_imported"] == expected

    def test_church_name_in_params(self):
        ctx, conn = _make_transaction([True] * 20)
        with patch("import_settings.transaction", return_value=ctx):
            import_settings_from_json(str(FIXTURES / "settings.json"))
        all_params = [
            str(c.args[1]) if len(c.args) > 1 else ""
            for c in conn.execute.call_args_list
        ]
        assert any("Visalia CRC" in p for p in all_params)


class TestAnnouncementsFixture:
    """import_announcements_from_json with tests/fixtures/announcements.json (3 items)."""

    def test_imports_all_three(self):
        ctx, _ = _make_transaction([True, True, True])
        with patch("import_announcements.transaction", return_value=ctx):
            result = import_announcements_from_json(str(FIXTURES / "announcements.json"))
        assert result["imported"] == 3

    def test_no_errors(self):
        ctx, _ = _make_transaction([True, True, True])
        with patch("import_announcements.transaction", return_value=ctx):
            result = import_announcements_from_json(str(FIXTURES / "announcements.json"))
        assert result["errors"] == []

    def test_skipped_zero(self):
        ctx, _ = _make_transaction([True, True, True])
        with patch("import_announcements.transaction", return_value=ctx):
            result = import_announcements_from_json(str(FIXTURES / "announcements.json"))
        assert result["skipped"] == 0

    def test_title_field_in_upsert(self):
        """Title strings must appear in the SQL params sent to the DB."""
        ctx, conn = _make_transaction([True, True, True])
        with patch("import_announcements.transaction", return_value=ctx):
            import_announcements_from_json(str(FIXTURES / "announcements.json"))
        all_params = [
            str(c.args[1]) if len(c.args) > 1 else ""
            for c in conn.execute.call_args_list
        ]
        assert any("Food Pantry" in p for p in all_params)


class TestSongsFixture:
    """import_songs_from_json with tests/fixtures/song_database.json (3 songs)."""

    def test_imports_all_three(self):
        ctx, _ = _make_transaction([True, True, True])
        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(FIXTURES / "song_database.json"))
        assert result["imported"] == 3

    def test_no_errors(self):
        ctx, _ = _make_transaction([True, True, True])
        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(FIXTURES / "song_database.json"))
        assert result["errors"] == []

    def test_title_preserved_in_params(self):
        ctx, conn = _make_transaction([True, True, True])
        with patch("import_songs.transaction", return_value=ctx):
            import_songs_from_json(str(FIXTURES / "song_database.json"))
        all_params = [
            str(c.args[1]) if len(c.args) > 1 else ""
            for c in conn.execute.call_args_list
        ]
        assert any("Amazing Grace" in p for p in all_params)

    def test_author_preserved_in_params(self):
        ctx, conn = _make_transaction([True, True, True])
        with patch("import_songs.transaction", return_value=ctx):
            import_songs_from_json(str(FIXTURES / "song_database.json"))
        all_params = [
            str(c.args[1]) if len(c.args) > 1 else ""
            for c in conn.execute.call_args_list
        ]
        assert any("Newton" in p for p in all_params)


class TestTemplatesFixture:
    """import_templates_from_json with tests/fixtures/templates.json (2 built-in, 1 custom)."""

    def test_imports_all_three(self):
        ctx, _ = _make_transaction([True, True, True])
        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(FIXTURES / "templates.json"))
        assert result["imported"] == 3

    def test_built_in_count_is_two(self):
        ctx, _ = _make_transaction([True, True, True])
        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(FIXTURES / "templates.json"))
        assert result["built_in"] == 2

    def test_custom_count_is_one(self):
        ctx, _ = _make_transaction([True, True, True])
        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(FIXTURES / "templates.json"))
        assert result["custom"] == 1

    def test_no_errors(self):
        ctx, _ = _make_transaction([True, True, True])
        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(FIXTURES / "templates.json"))
        assert result.get("errors", []) == []


class TestFontsFixture:
    """import_fonts_from_directories with a tmp_path font tree."""

    def _make_font_dirs(self, tmp_path: Path):
        user_dir = tmp_path / "user"
        cache_dir = tmp_path / "cache"

        # Two user font families
        for slug in ("open-sans", "merriweather"):
            d = user_dir / slug
            d.mkdir(parents=True)
            (d / f"{slug}.woff2").write_bytes(b"FONT")

        # One cache font family
        roboto = cache_dir / "roboto"
        roboto.mkdir(parents=True)
        (roboto / "Roboto-Regular.woff2").write_bytes(b"FONT")

        return user_dir, cache_dir

    def test_user_fonts_imported(self, tmp_path):
        user_dir, cache_dir = self._make_font_dirs(tmp_path)
        ctx, _ = _make_transaction([True] * 10)
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(str(user_dir), str(cache_dir))
        assert result["user_imported"] == 2

    def test_cache_fonts_imported(self, tmp_path):
        user_dir, cache_dir = self._make_font_dirs(tmp_path)
        ctx, _ = _make_transaction([True] * 10)
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(str(user_dir), str(cache_dir))
        assert result["cache_imported"] == 1

    def test_no_errors(self, tmp_path):
        user_dir, cache_dir = self._make_font_dirs(tmp_path)
        ctx, _ = _make_transaction([True] * 10)
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(str(user_dir), str(cache_dir))
        assert result["errors"] == []

    def test_empty_dirs_return_zero(self, tmp_path):
        user_dir = tmp_path / "user"
        cache_dir = tmp_path / "cache"
        user_dir.mkdir()
        cache_dir.mkdir()
        ctx, _ = _make_transaction([])
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(str(user_dir), str(cache_dir))
        assert result["user_imported"] == 0
        assert result["cache_imported"] == 0


# ---------------------------------------------------------------------------
# Section 2: Idempotency — second run skips all rows
# ---------------------------------------------------------------------------

class TestIdempotencyProjects:
    def test_second_run_skips_all(self):
        ctx, _ = _make_skipped_transaction(3)
        with patch("import_projects.transaction", return_value=ctx):
            result = import_projects_from_json(str(FIXTURES / "projects.json"))
        assert result["imported"] == 0
        assert result["skipped"] == 3
        assert result["errors"] == []


class TestIdempotencySettings:
    def test_second_run_skips_all(self):
        # 9 org_keys + 1 oauth_tokens row = 10 rows
        ctx, _ = _make_skipped_transaction(10)
        with patch("import_settings.transaction", return_value=ctx):
            result = import_settings_from_json(str(FIXTURES / "settings.json"))
        assert result["org_keys_imported"] == 0
        assert result["skipped"] > 0


class TestIdempotencyAnnouncements:
    def test_second_run_skips_all(self):
        ctx, _ = _make_skipped_transaction(3)
        with patch("import_announcements.transaction", return_value=ctx):
            result = import_announcements_from_json(str(FIXTURES / "announcements.json"))
        assert result["imported"] == 0
        assert result["skipped"] == 3


class TestIdempotencySongs:
    def test_second_run_skips_all(self):
        ctx, _ = _make_skipped_transaction(3)
        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(FIXTURES / "song_database.json"))
        assert result["imported"] == 0
        assert result["skipped"] == 3


class TestIdempotencyTemplates:
    def test_second_run_skips_all(self):
        ctx, _ = _make_skipped_transaction(3)
        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(FIXTURES / "templates.json"))
        assert result["imported"] == 0
        assert result["skipped"] == 3


class TestIdempotencyFonts:
    def test_second_run_skips_all(self, tmp_path):
        user_dir = tmp_path / "user"
        cache_dir = tmp_path / "cache"
        for slug in ("open-sans",):
            d = user_dir / slug
            d.mkdir(parents=True)
            (d / f"{slug}.woff2").write_bytes(b"FONT")

        ctx, _ = _make_skipped_transaction(5)
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(str(user_dir), str(cache_dir))
        assert result["user_imported"] == 0
        assert result["skipped"] >= 1


# ---------------------------------------------------------------------------
# Section 3: Dry run — no DB calls made
# ---------------------------------------------------------------------------

class TestDryRunProjects:
    def test_no_db_calls(self):
        with patch("import_projects.transaction") as mock_tx:
            result = import_projects_from_json(
                str(FIXTURES / "projects.json"), dry_run=True
            )
            mock_tx.assert_not_called()
        assert result["dry_run"] is True
        assert result["imported"] == 3

    def test_no_errors(self):
        with patch("import_projects.transaction"):
            result = import_projects_from_json(
                str(FIXTURES / "projects.json"), dry_run=True
            )
        assert result["errors"] == []


class TestDryRunSettings:
    def test_no_db_calls(self):
        with patch("import_settings.transaction") as mock_tx:
            result = import_settings_from_json(
                str(FIXTURES / "settings.json"), dry_run=True
            )
            mock_tx.assert_not_called()
        assert result["dry_run"] is True
        assert result["org_keys_imported"] > 0


class TestDryRunAnnouncements:
    def test_no_db_calls(self):
        with patch("import_announcements.transaction") as mock_tx:
            result = import_announcements_from_json(
                str(FIXTURES / "announcements.json"), dry_run=True
            )
            mock_tx.assert_not_called()
        assert result["dry_run"] is True
        assert result["imported"] == 3


class TestDryRunSongs:
    def test_no_db_calls(self):
        with patch("import_songs.transaction") as mock_tx:
            result = import_songs_from_json(
                str(FIXTURES / "song_database.json"), dry_run=True
            )
            mock_tx.assert_not_called()
        assert result["dry_run"] is True
        assert result["imported"] == 3


class TestDryRunTemplates:
    def test_no_db_calls(self):
        with patch("import_templates.transaction") as mock_tx:
            result = import_templates_from_json(
                str(FIXTURES / "templates.json"), dry_run=True
            )
            mock_tx.assert_not_called()
        assert result["dry_run"] is True
        assert result["imported"] == 3
        assert result["built_in"] == 2
        assert result["custom"] == 1


class TestDryRunFonts:
    def test_no_db_calls(self, tmp_path):
        user_dir = tmp_path / "user"
        cache_dir = tmp_path / "cache"
        slug_dir = user_dir / "open-sans"
        slug_dir.mkdir(parents=True)
        (slug_dir / "open-sans.woff2").write_bytes(b"FONT")

        with patch("import_fonts.transaction") as mock_tx:
            result = import_fonts_from_directories(
                str(user_dir), str(cache_dir), dry_run=True
            )
            mock_tx.assert_not_called()
        assert result["dry_run"] is True
        assert result["user_imported"] == 1


# ---------------------------------------------------------------------------
# Section 4: Full pipeline via run_all_migrations
# ---------------------------------------------------------------------------

def _make_ok_result(imported=1, skipped=0):
    return {"imported": imported, "skipped": skipped, "errors": [], "dry_run": False}


def _make_settings_result(org=5, skipped=0, dry_run=False):
    return {
        "org_keys_imported": org,
        "user_keys_imported": 0,
        "skipped": skipped,
        "errors": [],
        "dry_run": dry_run,
    }


def _make_templates_result(imported=3, built_in=2, custom=1, skipped=0, dry_run=False):
    return {
        "imported": imported,
        "skipped": skipped,
        "built_in": built_in,
        "custom": custom,
        "errors": [],
        "dry_run": dry_run,
    }


def _make_fonts_result(user_imported=2, cache_imported=1, skipped=0, dry_run=False):
    return {
        "user_imported": user_imported,
        "cache_imported": cache_imported,
        "skipped": skipped,
        "errors": [],
        "dry_run": dry_run,
    }


@pytest.fixture
def fixture_data_dir(tmp_path):
    """Return a data dir populated with the fixture JSON files."""
    d = tmp_path / "data"
    d.mkdir()

    for name in ("projects.json", "settings.json", "announcements.json",
                 "song_database.json", "templates.json"):
        src = FIXTURES / name
        (d / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    return d


class TestPipelineDryRun:
    """--dry-run flag: all importers called with dry_run=True, no backup."""

    def _run_dry(self, fixture_data_dir):
        with (
            patch("migrations.run_all_migrations.import_projects_from_json",
                  return_value=_make_ok_result()) as p_proj,
            patch("migrations.run_all_migrations.import_settings_from_json",
                  return_value=_make_settings_result()) as p_set,
            patch("migrations.run_all_migrations.import_announcements_from_json",
                  return_value=_make_ok_result()) as p_ann,
            patch("migrations.run_all_migrations.import_songs_from_json",
                  return_value=_make_ok_result()) as p_songs,
            patch("migrations.run_all_migrations.import_templates_from_json",
                  return_value=_make_templates_result()) as p_tmpl,
            patch("migrations.run_all_migrations.import_fonts_from_directories",
                  return_value=_make_fonts_result()) as p_fonts,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--dry-run", "--data-dir", str(fixture_data_dir)])
            return exc, {
                "projects": p_proj,
                "settings": p_set,
                "announcements": p_ann,
                "songs": p_songs,
                "templates": p_tmpl,
                "fonts": p_fonts,
            }

    def test_exits_zero(self, fixture_data_dir):
        exc, _ = self._run_dry(fixture_data_dir)
        assert exc.value.code == 0

    def test_all_importers_called_with_dry_run_true(self, fixture_data_dir):
        _, mocks = self._run_dry(fixture_data_dir)
        for name, mock in mocks.items():
            assert mock.called, f"{name} importer was not called"
            # dry_run=True should be in kwargs or positional args
            kwargs = mock.call_args.kwargs
            pos = mock.call_args.args
            assert kwargs.get("dry_run") is True or True in pos, (
                f"{name} importer not called with dry_run=True"
            )

    def test_no_backup_created(self, fixture_data_dir):
        self._run_dry(fixture_data_dir)
        assert not (fixture_data_dir / "backups").exists()


class TestPipelineRealRun:
    """Real run: backup dir created, all importers called."""

    def _run_real(self, fixture_data_dir):
        with (
            patch("migrations.run_all_migrations.import_projects_from_json",
                  return_value=_make_ok_result(imported=3)) as p_proj,
            patch("migrations.run_all_migrations.import_settings_from_json",
                  return_value=_make_settings_result(org=10)) as p_set,
            patch("migrations.run_all_migrations.import_announcements_from_json",
                  return_value=_make_ok_result(imported=3)) as p_ann,
            patch("migrations.run_all_migrations.import_songs_from_json",
                  return_value=_make_ok_result(imported=3)) as p_songs,
            patch("migrations.run_all_migrations.import_templates_from_json",
                  return_value=_make_templates_result()) as p_tmpl,
            patch("migrations.run_all_migrations.import_fonts_from_directories",
                  return_value=_make_fonts_result()) as p_fonts,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--data-dir", str(fixture_data_dir)])
            return exc, {
                "projects": p_proj,
                "settings": p_set,
                "announcements": p_ann,
                "songs": p_songs,
                "templates": p_tmpl,
                "fonts": p_fonts,
            }

    def test_exits_zero(self, fixture_data_dir):
        exc, _ = self._run_real(fixture_data_dir)
        assert exc.value.code == 0

    def test_backup_dir_created(self, fixture_data_dir):
        self._run_real(fixture_data_dir)
        backups = fixture_data_dir / "backups"
        assert backups.exists()
        assert any(True for _ in backups.iterdir())

    def test_all_importers_called(self, fixture_data_dir):
        _, mocks = self._run_real(fixture_data_dir)
        for name, mock in mocks.items():
            assert mock.called, f"{name} importer was not called"

    def test_importers_not_called_with_dry_run_true(self, fixture_data_dir):
        _, mocks = self._run_real(fixture_data_dir)
        for name, mock in mocks.items():
            kwargs = mock.call_args.kwargs
            pos = mock.call_args.args
            assert kwargs.get("dry_run") is not True and True not in pos, (
                f"{name} importer unexpectedly called with dry_run=True on real run"
            )

    def test_backup_contains_fixture_json(self, fixture_data_dir):
        self._run_real(fixture_data_dir)
        backups = fixture_data_dir / "backups"
        backup_dir = next(backups.iterdir())
        assert (backup_dir / "projects.json").exists()


class TestPipelineIdempotency:
    """Second pipeline run: all importers return skipped=N, imported=0 → exit 0."""

    def test_all_skipped_exits_zero(self, fixture_data_dir):
        with (
            patch("migrations.run_all_migrations.import_projects_from_json",
                  return_value={"imported": 0, "skipped": 3, "errors": [], "dry_run": False}),
            patch("migrations.run_all_migrations.import_settings_from_json",
                  return_value={"org_keys_imported": 0, "user_keys_imported": 0,
                                "skipped": 10, "errors": [], "dry_run": False}),
            patch("migrations.run_all_migrations.import_announcements_from_json",
                  return_value={"imported": 0, "skipped": 3, "errors": [], "dry_run": False}),
            patch("migrations.run_all_migrations.import_songs_from_json",
                  return_value={"imported": 0, "skipped": 3, "errors": [], "dry_run": False}),
            patch("migrations.run_all_migrations.import_templates_from_json",
                  return_value={"imported": 0, "skipped": 3, "built_in": 2, "custom": 1,
                                "errors": [], "dry_run": False}),
            patch("migrations.run_all_migrations.import_fonts_from_directories",
                  return_value={"user_imported": 0, "cache_imported": 0,
                                "skipped": 3, "errors": [], "dry_run": False}),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--data-dir", str(fixture_data_dir)])
        assert exc.value.code == 0

    def test_no_errors_output_when_all_skipped(self, fixture_data_dir, capsys):
        with (
            patch("migrations.run_all_migrations.import_projects_from_json",
                  return_value={"imported": 0, "skipped": 3, "errors": [], "dry_run": False}),
            patch("migrations.run_all_migrations.import_settings_from_json",
                  return_value={"org_keys_imported": 0, "user_keys_imported": 0,
                                "skipped": 10, "errors": [], "dry_run": False}),
            patch("migrations.run_all_migrations.import_announcements_from_json",
                  return_value={"imported": 0, "skipped": 3, "errors": [], "dry_run": False}),
            patch("migrations.run_all_migrations.import_songs_from_json",
                  return_value={"imported": 0, "skipped": 3, "errors": [], "dry_run": False}),
            patch("migrations.run_all_migrations.import_templates_from_json",
                  return_value={"imported": 0, "skipped": 3, "built_in": 2, "custom": 1,
                                "errors": [], "dry_run": False}),
            patch("migrations.run_all_migrations.import_fonts_from_directories",
                  return_value={"user_imported": 0, "cache_imported": 0,
                                "skipped": 3, "errors": [], "dry_run": False}),
        ):
            with pytest.raises(SystemExit):
                main(["--data-dir", str(fixture_data_dir)])
        captured = capsys.readouterr()
        assert "ERROR" not in captured.err
