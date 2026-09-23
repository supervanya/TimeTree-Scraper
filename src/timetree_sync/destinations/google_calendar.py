"""Google Calendar API conversion and operations."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from dateutil.rrule import rrulestr
from googleapiclient.errors import HttpError

from timetree_sync.destinations.google_colors import closest_google_color_id
from timetree_sync.models import SourceEvent

MANAGED_BY = "timetree-sync"


class GoogleCalendarError(RuntimeError):
    """Raised for invalid target-calendar configuration or API state."""


def list_calendars(service: Any) -> list[dict]:
    """Return every calendar visible to the authenticated Google account."""

    calendars: list[dict] = []
    page_token = None
    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        calendars.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return calendars


def writable_calendars(service: Any) -> list[dict]:
    """Return calendars on which this account may modify events."""

    return [
        calendar
        for calendar in list_calendars(service)
        if calendar.get("accessRole") in {"owner", "writer"}
    ]


def validate_target_calendar(service: Any, calendar_id: str) -> dict:
    """Return a writable target calendar or raise a clear configuration error."""

    match = next((item for item in list_calendars(service) if item.get("id") == calendar_id), None)
    if match is None:
        raise GoogleCalendarError(f"Google calendar is not visible to this account: {calendar_id}")
    if match.get("accessRole") not in {"owner", "writer"}:
        raise GoogleCalendarError(f"Google calendar is not writable: {calendar_id}")
    return match


def event_color_palette(service: Any) -> dict[str, str]:
    """Return Google event color IDs mapped to background hex colors."""

    response = service.colors().get().execute()
    return {
        str(color_id): definition["background"]
        for color_id, definition in response.get("event", {}).items()
        if definition.get("background")
    }


def list_managed_events(service: Any, calendar_id: str) -> list[dict]:
    """Return only events created by this synchronization tool."""

    events: list[dict] = []
    page_token = None
    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                privateExtendedProperty=f"managedBy={MANAGED_BY}",
                maxResults=2500,
                pageToken=page_token,
                showDeleted=False,
                singleEvents=False,
            )
            .execute()
        )
        events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return events


def deterministic_google_id(source_uid: str) -> str:
    """Return a retry-safe Google event ID derived from a TimeTree UID."""

    digest = hashlib.sha256(source_uid.encode()).digest()
    return "tt" + base64.b32hexencode(digest).decode().lower().rstrip("=")


def _as_datetime(value: date | datetime, timezone=None) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone or UTC)
        return value
    return datetime.combine(value, time.min, tzinfo=timezone or UTC)


def _replace_count(rule: str, remaining: int) -> str:
    prefix, value = rule.split(":", 1)
    parts = value.split(";")
    replaced = [
        f"COUNT={remaining}" if part.upper().startswith("COUNT=") else part for part in parts
    ]
    return f"{prefix}:{';'.join(replaced)}"


def _truncate_recurrence(
    event: SourceEvent, cutoff: datetime
) -> tuple[date | datetime, date | datetime | None, tuple[str, ...]]:
    """Move a recurring series to its first active/future occurrence."""

    if not event.recurrence:
        return event.start, event.end, event.recurrence

    start_datetime = _as_datetime(event.start)
    end_datetime = _as_datetime(event.end or event.start, start_datetime.tzinfo)
    duration = max(end_datetime - start_datetime, timedelta(0))
    local_cutoff = cutoff.astimezone(start_datetime.tzinfo or UTC)
    if end_datetime > local_cutoff:
        return event.start, event.end, event.recurrence

    next_occurrences: list[tuple[datetime, int | None, str]] = []
    for line in event.recurrence:
        if not line.upper().startswith("RRULE:"):
            continue
        value = line.split(":", 1)[1]
        try:
            rule = rrulestr(value, dtstart=start_datetime)
            occurrence = rule.after(local_cutoff - duration, inc=True)
        except (TypeError, ValueError, OverflowError):
            continue
        if occurrence is None:
            continue
        remaining = None
        if "COUNT=" in value.upper():
            remaining = sum(1 for candidate in rule if candidate >= occurrence)
        next_occurrences.append((occurrence, remaining, line))

    if not next_occurrences:
        return event.start, event.end, event.recurrence

    next_start, remaining, selected_rule = min(next_occurrences, key=lambda item: item[0])
    next_end = next_start + duration
    recurrence = tuple(
        _replace_count(line, remaining) if remaining is not None and line == selected_rule else line
        for line in event.recurrence
    )
    if event.all_day:
        return next_start.date(), next_end.date(), recurrence
    return next_start, next_end, recurrence


def _time_value(value: date | datetime, *, is_end: bool = False) -> dict[str, str]:
    if isinstance(value, datetime):
        result = {"dateTime": value.isoformat()}
        timezone = getattr(value.tzinfo, "key", None)
        if timezone:
            result["timeZone"] = timezone
        return result
    return {"date": value.isoformat()}


def event_body(
    event: SourceEvent,
    palette: dict[str, str],
    *,
    cutoff: datetime | None = None,
) -> dict:
    """Convert one normalized TimeTree event into a Google event request body."""

    cutoff = cutoff or datetime.now().astimezone()
    start, end, recurrence = _truncate_recurrence(event, cutoff)
    if end is None:
        end = start + (timedelta(days=1) if event.all_day else timedelta(hours=1))

    body: dict[str, Any] = {
        "summary": event.summary,
        "start": _time_value(start),
        "end": _time_value(end, is_end=True),
    }
    description = event.description or ""
    if event.url and event.url not in description:
        description = f"{description}\n\nTimeTree: {event.url}".strip()
    if description:
        body["description"] = description
    if event.location:
        body["location"] = event.location
    if recurrence:
        body["recurrence"] = list(recurrence)
    if event.color and palette:
        body["colorId"] = closest_google_color_id(event.color, palette)
    return body


def create_event(service: Any, calendar_id: str, body: dict) -> dict:
    """Create an event, recovering safely from a retry after a successful insert."""

    try:
        return (
            service.events().insert(calendarId=calendar_id, body=body, sendUpdates="none").execute()
        )
    except HttpError as exc:
        if getattr(exc.resp, "status", None) != 409 or not body.get("id"):
            raise
        return service.events().get(calendarId=calendar_id, eventId=body["id"]).execute()


def update_event(service: Any, calendar_id: str, event_id: str, body: dict) -> dict:
    """Replace one managed Google event with normalized source data."""

    return (
        service.events()
        .update(
            calendarId=calendar_id,
            eventId=event_id,
            body=body,
            sendUpdates="none",
        )
        .execute()
    )


def delete_event(service: Any, calendar_id: str, event_id: str) -> None:
    """Delete one managed Google event without sending invitations."""

    service.events().delete(
        calendarId=calendar_id,
        eventId=event_id,
        sendUpdates="none",
    ).execute()
