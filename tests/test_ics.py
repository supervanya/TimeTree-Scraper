from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from timetree_sync.sources.ics import InvalidExportError, parse_ics, prepare_ics

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_exported_events() -> None:
    result = parse_ics(FIXTURES / "sample.ics")

    assert len(result.events) == 2
    timed, all_day = result.events
    assert timed.source_uid == "timed-event-uuid"
    assert timed.summary == "Dinner"
    assert isinstance(timed.start, datetime)
    assert timed.start.tzinfo is not None
    assert timed.recurrence == ("RRULE:FREQ=WEEKLY;COUNT=3",)
    assert timed.color == "#33B679"
    assert timed.assignees == ("Hazel",)
    assert len(timed.content_hash()) == 64

    assert all_day.source_uid == "all-day-event-uuid"
    assert all_day.start == date(2026, 10, 1)
    assert all_day.end == date(2026, 10, 4)
    assert all_day.all_day is True


def test_missing_export_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(InvalidExportError, match="was not created"):
        parse_ics(tmp_path / "missing.ics")


def test_duplicate_uid_fails_closed(tmp_path: Path) -> None:
    source = (FIXTURES / "sample.ics").read_text()
    duplicate = source.replace("UID:all-day-event-uuid", "UID:timed-event-uuid")
    path = tmp_path / "duplicate.ics"
    path.write_text(duplicate)

    with pytest.raises(InvalidExportError, match="Duplicate VEVENT UID"):
        parse_ics(path)


def test_prepare_ics_keeps_only_future_events_and_prefixes_assignee(tmp_path: Path) -> None:
    source = tmp_path / "source.ics"
    output = tmp_path / "future.ics"
    source.write_text(
        (FIXTURES / "sample.ics").read_text().replace("RRULE:FREQ=WEEKLY;COUNT=3\n", "")
    )

    prepare_ics(
        source,
        output,
        assignees_by_uid={"all-day-event-uuid": ("Hazel",)},
        cutoff=datetime(2026, 9, 30, tzinfo=UTC),
    )
    events = parse_ics(output).events

    assert [event.source_uid for event in events] == ["all-day-event-uuid"]
    assert events[0].summary == "Hazel: Vacation"
    assert events[0].assignees == ("Hazel",)


def test_prepare_ics_keeps_a_recurring_series_with_a_future_occurrence(tmp_path: Path) -> None:
    output = tmp_path / "future.ics"

    prepare_ics(
        FIXTURES / "sample.ics",
        output,
        cutoff=datetime(2026, 9, 23, tzinfo=UTC),
    )

    assert "timed-event-uuid" in {event.source_uid for event in parse_ics(output).events}


def test_prepare_ics_excludes_events_by_assignee(tmp_path: Path) -> None:
    output = tmp_path / "filtered.ics"

    prepare_ics(
        FIXTURES / "sample.ics",
        output,
        assignees_by_uid={"all-day-event-uuid": ("Brittani",)},
        cutoff=datetime(2026, 9, 30, tzinfo=UTC),
    )

    event_uids = {event.source_uid for event in parse_ics(output).events}
    assert "all-day-event-uuid" not in event_uids
