"""Calendar integration. Local .ics parser + optional Google Calendar."""

import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from .base import tool_fn, IntegrationCache


_cache = IntegrationCache(default_ttl=300)
CALENDAR_FILE = Path("./calendar") / "events.ics"


def _ensure_calendar_dir():
    CALENDAR_FILE.parent.mkdir(parents=True, exist_ok=True)


def _parse_ics(content: str) -> list[dict[str, Any]]:
    """Minimal ICS parser for local calendar files."""
    events = []
    current = {}
    in_event = False

    for line in content.split("\n"):
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            current = {}
        elif line == "END:VEVENT":
            in_event = False
            if current:
                events.append(current)
                current = {}
        elif in_event:
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.split(";")[0]  # Strip params like VERSION;ENCODING
                current[key] = value

    return events


def _format_events(events: list[dict], max_results: int = 10) -> str:
    if not events:
        return "[no events found]"

    lines = [f"Calendar ({len(events)} events):", ""]
    now = datetime.now(timezone.utc)

    for ev in events[:max_results]:
        summary = ev.get("SUMMARY", "Untitled")
        dtstart = ev.get("DTSTART", "")
        dtend = ev.get("DTEND", "")

        # Format date
        date_str = dtstart
        if len(dtstart) == 8:
            date_str = f"{dtstart[:4]}-{dtstart[4:6]}-{dtstart[6:8]}"
        elif len(dtstart) >= 15:
            date_str = f"{dtstart[:4]}-{dtstart[4:6]}-{dtstart[6:8]} {dtstart[9:11]}:{dtstart[11:13]}"

        location = ev.get("LOCATION", "")
        loc_str = f" @ {location}" if location else ""

        lines.append(f"  {date_str}{loc_str}")
        lines.append(f"    {summary}")
        lines.append("")

    return "\n".join(lines)


def _get_events(date: str = "") -> str:
    """Get calendar events for a date. Reads from local .ics file."""
    _ensure_calendar_dir()

    if not CALENDAR_FILE.exists():
        return (
            "[info] No calendar file found. Create a .ics file at "
            f"{CALENDAR_FILE} or configure Google Calendar integration."
        )

    cached = _cache.get(f"events:{date}")
    if cached:
        return cached

    try:
        content = CALENDAR_FILE.read_text(encoding="utf-8")
        events = _parse_ics(content)

        if date:
            date_clean = date.replace("-", "")
            events = [
                e for e in events
                if e.get("DTSTART", "").startswith(date_clean)
            ]

        result = _format_events(events)
        _cache.set(f"events:{date}", result, ttl=300)
        return result
    except Exception as e:
        return f"[error] calendar: {e}"


get_events = tool_fn(
    "get_events",
    "Get calendar events. Optionally filter by date (YYYY-MM-DD). Reads from local .ics file.",
    _get_events,
)


def get_tools(config: dict) -> list:
    return [get_events]
