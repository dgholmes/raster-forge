"""Per-job structured log file.

One file per processing job, written as it happens so the log is readable
while the job is still running (PRD §19). UTF-8 throughout — dataset names
are routinely Korean.

    2026-09-01T11:42:05Z INFO  inspect     Detected EPSG:32652, 48567x25143
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["JobLog"]


class JobLog:
    """Append-only job log. Thread-safe; the worker and API may both write."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # -- writing ---------------------------------------------------------

    def _write(self, level: str, step: str, message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{stamp} {level:<5} {step:<11} {message}\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8", errors="replace") as fh:
                fh.write(line)

    def info(self, step: str, message: str) -> None:
        self._write("INFO", step, message)

    def warn(self, step: str, message: str) -> None:
        self._write("WARN", step, message)

    def error(self, step: str, message: str) -> None:
        self._write("ERROR", step, message)

    def command(self, step: str, argv: list[str]) -> None:
        """Record the exact argv used. Advanced users can see this in the UI
        under 'View Processing Command'; it is never a shell string."""
        self._write("INFO", step, "exec: " + " ".join(_quote(a) for a in argv))

    # -- reading ---------------------------------------------------------

    def tail(self, lines: int = 500) -> list[str]:
        """Last `lines` lines. Never loads a huge log fully into memory."""
        if not self.path.is_file():
            return []
        with self.path.open("r", encoding="utf-8", errors="replace") as fh:
            from collections import deque
            return [line.rstrip("\n") for line in deque(fh, maxlen=max(1, lines))]


def _quote(arg: str) -> str:
    return f'"{arg}"' if " " in arg else arg
