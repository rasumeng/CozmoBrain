"""Background scheduler for periodic tasks (reminders, etc.)."""

import time
import threading
from datetime import datetime, timezone


class Scheduler:
    """Runs periodic callbacks in a background thread."""

    def __init__(self):
        self._tasks: list[tuple[float, callable]] = []
        self._running = False
        self._thread: threading.Thread | None = None

    def add_task(self, interval_sec: float, callback: callable):
        """Add a recurring task.

        Args:
            interval_sec: Seconds between runs.
            callback: Function to call (no args).
        """
        self._tasks.append((interval_sec, callback))

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self):
        while self._running:
            for interval, callback in self._tasks:
                try:
                    callback()
                except Exception:
                    pass
            time.sleep(10)
