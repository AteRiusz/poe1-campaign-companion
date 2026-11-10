"""
Application logging & crash diagnostics for PoE1 Campaign Speedrun Companion.

Writes timestamped startup, UI, route, and exception logs to `logs/companion.log`
so issues can be diagnosed even when launched headless via `pythonw.exe` (`run_companion.bat`).
"""

from __future__ import annotations

import faulthandler
import logging
from pathlib import Path
import sys
import traceback
from types import TracebackType
from typing import Optional, Type

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "companion.log"

_fault_file = None


def setup_logging() -> logging.Logger:
    """Configure file + console logging and install global exception & fault hooks."""
    global _fault_file
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Enable faulthandler to capture native Qt / ctypes crashes in logs/companion.log
    try:
        _fault_file = open(LOG_FILE, "a", encoding="utf-8")
        faulthandler.enable(file=_fault_file, all_threads=True)
    except Exception:
        pass

    logger = logging.getLogger("poe_companion")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)

    def _handle_uncaught_exception(
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_tb: Optional[TracebackType],
    ) -> None:
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("Uncaught exception:\n%s", tb_str)

    sys.excepthook = _handle_uncaught_exception
    return logger
