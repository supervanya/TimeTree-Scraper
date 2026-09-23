"""Adapter around the external TimeTree Exporter command."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from timetree_sync.models import ExtractionResult
from timetree_sync.sources.ics import parse_ics, prepare_ics


class ExporterExecutionError(RuntimeError):
    """Raised when TimeTree Exporter exits unsuccessfully."""


def _id_variants(value: object) -> set[str]:
    if value is None:
        return set()
    rendered = str(value)
    return {rendered, rendered.rsplit(",", 1)[-1]}


def _calendar_user_names(calendar: dict) -> dict[str, str]:
    names: dict[str, str] = {}
    for user in calendar.get("calendar_users") or []:
        name = user.get("name")
        if not name:
            continue
        for key in ("id", "user_id", "uuid"):
            for variant in _id_variants(user.get(key)):
                names[variant] = name
    return names


def _attendee_references(event: dict) -> list[object]:
    candidates = event.get("attendees") or event.get("attendee_ids") or []
    relationships = event.get("relationships") or {}
    relationship = relationships.get("attendees") or {}
    if relationship.get("data") is not None:
        candidates = relationship["data"]
    if not isinstance(candidates, list):
        candidates = [candidates]
    return candidates


def _assignee_names(event: dict, user_names: dict[str, str]) -> tuple[str, ...]:
    names: list[str] = []
    for attendee in _attendee_references(event):
        if isinstance(attendee, dict):
            direct_name = attendee.get("name") or (attendee.get("attributes") or {}).get("name")
            attendee_id = attendee.get("id") or attendee.get("user_id")
        else:
            direct_name = None
            attendee_id = attendee
        name = direct_name or next(
            (user_names[key] for key in _id_variants(attendee_id) if key in user_names),
            None,
        )
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _load_assignees(raw_output_dir: Path, calendar_code: str | None) -> dict[str, tuple[str, ...]]:
    payloads = []
    for path in raw_output_dir.rglob("*.json"):
        try:
            payloads.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue

    calendars = [calendar for payload in payloads for calendar in payload.get("calendars", [])]
    if calendar_code:
        calendars = [c for c in calendars if c.get("alias_code") == calendar_code] or calendars
    user_names: dict[str, str] = {}
    for calendar in calendars:
        user_names.update(_calendar_user_names(calendar))

    assignees: dict[str, tuple[str, ...]] = {}
    for payload in payloads:
        for event in payload.get("events", []):
            uid = event.get("uuid")
            if uid:
                names = _assignee_names(event, user_names)
                if names:
                    assignees[str(uid)] = names
    return assignees


def extract_calendar(
    output_path: Path,
    *,
    calendar_code: str | None = None,
    email: str | None = None,
    include_comments: bool = False,
    include_past: bool = False,
    now: datetime | None = None,
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

    with tempfile.TemporaryDirectory(prefix="timetree-sync-") as raw_directory:
        raw_output_dir = Path(raw_directory)
        command = [
            sys.executable,
            "-m",
            "timetree_exporter",
            "--output",
            str(temporary_path),
            "--developer-mode",
            "--raw-output-dir",
            str(raw_output_dir),
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
            prepare_ics(
                temporary_path,
                output_path,
                assignees_by_uid=_load_assignees(raw_output_dir, calendar_code),
                cutoff=now,
                include_past=include_past,
            )
            return parse_ics(output_path)
        finally:
            temporary_path.unlink(missing_ok=True)
