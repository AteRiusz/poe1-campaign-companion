"""
Unit and UI integration tests for PoE1 Campaign Speedrun Companion.

Run with:
    .venv\\Scripts\\pytest.exe -v
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from src.log_watcher import ClientLogTailer, parse_client_log_line
from src.route_engine import RouteEngine
from src.settings_manager import AppSettings, SettingsManager
from src.ui.dashboard_window import DashboardWindow


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


# ==================== 1. CLIENT.TXT PARSER & TAILER TESTS ====================

def test_parse_zone_entered_line() -> None:
    line = "2026/08/21 11:34:24 6977921 cffb065b [INFO Client 29304] : You have entered The Mud Flats."
    evt = parse_client_log_line(line)
    assert evt is not None
    assert evt.event_type == "ZONE_ENTERED"
    assert evt.zone_name == "The Mud Flats"
    assert evt.timestamp == "2026/08/21 11:34:24"


def test_parse_window_focus_lines() -> None:
    lost = "2026/08/21 11:35:46 7060796 54ee9dc3 [INFO Client 29304] [WINDOW] Lost focus"
    gained = "2026/08/21 11:35:47 7061187 54ee9d8c [INFO Client 29304] [WINDOW] Gained focus"

    evt_lost = parse_client_log_line(lost)
    evt_gained = parse_client_log_line(gained)

    assert evt_lost is not None and evt_lost.event_type == "WINDOW_FOCUS"
    assert evt_lost.window_focused is False
    assert evt_gained is not None and evt_gained.event_type == "WINDOW_FOCUS"
    assert evt_gained.window_focused is True


def test_parse_level_up_line() -> None:
    line = "2026/08/21 11:40:12 7090000 cffb065b [INFO Client 29304] : SpeedExile (Ranger) is now level 12"
    evt = parse_client_log_line(line)
    assert evt is not None
    assert evt.event_type == "LEVEL_UP"
    assert evt.character_name == "SpeedExile"
    assert evt.character_class == "Ranger"
    assert evt.level == 12


def test_log_tailer_incremental_reads(tmp_path: Path) -> None:
    log_file = tmp_path / "Client.txt"
    log_file.write_text(
        "2026/11/10 12:00:01 111 cffb065b [INFO Client 100] : You have entered The Coast.\n",
        encoding="utf-8",
    )

    tailer = ClientLogTailer(log_file)
    first_batch = tailer.poll_events()
    assert len(first_batch) == 1
    assert first_batch[0].zone_name == "The Coast"

    # Polling again with no new lines returns empty list
    assert tailer.poll_events() == []

    # Append new zone entry line
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write("2026/11/10 12:01:15 222 cffb065b [INFO Client 100] : You have entered The Mud Flats.\n")

    second_batch = tailer.poll_events()
    assert len(second_batch) == 1
    assert second_batch[0].zone_name == "The Mud Flats"


# ==================== 2. SETTINGS MANAGER TESTS ====================

def test_settings_defaults_extra_info_off(tmp_path: Path) -> None:
    cfg_file = tmp_path / "user_settings.json"
    mgr = SettingsManager(config_path=cfg_file)
    s: AppSettings = mgr.settings

    # Extra info settings MUST be off by default
    assert s.show_boss_info is False
    assert s.show_gem_rewards is False
    assert s.show_variants is False
    assert 0.25 <= s.opacity <= 1.0


def test_settings_opacity_and_extra_toggle_persistence(tmp_path: Path) -> None:
    cfg_file = tmp_path / "user_settings.json"
    mgr = SettingsManager(config_path=cfg_file)

    mgr.set_opacity(0.65)
    mgr.set_extra_toggle("show_boss_info", True)
    mgr.set_extra_toggle("show_gem_rewards", True)

    # Reload from disk
    reloaded = SettingsManager(config_path=cfg_file)
    assert reloaded.settings.opacity == 0.65
    assert reloaded.settings.show_boss_info is True
    assert reloaded.settings.show_gem_rewards is True
    assert reloaded.settings.show_variants is False


# ==================== 3. ROUTE ENGINE TESTS ====================

def test_route_engine_zone_matching_and_fallback() -> None:
    engine = RouteEngine()
    assert len(engine.steps) >= 20

    step = engine.on_zone_entered("The Mud Flats")
    assert step.zone_name == "The Mud Flats"
    assert step.act == 1
    assert "Rhoa Nests" in step.layout_tell

    # Entering an endgame map or unmapped zone creates a clean fallback without crashing
    fb = engine.on_zone_entered("Dunes")
    assert fb.zone_name == "Dunes"
    assert fb.compass == "LIVE ZONE"

    # Entering a campaign zone again resumes guided route
    resumed = engine.on_zone_entered("The Submerged Passage")
    assert resumed.zone_name == "The Submerged Passage"
    assert engine.active_fallback is None


# ==================== 4. UI & OPACITY / EXTRA INFO INTEGRATION TESTS ====================

def test_dashboard_and_overlay_ui_sync(qapp: QApplication, tmp_path: Path) -> None:
    cfg_file = tmp_path / "user_settings.json"
    log_file = tmp_path / "Client.txt"
    log_file.write_text("", encoding="utf-8")

    settings_mgr = SettingsManager(config_path=cfg_file)
    settings_mgr.settings.client_log_path = str(log_file)
    engine = RouteEngine()
    tailer = ClientLogTailer(log_file)

    win = DashboardWindow(engine=engine, settings_mgr=settings_mgr, tailer=tailer)

    # Verify extra info widgets are empty/hidden by default
    assert win.extra_info_layout.count() == 0
    assert win.overlay.extra_container.count() == 0
    assert win.variants_box.isHidden() is True

    # Test Opacity Slider updates both Dashboard and Overlay
    win.opacity_slider.setValue(55)
    assert settings_mgr.settings.opacity == 0.55
    assert round(win.windowOpacity(), 2) == 0.55
    assert round(win.overlay.windowOpacity(), 2) == 0.55

    # Enable extra info toggles and verify they render
    win.chk_boss_info.setChecked(True)
    win.chk_gem_rewards.setChecked(True)
    win.chk_variants.setChecked(True)

    assert win.extra_info_layout.count() == 2
    assert win.overlay.extra_container.count() == 3
    assert win.variants_box.isHidden() is False

    win.close()
