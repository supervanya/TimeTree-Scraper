# TimeTree Sync

One-way synchronization from a TimeTree calendar to a specific Google Calendar.

The project wraps [`timetree-exporter`](https://github.com/eoleedi/TimeTree-Exporter), keeps only
active and future events, and mirrors them into a specific Google Calendar. Only Google events
tagged as managed by this project are updated or deleted.

## Requirements

- Python 3.10 or newer
- [`uv`](https://docs.astral.sh/uv/)
- A TimeTree account that supports email/password login

Install the pinned tools and dependencies with:

```bash
mise install
mise exec -- uv sync
```

## Setup

```bash
mise exec -- uv run timetree-sync --help
```

The checked-in mise configuration manages the virtual environment and cache paths, so no manual
activation is needed.

## Configuration

Put the destination calendar ID and optional TimeTree defaults in `.env`:

```dotenv
TIMETREE_CALENDAR_CODE=your_calendar_code
TIMETREE_EMAIL=you@example.com
GOOGLE_CALENDAR_ID=your-calendar-id@group.calendar.google.com
```

Keep the downloaded Google Desktop OAuth client at `.state/google-credentials.json`. Both `.env`
and `.state/` are excluded from Git.

## Authorize Google

Run this once:

```bash
mise exec -- uv run timetree-sync google-auth
```

The browser authorization stores a refreshable token at `.state/google-token.json` and prints all
writable calendars with their IDs.

## Preview and synchronize

Always preview the first synchronization:

```bash
mise exec -- uv run timetree-sync sync --dry-run
```

Apply the same plan with:

```bash
mise exec -- uv run timetree-sync sync
```

Each run fetches a fresh TimeTree snapshot before diffing Google Calendar. Creates are retry-safe,
updates are idempotent, and deletions apply only to events previously created by this tool. Use
`--keep-missing` to suppress deletions.

## Run only the extractor

The safest initial run is interactive:

```bash
mise exec -- uv run timetree-sync extract
```

You will be prompted for your TimeTree email, password, and calendar selection. The password is
not stored by this project. The resulting snapshot is written to `.state/timetree.ics`, which is
excluded from Git.

By default, the snapshot contains only events that have not ended. Use `--include-past` only when
you intentionally need historical events. TimeTree assignees are prefixed to titles (for example,
`Hazel: Volleyball Game`), and TimeTree label colors are retained for mapping to the closest color
in Google Calendar's event palette.

Assignee aliases and title emoji rules live in `src/timetree_sync/title_rules.py`. The default
mapping shortens `Jessica Danley` to `Jess`. Titles containing `volleyball` or `tournament` receive
`🏐`, while titles containing `pom` receive `🎀`; keyword matching is case-insensitive.

The same file contains `EXCLUDED_ASSIGNEES`, which controls which events reach Google Calendar.
By default, any event assigned to `Brittani` is excluded. Matching is case-insensitive, and an
event with multiple assignees is excluded if any one of them is listed.

After identifying the calendar code, future runs can avoid the calendar prompt:

```bash
mise exec -- uv run timetree-sync extract \
  --email you@example.com \
  --calendar-code your_calendar_code
```

Do not put `TIMETREE_PASSWORD` in a committed file unless you accept the local plaintext-secret
risk. Without it, TimeTree Exporter prompts on each run.

## Tests and formatting

```bash
mise exec -- uv run pytest
mise exec -- uv run ruff check .
mise exec -- uv run ruff format --check .
```

TimeTree Exporter uses unofficial TimeTree web APIs. Those endpoints may change, so synchronization
will always fail closed when extraction cannot be validated.
