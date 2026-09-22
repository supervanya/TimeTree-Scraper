"""Parse TimeTree Exporter's iCalendar output."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from icalendar import Calendar

from timetree_sync.models import ExtractionResult, SourceEvent


class InvalidExportError(ValueError):
    """Raised when an export cannot be trusted as a complete calendar snapshot."""


def _decoded(component: Any, name: str) -> Any | None:
    value = component.get(name)
    if value is None:
        return None
    return component.decoded(name)


def _text(component: Any, name: str) -> str | None:
    value = _decoded(component, name)
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _temporal(component: Any, name: str) -> date | datetime | None:
    value = _decoded(component, name)
    if value is None:
        return None
    if not isinstance(value, (date, datetime)):
        raise InvalidExportError(f"VEVENT {name} is not a date or datetime: {value!r}")
    return value


def _property_lines(component: Any, names: tuple[str, ...]) -> tuple[str, ...]:
    lines: list[str] = []
    for name in names:
        values = component.get(name)
        if values is None:
            continue
        if not isinstance(values, list):
            values = [values]
        for value in values:
            rendered = value.to_ical()
            if isinstance(rendered, bytes):
                rendered = rendered.decode("utf-8")
            lines.append(f"{name}:{rendered}")
    return tuple(lines)


def parse_ics(path: Path) -> ExtractionResult:
    """Parse and validate the complete ICS snapshot at *path*."""

    if not path.is_file():
        raise InvalidExportError(f"TimeTree export was not created: {path}")

    try:
        calendar = Calendar.from_ical(path.read_bytes())
    except Exception as exc:
        raise InvalidExportError(f"TimeTree export is not valid iCalendar: {path}") from exc

    events: list[SourceEvent] = []
    seen_uids: set[str] = set()
    for component in calendar.walk("VEVENT"):
        uid = _text(component, "UID")
        summary = _text(component, "SUMMARY")
        start = _temporal(component, "DTSTART")
        end = _temporal(component, "DTEND")

        if not uid:
            raise InvalidExportError("A VEVENT is missing its TimeTree UID")
        if uid in seen_uids:
            raise InvalidExportError(f"Duplicate VEVENT UID in export: {uid}")
        if start is None:
            raise InvalidExportError(f"VEVENT {uid} is missing DTSTART")

        last_modified = _temporal(component, "LAST-MODIFIED")
        if last_modified is not None and not isinstance(last_modified, datetime):
            raise InvalidExportError(f"VEVENT {uid} has an invalid LAST-MODIFIED value")

        seen_uids.add(uid)
        events.append(
            SourceEvent(
                source_uid=uid,
                summary=summary or "(untitled)",
                start=start,
                end=end,
                description=_text(component, "DESCRIPTION"),
                location=_text(component, "LOCATION"),
                url=_text(component, "URL"),
                last_modified=last_modified,
                recurrence=_property_lines(component, ("RRULE", "RDATE", "EXDATE")),
                related_to=_text(component, "RELATED-TO"),
            )
        )

    return ExtractionResult(events=tuple(events), source_path=str(path.resolve()))
