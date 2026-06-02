"""
revisions.py — Revision summary generation for bulletin project saves.

Compares a previous project state with a new state and produces a concise
human-readable summary of what changed.  Used by
``storage.PostgresStorageBackend.save_project_transactional()`` to populate
the ``summary`` column of the ``project_revisions`` table.

Public API:
    generate_summary(prev_state, new_state) -> str
"""

from __future__ import annotations

_MAX_LEN = 200


def generate_summary(prev_state: "dict | None", new_state: dict) -> str:
    """Return a human-readable summary of what changed between two project states.

    Args:
        prev_state: The project state before the save, or ``None`` for the
                    first save (returns ``"Initial save"``).
        new_state:  The project state being saved.

    Returns:
        A non-empty string, capped at 200 characters.  Falls back to
        ``"Updated project content"`` when no specific changes are detected
        or if an exception occurs during comparison.
    """
    if prev_state is None:
        return "Initial save"

    try:
        phrases = _collect_phrases(prev_state, new_state)
    except Exception:  # noqa: BLE001
        return "Updated project content"

    if not phrases:
        return "Updated project content"

    summary = "; ".join(phrases)
    if len(summary) > _MAX_LEN:
        summary = summary[:_MAX_LEN - 1] + "…"
    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_phrases(prev: dict, new: dict) -> list[str]:
    """Build a list of change phrases by comparing the two states."""
    phrases: list[str] = []

    _check_items(prev, new, phrases)
    _check_service_date(prev, new, phrases)
    _check_announcements(prev, new, phrases)
    _check_cal_events(prev, new, phrases)
    _check_serving_schedule(prev, new, phrases)
    _check_images(prev, new, phrases)
    _check_formatting(prev, new, phrases)
    _check_give_url(prev, new, phrases)

    return phrases


def _check_items(prev: dict, new: dict, phrases: list[str]) -> None:
    """Compare order-of-worship items and append change phrases."""
    prev_items = prev.get("items") or []
    new_items = new.get("items") or []

    if not isinstance(prev_items, list):
        prev_items = []
    if not isinstance(new_items, list):
        new_items = []

    prev_count = len(prev_items)
    new_count = len(new_items)

    added = max(0, new_count - prev_count)
    removed = max(0, prev_count - new_count)

    # Count changed items among the overlapping range (by title comparison).
    compare_len = min(prev_count, new_count)
    changed = 0
    for i in range(compare_len):
        p_item = prev_items[i] if isinstance(prev_items[i], dict) else {}
        n_item = new_items[i] if isinstance(new_items[i], dict) else {}
        # Compare title and type as a lightweight content signal.
        if p_item.get("title") != n_item.get("title") or p_item.get("type") != n_item.get("type"):
            changed += 1

    parts: list[str] = []
    if added:
        parts.append(f"added {added} {'item' if added == 1 else 'items'}")
    if removed:
        parts.append(f"removed {removed} {'item' if removed == 1 else 'items'}")
    if changed:
        parts.append(f"changed {changed} order-of-worship {'item' if changed == 1 else 'items'}")

    if parts:
        phrases.append("; ".join(parts))


def _check_service_date(prev: dict, new: dict, phrases: list[str]) -> None:
    """Append a phrase when the service date or title changed."""
    prev_date = prev.get("serviceDate") or prev.get("serviceTitle") or ""
    new_date = new.get("serviceDate") or new.get("serviceTitle") or ""
    if prev_date != new_date:
        phrases.append("updated service date")


def _check_announcements(prev: dict, new: dict, phrases: list[str]) -> None:
    """Append a phrase when announcements changed."""
    prev_ann = prev.get("annData") or []
    new_ann = new.get("annData") or []
    if not isinstance(prev_ann, list):
        prev_ann = []
    if not isinstance(new_ann, list):
        new_ann = []

    if len(prev_ann) != len(new_ann):
        phrases.append("updated announcements")
        return

    # Same count — check content (title comparison).
    for p, n in zip(prev_ann, new_ann):
        p_item = p if isinstance(p, dict) else {}
        n_item = n if isinstance(n, dict) else {}
        if p_item.get("title") != n_item.get("title") or p_item.get("body") != n_item.get("body"):
            phrases.append("updated announcements")
            return


def _check_cal_events(prev: dict, new: dict, phrases: list[str]) -> None:
    """Append a phrase when the calendar event count changed."""
    prev_ev = prev.get("calEvents") or []
    new_ev = new.get("calEvents") or []
    if not isinstance(prev_ev, list):
        prev_ev = []
    if not isinstance(new_ev, list):
        new_ev = []
    if len(prev_ev) != len(new_ev):
        phrases.append("updated calendar events")


def _check_serving_schedule(prev: dict, new: dict, phrases: list[str]) -> None:
    """Append a phrase when the serving schedule changed."""
    prev_sched = prev.get("servingSchedule")
    new_sched = new.get("servingSchedule")
    if prev_sched != new_sched:
        phrases.append("updated serving schedule")


def _check_images(prev: dict, new: dict, phrases: list[str]) -> None:
    """Append a phrase when cover or logo images changed."""
    cover_changed = prev.get("coverImage") != new.get("coverImage")
    logo_changed = prev.get("logoImage") != new.get("logoImage")
    if cover_changed or logo_changed:
        phrases.append("updated images")


def _check_formatting(prev: dict, new: dict, phrases: list[str]) -> None:
    """Append a phrase when type formats or template/page settings changed."""
    fmt_changed = prev.get("typeFormats") != new.get("typeFormats")
    template_changed = prev.get("docTemplate") != new.get("docTemplate")
    page_changed = prev.get("pageSettings") != new.get("pageSettings")
    if fmt_changed or template_changed or page_changed:
        phrases.append("updated formatting")


def _check_give_url(prev: dict, new: dict, phrases: list[str]) -> None:
    """Append a phrase when the giving URL changed."""
    if prev.get("giveOnlineUrl") != new.get("giveOnlineUrl"):
        phrases.append("updated giving URL")
