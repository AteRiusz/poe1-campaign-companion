"""
Real-time Path of Exile 1 `Client.txt` log parser and non-blocking tailer.

Recognizes:
- Zone entry: `: You have entered <Zone Name>.`
- Loading screen fallback: `[LOADING SCREEN] (<Zone Name>) Duration = ...`
- Window focus changes: `[WINDOW] Gained focus` / `[WINDOW] Lost focus`
- Character level-ups: `: <CharName> (<Class>) is now level <N>`
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

ZONE_ENTERED_RE = re.compile(
    r"^(?P<timestamp>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}).*?\[INFO Client \d+\] : You have entered (?P<zone>.+?)\.\s*$"
)

LOADING_SCREEN_RE = re.compile(
    r"^(?P<timestamp>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}).*?\[INFO Client \d+\] \[LOADING SCREEN\] \((?P<zone>.+?)\) Duration ="
)

WINDOW_FOCUS_RE = re.compile(
    r"^(?P<timestamp>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}).*?\[INFO Client \d+\] \[WINDOW\] (?P<state>Gained focus|Lost focus)\s*$"
)

LEVEL_UP_RE = re.compile(
    r"^(?P<timestamp>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}).*?\[INFO Client \d+\] : (?P<character>[^\s(]+) \((?P<char_class>[^)]+)\) is now level (?P<level>\d+)\s*$"
)


@dataclass(frozen=True)
class LogEvent:
    """Structured event parsed from a single line of PoE1's Client.txt."""

    event_type: str  # "ZONE_ENTERED" | "WINDOW_FOCUS" | "LEVEL_UP"
    timestamp: str
    zone_name: Optional[str] = None
    window_focused: Optional[bool] = None
    character_name: Optional[str] = None
    character_class: Optional[str] = None
    level: Optional[int] = None
    raw_line: str = ""


def parse_client_log_line(line: str) -> Optional[LogEvent]:
    """Parse a single line from PoE1 Client.txt into a structured LogEvent if matched."""
    clean = line.strip()
    if not clean:
        return None

    m_zone = ZONE_ENTERED_RE.match(clean)
    if m_zone:
        return LogEvent(
            event_type="ZONE_ENTERED",
            timestamp=m_zone.group("timestamp"),
            zone_name=m_zone.group("zone").strip(),
            raw_line=clean,
        )

    m_focus = WINDOW_FOCUS_RE.match(clean)
    if m_focus:
        focused = m_focus.group("state") == "Gained focus"
        return LogEvent(
            event_type="WINDOW_FOCUS",
            timestamp=m_focus.group("timestamp"),
            window_focused=focused,
            raw_line=clean,
        )

    m_lvl = LEVEL_UP_RE.match(clean)
    if m_lvl:
        return LogEvent(
            event_type="LEVEL_UP",
            timestamp=m_lvl.group("timestamp"),
            character_name=m_lvl.group("character"),
            character_class=m_lvl.group("char_class"),
            level=int(m_lvl.group("level")),
            raw_line=clean,
        )

    return None


class ClientLogTailer:
    """
    Non-blocking incremental file reader for PoE's Client.txt.
    Safe to poll from a QTimer (e.g. every 150ms) without locking the file for the game.
    """

    def __init__(self, log_path: str | Path, read_recent_bytes_on_start: int = 65536) -> None:
        self.log_path = Path(log_path)
        self._offset: int = 0
        self._initialized: bool = False
        self._read_recent_bytes_on_start = read_recent_bytes_on_start

    def set_log_path(self, log_path: str | Path) -> None:
        """Switch to a new Client.txt file path and reset tail state."""
        self.log_path = Path(log_path)
        self._offset = 0
        self._initialized = False

    def poll_events(self) -> List[LogEvent]:
        """Read any newly appended lines from Client.txt and return parsed LogEvents."""
        if not self.log_path.exists():
            return []

        try:
            file_size = self.log_path.stat().st_size
        except OSError:
            return []

        events: List[LogEvent] = []
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as fh:
                if not self._initialized:
                    self._initialized = True
                    start_pos = max(0, file_size - self._read_recent_bytes_on_start)
                    fh.seek(start_pos, os.SEEK_SET)
                    if start_pos > 0:
                        # Discard partial first line when seeking mid-file
                        fh.readline()
                else:
                    if file_size < self._offset:
                        # File was truncated or rotated
                        self._offset = 0
                    fh.seek(self._offset, os.SEEK_SET)

                for line in fh:
                    evt = parse_client_log_line(line)
                    if evt is not None:
                        events.append(evt)

                self._offset = fh.tell()
        except OSError:
            return []

        return events
