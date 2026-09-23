from datetime import UTC, date, datetime

from timetree_sync.destinations.google_calendar import (
    deterministic_google_id,
    event_body,
)
from timetree_sync.models import SourceEvent


def test_event_body_preserves_color_and_truncates_past_recurrence() -> None:
    event = SourceEvent(
        source_uid="series-1",
        summary="Hazel: Volleyball",
        start=datetime(2026, 1, 1, 10, tzinfo=UTC),
        end=datetime(2026, 1, 1, 11, tzinfo=UTC),
        recurrence=("RRULE:FREQ=DAILY;COUNT=5",),
        color="#33B679",
    )

    body = event_body(
        event,
        {"1": "#7986CB", "2": "#33B679"},
        cutoff=datetime(2026, 1, 3, 12, tzinfo=UTC),
    )

    assert body["summary"] == "Hazel: Volleyball"
    assert body["start"]["dateTime"] == "2026-01-04T10:00:00+00:00"
    assert body["end"]["dateTime"] == "2026-01-04T11:00:00+00:00"
    assert body["recurrence"] == ["RRULE:FREQ=DAILY;COUNT=2"]
    assert body["colorId"] == "2"


def test_all_day_event_uses_exclusive_end_date() -> None:
    event = SourceEvent(
        source_uid="all-day",
        summary="Vacation",
        start=date(2026, 10, 1),
        end=date(2026, 10, 4),
    )

    body = event_body(event, {}, cutoff=datetime(2026, 9, 1, tzinfo=UTC))

    assert body["start"] == {"date": "2026-10-01"}
    assert body["end"] == {"date": "2026-10-04"}


def test_deterministic_google_id_is_retry_safe() -> None:
    first = deterministic_google_id("source-event")

    assert first == deterministic_google_id("source-event")
    assert first != deterministic_google_id("other-event")
    assert set(first) <= set("0123456789abcdefghijklmnopqrstuv")
