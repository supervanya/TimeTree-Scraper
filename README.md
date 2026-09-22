# TimeTree Sync

One-way synchronization from a TimeTree calendar to a specific Google Calendar.

The project currently implements milestone one: a read-only TimeTree extraction and validation
command. It wraps [`timetree-exporter`](https://github.com/eoleedi/TimeTree-Exporter), saves an
iCalendar snapshot, and converts the snapshot into provider-neutral events. It does not modify
TimeTree or Google Calendar yet.

## Requirements

- Python 3.10 or newer
- [`uv`](https://docs.astral.sh/uv/)
- A TimeTree account that supports email/password login

On macOS, install `uv` with:

```bash
brew install uv
```

## Setup

```bash
uv sync
uv run timetree-sync --help
```

`uv sync` creates the `venv` virtual environment and installs the exact version of TimeTree
Exporter declared in `pyproject.toml`. This project intentionally uses `venv` instead of `.venv`
because some macOS/Python combinations ignore editable-install path files that inherit macOS's
hidden filesystem flag.

## Run the read-only extractor

The safest initial run is interactive:

```bash
uv run timetree-sync extract
```

You will be prompted for your TimeTree email, password, and calendar selection. The password is
not stored by this project. The resulting snapshot is written to `.state/timetree.ics`, which is
excluded from Git.

After identifying the calendar code, future runs can avoid the calendar prompt:

```bash
uv run timetree-sync extract \
  --email you@example.com \
  --calendar-code your_calendar_code
```

Do not put `TIMETREE_PASSWORD` in a committed file. A later milestone will add macOS Keychain
storage for unattended runs.

## Tests and formatting

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Planned milestones

1. Validate extraction against the real calendar, including recurrence exceptions and deletions.
2. Add Google OAuth and target-calendar validation.
3. Add a dry-run diff that reports creates, updates, and deletions.
4. Add idempotent Google writes, private source metadata, and SQLite state.
5. Add macOS Keychain credentials and optional scheduling.

TimeTree Exporter uses unofficial TimeTree web APIs. Those endpoints may change, so synchronization
will always fail closed when extraction cannot be validated.
