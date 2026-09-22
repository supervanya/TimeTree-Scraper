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
        temporary_output.write_bytes((FIXTURES / "sample.ics").read_bytes())
        assert temporary_output != output
        return CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    result = extract_calendar(output, calendar_code="calendar-code", email="user@example.com")

    assert len(result.events) == 2
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
