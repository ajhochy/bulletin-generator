"""
Tests for propresenter_export.py (#77 / #103).
Covers: _split_stanzas, _rtf_encode, _build_presentation, export_items_to_zip
"""
import io
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from propresenter_export import (
        _split_stanzas,
        _rtf_encode,
        _build_presentation,
        export_items_to_zip,
    )
    _PP_AVAILABLE = True
except ImportError:
    _PP_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _PP_AVAILABLE,
    reason="propresenter_export.py not present"
)


# ── _split_stanzas ────────────────────────────────────────────────────────────

class TestSplitStanzas:
    def test_single_stanza(self):
        text = "Amazing grace\nHow sweet the sound"
        result = _split_stanzas(text)
        assert len(result) == 1
        assert "Amazing grace" in result[0]

    def test_two_stanzas_split_on_blank_line(self):
        text = "Verse one line one\nVerse one line two\n\nVerse two line one"
        result = _split_stanzas(text)
        assert len(result) == 2

    def test_empty_string_returns_empty(self):
        assert _split_stanzas("") == []

    def test_none_returns_empty(self):
        assert _split_stanzas(None) == []

    def test_multiple_blank_lines_not_extra_stanzas(self):
        text = "Stanza 1\n\n\nStanza 2"
        result = _split_stanzas(text)
        assert len(result) == 2

    def test_trailing_blank_line_ignored(self):
        text = "Only stanza\n\n"
        result = _split_stanzas(text)
        assert len(result) == 1


# ── _rtf_encode ───────────────────────────────────────────────────────────────

class TestRtfEncode:
    def test_returns_string(self):
        assert isinstance(_rtf_encode("Hello"), str)

    def test_contains_input_text(self):
        assert "Hello" in _rtf_encode("Hello")

    def test_rtf_header_present(self):
        result = _rtf_encode("test")
        assert result.startswith("{\\rtf1")

    def test_escapes_backslash(self):
        result = _rtf_encode("path\\to\\file")
        assert "\\\\" in result

    def test_escapes_braces(self):
        result = _rtf_encode("{test}")
        assert "\\{" in result
        assert "\\}" in result


# ── _build_presentation ───────────────────────────────────────────────────────

class TestBuildPresentation:
    def test_song_returns_dict(self):
        item = {"type": "song", "title": "Amazing Grace", "body": "Amazing grace\n\nHow sweet"}
        result = _build_presentation(item)
        assert result is not None
        assert result["name"] == "Amazing Grace"

    def test_song_has_groups(self):
        item = {"type": "song", "title": "Test Song", "body": "Stanza 1\n\nStanza 2"}
        result = _build_presentation(item)
        assert len(result["groups"]) > 0

    def test_song_category(self):
        item = {"type": "song", "title": "Test", "body": "lyrics"}
        assert _build_presentation(item)["category"] == "Song"

    def test_liturgy_returns_dict(self):
        item = {"type": "liturgy", "title": "Lord's Prayer", "body": "Our Father\n\nHallowed be thy name"}
        result = _build_presentation(item)
        assert result is not None
        assert result["category"] == "Liturgy"

    def test_label_returns_dict(self):
        item = {"type": "label", "title": "Welcome", "body": "Welcome everyone"}
        assert _build_presentation(item) is not None

    def test_section_returns_none(self):
        item = {"type": "section", "title": "GATHERING"}
        assert _build_presentation(item) is None

    def test_note_returns_none(self):
        item = {"type": "note", "title": "Internal note", "body": "Don't print"}
        assert _build_presentation(item) is None

    def test_media_returns_none(self):
        item = {"type": "media", "title": "Video"}
        assert _build_presentation(item) is None

    def test_page_break_returns_none(self):
        item = {"type": "page-break"}
        assert _build_presentation(item) is None

    def test_song_ccli_populated(self):
        item = {"type": "song", "title": "Test", "body": "lyrics", "ccli": "12345", "author": "J. Newton"}
        result = _build_presentation(item)
        assert result["ccli"]["songNumber"] == "12345"
        assert result["ccli"]["artist"] == "J. Newton"


# ── export_items_to_zip ───────────────────────────────────────────────────────

class TestExportItemsToZip:
    def _make_items(self):
        return [
            {"type": "song",    "title": "Amazing Grace", "body": "Amazing grace\n\nHow sweet the sound"},
            {"type": "liturgy", "title": "Lords Prayer",  "body": "Our Father\n\nHallowed be thy name"},
            {"type": "section", "title": "GATHERING"},
            {"type": "note",    "title": "Internal",      "body": "skip me"},
        ]

    def test_returns_bytes(self):
        result = export_items_to_zip(self._make_items())
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_is_valid_zip(self):
        result = export_items_to_zip(self._make_items())
        assert zipfile.is_zipfile(io.BytesIO(result))

    def test_only_exportable_items_in_zip(self):
        result = export_items_to_zip(self._make_items())
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        # section and note should be excluded
        assert len(names) == 2
        assert any("Amazing Grace" in n for n in names)
        assert any("Lords Prayer" in n for n in names)

    def test_filenames_are_sequential(self):
        result = export_items_to_zip(self._make_items())
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = sorted(zf.namelist())
        assert names[0].startswith("01 -")
        assert names[1].startswith("02 -")

    def test_files_have_pro6_extension(self):
        """Exported files must be .pro6 (ProPresenter 6 XML), not .pro.json."""
        result = export_items_to_zip(self._make_items())
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            for name in zf.namelist():
                if name != "README.json":
                    assert name.endswith(".pro6"), f"Expected .pro6 extension, got: {name}"

    def test_files_contain_valid_xml(self):
        """Exported .pro6 files must be parseable XML."""
        result = export_items_to_zip(self._make_items())
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            for name in zf.namelist():
                if name.endswith(".pro6"):
                    xml_bytes = zf.read(name)
                    root = ET.fromstring(xml_bytes)
                    assert root.tag == "RVPresentationDocument"

    def test_xml_contains_ccli_attributes(self):
        """Root element must carry song metadata attributes."""
        items = [{"type": "song", "title": "Test Song", "body": "lyrics", "author": "Author"}]
        result = export_items_to_zip(items)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read(zf.namelist()[0])
        root = ET.fromstring(xml_bytes)
        assert root.get("CCLISongTitle") == "Test Song"
        assert root.get("CCLIArtistCredits") == "Author"

    def test_xml_contains_slide_groupings(self):
        """Each .pro6 must contain at least one RVSlideGrouping element."""
        items = [{"type": "song", "title": "Test", "body": "Stanza 1\n\nStanza 2"}]
        result = export_items_to_zip(items)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read(zf.namelist()[0])
        root = ET.fromstring(xml_bytes)
        groupings = root.findall(".//RVSlideGrouping")
        assert len(groupings) > 0

    def test_xml_slides_contain_plain_text(self):
        """NSString source elements must contain the lyric text."""
        items = [{"type": "song", "title": "Test", "body": "Amazing grace"}]
        result = export_items_to_zip(items)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read(zf.namelist()[0])
        root = ET.fromstring(xml_bytes)
        sources = [el for el in root.findall(".//NSString") if el.get("rvXMLIvarName") == "source"]
        texts = " ".join(el.text or "" for el in sources)
        assert "Amazing grace" in texts

    def test_empty_items_returns_readme_fallback(self):
        result = export_items_to_zip([])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert names == ["README.json"]

    def test_only_non_exportable_returns_readme_fallback(self):
        items = [{"type": "section", "title": "GATHERING"}, {"type": "note", "title": "x"}]
        result = export_items_to_zip(items)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert names == ["README.json"]

    def test_project_name_in_readme_fallback(self):
        result = export_items_to_zip([], project_name="my-church")
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            readme = json.loads(zf.read("README.json"))
        assert readme["projectName"] == "my-church"

    def test_slash_in_title_sanitized(self):
        items = [{"type": "song", "title": "AC/DC Song", "body": "lyrics"}]
        result = export_items_to_zip(items)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            name = zf.namelist()[0]
        assert "/" not in name.split(" - ", 1)[1]  # slash removed from title part
