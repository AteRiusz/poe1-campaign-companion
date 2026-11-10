"""
Main entry point for the PoE1 Campaign Speedrun Companion.

Run via:
    .venv\\Scripts\\python.exe main.py
or double-click `run_companion.bat`.
"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from src.logger import setup_logging
from src.route_engine import RouteEngine
from src.settings_manager import SettingsManager
from src.ui.dashboard_window import DashboardWindow


def main() -> int:
    logger = setup_logging()
    logger.info("=== Launching PoE1 Campaign Speedrun Companion ===")
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("PoE1 Campaign Speedrun Companion")
        logger.info("QApplication initialized (platform=%s)", app.platformName())

        settings_mgr = SettingsManager()
        logger.info("Settings loaded from %s (ui_mode=%s)", settings_mgr.config_path, settings_mgr.settings.ui_mode)

        engine = RouteEngine()
        logger.info("RouteEngine loaded (%d steps, %d trials)", len(engine.steps), len(engine.trials))

        window = DashboardWindow(engine=engine, settings_mgr=settings_mgr)
        logger.info("DashboardWindow constructed; showing main window")
        window.show()
        logger.info("Entering Qt event loop")
        exit_code = app.exec()
        logger.info("Application exited cleanly with code %d", exit_code)
        return exit_code
    except Exception:
        logger.exception("Fatal error during application startup")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
