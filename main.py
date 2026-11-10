"""
Main entry point for the PoE1 Campaign Speedrun Companion.

Run via:
    .venv\\Scripts\\python.exe main.py
or double-click `run_companion.bat`.
"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from src.route_engine import RouteEngine
from src.settings_manager import SettingsManager
from src.ui.dashboard_window import DashboardWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PoE1 Campaign Speedrun Companion")

    settings_mgr = SettingsManager()
    engine = RouteEngine()

    window = DashboardWindow(engine=engine, settings_mgr=settings_mgr)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
