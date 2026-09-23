"""Application-level calendar event models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime

Temporal = date | datetime


@dataclass(frozen=True)
class SourceEvent:
    """Calendar-provider-neutral representation of one source event."""

    source_uid: str
    summary: str
    start: Temporal
    end: Temporal | None
    description: str | None = None
    location: str | None = None
    url: str | None = None
    last_modified: datetime | None = None
    recurrence: tuple[str, ...] = ()
    related_to: str | None = None
    color: str | None = None
    assignees: tuple[str, ...] = ()

    @property
    def all_day(self) -> bool:
        return isinstance(self.start, date) and not isinstance(self.start, datetime)

    def content_hash(self) -> str:
        """Return a stable digest used later to detect source changes."""

        payload = asdict(self)
        for key in ("start", "end", "last_modified"):
            value = payload[key]
            if value is not None:
                payload[key] = value.isoformat()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ExtractionResult:
    """Validated result of a complete TimeTree export."""

    events: tuple[SourceEvent, ...]
    source_path: str
