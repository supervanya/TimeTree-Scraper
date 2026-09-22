from datetime import datetime, timezone

from timetree_sync.models import SourceEvent


def test_content_hash_is_stable_and_changes_with_content() -> None:
    event = SourceEvent(
        source_uid="event-1",
        summary="Dinner",
        start=datetime(2026, 9, 22, 18, tzinfo=timezone.utc),
        end=datetime(2026, 9, 22, 19, tzinfo=timezone.utc),
    )
    same = SourceEvent(
        source_uid="event-1",
        summary="Dinner",
        start=datetime(2026, 9, 22, 18, tzinfo=timezone.utc),
        end=datetime(2026, 9, 22, 19, tzinfo=timezone.utc),
    )
    changed = SourceEvent(
        source_uid="event-1",
        summary="Late dinner",
        start=datetime(2026, 9, 22, 18, tzinfo=timezone.utc),
        end=datetime(2026, 9, 22, 19, tzinfo=timezone.utc),
    )

    assert event.content_hash() == same.content_hash()
    assert event.content_hash() != changed.content_hash()
