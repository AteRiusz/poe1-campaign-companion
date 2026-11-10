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
from src.ui.map_canvas import TopologyMapWidget, _intersection_area


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
    assert s.completed_trials == []
    assert s.unlocked_trials == []


def test_settings_opacity_and_extra_toggle_persistence(tmp_path: Path) -> None:
    cfg_file = tmp_path / "user_settings.json"
    mgr = SettingsManager(config_path=cfg_file)

    mgr.set_opacity(0.65)
    mgr.set_extra_toggle("show_boss_info", True)
    mgr.set_extra_toggle("show_gem_rewards", True)
    mgr.set_trial_completed("norm_1_lower_prison", True)

    # Reload from disk
    reloaded = SettingsManager(config_path=cfg_file)
    assert reloaded.settings.opacity == 0.65
    assert reloaded.settings.show_boss_info is True
    assert reloaded.settings.show_gem_rewards is True
    assert reloaded.settings.show_variants is False
    assert "norm_1_lower_prison" in reloaded.settings.completed_trials


# ==================== 3. ROUTE ENGINE & LABYRINTH TRIALS TESTS ====================

def test_route_engine_all_ten_acts_and_fallback() -> None:
    engine = RouteEngine()
    acts_present = {s.act for s in engine.steps}
    assert acts_present == {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
    assert len(engine.steps) >= 90

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


def test_labyrinth_trials_locked_unlocked_completed_states() -> None:
    engine = RouteEngine()
    assert len(engine.get_trials_by_tier("Normal")) == 6
    assert len(engine.get_trials_by_tier("Cruel")) == 3
    assert len(engine.get_trials_by_tier("Merciless")) == 3

    crypt_trial = [t for t in engine.trials if t.trial_id == "norm_3_crypt_1"][0]
    # At start of Act 1, Act 2 Crypt trial is locked
    assert engine.get_trial_status(crypt_trial) == "locked"

    # When player reaches Act 2 'The Crossroads' (the unlock_zone for Crypt Level 1), it becomes unlocked!
    engine.on_zone_entered("The Crossroads")
    assert engine.get_trial_status(crypt_trial) == "unlocked"

    # When marked completed, status is 'completed'
    assert engine.get_trial_status(crypt_trial, completed_ids=["norm_3_crypt_1"]) == "completed"


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

    # In Window Mode (overlay hidden), opacity is locked at 100% and opacity setting is hidden
    assert win.overlay.isVisible() is False
    assert round(win.windowOpacity(), 2) == 1.0
    assert win.opacity_group.isHidden() is True

    # Toggle into Overlay Mode: opacity setting becomes visible and only affects the overlay
    win.toggle_overlay()
    assert win.overlay.isVisible() is True
    assert win.opacity_group.isHidden() is False

    win.opacity_slider.setValue(55)
    assert settings_mgr.settings.opacity == 0.55
    assert round(win.windowOpacity(), 2) == 1.0  # Window mode stays locked at 100%
    assert round(win.overlay.windowOpacity(), 2) == 0.55

    # Switch back to Window Mode: opacity setting hides again
    win.toggle_overlay()
    assert win.overlay.isVisible() is False
    assert win.opacity_group.isHidden() is True
    assert round(win.windowOpacity(), 2) == 1.0

    # Enable extra info toggles and verify they render
    win.chk_boss_info.setChecked(True)
    win.chk_gem_rewards.setChecked(True)
    win.chk_variants.setChecked(True)

    assert win.extra_info_layout.count() == 2
    assert win.overlay.extra_container.count() == 3
    assert win.variants_box.isHidden() is False

    win.close()


def test_topology_labels_never_overlap_across_all_103_steps(qapp: QApplication) -> None:
    from PyQt6.QtCore import QRectF

    engine = RouteEngine()
    for compact, cw, ch in [(False, 380.0, 252.0), (True, 220.0, 158.0)]:
        canvas = TopologyMapWidget(compact=compact)
        for step in engine.steps:
            canvas.set_topology(step.topology, compass_label=step.compass)
            coords, rad = canvas._compute_node_positions(cw, ch)
            placements = canvas.compute_label_rects(cw, ch)
            banner_h = canvas._banner_height()
            banner_rect = (
                QRectF(4.0, ch - banner_h + 1.0, cw - 8.0, banner_h - 3.0)
                if banner_h > 0.0
                else QRectF()
            )

            # 1. Verify no two tooltip boxes overlap each other
            for i in range(len(placements)):
                for j in range(i + 1, len(placements)):
                    overlap = _intersection_area(placements[i][2], placements[j][2])
                    assert overlap == 0.0, (
                        f"Label-Label overlap (compact={compact}) on {step.step_id}: "
                        f"{placements[i][0]['label']} vs {placements[j][0]['label']}"
                    )

            # 2. Verify no tooltip box overlaps any node circle or the bottom procedural warning banner
            for n, _pt, lrect in placements:
                if not banner_rect.isEmpty():
                    assert _intersection_area(lrect, banner_rect) == 0.0, (
                        f"Label-Banner overlap (compact={compact}) on {step.step_id}: '{n['label']}'"
                    )
                for nid, npt in coords.items():
                    node_rect = QRectF(npt.x() - rad, npt.y() - rad, 2 * rad, 2 * rad)
                    node_overlap = _intersection_area(lrect, node_rect)
                    assert node_overlap == 0.0, (
                        f"Label-Node overlap (compact={compact}) on {step.step_id}: "
                        f"label '{n['label']}' overlaps node '{nid}'"
                    )


def test_zone_aliases_and_town_hubs_match_guided_steps() -> None:
    engine = RouteEngine()
    # Verify newly added town hubs & Weaver's Chambers + key sub-zone aliases resolve to guided steps (never LIVE ZONE)
    expected_zones = [
        ("The Warden's Quarters", "a1_s11_upper_prison"),
        ("Merveil's Caverns", "a1_s16_cavern_of_anger"),
        ("The Forest Encampment", "a2_s02_forest_encampment"),
        ("The Weaver's Chambers", "a2_s09_weavers_chambers"),
        ("The Fellshrine Ruins", "a2_s10_crypt_level_1"),
        ("The Ancient Pyramid", "a2_s14_caverns_and_pyramid"),
        ("The Sarn Encampment", "a3_s02_sarn_encampment"),
        ("The Solaris Temple Level 2", "a3_s08_solaris_temple"),
        ("The Lunaris Temple Level 2", "a3_s10_lunaris_temple"),
        ("The Upper Sceptre of God", "a3_s12_sceptre_of_god"),
        ("Highgate", "a4_s02_highgate"),
        ("The Belly of the Beast Level 2", "a4_s10_belly_of_the_beast"),
        ("Overseer's Tower", "a5_s02_overseers_tower"),
        ("The Bridge Encampment", "a7_s01_bridge_encampment"),
        ("Doedre's Cesspool", "a8_s02_toxic_conduits_doedre"),
        ("The Descent", "a9_s02_descent_vastiri_desert"),
        ("Oriath Docks", "a10_s01_oriath_docks"),
    ]
    for zone_name, expected_step_id in expected_zones:
        step = engine.on_zone_entered(zone_name)
        assert engine.active_fallback is None, f"Zone '{zone_name}' fell back to unmapped LIVE ZONE"
        assert step.step_id == expected_step_id, f"Zone '{zone_name}' matched {step.step_id} instead of {expected_step_id}"


def test_topology_compass_quadrants_across_all_103_steps() -> None:
    import re

    engine = RouteEngine()
    for step in engine.steps:
        sid = step.step_id
        for node in step.topology.get("nodes", []):
            lbl = str(node.get("label", ""))
            x = float(node.get("x", 0.5))
            y = float(node.get("y", 0.5))

            has_nw = bool(re.search(r"\bNW\b|North-West|↖", lbl))
            has_ne = bool(re.search(r"\bNE\b|North-East|↗", lbl))
            has_sw = bool(re.search(r"\bSW\b|South-West|↙", lbl))
            has_se = bool(re.search(r"\bSE\b|South-East|↘", lbl))

            if has_nw:
                assert x <= 0.52 and y <= 0.52, f"{sid} '{lbl}' at ({x},{y}) must be in NW quadrant"
            if has_ne:
                assert x >= 0.48 and y <= 0.52, f"{sid} '{lbl}' at ({x},{y}) must be in NE quadrant"
            if has_sw:
                assert x <= 0.52 and y >= 0.48, f"{sid} '{lbl}' at ({x},{y}) must be in SW quadrant"
            if has_se:
                assert x >= 0.48 and y >= 0.48, f"{sid} '{lbl}' at ({x},{y}) must be in SE quadrant"

            if not (has_nw or has_ne or has_sw or has_se):
                if re.search(r"\b(North|N)\b|↑", lbl):
                    assert y <= 0.50, f"{sid} '{lbl}' at ({x},{y}) must be in North half (y<=0.50)"
                if re.search(r"\b(South|S)\b|↓", lbl):
                    assert y >= 0.50, f"{sid} '{lbl}' at ({x},{y}) must be in South half (y>=0.50)"
                if re.search(r"\b(West|W|Left)\b|←", lbl):
                    assert x <= 0.50, f"{sid} '{lbl}' at ({x},{y}) must be in West half (x<=0.50)"
                if re.search(r"\b(East|E|Right)\b", lbl):
                    assert x >= 0.50, f"{sid} '{lbl}' at ({x},{y}) must be in East half (x>=0.50)"
                if re.search(r"\bCenter\b", lbl):
                    assert 0.35 <= x <= 0.65 and 0.35 <= y <= 0.65, f"{sid} '{lbl}' at ({x},{y}) must be near Center"


def test_overlay_and_dashboard_checklist_items_never_squash_when_switching_steps(
    qapp: QApplication, tmp_path: Path
) -> None:
    sm = SettingsManager(tmp_path / "settings.json")
    sm.settings.show_boss_info = True
    sm.settings.show_gem_rewards = True
    sm.settings.show_variants = True
    engine = RouteEngine()
    dash = DashboardWindow(engine, sm, ClientLogTailer(tmp_path / "Client.txt"))
    dash.show()
    dash.overlay.show()
    qapp.processEvents()

    # Check a representative set of steps across Acts 1-10 (including Lioneye's Watch)
    test_indices = [0, 1, 2, 4, 5, 10, 15, 22, 35, 50, 75, 100, 102]
    for idx in test_indices:
        engine.select_index(idx)
        dash.refresh_ui()
        qapp.processEvents()

        assert dash.overlay.width() == dash.overlay.OVERLAY_WIDTH

        for i in range(dash.overlay.actions_container.count()):
            pill = dash.overlay.actions_container.itemAt(i).widget()
            assert pill is not None
            needed = pill.heightForWidth(pill.width())
            assert pill.height() >= needed, (
                f"Overlay pill {i} squashed on {engine.current_step.step_id}: "
                f"height={pill.height()} < needed={needed}"
            )

        for i in range(dash.overlay.extra_container.count()):
            extra = dash.overlay.extra_container.itemAt(i).widget()
            assert extra is not None
            needed = extra.heightForWidth(extra.width())
            assert extra.height() >= needed, (
                f"Overlay extra {i} squashed on {engine.current_step.step_id}: "
                f"height={extra.height()} < needed={needed}"
            )

        for i in range(dash.actions_layout.count()):
            dpill = dash.actions_layout.itemAt(i).widget()
            assert dpill is not None
            needed = dpill.heightForWidth(dpill.width())
            assert dpill.height() >= needed, (
                f"Dashboard pill {i} squashed on {engine.current_step.step_id}: "
                f"height={dpill.height()} < needed={needed}"
            )

    dash.close()


def test_global_hotkeys_trigger_overlay_and_step_navigation(
    qapp: QApplication, tmp_path: Path
) -> None:
    sm = SettingsManager(tmp_path / "settings.json")
    engine = RouteEngine()
    dash = DashboardWindow(engine, sm, ClientLogTailer(tmp_path / "Client.txt"))
    dash.show()
    qapp.processEvents()

    assert not dash.overlay.isVisible()
    assert engine.current_index == 0

    pressed: set[int] = set()
    key_fn = lambda vk: 0x8000 if vk in pressed else 0

    # Simulate pressing Alt+L globally in-game
    pressed = {DashboardWindow.VK_MENU, DashboardWindow.VK_L}
    dash._poll_global_key_states(key_state_fn=key_fn)
    assert dash.overlay.isVisible()

    # Holding the key down or immediate duplicate within 180ms should not re-toggle
    dash._poll_global_key_states(key_state_fn=key_fn)
    assert dash.overlay.isVisible()

    # Release keys
    pressed = set()
    dash._poll_global_key_states(key_state_fn=key_fn)

    # Simulate pressing Alt+] (Next Step) globally in-game
    vk_next = getattr(dash, "_vk_next", 0xDD)
    pressed = {DashboardWindow.VK_MENU, vk_next}
    dash._poll_global_key_states(key_state_fn=key_fn)
    assert engine.current_index == 1

    pressed = set()
    dash._poll_global_key_states(key_state_fn=key_fn)

    # Simulate pressing Alt+[ (Previous Step) globally in-game
    vk_prev = getattr(dash, "_vk_prev", 0xDB)
    pressed = {DashboardWindow.VK_MENU, vk_prev}
    dash._poll_global_key_states(key_state_fn=key_fn)
    assert engine.current_index == 0

    dash.close()


def test_automatic_step_checkmarks_and_reset_progress_button(
    qapp: QApplication, tmp_path: Path
) -> None:
    cfg_file = tmp_path / "settings.json"
    log_file = tmp_path / "Client.txt"
    log_file.write_text("", encoding="utf-8")

    sm = SettingsManager(cfg_file)
    engine = RouteEngine()
    tailer = ClientLogTailer(log_file)
    dash = DashboardWindow(engine, sm, tailer)
    dash.show()
    qapp.processEvents()

    # 1. Manual browsing in the Route Timeline should NEVER unlock trials or complete steps
    dash.on_route_list_selected(20)
    assert sm.settings.completed_steps == []
    assert sm.settings.unlocked_trials == []
    for trial in engine.trials:
        assert engine.get_trial_status(trial, sm.settings.unlocked_trials, sm.settings.completed_trials) == "locked"

    # Reset back to start
    dash.on_route_list_selected(0)

    # 2. Simulate entering Twilight Strand -> killing Hillock -> entering Lioneye's Watch -> The Coast -> Tidal Island
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write("2026/11/10 12:00:01 100 cffb065b [INFO Client 100] : You have entered The Twilight Strand.\n")
        fh.write("2026/11/10 12:01:00 101 cffb065b [INFO Client 100] : You have entered Lioneye's Watch.\n")
        fh.write("2026/11/10 12:01:30 102 cffb065b [INFO Client 100] : You have entered The Coast.\n")
        fh.write("2026/11/10 12:02:10 103 cffb065b [INFO Client 100] : You have entered The Tidal Island.\n")
    dash.poll_client_log()

    assert "a1_s01_twilight_strand" in sm.settings.completed_steps
    assert "a1_s02_lioneyes_watch" in sm.settings.completed_steps
    assert "a1_s03_the_coast" in sm.settings.completed_steps
    assert dash.route_list.item(0).text().startswith("✅ ")
    assert dash.route_list.item(1).text().startswith("✅ ")
    assert dash.route_list.item(2).text().startswith("✅ ")

    # 3. Leaving Tidal Island via Logout to Lioneye's Watch (after Hailrake + Medicine Chest) marks Tidal Island done
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write("2026/11/10 12:03:00 104 cffb065b [INFO Client 100] : You have entered Lioneye's Watch.\n")
    dash.poll_client_log()
    assert "a1_s04_tidal_island" in sm.settings.completed_steps
    assert dash.route_list.item(3).text().startswith("✅ ")

    # 4. Entering Mud Flats (3 Glyphs quest items) and backtracking to The Coast does NOT complete Mud Flats;
    #    exiting forward into The Submerged Passage DOES complete Mud Flats
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write("2026/11/10 12:04:00 105 cffb065b [INFO Client 100] : You have entered The Mud Flats.\n")
        fh.write("2026/11/10 12:04:20 106 cffb065b [INFO Client 100] : You have entered The Coast.\n")
    dash.poll_client_log()
    assert "a1_s05_mud_flats" not in sm.settings.completed_steps

    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write("2026/11/10 12:05:00 107 cffb065b [INFO Client 100] : You have entered The Mud Flats.\n")
        fh.write("2026/11/10 12:06:00 108 cffb065b [INFO Client 100] : You have entered The Submerged Passage.\n")
    dash.poll_client_log()
    assert "a1_s05_mud_flats" in sm.settings.completed_steps

    # 5. Entering Upper Prison: leaving before entering Warden's Quarters (Brutus) does NOT complete it;
    #    entering Warden's Quarters and then leaving to Prisoner's Gate DOES complete it!
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write("2026/11/10 12:07:00 109 cffb065b [INFO Client 100] : You have entered The Lower Prison.\n")
        fh.write("2026/11/10 12:08:00 110 cffb065b [INFO Client 100] : You have entered The Upper Prison.\n")
        fh.write("2026/11/10 12:08:15 111 cffb065b [INFO Client 100] : You have entered Lioneye's Watch.\n")
    dash.poll_client_log()
    assert "norm_1_lower_prison" in sm.settings.unlocked_trials
    assert "a1_s11_upper_prison" not in sm.settings.completed_steps

    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write("2026/11/10 12:09:00 112 cffb065b [INFO Client 100] : You have entered The Upper Prison.\n")
        fh.write("2026/11/10 12:09:40 113 cffb065b [INFO Client 100] : You have entered The Warden's Quarters.\n")
        fh.write("2026/11/10 12:10:20 114 cffb065b [INFO Client 100] : You have entered Prisoner's Gate.\n")
    dash.poll_client_log()
    assert "a1_s11_upper_prison" in sm.settings.completed_steps

    # 6. Clicking 'Reset Progress' clears all completed steps and all unlocked/completed Lab Trials
    dash.set_trial_completed_state = sm.set_trial_completed("norm_1_lower_prison", True)
    assert len(sm.settings.completed_steps) > 0
    assert len(sm.settings.unlocked_trials) > 0
    assert len(sm.settings.completed_trials) > 0

    dash.btn_reset_progress.click()
    qapp.processEvents()

    assert sm.settings.completed_steps == []
    assert sm.settings.unlocked_trials == []
    assert sm.settings.completed_trials == []
    assert engine.completed_steps == set()
    assert engine.current_index == 0
    assert not dash.route_list.item(0).text().startswith("✅ ")
    for trial in engine.trials:
        assert engine.get_trial_status(trial, sm.settings.unlocked_trials, sm.settings.completed_trials) == "locked"

    # Polling again with no new lines after Reset Progress keeps everything locked/reset
    dash.poll_client_log()
    assert sm.settings.completed_steps == []
    assert sm.settings.unlocked_trials == []

    dash.close()




