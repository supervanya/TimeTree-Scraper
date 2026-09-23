"""Map arbitrary TimeTree label colors to Google Calendar's event palette."""

from __future__ import annotations

from collections.abc import Mapping


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().lstrip("#")[:6]
    if len(value) != 6:
        raise ValueError(f"Invalid color: {hex_color}")
    try:
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError as exc:
        raise ValueError(f"Invalid color: {hex_color}") from exc


def closest_google_color_id(source_color: str, palette: Mapping[str, str]) -> str:
    """Return the ID of the visually closest color in a Google event palette."""

    source = _rgb(source_color)

    def distance(candidate: str) -> int:
        rgb = _rgb(candidate)
        return sum((left - right) ** 2 for left, right in zip(source, rgb, strict=True))

    if not palette:
        raise ValueError("Google event color palette is empty")
    return min(palette, key=lambda color_id: distance(palette[color_id]))
