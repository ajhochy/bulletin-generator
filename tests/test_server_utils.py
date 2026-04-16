"""
Tests for server.py utility functions.
Covers: _read_json, _write_json, unfold_ical, unescape_ical, _parse_list_env, _load_dotenv
"""
import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

# Add project root so server.py can be imported without starting the server
sys.path.insert(0, str(Path(__file__).parent.parent))

import server


# ── _read_json / _write_json ───────────────────────────────────────────────────

class TestReadWriteJson:
    def test_write_then_read(self, tmp_path):
        p = tmp_path / "test.json"
        data = {"key": "value", "num": 42}
        server._write_json(p, data)
        result = server._read_json(p, {})
        assert result == data

    def test_read_missing_file_returns_default(self, tmp_path):
        p = tmp_path / "nonexistent.json"
        result = server._read_json(p, {"default": True})
        assert result == {"default": True}

    def test_read_corrupted_file_returns_default(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not valid json {{{{", encoding="utf-8")
        result = server._read_json(p, [])
        assert result == []

    def test_write_is_atomic_via_tmp(self, tmp_path):
        """_write_json should write to .tmp then rename — no partial writes."""
        p = tmp_path / "data.json"
        server._write_json(p, {"ok": True})
        # .tmp should be gone after write
        assert not (tmp_path / "data.tmp").exists()
        assert p.exists()

    def test_write_overwrites_existing(self, tmp_path):
        p = tmp_path / "data.json"
        server._write_json(p, {"v": 1})
        server._write_json(p, {"v": 2})
        assert server._read_json(p, {})["v"] == 2

    def test_write_unicode(self, tmp_path):
        p = tmp_path / "unicode.json"
        data = {"name": "Héllo Wörld 🎵"}
        server._write_json(p, data)
        assert server._read_json(p, {})["name"] == "Héllo Wörld 🎵"


# ── Template migrations ───────────────────────────────────────────────────────

class TestTemplateMigration:
    def test_classic_template_migration_seeds_templates_and_projects(self, tmp_path, monkeypatch):
        templates_path = tmp_path / "templates.json"
        projects_path = tmp_path / "projects.json"
        monkeypatch.setattr(server, "TEMPLATES_FILE", templates_path)
        monkeypatch.setattr(server, "PROJECTS_FILE", projects_path)

        server._write_json(projects_path, [
            {
                "id": "proj_old",
                "state": {
                    "svcTitle": "Legacy",
                    "activeDocTemplate": {"pageSize": "8.5x11"},
                },
            }
        ])

        server._migration_002_classic_template_default()

        templates = server._read_json(templates_path, [])
        projects = server._read_json(projects_path, [])
        assert [t["id"] for t in templates] == ["classic"]
        migrated = projects[0]["state"]["activeDocTemplate"]
        assert migrated["id"] == "classic"
        assert migrated["pageSize"] == "8.5x11"
        assert migrated["zones"]

    def test_classic_template_migration_is_idempotent(self, tmp_path, monkeypatch):
        templates_path = tmp_path / "templates.json"
        projects_path = tmp_path / "projects.json"
        monkeypatch.setattr(server, "TEMPLATES_FILE", templates_path)
        monkeypatch.setattr(server, "PROJECTS_FILE", projects_path)

        server._write_json(projects_path, [{"id": "proj_old", "state": {}}])

        server._migration_002_classic_template_default()
        server._migration_002_classic_template_default()

        templates = server._read_json(templates_path, [])
        projects = server._read_json(projects_path, [])
        assert len([t for t in templates if t.get("id") == "classic"]) == 1
        assert projects[0]["state"]["activeDocTemplate"]["zones"]

    def test_project_backfill_runs_when_m002_was_already_applied(self, tmp_path, monkeypatch):
        templates_path = tmp_path / "templates.json"
        projects_path = tmp_path / "projects.json"
        migrations_path = tmp_path / "migrations.json"
        monkeypatch.setattr(server, "TEMPLATES_FILE", templates_path)
        monkeypatch.setattr(server, "PROJECTS_FILE", projects_path)
        monkeypatch.setattr(server, "MIGRATIONS_FILE", migrations_path)

        server._write_json(templates_path, [server._classic_template()])
        server._write_json(projects_path, [{"id": "proj_old", "state": {}}])
        server._write_json(migrations_path, ["M001_songdb_extraction", "M002_classic_template_default"])

        server.run_migrations()

        projects = server._read_json(projects_path, [])
        migrations = server._read_json(migrations_path, [])
        assert projects[0]["state"]["activeDocTemplate"]["zones"]
        assert "M003_project_template_backfill" in migrations

    def test_classic_staff_zone_migration_enables_staff(self, tmp_path, monkeypatch):
        templates_path = tmp_path / "templates.json"
        monkeypatch.setattr(server, "TEMPLATES_FILE", templates_path)
        classic = server._classic_template()
        for zone in classic["zones"]:
            if zone["binding"] == "staff":
                zone["enabled"] = False
        server._write_json(templates_path, [classic])

        server._migration_004_classic_staff_zone_enabled()

        templates = server._read_json(templates_path, [])
        staff_zone = next(z for z in templates[0]["zones"] if z["binding"] == "staff")
        assert staff_zone["enabled"] is True

    def test_builtin_template_sync_seeds_classic_and_modern(self, tmp_path, monkeypatch):
        templates_path = tmp_path / "templates.json"
        monkeypatch.setattr(server, "TEMPLATES_FILE", templates_path)
        server._write_json(templates_path, [])

        server._sync_builtin_templates()

        templates = server._read_json(templates_path, [])
        ids = [t["id"] for t in templates]
        assert ids == ["classic", "modern"]
        assert all(t["builtIn"] for t in templates)
        assert templates[1]["cssVars"]["fontFamily"] == "Open Sans"

    def test_template_validator_rejects_builtin_modification(self):
        class Dummy:
            pass
        dummy = Dummy()
        dummy._validate_template = server.Handler._validate_template.__get__(dummy, Dummy)
        assert dummy._validate_template(server._classic_template()) == "built-in templates cannot be modified"

    def test_user_font_css_generation(self, tmp_path):
        font_dir = tmp_path / "my-font"
        font_dir.mkdir()
        (font_dir / "MyFont.woff2").write_bytes(b"font")
        class Dummy:
            pass
        dummy = Dummy()
        dummy._build_user_font_css = server.Handler._build_user_font_css.__get__(dummy, Dummy)
        css = dummy._build_user_font_css("my-font", font_dir)
        assert 'font-family: "My Font"' in css
        assert "/fonts/user/my-font/MyFont.woff2" in css


# ── iCal helpers ──────────────────────────────────────────────────────────────

class TestUnfoldIcal:
    def test_simple_unfold(self):
        # RFC 5545: CRLF + leading whitespace are removed entirely (no space preserved)
        folded = "SUMMARY:Hello\r\n World"
        assert server.unfold_ical(folded) == "SUMMARY:HelloWorld"

    def test_tab_continuation(self):
        folded = "DESCRIPTION:line1\r\n\tcontinued"
        assert server.unfold_ical(folded) == "DESCRIPTION:line1continued"

    def test_no_folding_unchanged(self):
        plain = "BEGIN:VCALENDAR\nEND:VCALENDAR"
        assert server.unfold_ical(plain) == plain

    def test_cr_without_lf(self):
        text = "A:1\rB:2"
        result = server.unfold_ical(text)
        assert "A:1" in result and "B:2" in result


class TestUnescapeIcal:
    def test_newline_escape(self):
        assert server.unescape_ical(r"line1\nline2") == "line1\nline2"

    def test_comma_escape(self):
        assert server.unescape_ical(r"a\,b") == "a,b"

    def test_semicolon_escape(self):
        assert server.unescape_ical(r"a\;b") == "a;b"

    def test_backslash_escape(self):
        assert server.unescape_ical(r"a\\b") == "a\\b"

    def test_no_escapes_unchanged(self):
        assert server.unescape_ical("plain text") == "plain text"


# ── _parse_list_env ───────────────────────────────────────────────────────────

class TestParseListEnv:
    def test_empty_returns_empty(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_LIST_ENV", None)
            assert server._parse_list_env("TEST_LIST_ENV") == []

    def test_json_array(self):
        with patch.dict(os.environ, {"TEST_LIST_ENV": '["a","b","c"]'}):
            assert server._parse_list_env("TEST_LIST_ENV") == ["a", "b", "c"]

    def test_comma_separated(self):
        with patch.dict(os.environ, {"TEST_LIST_ENV": "a,b,c"}):
            result = server._parse_list_env("TEST_LIST_ENV")
            assert result == ["a", "b", "c"]

    def test_newline_separated(self):
        with patch.dict(os.environ, {"TEST_LIST_ENV": "a\nb\nc"}):
            result = server._parse_list_env("TEST_LIST_ENV")
            assert result == ["a", "b", "c"]

    def test_strips_whitespace(self):
        with patch.dict(os.environ, {"TEST_LIST_ENV": "  a , b , c  "}):
            result = server._parse_list_env("TEST_LIST_ENV")
            assert result == ["a", "b", "c"]
