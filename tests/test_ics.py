from datetime import date, datetime
from pathlib import Path

import pytest

from timetree_sync.sources.ics import InvalidExportError, parse_ics

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
