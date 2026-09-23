"""Command-line interface for TimeTree Sync."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from timetree_sync.destinations.google_auth import (
    DEFAULT_CREDENTIALS_PATH,
    DEFAULT_TOKEN_PATH,
    GoogleAuthError,
    authorize,
    calendar_service,
    load_credentials,
)
from timetree_sync.destinations.google_calendar import (
    GoogleCalendarError,
    event_color_palette,
    list_managed_events,
    validate_target_calendar,
    writable_calendars,
)
from timetree_sync.sources.ics import parse_ics
from timetree_sync.sources.timetree_exporter import extract_calendar
from timetree_sync.sync_engine import apply_sync_plan, build_sync_plan

ENV_KEYS = {
    "GOOGLE_CALENDAR_ID",
    "TIMETREE_CALENDAR_CODE",
    "TIMETREE_EMAIL",
    "TIMETREE_PASSWORD",
}


def _load_local_env(path: Path = Path(".env")) -> None:
    """Load only this application's simple KEY=VALUE settings."""

    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.removeprefix("export ").strip()
        if key in ENV_KEYS:
            os.environ.setdefault(key, value.strip().strip("\"'"))


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
    extract.add_argument(
        "--include-past",
        action="store_true",
        help="Include events that have already ended (off by default)",
    )

    google_auth = subparsers.add_parser(
        "google-auth",
        help="Authorize Google Calendar and list writable calendars",
    )
    google_auth.add_argument(
        "--credentials",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help="Google Desktop OAuth client JSON",
    )
    google_auth.add_argument(
        "--token",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help="Where to save the Google OAuth token",
    )

    sync = subparsers.add_parser(
        "sync",
        help="Extract TimeTree and synchronize managed Google events",
    )
    sync.add_argument(
        "--google-calendar-id",
        default=os.environ.get("GOOGLE_CALENDAR_ID"),
        help="Destination Google Calendar ID (or GOOGLE_CALENDAR_ID)",
    )
    sync.add_argument(
        "--credentials",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help="Google Desktop OAuth client JSON",
    )
    sync.add_argument(
        "--token",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help="Saved Google OAuth token",
    )
    sync.add_argument(
        "--calendar-code",
        default=os.environ.get("TIMETREE_CALENDAR_CODE"),
        help="TimeTree calendar code; prompts for a calendar when omitted",
    )
    sync.add_argument(
        "--email",
        default=os.environ.get("TIMETREE_EMAIL"),
        help="TimeTree account email; prompts when omitted",
    )
    sync.add_argument(
        "--snapshot",
        type=Path,
        default=Path(".state/timetree.ics"),
        help="Where to save the fresh TimeTree snapshot",
    )
    sync.add_argument(
        "--source",
        type=Path,
        help="Use an existing filtered ICS file instead of contacting TimeTree",
    )
    sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the diff without changing Google Calendar",
    )
    sync.add_argument(
        "--keep-missing",
        action="store_true",
        help="Keep managed Google events that are missing from TimeTree",
    )
    return parser


def _run_extract(args: argparse.Namespace) -> int:
    result = extract_calendar(
        args.output,
        calendar_code=args.calendar_code,
        email=args.email,
        include_comments=args.include_comments,
        include_past=args.include_past,
    )
    recurring = sum(bool(event.recurrence) for event in result.events)
    all_day = sum(event.all_day for event in result.events)
    print(f"Validated {len(result.events)} TimeTree events")
    print(f"  all-day:  {all_day}")
    print(f"  recurring: {recurring}")
    print(f"  snapshot: {result.source_path}")
    return 0


def _run_google_auth(args: argparse.Namespace) -> int:
    credentials = authorize(args.credentials, args.token)
    service = calendar_service(credentials)
    configured_id = os.environ.get("GOOGLE_CALENDAR_ID")
    print("Writable Google calendars:")
    for calendar in writable_calendars(service):
        marker = " * configured" if calendar.get("id") == configured_id else ""
        print(f"  {calendar.get('summary', '(untitled)')}: {calendar['id']}{marker}")
    print(f"Token saved to {args.token.expanduser().resolve()}")
    return 0


def _print_plan(plan) -> None:
    print(
        "Google diff: "
        f"{plan.count('create')} create, "
        f"{plan.count('update')} update, "
        f"{plan.count('delete')} delete, "
        f"{plan.count('unchanged')} unchanged"
    )
    for action in plan.actions:
        if action.operation != "unchanged":
            print(f"  {action.operation:>6}  {action.summary}")


def _run_sync(args: argparse.Namespace) -> int:
    if not args.google_calendar_id:
        raise GoogleCalendarError("Set GOOGLE_CALENDAR_ID in .env or pass --google-calendar-id")

    cutoff = datetime.now().astimezone()
    if args.source:
        extraction = parse_ics(args.source)
    else:
        extraction = extract_calendar(
            args.snapshot,
            calendar_code=args.calendar_code,
            email=args.email,
            now=cutoff,
        )

    credentials = load_credentials(args.credentials, args.token)
    service = calendar_service(credentials)
    target = validate_target_calendar(service, args.google_calendar_id)
    palette = event_color_palette(service)
    existing = list_managed_events(service, args.google_calendar_id)
    if not extraction.events and existing and not args.keep_missing:
        raise GoogleCalendarError(
            "TimeTree returned zero events; refusing to delete managed Google events"
        )

    plan = build_sync_plan(
        extraction.events,
        existing,
        palette,
        cutoff=cutoff,
        delete_missing=not args.keep_missing,
    )
    print(f"Target: {target.get('summary', '(untitled)')} ({args.google_calendar_id})")
    _print_plan(plan)
    if args.dry_run:
        print("Dry run only; Google Calendar was not changed.")
        return 0

    apply_sync_plan(service, args.google_calendar_id, plan)
    print("Google Calendar synchronization complete.")
    return 0


def main() -> int:
    _load_local_env()
    args = _build_parser().parse_args()
    try:
        if args.command == "extract":
            return _run_extract(args)
        if args.command == "google-auth":
            return _run_google_auth(args)
        if args.command == "sync":
            return _run_sync(args)
        raise AssertionError(f"Unknown command: {args.command}")
    except (GoogleAuthError, GoogleCalendarError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
