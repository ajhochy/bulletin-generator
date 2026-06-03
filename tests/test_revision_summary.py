"""
tests/test_revision_summary.py — Unit tests for revisions.generate_summary().

Covers:
  revisions.generate_summary():
    - No previous state → "Initial save"
    - Added items → summary contains "added N"
    - Removed items → summary contains "removed N"
    - Changed item titles → summary contains "changed N"
    - Changed service date → summary contains "service date"
    - Multiple changes → multiple phrases joined by "; "
    - Identical states → "Updated project content"
    - Exception during comparison → "Updated project content" (safe fallback)
    - Summary never exceeds 200 characters
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── Project root on sys.path ───────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(**overrides) -> dict:
    """Return a minimal but realistic project state dict."""
    state = {
        "id": "proj-1",
        "name": "Sunday Service",
        "items": [],
        "annData": [],
        "calEvents": [],
        "servingSchedule": {},
        "serviceDate": "2026-05-17",
        "coverImage": None,
        "logoImage": None,
        "typeFormats": {},
        "docTemplate": None,
        "pageSettings": {},
        "giveOnlineUrl": "",
    }
    state.update(overrides)
    return state


def _item(type_: str = "song", title: str = "A Song") -> dict:
    return {"type": type_, "title": title, "text": ""}


# =============================================================================
# No previous state
# =============================================================================

class TestNoPreviousState:
    def test_none_prev_returns_initial_save(self):
        from revisions import generate_summary

        result = generate_summary(None, _base_state())
        assert result == "Initial save"

    def test_empty_dict_prev_is_not_none(self):
        """An empty dict is a valid prev_state; it is NOT None."""
        from revisions import generate_summary

        result = generate_summary({}, _base_state())
        # Not "Initial save" — some change will be detected or fallback used
        assert result != "Initial save"


# =============================================================================
# Item changes
# =============================================================================

class TestItemChanges:
    def test_added_two_items(self):
        from revisions import generate_summary

        prev = _base_state(items=[])
        new = _base_state(items=[_item(), _item(title="Another Song")])
        result = generate_summary(prev, new)
        assert "added 2" in result

    def test_added_one_item_uses_singular(self):
        from revisions import generate_summary

        prev = _base_state(items=[])
        new = _base_state(items=[_item()])
        result = generate_summary(prev, new)
        assert "added 1 item" in result
        assert "items" not in result.split("added 1 ")[1].split(";")[0]

    def test_removed_one_item(self):
        from revisions import generate_summary

        prev = _base_state(items=[_item(), _item(title="Song B")])
        new = _base_state(items=[_item()])
        result = generate_summary(prev, new)
        assert "removed 1" in result

    def test_removed_three_items(self):
        from revisions import generate_summary

        prev = _base_state(items=[_item(title=f"Song {i}") for i in range(4)])
        new = _base_state(items=[_item(title="Song 0")])
        result = generate_summary(prev, new)
        assert "removed 3" in result

    def test_changed_title_detected(self):
        from revisions import generate_summary

        prev = _base_state(items=[_item(title="Old Title")])
        new = _base_state(items=[_item(title="New Title")])
        result = generate_summary(prev, new)
        assert "changed 1" in result

    def test_changed_two_items(self):
        from revisions import generate_summary

        prev = _base_state(items=[_item(title="A"), _item(title="B")])
        new = _base_state(items=[_item(title="X"), _item(title="Y")])
        result = generate_summary(prev, new)
        assert "changed 2" in result

    def test_no_item_phrase_when_items_identical(self):
        from revisions import generate_summary

        items = [_item(title="Song A"), _item(title="Song B")]
        prev = _base_state(items=items)
        new = _base_state(items=items)
        # Only check items — isolate by making everything else identical
        result = generate_summary(prev, new)
        assert "item" not in result or "added" not in result


# =============================================================================
# Service date / title
# =============================================================================

class TestServiceDate:
    def test_service_date_changed(self):
        from revisions import generate_summary

        prev = _base_state(serviceDate="2026-05-10")
        new = _base_state(serviceDate="2026-05-17")
        result = generate_summary(prev, new)
        assert "service date" in result

    def test_service_title_changed(self):
        from revisions import generate_summary

        # Use serviceTitle as the sole date signal (no serviceDate in either state).
        prev = _base_state(serviceDate="", serviceTitle="Pentecost Sunday")
        new = _base_state(serviceDate="", serviceTitle="Trinity Sunday")
        result = generate_summary(prev, new)
        assert "service date" in result

    def test_service_date_unchanged_no_phrase(self):
        from revisions import generate_summary

        prev = _base_state(serviceDate="2026-05-17")
        new = _base_state(serviceDate="2026-05-17")
        result = generate_summary(prev, new)
        assert "service date" not in result


# =============================================================================
# Announcements
# =============================================================================

class TestAnnouncements:
    def test_announcement_count_changed(self):
        from revisions import generate_summary

        prev = _base_state(annData=[{"title": "A", "body": ""}])
        new = _base_state(annData=[])
        result = generate_summary(prev, new)
        assert "announcements" in result

    def test_announcement_title_changed(self):
        from revisions import generate_summary

        prev = _base_state(annData=[{"title": "Old", "body": ""}])
        new = _base_state(annData=[{"title": "New", "body": ""}])
        result = generate_summary(prev, new)
        assert "announcements" in result

    def test_announcements_unchanged_no_phrase(self):
        from revisions import generate_summary

        ann = [{"title": "Same", "body": "Same body"}]
        prev = _base_state(annData=ann)
        new = _base_state(annData=ann)
        result = generate_summary(prev, new)
        assert "announcements" not in result


# =============================================================================
# Calendar events
# =============================================================================

class TestCalendarEvents:
    def test_cal_event_count_changed(self):
        from revisions import generate_summary

        prev = _base_state(calEvents=[{"id": "1"}])
        new = _base_state(calEvents=[{"id": "1"}, {"id": "2"}])
        result = generate_summary(prev, new)
        assert "calendar events" in result

    def test_cal_events_same_count_no_phrase(self):
        from revisions import generate_summary

        events = [{"id": "1"}]
        prev = _base_state(calEvents=events)
        new = _base_state(calEvents=events)
        result = generate_summary(prev, new)
        assert "calendar" not in result


# =============================================================================
# Serving schedule
# =============================================================================

class TestServingSchedule:
    def test_serving_schedule_changed(self):
        from revisions import generate_summary

        prev = _base_state(servingSchedule={"Pianist": "Alice"})
        new = _base_state(servingSchedule={"Pianist": "Bob"})
        result = generate_summary(prev, new)
        assert "serving schedule" in result

    def test_serving_schedule_unchanged_no_phrase(self):
        from revisions import generate_summary

        sched = {"Pianist": "Alice"}
        prev = _base_state(servingSchedule=sched)
        new = _base_state(servingSchedule=sched)
        result = generate_summary(prev, new)
        assert "serving schedule" not in result


# =============================================================================
# Images
# =============================================================================

class TestImages:
    def test_cover_image_changed(self):
        from revisions import generate_summary

        prev = _base_state(coverImage=None)
        new = _base_state(coverImage="data:image/png;base64,abc")
        result = generate_summary(prev, new)
        assert "images" in result

    def test_logo_image_changed(self):
        from revisions import generate_summary

        prev = _base_state(logoImage=None)
        new = _base_state(logoImage="data:image/png;base64,xyz")
        result = generate_summary(prev, new)
        assert "images" in result

    def test_images_unchanged_no_phrase(self):
        from revisions import generate_summary

        prev = _base_state(coverImage=None, logoImage=None)
        new = _base_state(coverImage=None, logoImage=None)
        result = generate_summary(prev, new)
        assert "images" not in result


# =============================================================================
# Formatting
# =============================================================================

class TestFormatting:
    def test_type_formats_changed(self):
        from revisions import generate_summary

        prev = _base_state(typeFormats={})
        new = _base_state(typeFormats={"song": {"titleBold": True}})
        result = generate_summary(prev, new)
        assert "formatting" in result

    def test_doc_template_changed(self):
        from revisions import generate_summary

        prev = _base_state(docTemplate=None)
        new = _base_state(docTemplate="letter")
        result = generate_summary(prev, new)
        assert "formatting" in result

    def test_page_settings_changed(self):
        from revisions import generate_summary

        prev = _base_state(pageSettings={})
        new = _base_state(pageSettings={"pageWidth": "8.5in"})
        result = generate_summary(prev, new)
        assert "formatting" in result

    def test_formatting_unchanged_no_phrase(self):
        from revisions import generate_summary

        prev = _base_state(typeFormats={}, docTemplate=None, pageSettings={})
        new = _base_state(typeFormats={}, docTemplate=None, pageSettings={})
        result = generate_summary(prev, new)
        assert "formatting" not in result


# =============================================================================
# Give URL
# =============================================================================

class TestGiveUrl:
    def test_give_url_changed(self):
        from revisions import generate_summary

        prev = _base_state(giveOnlineUrl="")
        new = _base_state(giveOnlineUrl="https://example.com/give")
        result = generate_summary(prev, new)
        assert "giving URL" in result

    def test_give_url_unchanged_no_phrase(self):
        from revisions import generate_summary

        prev = _base_state(giveOnlineUrl="https://example.com/give")
        new = _base_state(giveOnlineUrl="https://example.com/give")
        result = generate_summary(prev, new)
        assert "giving URL" not in result


# =============================================================================
# Multiple changes
# =============================================================================

class TestMultipleChanges:
    def test_two_changes_joined_by_semicolon(self):
        from revisions import generate_summary

        prev = _base_state(serviceDate="2026-05-10", items=[])
        new = _base_state(serviceDate="2026-05-17", items=[_item()])
        result = generate_summary(prev, new)
        assert ";" in result
        assert "service date" in result
        assert "added 1" in result

    def test_many_changes_produces_full_summary(self):
        from revisions import generate_summary

        prev = _base_state(
            serviceDate="2026-05-10",
            items=[],
            annData=[],
            giveOnlineUrl="",
        )
        new = _base_state(
            serviceDate="2026-05-17",
            items=[_item()],
            annData=[{"title": "Event", "body": ""}],
            giveOnlineUrl="https://example.com/give",
        )
        result = generate_summary(prev, new)
        assert "service date" in result
        assert "added" in result
        assert "announcements" in result
        assert "giving URL" in result


# =============================================================================
# Identical states → fallback
# =============================================================================

class TestIdenticalStates:
    def test_identical_returns_fallback(self):
        from revisions import generate_summary

        state = _base_state(
            items=[_item()],
            annData=[{"title": "A", "body": "body"}],
        )
        result = generate_summary(state, state)
        assert result == "Updated project content"

    def test_completely_empty_identical_states(self):
        from revisions import generate_summary

        result = generate_summary({}, {})
        assert result == "Updated project content"


# =============================================================================
# Exception safety
# =============================================================================

class TestExceptionSafety:
    def test_exception_returns_fallback(self):
        """If an unexpected error occurs, must return the safe fallback string."""
        from revisions import generate_summary

        # Pass a non-dict that will trigger an exception internally.
        result = generate_summary("not-a-dict", _base_state())  # type: ignore[arg-type]
        assert result == "Updated project content"

    def test_items_not_list_does_not_crash(self):
        from revisions import generate_summary

        prev = _base_state(items="corrupt")
        new = _base_state(items=[_item()])
        # Should not raise; either detects a change or returns fallback
        result = generate_summary(prev, new)
        assert isinstance(result, str)
        assert result  # non-empty


# =============================================================================
# Length cap
# =============================================================================

class TestLengthCap:
    def test_summary_never_exceeds_200_chars(self):
        from revisions import generate_summary

        # Craft states that trigger many long phrases simultaneously.
        prev = _base_state(
            serviceDate="2026-01-01",
            items=[],
            annData=[],
            calEvents=[],
            servingSchedule={},
            coverImage=None,
            logoImage=None,
            typeFormats={},
            docTemplate=None,
            pageSettings={},
            giveOnlineUrl="",
        )
        new = _base_state(
            serviceDate="2026-12-31",
            items=[_item(title="X" * 50) for _ in range(10)],
            annData=[{"title": "Y" * 50, "body": ""}],
            calEvents=[{"id": str(i)} for i in range(5)],
            servingSchedule={"A": "B"},
            coverImage="data:image/png;base64," + "z" * 200,
            logoImage="data:image/png;base64," + "z" * 200,
            typeFormats={"song": {"titleBold": True}},
            docTemplate="legal",
            pageSettings={"pageWidth": "8.5in"},
            giveOnlineUrl="https://example.com/give",
        )
        result = generate_summary(prev, new)
        assert len(result) <= 200

    def test_short_summary_not_truncated(self):
        from revisions import generate_summary

        prev = _base_state(serviceDate="2026-05-10")
        new = _base_state(serviceDate="2026-05-17")
        result = generate_summary(prev, new)
        assert len(result) < 200
        assert "…" not in result


# =============================================================================
# Never empty
# =============================================================================

class TestNeverEmpty:
    def test_initial_save_not_empty(self):
        from revisions import generate_summary
        assert generate_summary(None, {})

    def test_identical_states_not_empty(self):
        from revisions import generate_summary
        state = _base_state()
        assert generate_summary(state, state)

    def test_exception_not_empty(self):
        from revisions import generate_summary
        result = generate_summary("bad", {})  # type: ignore[arg-type]
        assert result
