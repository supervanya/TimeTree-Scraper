from datetime import UTC, datetime

from timetree_sync.models import SourceEvent
from timetree_sync.sync_engine import build_sync_plan

CUTOFF = datetime(2026, 9, 22, tzinfo=UTC)


def _source(
    uid: str = "event-1",
    summary: str = "Hazel: Volleyball",
    assignees: tuple[str, ...] = (),
) -> SourceEvent:
    return SourceEvent(
        source_uid=uid,
        summary=summary,
        start=datetime(2026, 10, 1, 18, tzinfo=UTC),
        end=datetime(2026, 10, 1, 19, tzinfo=UTC),
        assignees=assignees,
    )


def test_new_source_event_is_created() -> None:
    plan = build_sync_plan((_source(),), [], {}, cutoff=CUTOFF)

    assert plan.count("create") == 1
    action = plan.actions[0]
    assert action.body["extendedProperties"]["private"]["sourceUid"] == "event-1"
    assert action.body["id"].startswith("tt")


def test_matching_managed_event_is_unchanged() -> None:
    initial = build_sync_plan((_source(),), [], {}, cutoff=CUTOFF).actions[0].body
    existing = dict(initial)
    existing["id"] = "google-id"

    plan = build_sync_plan((_source(),), [existing], {}, cutoff=CUTOFF)

    assert plan.count("unchanged") == 1


def test_source_change_updates_managed_event() -> None:
    initial = build_sync_plan((_source(),), [], {}, cutoff=CUTOFF).actions[0].body
    existing = dict(initial)
    existing["id"] = "google-id"

    plan = build_sync_plan(
        (_source(summary="Hazel: Rescheduled Volleyball"),),
        [existing],
        {},
        cutoff=CUTOFF,
    )

    assert plan.count("update") == 1


def test_missing_source_deletes_only_managed_event() -> None:
    existing = {
        "id": "google-id",
        "summary": "Old event",
        "extendedProperties": {
            "private": {"managedBy": "timetree-sync", "sourceUid": "old-source"}
        },
    }

    plan = build_sync_plan((), [existing], {}, cutoff=CUTOFF)

    assert plan.count("delete") == 1


def test_excluded_assignee_is_not_created() -> None:
    plan = build_sync_plan(
        (_source(assignees=("Brittani",)),),
        [],
        {},
        cutoff=CUTOFF,
    )

    assert plan.actions == ()
