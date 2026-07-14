"""Persistent reminder system backed by SQLite."""

import sqlite3
import re
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser

from .base import tool_fn


DB_PATH = Path("./memory") / "reminders.db"


def _ensure_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            due_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_done INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def _parse_time(time_str: str) -> str | None:
    """Parse natural language time into ISO format."""
    now = datetime.now(timezone.utc)
    time_lower = time_str.lower().strip()

    # "in X minutes/hours/days"
    m = re.match(r"in (\d+)\s*(min|minute|minutes|hour|hours|day|days|hr|hrs)", time_lower)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit in ("min", "minute", "minutes"):
            delta = timedelta(minutes=amount)
        elif unit in ("hour", "hours", "hr", "hrs"):
            delta = timedelta(hours=amount)
        elif unit in ("day", "days"):
            delta = timedelta(days=amount)
        else:
            return None
        return (now + delta).isoformat()

    # "today at 5pm", "tomorrow at 9am"
    try:
        dt = dateparser.parse(time_str, fuzzy=True)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
    except Exception:
        pass

    return None


def _set_reminder(text: str, time: str) -> str:
    """Set a reminder."""
    due = _parse_time(time)
    if due is None:
        return (
            f"[error] couldn't understand time '{time}'. "
            f"Try: 'in 30 minutes', 'tomorrow at 9am', "
            f"or an ISO date like '2026-07-14T15:00:00'"
        )

    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO reminders (text, due_at, created_at) VALUES (?, ?, ?)",
        (text, due, now),
    )
    conn.commit()
    conn.close()

    return f"[ok] Reminder set: '{text}' at {due}"


def _list_reminders() -> str:
    """List all pending reminders."""
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT id, text, due_at, created_at FROM reminders WHERE is_done = 0 ORDER BY due_at ASC"
    ).fetchall()
    conn.close()

    if not rows:
        return "[no pending reminders]"

    now = datetime.now(timezone.utc)
    overdue = 0
    lines = ["Pending reminders:", ""]
    for row in rows:
        rid, text, due_str, created = row
        try:
            due = datetime.fromisoformat(due_str)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            status = " 🔴 OVERDUE" if due < now else ""
            if due < now:
                overdue += 1
            time_left = due.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            time_left = due_str
            status = ""
        lines.append(f"  [{rid}] {time_left}{status}")
        lines.append(f"       {text}")
        lines.append("")

    summary = f"{len(rows)} pending, {overdue} overdue"
    return f"{summary}\n\n" + "\n".join(lines)


def _clear_reminder(reminder_id: int) -> str:
    """Mark a reminder as done."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(
        "UPDATE reminders SET is_done = 1 WHERE id = ? AND is_done = 0",
        (reminder_id,),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()

    if affected:
        return f"[ok] Reminder {reminder_id} cleared"
    return f"[error] No active reminder with id {reminder_id}"


def _check_due_reminders() -> str:
    """Check for due reminders and return them."""
    conn = sqlite3.connect(str(DB_PATH))
    now = datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT id, text, due_at FROM reminders WHERE is_done = 0 AND due_at <= ? ORDER BY due_at ASC",
        (now,),
    ).fetchall()
    conn.close()

    if not rows:
        return ""

    lines = ["**Due reminders:**"]
    for row in rows:
        lines.append(f"- [{row[0]}] {row[1]} (due: {row[2]})")

    return "\n".join(lines)


set_reminder = tool_fn(
    "set_reminder",
    "Set a reminder with text and time. Time formats: 'in 30 minutes', 'tomorrow at 9am', 'in 2 hours', or ISO date.",
    _set_reminder,
)

list_reminders = tool_fn(
    "list_reminders",
    "List all pending reminders sorted by due time.",
    _list_reminders,
)

clear_reminder = tool_fn(
    "clear_reminder",
    "Mark a reminder as done by its ID number.",
    _clear_reminder,
)

check_due_reminders = tool_fn(
    "check_due_reminders",
    "Check for any due reminders and return them. Call this automatically before each response.",
    _check_due_reminders,
)


def get_tools(config: dict) -> list:
    _ensure_db()
    return [set_reminder, list_reminders, clear_reminder, check_due_reminders]
