"""
tests/test_import_fonts.py — Unit tests for migrations/import_fonts.py.

All Postgres interactions are mocked; no live database required.
Filesystem fixtures use pytest's tmp_path.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root and migrations/ are importable.
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "migrations"))

from import_fonts import (
    scan_font_directory,
    import_fonts_from_directories,
    _family_from_slug,
    _font_uuid,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_font_file(directory: Path, filename: str, content: bytes = b"FONT") -> Path:
    """Write a minimal font file and return its path."""
    p = directory / filename
    p.write_bytes(content)
    return p


def _make_css_file(directory: Path, content: str = "/* font.css */") -> Path:
    p = directory / "font.css"
    p.write_text(content, encoding="utf-8")
    return p


def _mock_transaction(inserted_flags: list[bool]):
    """Build a mock ``transaction()`` context manager.

    *inserted_flags* is consumed in call order: True → rowcount=1 (inserted),
    False → rowcount=0 (ON CONFLICT DO NOTHING).
    """
    call_index = [0]

    def _execute(sql, params=None):
        cursor = MagicMock()
        idx = call_index[0]
        cursor.rowcount = 1 if (idx < len(inserted_flags) and inserted_flags[idx]) else 0
        call_index[0] += 1
        return cursor

    conn = MagicMock()
    conn.execute.side_effect = _execute

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, conn


# ---------------------------------------------------------------------------
# scan_font_directory — filesystem-only tests (no DB)
# ---------------------------------------------------------------------------


class TestScanFontDirectory:
    def test_two_woff2_files_returns_two_entries(self, tmp_path):
        """A directory with two font-family subdirs each containing .woff2 → 2 entries."""
        for slug in ("open-sans", "roboto"):
            family_dir = tmp_path / slug
            family_dir.mkdir()
            _make_font_file(family_dir, f"{slug}.woff2")

        results = scan_font_directory(str(tmp_path), "user")

        assert len(results) == 2
        slugs = {r["slug"] for r in results}
        assert "open-sans" in slugs
        assert "roboto" in slugs

    def test_source_field_propagated(self, tmp_path):
        (tmp_path / "myfont").mkdir()
        _make_font_file(tmp_path / "myfont", "myfont.woff2")

        results = scan_font_directory(str(tmp_path), "user")
        assert results[0]["source"] == "user"

    def test_family_derived_from_slug(self, tmp_path):
        (tmp_path / "open-sans").mkdir()
        _make_font_file(tmp_path / "open-sans", "opensans.woff2")

        results = scan_font_directory(str(tmp_path), "user")
        assert results[0]["family"] == "Open Sans"

    def test_css_url_user_source(self, tmp_path):
        (tmp_path / "my-font").mkdir()
        _make_font_file(tmp_path / "my-font", "my-font.woff2")

        results = scan_font_directory(str(tmp_path), "user")
        assert results[0]["css_url"] == "/fonts/user/my-font/font.css"

    def test_css_url_cache_source_with_css_file(self, tmp_path):
        """Cache fonts: css_url is populated when font.css exists on disk."""
        family_dir = tmp_path / "noto-serif"
        family_dir.mkdir()
        _make_font_file(family_dir, "noto.woff2")
        _make_css_file(family_dir)

        results = scan_font_directory(str(tmp_path), "cache")
        assert results[0]["css_url"] == "/fonts/cache/noto-serif/font.css"

    def test_css_url_cache_source_without_css_file(self, tmp_path):
        """Cache fonts without a font.css file → css_url is empty string."""
        family_dir = tmp_path / "lato"
        family_dir.mkdir()
        _make_font_file(family_dir, "lato.woff2")

        results = scan_font_directory(str(tmp_path), "cache")
        assert results[0]["css_url"] == ""

    def test_file_path_is_first_binary(self, tmp_path):
        family_dir = tmp_path / "raleway"
        family_dir.mkdir()
        _make_font_file(family_dir, "raleway-bold.woff2")
        _make_font_file(family_dir, "raleway-regular.woff2")

        results = scan_font_directory(str(tmp_path), "user")
        # Sorted alphabetically → bold comes before regular
        assert results[0]["file_path"].endswith("raleway-bold.woff2")

    def test_cached_at_is_iso_string(self, tmp_path):
        family_dir = tmp_path / "myfont"
        family_dir.mkdir()
        _make_font_file(family_dir, "myfont.ttf")

        results = scan_font_directory(str(tmp_path), "user")
        cached_at = results[0]["cached_at"]
        assert cached_at is not None
        # Should parse as ISO 8601 without raising.
        from datetime import datetime, timezone
        # Python's fromisoformat handles "+00:00" suffixes.
        dt = datetime.fromisoformat(cached_at)
        assert dt.tzinfo is not None  # timezone-aware

    def test_upload_metadata_is_empty_dict(self, tmp_path):
        family_dir = tmp_path / "myfont"
        family_dir.mkdir()
        _make_font_file(family_dir, "myfont.woff")

        results = scan_font_directory(str(tmp_path), "user")
        assert results[0]["upload_metadata"] == {}

    def test_css_only_directory_included_for_cache(self, tmp_path):
        """A subdir with only font.css (no binary) is included for 'cache' source."""
        family_dir = tmp_path / "cached-web-font"
        family_dir.mkdir()
        _make_css_file(family_dir)

        results = scan_font_directory(str(tmp_path), "cache")
        assert len(results) == 1
        assert results[0]["file_path"] == ""
        assert results[0]["cached_at"] is None

    def test_empty_subdir_excluded(self, tmp_path):
        """A subdir with no font files and no CSS is excluded."""
        (tmp_path / "empty-dir").mkdir()

        results = scan_font_directory(str(tmp_path), "user")
        assert results == []

    def test_empty_directory_returns_empty_list(self, tmp_path):
        results = scan_font_directory(str(tmp_path), "user")
        assert results == []

    def test_missing_directory_returns_empty_list(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        results = scan_font_directory(str(missing), "user")
        assert results == []

    def test_missing_directory_does_not_raise(self, tmp_path):
        """scan_font_directory must never raise for a missing directory."""
        missing = tmp_path / "nonexistent"
        try:
            scan_font_directory(str(missing), "user")
        except Exception as exc:
            pytest.fail(f"scan_font_directory raised unexpectedly: {exc}")

    def test_all_binary_extensions_recognised(self, tmp_path):
        """Each of .woff, .woff2, .ttf, .otf should count as a font binary."""
        for ext in (".woff", ".woff2", ".ttf", ".otf"):
            slug = f"font{ext.lstrip('.')}"
            (tmp_path / slug).mkdir()
            _make_font_file(tmp_path / slug, f"font{ext}")

        results = scan_font_directory(str(tmp_path), "user")
        assert len(results) == 4

    def test_non_font_files_ignored(self, tmp_path):
        """PNG, PDF, and other files in a font dir are not treated as binaries."""
        family_dir = tmp_path / "myfont"
        family_dir.mkdir()
        (family_dir / "license.txt").write_text("MIT", encoding="utf-8")
        (family_dir / "preview.png").write_bytes(b"\x89PNG")

        results = scan_font_directory(str(tmp_path), "user")
        assert results == []


# ---------------------------------------------------------------------------
# import_fonts_from_directories — integration + DB mock tests
# ---------------------------------------------------------------------------


class TestImportFontsFromDirectories:
    def _make_user_dir(self, tmp_path: Path) -> Path:
        user = tmp_path / "fonts" / "user"
        user.mkdir(parents=True)
        return user

    def _make_cache_dir(self, tmp_path: Path) -> Path:
        cache = tmp_path / "fonts" / "cache"
        cache.mkdir(parents=True)
        return cache

    # ── Happy path: two user fonts imported ───────────────────────────────────

    def test_two_user_fonts_imported(self, tmp_path):
        user = self._make_user_dir(tmp_path)
        cache = self._make_cache_dir(tmp_path)

        for slug in ("open-sans", "roboto"):
            d = user / slug
            d.mkdir()
            _make_font_file(d, f"{slug}.woff2")

        ctx, conn = _mock_transaction([True, True])
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(str(user), str(cache))

        assert result["user_imported"] == 2
        assert result["cache_imported"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == []
        assert result["dry_run"] is False

    def test_upsert_called_for_each_font(self, tmp_path):
        user = self._make_user_dir(tmp_path)
        cache = self._make_cache_dir(tmp_path)

        for slug in ("merriweather", "playfair-display"):
            d = user / slug
            d.mkdir()
            _make_font_file(d, f"{slug}.woff2")

        ctx, conn = _mock_transaction([True, True])
        with patch("import_fonts.transaction", return_value=ctx):
            import_fonts_from_directories(str(user), str(cache))

        assert conn.execute.call_count == 2

    def test_on_conflict_do_nothing_in_sql(self, tmp_path):
        """The INSERT SQL must include ON CONFLICT (slug) DO NOTHING."""
        user = self._make_user_dir(tmp_path)
        cache = self._make_cache_dir(tmp_path)

        d = user / "lato"
        d.mkdir()
        _make_font_file(d, "lato.woff2")

        ctx, conn = _mock_transaction([True])
        with patch("import_fonts.transaction", return_value=ctx):
            import_fonts_from_directories(str(user), str(cache))

        sql = conn.execute.call_args_list[0].args[0]
        assert "ON CONFLICT" in sql
        assert "DO NOTHING" in sql

    # ── CSS file in directory → css_url captured ──────────────────────────────

    def test_css_file_captured_for_cache_font(self, tmp_path):
        user = self._make_user_dir(tmp_path)
        cache = self._make_cache_dir(tmp_path)

        d = cache / "noto-sans"
        d.mkdir()
        _make_font_file(d, "noto.woff2")
        _make_css_file(d)

        ctx, conn = _mock_transaction([True])
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(str(user), str(cache))

        assert result["cache_imported"] == 1
        # Confirm css_url was included in the params passed to conn.execute.
        params = conn.execute.call_args_list[0].args[1]
        assert params["css_url"] == "/fonts/cache/noto-sans/font.css"

    # ── Empty directory → 0 imported, no error ────────────────────────────────

    def test_empty_user_dir_no_error(self, tmp_path):
        user = self._make_user_dir(tmp_path)
        cache = self._make_cache_dir(tmp_path)

        ctx, conn = _mock_transaction([])
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(str(user), str(cache))

        assert result["user_imported"] == 0
        assert result["cache_imported"] == 0
        assert result["errors"] == []

    def test_empty_dir_no_db_calls(self, tmp_path):
        user = self._make_user_dir(tmp_path)
        cache = self._make_cache_dir(tmp_path)

        ctx, conn = _mock_transaction([])
        with patch("import_fonts.transaction", return_value=ctx):
            import_fonts_from_directories(str(user), str(cache))

        conn.execute.assert_not_called()

    # ── Missing directory → 0 imported, no crash ──────────────────────────────

    def test_missing_user_dir_no_crash(self, tmp_path):
        missing_user = tmp_path / "no-such-user"
        cache = self._make_cache_dir(tmp_path)

        ctx, conn = _mock_transaction([])
        with patch("import_fonts.transaction", return_value=ctx):
            try:
                result = import_fonts_from_directories(str(missing_user), str(cache))
            except Exception as exc:
                pytest.fail(f"Raised unexpectedly: {exc}")

        assert result["user_imported"] == 0
        assert result["errors"] == []

    def test_missing_cache_dir_no_crash(self, tmp_path):
        user = self._make_user_dir(tmp_path)
        missing_cache = tmp_path / "no-such-cache"

        ctx, conn = _mock_transaction([])
        with patch("import_fonts.transaction", return_value=ctx):
            try:
                result = import_fonts_from_directories(str(user), str(missing_cache))
            except Exception as exc:
                pytest.fail(f"Raised unexpectedly: {exc}")

        assert result["cache_imported"] == 0
        assert result["errors"] == []

    def test_both_dirs_missing_returns_zero_counts(self, tmp_path):
        ctx, conn = _mock_transaction([])
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(
                str(tmp_path / "x"), str(tmp_path / "y")
            )

        assert result == {
            "user_imported": 0,
            "cache_imported": 0,
            "skipped": 0,
            "errors": [],
            "dry_run": False,
        }

    # ── Re-run → 0 new (ON CONFLICT DO NOTHING) ───────────────────────────────

    def test_rerun_counts_as_skipped(self, tmp_path):
        user = self._make_user_dir(tmp_path)
        cache = self._make_cache_dir(tmp_path)

        d = user / "already-there"
        d.mkdir()
        _make_font_file(d, "already.woff2")

        # DB reports rowcount=0 (conflict → DO NOTHING)
        ctx, conn = _mock_transaction([False])
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(str(user), str(cache))

        assert result["user_imported"] == 0
        assert result["skipped"] == 1
        assert result["errors"] == []

    def test_mixed_new_and_existing(self, tmp_path):
        user = self._make_user_dir(tmp_path)
        cache = self._make_cache_dir(tmp_path)

        for slug in ("new-font", "old-font"):
            d = user / slug
            d.mkdir()
            _make_font_file(d, f"{slug}.woff2")

        ctx, conn = _mock_transaction([True, False])
        with patch("import_fonts.transaction", return_value=ctx):
            result = import_fonts_from_directories(str(user), str(cache))

        assert result["user_imported"] == 1
        assert result["skipped"] == 1

    # ── Dry run → no DB writes ────────────────────────────────────────────────

    def test_dry_run_returns_would_be_counts(self, tmp_path):
        user = self._make_user_dir(tmp_path)
        cache = self._make_cache_dir(tmp_path)

        for slug in ("font-a", "font-b"):
            d = user / slug
            d.mkdir()
            _make_font_file(d, f"{slug}.woff2")

        cached_d = cache / "cached-font"
        cached_d.mkdir()
        _make_font_file(cached_d, "cached.woff2")
        _make_css_file(cached_d)

        with patch("import_fonts.transaction") as mock_tx:
            result = import_fonts_from_directories(str(user), str(cache), dry_run=True)
            mock_tx.assert_not_called()

        assert result["dry_run"] is True
        assert result["user_imported"] == 2
        assert result["cache_imported"] == 1
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_dry_run_does_not_open_transaction(self, tmp_path):
        user = self._make_user_dir(tmp_path)
        cache = self._make_cache_dir(tmp_path)

        d = user / "some-font"
        d.mkdir()
        _make_font_file(d, "some.ttf")

        with patch("import_fonts.transaction") as mock_tx:
            import_fonts_from_directories(str(user), str(cache), dry_run=True)

        mock_tx.assert_not_called()

    def test_dry_run_with_missing_dirs_returns_zeros(self, tmp_path):
        with patch("import_fonts.transaction") as mock_tx:
            result = import_fonts_from_directories(
                str(tmp_path / "x"), str(tmp_path / "y"), dry_run=True
            )
            mock_tx.assert_not_called()

        assert result == {
            "user_imported": 0,
            "cache_imported": 0,
            "skipped": 0,
            "errors": [],
            "dry_run": True,
        }


# ---------------------------------------------------------------------------
# _family_from_slug — pure helper
# ---------------------------------------------------------------------------


class TestFamilyFromSlug:
    def test_dashes_to_spaces_title_case(self):
        assert _family_from_slug("open-sans") == "Open Sans"

    def test_single_word(self):
        assert _family_from_slug("roboto") == "Roboto"

    def test_already_title_case(self):
        assert _family_from_slug("Merriweather") == "Merriweather"

    def test_multiple_words(self):
        assert _family_from_slug("playfair-display-sc") == "Playfair Display Sc"


# ---------------------------------------------------------------------------
# _font_uuid — stable UUID generation
# ---------------------------------------------------------------------------


class TestFontUUID:
    def test_same_inputs_same_uuid(self):
        assert _font_uuid("open-sans", "user") == _font_uuid("open-sans", "user")

    def test_different_slug_different_uuid(self):
        assert _font_uuid("open-sans", "user") != _font_uuid("roboto", "user")

    def test_different_source_different_uuid(self):
        assert _font_uuid("lato", "user") != _font_uuid("lato", "cache")

    def test_returns_valid_uuid_string(self):
        result = _font_uuid("merriweather", "cache")
        # Should not raise.
        uuid.UUID(result)
