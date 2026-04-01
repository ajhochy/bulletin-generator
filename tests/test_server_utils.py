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
