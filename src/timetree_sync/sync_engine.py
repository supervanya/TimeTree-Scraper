"""Pure diff planning and mutation orchestration for calendar synchronization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from timetree_sync.destinations.google_calendar import (
    MANAGED_BY,
    create_event,
    delete_event,
    deterministic_google_id,
    event_body,
    update_event,
)
from timetree_sync.models import SourceEvent
from timetree_sync.title_rules import should_include_event

Operation = Literal["create", "update", "delete", "unchanged"]
MANAGED_FIELDS = ("summary", "description", "location", "start", "end", "recurrence", "colorId")


@dataclass(frozen=True)
class SyncAction:
    operation: Operation
    source_uid: str
    summary: str
    body: dict | None = None
    google_event_id: str | None = None
    start: str | None = None


@dataclass(frozen=True)
class SyncPlan:
    actions: tuple[SyncAction, ...]

    def count(self, operation: Operation) -> int:
        return sum(action.operation == operation for action in self.actions)


def _projection(body: dict) -> dict:
    return {field: body[field] for field in MANAGED_FIELDS if field in body}


def _body_hash(body: dict) -> str:
    encoded = json.dumps(_projection(body), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _start_label(event: dict) -> str | None:
    start = event.get("start") or {}
    return start.get("dateTime") or start.get("date")


def _private_properties(event: dict) -> dict:
    return (event.get("extendedProperties") or {}).get("private") or {}


def _managed_body(source: SourceEvent, palette: dict[str, str], cutoff: datetime) -> dict:
    body = event_body(source, palette, cutoff=cutoff)
    body["extendedProperties"] = {
        "private": {
            "managedBy": MANAGED_BY,
            "sourceUid": source.source_uid,
            "sourceHash": _body_hash(body),
        }
    }
    return body


def build_sync_plan(
    source_events: tuple[SourceEvent, ...],
    google_events: list[dict],
    palette: dict[str, str],
    *,
    cutoff: datetime,
    delete_missing: bool = True,
) -> SyncPlan:
    """Build an idempotent plan without performing external writes."""

    existing_by_uid: dict[str, list[dict]] = {}
    for google_event in google_events:
        source_uid = _private_properties(google_event).get("sourceUid")
        if source_uid:
            existing_by_uid.setdefault(source_uid, []).append(google_event)

    actions: list[SyncAction] = []
    for source in source_events:
        if not should_include_event(source.assignees):
            continue
        body = _managed_body(source, palette, cutoff)
        matches = existing_by_uid.pop(source.source_uid, [])
        existing = matches.pop(0) if matches else None
        if existing is None:
            create_body = dict(body)
            create_body["id"] = deterministic_google_id(source.source_uid)
            actions.append(
                SyncAction(
                    "create",
                    source.source_uid,
                    source.summary,
                    body=create_body,
                    start=_start_label(body),
                )
            )
        elif _private_properties(existing).get("sourceHash") != body["extendedProperties"][
            "private"
        ]["sourceHash"] or _projection(existing) != _projection(body):
            actions.append(
                SyncAction(
                    "update",
                    source.source_uid,
                    source.summary,
                    body=body,
                    google_event_id=existing["id"],
                    start=_start_label(body),
                )
            )
        else:
            actions.append(
                SyncAction(
                    "unchanged",
                    source.source_uid,
                    source.summary,
                    google_event_id=existing["id"],
                    start=_start_label(body),
                )
            )

        for duplicate in matches:
            actions.append(
                SyncAction(
                    "delete",
                    source.source_uid,
                    duplicate.get("summary") or source.summary,
                    google_event_id=duplicate["id"],
                    start=_start_label(duplicate),
                )
            )

    for source_uid, missing_events in existing_by_uid.items():
        for existing in missing_events:
            actions.append(
                SyncAction(
                    "delete" if delete_missing else "unchanged",
                    source_uid,
                    existing.get("summary") or "(untitled)",
                    google_event_id=existing["id"],
                    start=_start_label(existing),
                )
            )
    return SyncPlan(tuple(actions))


def apply_sync_plan(service: Any, calendar_id: str, plan: SyncPlan) -> None:
    """Apply a previously reviewed plan to Google Calendar."""

    for action in plan.actions:
        if action.operation == "create":
            create_event(service, calendar_id, action.body or {})
        elif action.operation == "update":
            update_event(
                service,
                calendar_id,
                action.google_event_id or "",
                action.body or {},
            )
        elif action.operation == "delete":
            delete_event(service, calendar_id, action.google_event_id or "")
