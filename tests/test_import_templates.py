"""
tests/test_import_templates.py — Unit tests for migrations/import_templates.py.

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

from import_templates import (
    BUILT_IN_NAMES,
    import_templates_from_json,
    _parse_template,
)

# Reuse the same namespace as the module for consistency checks.
_TEMPLATE_NAMESPACE = uuid.UUID("b01e7e00-7e00-4000-8000-000000000000")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _template_name_uuid(name: str) -> str:
    """Reproduce the UUID5 generation used by _parse_template for slug ids."""
    return str(uuid.uuid5(_TEMPLATE_NAMESPACE, name))


@pytest.fixture
def templates_file(tmp_path):
    """Return a factory that writes a list of templates to a temp JSON file."""
    def _make(templates: list) -> Path:
        p = tmp_path / "templates.json"
        p.write_text(json.dumps(templates), encoding="utf-8")
        return p
    return _make


def _mock_transaction(inserted_rows: list[bool]):
    """Build a mock ``transaction()`` context manager.

    *inserted_rows* is a list of booleans (one per template): True means
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


def _classic_template() -> dict:
    return {
        "id": "classic",
        "name": "Classic",
        "builtIn": True,
        "pageSize": "5.5x8.5",
        "cssVars": {},
        "typeFormats": {},
        "zones": [],
    }


def _modern_template() -> dict:
    return {
        "id": "modern",
        "name": "Modern",
        "builtIn": True,
        "pageSize": "5.5x8.5",
        "cssVars": {},
        "typeFormats": {},
        "zones": [],
    }


def _custom_template(name: str = "My Custom") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "builtIn": False,
        "pageSize": "8.5x11",
        "cssVars": {},
        "typeFormats": {},
        "zones": [],
    }


# ---------------------------------------------------------------------------
# BUILT_IN_NAMES constant
# ---------------------------------------------------------------------------


class TestBuiltInNames:
    def test_classic_in_built_in_names(self):
        assert "Classic" in BUILT_IN_NAMES

    def test_modern_in_built_in_names(self):
        assert "Modern" in BUILT_IN_NAMES


# ---------------------------------------------------------------------------
# Missing / empty templates.json
# ---------------------------------------------------------------------------


class TestMissingFile:
    def test_missing_file_returns_zero_counts(self, tmp_path):
        result = import_templates_from_json(str(tmp_path / "nonexistent.json"))
        assert result["imported"] == 0
        assert result["skipped"] == 0
        assert result["built_in"] == 0
        assert result["custom"] == 0
        assert result["dry_run"] is False

    def test_missing_file_no_error_key(self, tmp_path):
        result = import_templates_from_json(str(tmp_path / "nonexistent.json"))
        # Should not have an errors key (or if present, it's empty)
        assert result.get("errors", []) == []

    def test_missing_file_no_db_calls(self, tmp_path):
        with patch("import_templates.transaction") as mock_tx:
            import_templates_from_json(str(tmp_path / "nonexistent.json"))
        mock_tx.assert_not_called()


class TestEmptyTemplatesJson:
    def test_empty_array_returns_zero_counts(self, templates_file):
        path = templates_file([])
        ctx, conn = _mock_transaction([])

        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(path))

        assert result["imported"] == 0
        assert result["skipped"] == 0
        assert result["built_in"] == 0
        assert result["custom"] == 0

    def test_empty_array_no_db_calls(self, templates_file):
        path = templates_file([])
        ctx, conn = _mock_transaction([])

        with patch("import_templates.transaction", return_value=ctx):
            import_templates_from_json(str(path))

        conn.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Built-ins only (Classic + Modern)
# ---------------------------------------------------------------------------


class TestBuiltInsOnly:
    TEMPLATES = [_classic_template(), _modern_template()]

    def test_returns_two_imported(self, templates_file):
        path = templates_file(self.TEMPLATES)
        ctx, conn = _mock_transaction([True, True])

        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(path))

        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert result["built_in"] == 2
        assert result["custom"] == 0

    def test_upsert_called_for_each_template(self, templates_file):
        path = templates_file(self.TEMPLATES)
        ctx, conn = _mock_transaction([True, True])

        with patch("import_templates.transaction", return_value=ctx):
            import_templates_from_json(str(path))

        assert conn.execute.call_count == 2

    def test_conflict_do_nothing_in_sql(self, templates_file):
        path = templates_file(self.TEMPLATES[:1])
        ctx, conn = _mock_transaction([True])

        with patch("import_templates.transaction", return_value=ctx):
            import_templates_from_json(str(path))

        upsert_sql = conn.execute.call_args_list[0].args[0]
        assert "ON CONFLICT" in upsert_sql
        assert "DO NOTHING" in upsert_sql

    def test_classic_gets_built_in_true(self):
        row = _parse_template(_classic_template(), 0)
        assert row["built_in"] is True

    def test_modern_gets_built_in_true(self):
        row = _parse_template(_modern_template(), 0)
        assert row["built_in"] is True

    def test_name_in_built_in_names_forces_built_in_true(self):
        """Even if builtIn flag is missing, name match sets built_in=True."""
        tmpl = {"id": "classic", "name": "Classic", "zones": []}
        row = _parse_template(tmpl, 0)
        assert row["built_in"] is True


# ---------------------------------------------------------------------------
# Mixed built-in + custom templates
# ---------------------------------------------------------------------------


class TestMixedBuiltInAndCustom:
    TEMPLATES = [_classic_template(), _modern_template(), _custom_template("Parish Style")]

    def test_returns_correct_counts(self, templates_file):
        path = templates_file(self.TEMPLATES)
        ctx, conn = _mock_transaction([True, True, True])

        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(path))

        assert result["imported"] == 3
        assert result["built_in"] == 2
        assert result["custom"] == 1
        assert result["skipped"] == 0

    def test_custom_template_gets_built_in_false(self):
        row = _parse_template(_custom_template("My Template"), 0)
        assert row["built_in"] is False

    def test_two_custom_one_builtin(self, templates_file):
        templates = [
            _classic_template(),
            _custom_template("Alpha"),
            _custom_template("Beta"),
        ]
        path = templates_file(templates)
        ctx, conn = _mock_transaction([True, True, True])

        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(path))

        assert result["built_in"] == 1
        assert result["custom"] == 2
        assert result["imported"] == 3


# ---------------------------------------------------------------------------
# Re-run → 0 new rows (idempotent)
# ---------------------------------------------------------------------------


class TestRerun:
    def test_second_run_counts_as_skipped(self, templates_file):
        path = templates_file([_classic_template()])
        # rowcount=0 simulates ON CONFLICT DO NOTHING
        ctx, conn = _mock_transaction([False])

        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(path))

        assert result["imported"] == 0
        assert result["skipped"] == 1
        assert result["built_in"] == 0
        assert result["custom"] == 0

    def test_mixed_new_and_existing(self, templates_file):
        """One new + one already-imported → imported=1, skipped=1."""
        templates = [_classic_template(), _modern_template()]
        path = templates_file(templates)
        ctx, conn = _mock_transaction([True, False])

        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(path))

        assert result["imported"] == 1
        assert result["skipped"] == 1

    def test_all_skipped_on_full_rerun(self, templates_file):
        templates = [_classic_template(), _modern_template(), _custom_template()]
        path = templates_file(templates)
        ctx, conn = _mock_transaction([False, False, False])

        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(path))

        assert result["imported"] == 0
        assert result["skipped"] == 3


# ---------------------------------------------------------------------------
# Dry run → no DB writes
# ---------------------------------------------------------------------------


class TestDryRun:
    TEMPLATES = [_classic_template(), _modern_template(), _custom_template()]

    def test_dry_run_returns_would_be_count(self, templates_file):
        path = templates_file(self.TEMPLATES)

        with patch("import_templates.transaction") as mock_tx:
            result = import_templates_from_json(str(path), dry_run=True)
            mock_tx.assert_not_called()

        assert result["dry_run"] is True
        assert result["imported"] == 3
        assert result["skipped"] == 0

    def test_dry_run_counts_built_in_and_custom(self, templates_file):
        path = templates_file(self.TEMPLATES)

        with patch("import_templates.transaction"):
            result = import_templates_from_json(str(path), dry_run=True)

        assert result["built_in"] == 2
        assert result["custom"] == 1

    def test_dry_run_does_not_open_transaction(self, templates_file):
        path = templates_file(self.TEMPLATES)

        with patch("import_templates.transaction") as mock_tx:
            import_templates_from_json(str(path), dry_run=True)

        mock_tx.assert_not_called()

    def test_dry_run_missing_file_returns_zeros(self, tmp_path):
        with patch("import_templates.transaction") as mock_tx:
            result = import_templates_from_json(
                str(tmp_path / "missing.json"), dry_run=True
            )
        assert result["imported"] == 0
        assert result["built_in"] == 0
        assert result["custom"] == 0
        mock_tx.assert_not_called()


# ---------------------------------------------------------------------------
# UUID generation
# ---------------------------------------------------------------------------


class TestUuidGeneration:
    def test_slug_id_produces_stable_uuid(self):
        """Non-UUID string ids (e.g. 'classic') → stable UUID5 from the slug."""
        row1 = _parse_template({"id": "classic", "name": "Classic", "zones": []}, 0)
        row2 = _parse_template({"id": "classic", "name": "Classic", "zones": []}, 1)
        assert row1["id"] == row2["id"]
        uuid.UUID(row1["id"])  # must be a valid UUID

    def test_valid_uuid_id_preserved(self):
        """A well-formed UUID id is kept as-is."""
        template_id = str(uuid.uuid4())
        row = _parse_template(
            {"id": template_id, "name": "Test", "builtIn": False, "zones": []}, 0
        )
        assert row["id"] == template_id

    def test_no_id_generates_stable_uuid_from_name(self):
        """Templates without an id get a UUID5 derived from their name."""
        item = {"name": "Unique Name Template", "zones": []}
        row1 = _parse_template(item, 0)
        row2 = _parse_template(item, 1)
        assert row1["id"] == row2["id"]
        uuid.UUID(row1["id"])

    def test_classic_id_is_stable(self):
        """'classic' slug always maps to the same UUID5."""
        expected = _template_name_uuid("classic")
        row = _parse_template({"id": "classic", "name": "Classic", "zones": []}, 0)
        assert row["id"] == expected

    def test_modern_id_is_stable(self):
        """'modern' slug always maps to the same UUID5."""
        expected = _template_name_uuid("modern")
        row = _parse_template({"id": "modern", "name": "Modern", "zones": []}, 0)
        assert row["id"] == expected


# ---------------------------------------------------------------------------
# Data stored as JSONB
# ---------------------------------------------------------------------------


class TestDataField:
    def test_full_template_object_stored_in_data(self):
        """_parse_template stores the full dict in the data field."""
        tmpl = _classic_template()
        row = _parse_template(tmpl, 0)
        assert "data" in row
        assert isinstance(row["data"], dict)
        assert row["data"]["pageSize"] == "5.5x8.5"

    def test_zones_preserved_in_data(self):
        zones = [{"id": "z1", "binding": "cover", "order": 1}]
        tmpl = {"id": str(uuid.uuid4()), "name": "Zone Test", "zones": zones}
        row = _parse_template(tmpl, 0)
        assert row["data"]["zones"] == zones


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_malformed_top_level_not_list(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"not": "a list"}', encoding="utf-8")

        result = import_templates_from_json(str(bad))
        assert result["imported"] == 0
        assert len(result.get("errors", [])) == 1
        assert "Expected a JSON array" in result["errors"][0]

    def test_invalid_json_file(self, tmp_path):
        bad = tmp_path / "corrupt.json"
        bad.write_text("not valid json {{", encoding="utf-8")

        result = import_templates_from_json(str(bad))
        assert len(result.get("errors", [])) == 1
        assert "Failed to read" in result["errors"][0]

    def test_non_dict_item_skips_with_error(self, templates_file):
        """A non-dict entry in the array records an error but doesn't abort."""
        templates = [
            "not a dict",
            _classic_template(),
        ]
        path = templates_file(templates)
        ctx, conn = _mock_transaction([True])

        with patch("import_templates.transaction", return_value=ctx):
            result = import_templates_from_json(str(path))

        assert result["imported"] == 1
        assert len(result.get("errors", [])) == 1
        assert "index 0" in result["errors"][0]

    def test_name_in_built_in_names_overrides_false_flag(self):
        """If name is 'Classic', built_in is True even if builtIn=False in the dict."""
        tmpl = {"id": "classic", "name": "Classic", "builtIn": False, "zones": []}
        row = _parse_template(tmpl, 0)
        assert row["built_in"] is True
