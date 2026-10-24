"""Customize assignee names and event titles before synchronization."""

# Add or change TimeTree display-name aliases here.
NAME_ALIASES = {
    "Jessica Danley": "Jess",
}

# Events assigned to any of these people are omitted from Google Calendar.
EXCLUDED_ASSIGNEES = {
    # "Britani"
}


def should_include_event(assignees: tuple[str, ...]) -> bool:
    """Return whether an event passes the assignee exclusion filter."""

    excluded = {name.casefold() for name in EXCLUDED_ASSIGNEES}
    return not any(name.casefold() in excluded for name in assignees)


def format_event_title(title: str, assignees: tuple[str, ...] = ()) -> str:
    """Prefix mapped assignees and append activity emoji to an event title."""

    mapped_names = tuple(NAME_ALIASES.get(name, name) for name in assignees)
    formatted = f"{', '.join(mapped_names)}: {title}" if mapped_names else title
    searchable = title.casefold()

    if ("volleyball" in searchable or "tournament" in searchable) and "🏐" not in formatted:
        formatted = f"{formatted} 🏐"
    if "pom" in searchable and "🎀" not in formatted:
        formatted = f"{formatted} 🎀"

    return formatted
