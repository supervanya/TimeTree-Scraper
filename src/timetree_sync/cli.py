"""Command-line interface for TimeTree Sync."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from timetree_sync.sources.timetree_exporter import extract_calendar


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="timetree-sync")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser(
        "extract",
        help="Export and validate a TimeTree calendar without changing it",
    )
    extract.add_argument(
        "--calendar-code",
        default=os.environ.get("TIMETREE_CALENDAR_CODE"),
        help="TimeTree calendar code; prompts for a calendar when omitted",
    )
    extract.add_argument(
        "--email",
        default=os.environ.get("TIMETREE_EMAIL"),
        help="TimeTree account email; prompts when omitted",
    )
    extract.add_argument(
        "--output",
        type=Path,
        default=Path(".state/timetree.ics"),
        help="Where to save the diagnostic ICS snapshot",
    )
    extract.add_argument(
        "--include-comments",
        action="store_true",
        help="Fetch event comments (slower and more likely to be rate-limited)",
    )
    return parser


def _run_extract(args: argparse.Namespace) -> int:
    result = extract_calendar(
        args.output,
        calendar_code=args.calendar_code,
        email=args.email,
        include_comments=args.include_comments,
    )
    recurring = sum(bool(event.recurrence) for event in result.events)
    all_day = sum(event.all_day for event in result.events)
    print(f"Validated {len(result.events)} TimeTree events")
    print(f"  all-day:  {all_day}")
    print(f"  recurring: {recurring}")
    print(f"  snapshot: {result.source_path}")
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "extract":
        return _run_extract(args)
    raise AssertionError(f"Unknown command: {args.command}")
