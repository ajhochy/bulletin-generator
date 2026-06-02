"""
tests/test_import_songs.py — Unit tests for migrations/import_songs.py.

All Postgres interactions are mocked; no live database required.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

# The module under test lives in migrations/; add that to the path too.
sys.path.insert(0, str(Path(__file__).parent.parent / "migrations"))

from import_songs import import_songs_from_json, _parse_song

# Reuse the same namespace as the module for consistency checks.
_SONG_NAMESPACE = uuid.UUID("c0ffee00-d400-4db0-0000-000000000000")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _song_fingerprint_uuid(title: str, author: str, source: str) -> str:
    """Reproduce the UUID5 generation used by _parse_song."""
    return str(uuid.uuid5(_SONG_NAMESPACE, f"{title}\x00{author}\x00{source}"))


@pytest.fixture
def songs_file(tmp_path):
    """Return a factory that writes a list of songs to a temp JSON file."""
    def _make(songs: list) -> Path:
        p = tmp_path / "song_database.json"
        p.write_text(json.dumps(songs), encoding="utf-8")
        return p
    return _make


def _mock_transaction(inserted_rows: list[bool]):
    """Build a mock ``transaction()`` context manager.

    *inserted_rows* is a list of booleans (one per song): True means
    INSERT succeeded (rowcount=1), False means ON CONFLICT DO NOTHING (rowcount=0).
    """
    call_index = [0]

    def side_effect(sql, params=None):
        cursor = MagicMock()
        idx = call_index[0]
        cursor.rowcount = 1 if (idx < len(inserted_rows) and inserted_rows[idx]) else 0
        call_index[0] += 1
        return cursor

    conn = MagicMock()
    conn.execute.side_effect = side_effect

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, conn


# ---------------------------------------------------------------------------
# Happy-path: three songs (manual, pco-imported, empty author) → all imported
# ---------------------------------------------------------------------------


class TestImportThreeSongs:
    SONGS = [
        {
            "id": str(uuid.uuid4()),
            "title": "Amazing Grace",
            "author": "John Newton",
            "lyrics": "Amazing grace how sweet the sound",
            "copyright": "Public Domain",
            "source": "manual",
            "dateAdded": "2024-01-15",
        },
        {
            "id": str(uuid.uuid4()),
            "title": "How Great Thou Art",
            "author": "Carl Boberg",
            "lyrics": "O Lord my God when I in awesome wonder",
            "copyright": "Stuart K. Hine Trust",
            "source": "pco-import",
            "dateAdded": "2024-02-20",
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Be Thou My Vision",
            "author": "",
            "lyrics": "Be thou my vision O Lord of my heart",
            "copyright": "Public Domain",
            "source": "manual",
            "dateAdded": "2024-03-01",
        },
    ]

    def test_returns_three_imported(self, songs_file):
        path = songs_file(self.SONGS)
        ctx, conn = _mock_transaction([True, True, True])

        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(path))

        assert result["imported"] == 3
        assert result["skipped"] == 0
        assert result["errors"] == []
        assert result["dry_run"] is False

    def test_upsert_called_for_each_song(self, songs_file):
        path = songs_file(self.SONGS)
        ctx, conn = _mock_transaction([True, True, True])

        with patch("import_songs.transaction", return_value=ctx):
            import_songs_from_json(str(path))

        assert conn.execute.call_count == 3

    def test_conflict_do_nothing_in_sql(self, songs_file):
        """The INSERT SQL must include ON CONFLICT (id) DO NOTHING."""
        path = songs_file(self.SONGS[:1])
        ctx, conn = _mock_transaction([True])

        with patch("import_songs.transaction", return_value=ctx):
            import_songs_from_json(str(path))

        upsert_sql = conn.execute.call_args_list[0].args[0]
        assert "ON CONFLICT" in upsert_sql
        assert "DO NOTHING" in upsert_sql


# ---------------------------------------------------------------------------
# Duplicate title + same author + same source → same UUID5 (1 unique song)
# ---------------------------------------------------------------------------


class TestDuplicateTitleSameAuthorSameSource:
    def test_same_fingerprint_produces_same_uuid(self):
        """Same title/author/source → same UUID5, regardless of whether an id is present."""
        song_a = {"title": "Holy Holy Holy", "author": "Reginald Heber", "source": "manual"}
        song_b = {"title": "Holy Holy Holy", "author": "Reginald Heber", "source": "manual"}

        row_a = _parse_song(song_a, 0)
        row_b = _parse_song(song_b, 1)

        assert row_a["id"] == row_b["id"]

    def test_duplicate_in_file_counts_only_once_when_db_skips(self, songs_file):
        """When both records share the same UUID, ON CONFLICT DO NOTHING skips the second."""
        shared_id = _song_fingerprint_uuid("Holy Holy Holy", "Reginald Heber", "manual")
        songs = [
            {"title": "Holy Holy Holy", "author": "Reginald Heber", "source": "manual"},
            {"title": "Holy Holy Holy", "author": "Reginald Heber", "source": "manual"},
        ]
        path = songs_file(songs)
        # DB inserts first, skips second
        ctx, conn = _mock_transaction([True, False])

        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(path))

        assert result["imported"] == 1
        assert result["skipped"] == 1
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Duplicate title different author → 2 distinct UUIDs
# ---------------------------------------------------------------------------


class TestDuplicateTitleDifferentAuthor:
    def test_different_author_produces_different_uuid(self):
        song_a = {"title": "Praise God", "author": "Author One", "source": "manual"}
        song_b = {"title": "Praise God", "author": "Author Two", "source": "manual"}

        row_a = _parse_song(song_a, 0)
        row_b = _parse_song(song_b, 1)

        assert row_a["id"] != row_b["id"]

    def test_both_imported_with_different_authors(self, songs_file):
        songs = [
            {"title": "Praise God", "author": "Author One", "source": "manual"},
            {"title": "Praise God", "author": "Author Two", "source": "manual"},
        ]
        path = songs_file(songs)
        ctx, conn = _mock_transaction([True, True])

        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(path))

        assert result["imported"] == 2
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Missing optional fields → no error
# ---------------------------------------------------------------------------


class TestMissingOptionalFields:
    def test_missing_author_defaults_to_empty_string(self):
        row = _parse_song({"title": "Song Without Author"}, 0)
        assert row["author"] == ""

    def test_missing_lyrics_defaults_to_empty_string(self):
        row = _parse_song({"title": "Lyric-free"}, 0)
        assert row["lyrics"] == ""

    def test_missing_copyright_defaults_to_empty_string(self):
        row = _parse_song({"title": "No Copyright"}, 0)
        assert row["copyright"] == ""

    def test_missing_source_defaults_to_empty_string(self):
        row = _parse_song({"title": "No Source"}, 0)
        assert row["source"] == ""

    def test_missing_date_added_defaults_to_empty_string(self):
        row = _parse_song({"title": "No Date"}, 0)
        assert row["date_added"] == ""

    def test_date_added_reads_camel_case_field(self):
        row = _parse_song({"title": "T", "dateAdded": "2024-01-01"}, 0)
        assert row["date_added"] == "2024-01-01"

    def test_date_added_reads_snake_case_field(self):
        row = _parse_song({"title": "T", "date_added": "2024-02-02"}, 0)
        assert row["date_added"] == "2024-02-02"

    def test_missing_id_generates_stable_uuid(self):
        item = {"title": "Stable Title", "author": "Author", "source": "manual"}
        row1 = _parse_song(item, 0)
        row2 = _parse_song(item, 1)
        assert row1["id"] == row2["id"]
        uuid.UUID(row1["id"])  # must be a valid UUID

    def test_import_succeeds_with_only_title(self, songs_file):
        path = songs_file([{"title": "Minimal Song"}])
        ctx, conn = _mock_transaction([True])

        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(path))

        assert result["imported"] == 1
        assert result["errors"] == []

    def test_non_uuid_id_generates_stable_uuid_from_content(self):
        """Legacy string ids (e.g. 'song_001') produce a stable UUID v5 from content."""
        row1 = _parse_song({"id": "song_001", "title": "T", "author": "A", "source": "s"}, 0)
        row2 = _parse_song({"id": "song_001", "title": "T", "author": "A", "source": "s"}, 0)
        assert row1["id"] == row2["id"]
        uuid.UUID(row1["id"])


# ---------------------------------------------------------------------------
# Re-run → 0 new rows (idempotent via ON CONFLICT DO NOTHING)
# ---------------------------------------------------------------------------


class TestRerun:
    SONG = {
        "id": str(uuid.uuid4()),
        "title": "Already Imported Song",
        "author": "Someone",
        "source": "manual",
    }

    def test_second_run_counts_as_skipped(self, songs_file):
        path = songs_file([self.SONG])
        # rowcount=0 simulates ON CONFLICT DO NOTHING
        ctx, conn = _mock_transaction([False])

        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(path))

        assert result["imported"] == 0
        assert result["skipped"] == 1
        assert result["errors"] == []

    def test_mixed_new_and_existing(self, songs_file):
        """One new + one already-imported → imported=1, skipped=1."""
        songs = [
            {"id": str(uuid.uuid4()), "title": "Brand New"},
            {"id": str(uuid.uuid4()), "title": "Already There"},
        ]
        path = songs_file(songs)
        ctx, conn = _mock_transaction([True, False])

        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(path))

        assert result["imported"] == 1
        assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# Dry run → no DB writes
# ---------------------------------------------------------------------------


class TestDryRun:
    SONGS = [
        {"id": str(uuid.uuid4()), "title": "Song Alpha", "author": "A"},
        {"id": str(uuid.uuid4()), "title": "Song Beta", "author": "B"},
    ]

    def test_dry_run_returns_would_be_count(self, songs_file):
        path = songs_file(self.SONGS)

        with patch("import_songs.transaction") as mock_tx:
            result = import_songs_from_json(str(path), dry_run=True)
            mock_tx.assert_not_called()

        assert result["dry_run"] is True
        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_dry_run_does_not_open_transaction(self, songs_file):
        path = songs_file(self.SONGS)

        with patch("import_songs.transaction") as mock_tx:
            import_songs_from_json(str(path), dry_run=True)

        mock_tx.assert_not_called()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_missing_file_returns_zero_counts(self, tmp_path):
        result = import_songs_from_json(str(tmp_path / "nonexistent.json"))
        assert result == {"imported": 0, "skipped": 0, "errors": [], "dry_run": False}

    def test_empty_array_returns_zero_counts(self, songs_file):
        path = songs_file([])
        ctx, conn = _mock_transaction([])

        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(path))

        assert result["imported"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_empty_array_no_db_calls(self, songs_file):
        path = songs_file([])
        ctx, conn = _mock_transaction([])

        with patch("import_songs.transaction", return_value=ctx):
            import_songs_from_json(str(path))

        conn.execute.assert_not_called()

    def test_malformed_top_level_not_list(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"not": "a list"}', encoding="utf-8")

        result = import_songs_from_json(str(bad))
        assert result["imported"] == 0
        assert len(result["errors"]) == 1
        assert "Expected a JSON array" in result["errors"][0]

    def test_invalid_json_file(self, tmp_path):
        bad = tmp_path / "corrupt.json"
        bad.write_text("not valid json {{", encoding="utf-8")

        result = import_songs_from_json(str(bad))
        assert len(result["errors"]) == 1
        assert "Failed to read" in result["errors"][0]

    def test_malformed_item_skips_with_error(self, songs_file):
        """A non-dict entry in the array records an error but doesn't abort."""
        songs = [
            "not a dict",
            {"id": str(uuid.uuid4()), "title": "Valid Song"},
        ]
        path = songs_file(songs)
        ctx, conn = _mock_transaction([True])

        with patch("import_songs.transaction", return_value=ctx):
            result = import_songs_from_json(str(path))

        assert result["imported"] == 1
        assert len(result["errors"]) == 1
        assert "index 0" in result["errors"][0]

    def test_valid_uuid_id_preserved(self):
        """A well-formed UUID id is kept as-is."""
        song_id = str(uuid.uuid4())
        row = _parse_song({"id": song_id, "title": "T"}, 0)
        assert row["id"] == song_id

    def test_all_fields_preserved(self):
        """All fields map through correctly."""
        raw = {
            "id": str(uuid.uuid4()),
            "title": "Blessed Assurance",
            "author": "Fanny Crosby",
            "lyrics": "Blessed assurance, Jesus is mine",
            "copyright": "Public Domain",
            "source": "pco-import",
            "dateAdded": "2023-12-25",
        }
        row = _parse_song(raw, 0)
        assert row["id"] == raw["id"]
        assert row["title"] == "Blessed Assurance"
        assert row["author"] == "Fanny Crosby"
        assert row["lyrics"] == "Blessed assurance, Jesus is mine"
        assert row["copyright"] == "Public Domain"
        assert row["source"] == "pco-import"
        assert row["date_added"] == "2023-12-25"
