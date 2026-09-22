"""Adapter around the external TimeTree Exporter command."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from timetree_sync.models import ExtractionResult
from timetree_sync.sources.ics import parse_ics


class ExporterExecutionError(RuntimeError):
    """Raised when TimeTree Exporter exits unsuccessfully."""


def extract_calendar(
    output_path: Path,
    *,
    calendar_code: str | None = None,
    email: str | None = None,
    include_comments: bool = False,
) -> ExtractionResult:
    """Run TimeTree Exporter and return its validated events."""

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.stem}-",
        suffix=".ics",
        dir=output_path.parent,
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)

    command = [
        sys.executable,
        "-m",
        "timetree_exporter",
        "--output",
        str(temporary_path),
    ]
    if calendar_code:
        command.extend(("--calendar_code", calendar_code))
    if email:
        command.extend(("--email", email))
    if include_comments:
        command.append("--include-comments")

    try:
        completed = subprocess.run(command, check=False, env=os.environ.copy())
        if completed.returncode != 0:
            raise ExporterExecutionError(
                f"TimeTree Exporter exited with status {completed.returncode}"
            )

        parse_ics(temporary_path)
        temporary_path.replace(output_path)
        return parse_ics(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
