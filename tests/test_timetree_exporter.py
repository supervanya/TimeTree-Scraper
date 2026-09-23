import json
from datetime import UTC, datetime
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from timetree_sync.sources.timetree_exporter import (
    ExporterExecutionError,
    extract_calendar,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_uses_temporary_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "snapshot.ics"

    def fake_run(command, **_kwargs):
        temporary_output = Path(command[command.index("--output") + 1])
        raw_output = Path(command[command.index("--raw-output-dir") + 1])
        temporary_output.write_bytes((FIXTURES / "sample.ics").read_bytes())
        (raw_output / "calendar_1").mkdir()
        (raw_output / "calendars.json").write_text(
            json.dumps(
                {
                    "calendars": [
                        {
                            "alias_code": "calendar-code",
                            "calendar_users": [{"user_id": 7, "name": "Hazel"}],
                        }
                    ]
                }
            )
        )
        (raw_output / "calendar_1" / "events.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "uuid": "all-day-event-uuid",
                            "relationships": {
                                "attendees": {"data": [{"id": "1,7", "type": "user"}]}
                            },
                        }
                    ]
                }
            )
        )
        assert temporary_output != output
        return CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    result = extract_calendar(
        output,
        calendar_code="calendar-code",
        email="user@example.com",
        now=datetime(2026, 9, 30, tzinfo=UTC),
    )

    assert len(result.events) == 2
    vacation = next(event for event in result.events if event.source_uid == "all-day-event-uuid")
    assert vacation.summary == "Hazel: Vacation"
    assert vacation.assignees == ("Hazel",)
    assert output.is_file()


def test_failed_extract_preserves_existing_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "snapshot.ics"
    output.write_text("existing snapshot")

    monkeypatch.setattr(
        "subprocess.run",
        lambda command, **_kwargs: CompletedProcess(command, 1),
    )

    with pytest.raises(ExporterExecutionError, match="status 1"):
        extract_calendar(output)

    assert output.read_text() == "existing snapshot"
