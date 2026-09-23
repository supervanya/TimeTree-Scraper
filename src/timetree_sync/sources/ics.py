"""Parse TimeTree Exporter's iCalendar output."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from dateutil.rrule import rrulestr
from icalendar import Calendar

from timetree_sync.models import ExtractionResult, SourceEvent
from timetree_sync.title_rules import format_event_title, should_include_event


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


def _text_values(component: Any, name: str) -> tuple[str, ...]:
    values = component.get(name)
    if values is None:
        return ()
    if not isinstance(values, list):
        values = [values]
    result = []
    for value in values:
        rendered = value.to_ical() if hasattr(value, "to_ical") else value
        if isinstance(rendered, bytes):
            rendered = rendered.decode("utf-8")
        result.append(str(rendered))
    return tuple(result)


def _as_datetime(value: date | datetime, timezone=None) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone or UTC)
        return value
    return datetime.combine(value, time.min, tzinfo=timezone or UTC)


def _ends_after(component: Any, cutoff: datetime) -> bool:
    start = _temporal(component, "DTSTART")
    end = _temporal(component, "DTEND") or start
    if start is None or end is None:
        return False

    if isinstance(start, date) and not isinstance(start, datetime):
        boundary = end if isinstance(end, date) else end.date()
        return boundary > cutoff.date()

    end_datetime = _as_datetime(end, start.tzinfo)
    return end_datetime.astimezone(UTC) > cutoff.astimezone(UTC)


def _recurs_after(component: Any, cutoff: datetime) -> bool:
    rules = component.get("RRULE")
    if rules is None:
        return False
    if not isinstance(rules, list):
        rules = [rules]

    start = _temporal(component, "DTSTART")
    end = _temporal(component, "DTEND") or start
    if start is None or end is None:
        return False

    start_datetime = _as_datetime(start)
    end_datetime = _as_datetime(end, start_datetime.tzinfo)
    duration = max(end_datetime - start_datetime, timedelta(0))
    local_cutoff = cutoff.astimezone(start_datetime.tzinfo or UTC)

    for rule in rules:
        rendered = rule.to_ical()
        if isinstance(rendered, bytes):
            rendered = rendered.decode("utf-8")
        try:
            recurrence = rrulestr(rendered, dtstart=start_datetime)
            occurrence = recurrence.after(local_cutoff - duration, inc=True)
        except (TypeError, ValueError, OverflowError):
            # Preserve an unrecognized recurring event rather than silently losing it.
            return True
        if occurrence is not None and occurrence + duration > local_cutoff:
            return True
    return False


def has_future_occurrence(component: Any, cutoff: datetime) -> bool:
    """Return whether a VEVENT has an occurrence that has not ended."""

    return _ends_after(component, cutoff) or _recurs_after(component, cutoff)


def prepare_ics(
    source_path: Path,
    output_path: Path,
    *,
    assignees_by_uid: dict[str, tuple[str, ...]] | None = None,
    cutoff: datetime | None = None,
    include_past: bool = False,
) -> None:
    """Filter an export and add TimeTree assignee names without losing ICS metadata."""

    try:
        calendar = Calendar.from_ical(source_path.read_bytes())
    except Exception as exc:
        raise InvalidExportError(f"TimeTree export is not valid iCalendar: {source_path}") from exc

    assignees_by_uid = assignees_by_uid or {}
    cutoff = cutoff or datetime.now().astimezone()
    components = []
    for component in calendar.subcomponents:
        if component.name != "VEVENT":
            components.append(component)
            continue
        if not include_past and not has_future_occurrence(component, cutoff):
            continue

        uid = _text(component, "UID")
        names = assignees_by_uid.get(uid or "", ())
        if not should_include_event(names):
            continue
        title = _text(component, "SUMMARY") or "(untitled)"
        component["SUMMARY"] = format_event_title(title, names)
        if names:
            for name in names:
                component.add("X-TIMETREE-ASSIGNEE", name)
        components.append(component)

    calendar.subcomponents = components
    output_path.write_bytes(calendar.to_ical())


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
                color=_text(component, "COLOR"),
                assignees=_text_values(component, "X-TIMETREE-ASSIGNEE"),
            )
        )

    return ExtractionResult(events=tuple(events), source_path=str(path.resolve()))
