"""
Second-Screen Tactical Dashboard (`DashboardWindow`) for PoE1 Speedrun Companion.

Provides:
- Full Mission Control view for Monitor 2 (Action Pills, Speedrunner Layout Tell,
  Large Vector Topology Map, and Interactive Act Route Timeline).
- Live Opacity Slider (25%–100%) controlling both the Dashboard and the In-Game Overlay.
- Collapsible Settings Panel with Extra Info toggles (OFF by default: Boss Damage/Resist,
  Quest Gem/Vendor Rewards, and Seed Layout Variations).
- One-click toggle for the In-Game Click-Through HUD Overlay + Drag-Position Lock toggle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from src.log_watcher import ClientLogTailer
from src.route_engine import RouteEngine, RouteStep
from src.settings_manager import SettingsManager
from src.ui.map_canvas import TopologyMapWidget
from src.ui.overlay_window import OverlayWindow, TAG_STYLES


class DashboardWindow(QMainWindow):
    """Main Second-Screen Companion Window & Controller for the In-Game HUD Overlay."""

    def __init__(
        self,
        engine: RouteEngine,
        settings_mgr: SettingsManager,
        tailer: Optional[ClientLogTailer] = None,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.settings_mgr = settings_mgr
        self.tailer = tailer or ClientLogTailer(self.settings_mgr.settings.client_log_path)
        self.overlay = OverlayWindow(self.settings_mgr)

        self.setWindowTitle("PoE1 Campaign Speedrun Companion — Tactical Dashboard")
        self.resize(1120, 720)
        self.setWindowOpacity(self.settings_mgr.settings.opacity)

        self._build_ui()
        self._bind_shortcuts()

        # Poll Client.txt every 150ms
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(150)
        self.poll_timer.timeout.connect(self.poll_client_log)
        self.poll_timer.start()

        # Do initial poll & UI render
        self.poll_client_log()
        self.refresh_ui()

        if self.settings_mgr.settings.ui_mode in ("overlay", "both"):
            self.overlay.show()
            self._update_overlay_button_state()

    def _bind_shortcuts(self) -> None:
        shortcut_next = QShortcut(QKeySequence("Alt+]"), self)
        shortcut_next.activated.connect(self.on_next_step)

        shortcut_prev = QShortcut(QKeySequence("Alt+["), self)
        shortcut_prev.activated.connect(self.on_prev_step)

        shortcut_overlay = QShortcut(QKeySequence("F9"), self)
        shortcut_overlay.activated.connect(self.toggle_overlay)

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        central.setStyleSheet(
            """
            QWidget {
                background-color: #0b0e14;
                color: #f5f5f4;
                font-family: 'Segoe UI', sans-serif;
            }
            QFrame.Card {
                background-color: #131720;
                border: 1px solid #262b38;
                border-radius: 10px;
            }
            QPushButton {
                background-color: #1e2430;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
                color: #e5e7eb;
            }
            QPushButton:hover {
                background-color: #283142;
                border-color: #f59e0b;
            }
            QCheckBox {
                font-size: 12px;
                color: #e5e7eb;
                spacing: 6px;
            }
            """
        )

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 14, 16, 14)
        root_layout.setSpacing(12)

        # ==================== TOP HEADER BAR ====================
        top_bar = QFrame()
        top_bar.setProperty("class", "Card")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(14, 10, 14, 10)
        top_layout.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.act_header_label = QLabel("ACT 1 • STEP 1")
        self.act_header_label.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: bold;")
        title_col.addWidget(self.act_header_label)

        self.zone_header_label = QLabel("The Twilight Strand (Lvl 1)")
        self.zone_header_label.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: bold;")
        title_col.addWidget(self.zone_header_label)
        top_layout.addLayout(title_col)

        top_layout.addStretch(1)

        # Primary Exit & Portal Reminder Banner
        banner_frame = QFrame()
        banner_frame.setStyleSheet(
            "background-color: #0f131a; border: 1px solid #292524; border-radius: 8px; padding: 4px 8px;"
        )
        banner_layout = QVBoxLayout(banner_frame)
        banner_layout.setContentsMargins(8, 4, 8, 4)
        banner_layout.setSpacing(2)
        self.next_exit_label = QLabel("Goal: —")
        self.next_exit_label.setStyleSheet("color: #6ee7b7; font-size: 12px; font-weight: bold;")
        self.portal_tip_label = QLabel("Portal Trick: —")
        self.portal_tip_label.setStyleSheet("color: #fcd34d; font-size: 11px;")
        banner_layout.addWidget(self.next_exit_label)
        banner_layout.addWidget(self.portal_tip_label)
        top_layout.addWidget(banner_frame)

        # Mode & Settings Buttons
        self.btn_toggle_overlay = QPushButton("🖥️ Show In-Game Overlay (F9)")
        self.btn_toggle_overlay.clicked.connect(self.toggle_overlay)
        top_layout.addWidget(self.btn_toggle_overlay)

        self.btn_toggle_settings = QPushButton("⚙️ Settings & Opacity")
        self.btn_toggle_settings.clicked.connect(self.toggle_settings_drawer)
        top_layout.addWidget(self.btn_toggle_settings)

        root_layout.addWidget(top_bar)

        # ==================== COLLAPSIBLE SETTINGS & OPACITY DRAWER ====================
        self.settings_drawer = QFrame()
        self.settings_drawer.setProperty("class", "Card")
        self.settings_drawer.setVisible(False)
        drawer_layout = QVBoxLayout(self.settings_drawer)
        drawer_layout.setContentsMargins(14, 10, 14, 10)
        drawer_layout.setSpacing(10)

        row_sliders = QHBoxLayout()
        row_sliders.setSpacing(16)

        # Opacity Slider (25% - 100%)
        opacity_lbl = QLabel("Opacity:")
        opacity_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #fbbf24;")
        row_sliders.addWidget(opacity_lbl)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(25, 100)
        self.opacity_slider.setValue(int(round(self.settings_mgr.settings.opacity * 100)))
        self.opacity_slider.setFixedWidth(180)
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        row_sliders.addWidget(self.opacity_slider)

        self.opacity_value_label = QLabel(f"{int(round(self.settings_mgr.settings.opacity * 100))}%")
        self.opacity_value_label.setStyleSheet("font-family: Consolas; font-size: 12px; color: #fde68a;")
        row_sliders.addWidget(self.opacity_value_label)

        row_sliders.addSpacing(20)

        # Extra Info Checkboxes (OFF BY DEFAULT)
        extra_title = QLabel("Extra Info (Off by default):")
        extra_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #a8a29e;")
        row_sliders.addWidget(extra_title)

        self.chk_boss_info = QCheckBox("🛡️ Boss Damage & Resist Warnings")
        self.chk_boss_info.setChecked(self.settings_mgr.settings.show_boss_info)
        self.chk_boss_info.toggled.connect(lambda v: self.on_extra_toggle("show_boss_info", v))
        row_sliders.addWidget(self.chk_boss_info)

        self.chk_gem_rewards = QCheckBox("💎 Quest Gem & Vendor Rewards")
        self.chk_gem_rewards.setChecked(self.settings_mgr.settings.show_gem_rewards)
        self.chk_gem_rewards.toggled.connect(lambda v: self.on_extra_toggle("show_gem_rewards", v))
        row_sliders.addWidget(self.chk_gem_rewards)

        self.chk_variants = QCheckBox("🗺️ Detailed Seed Variations")
        self.chk_variants.setChecked(self.settings_mgr.settings.show_variants)
        self.chk_variants.toggled.connect(lambda v: self.on_extra_toggle("show_variants", v))
        row_sliders.addWidget(self.chk_variants)

        row_sliders.addStretch(1)
        drawer_layout.addLayout(row_sliders)

        # Second settings row: Overlay Click-Through Lock & Client.txt path
        row_paths = QHBoxLayout()
        row_paths.setSpacing(14)

        self.chk_click_through = QCheckBox("🔒 Lock Overlay Click-Through (Uncheck to drag HUD position)")
        self.chk_click_through.setChecked(self.settings_mgr.settings.overlay_click_through)
        self.chk_click_through.toggled.connect(self.overlay.set_click_through)
        row_paths.addWidget(self.chk_click_through)

        self.log_status_label = QLabel("")
        self.log_status_label.setStyleSheet("font-size: 11px; color: #9ca3af; font-family: Consolas;")
        row_paths.addWidget(self.log_status_label, stretch=1)

        btn_browse_log = QPushButton("📂 Set Client.txt Path...")
        btn_browse_log.clicked.connect(self.on_browse_log_path)
        row_paths.addWidget(btn_browse_log)

        drawer_layout.addLayout(row_paths)
        root_layout.addWidget(self.settings_drawer)

        # ==================== MAIN 3-COLUMN TACTICAL GRID ====================
        grid_row = QHBoxLayout()
        grid_row.setSpacing(12)

        # ---- Left Column (4/12): Action Checklist + Tell + Optional Extra Info ----
        left_card = QFrame()
        left_card.setProperty("class", "Card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 12, 14, 12)
        left_layout.setSpacing(10)

        lbl_do_now = QLabel("WHAT TO DO IN THIS AREA (GLANCE CHECKLIST)")
        lbl_do_now.setStyleSheet("font-size: 11px; font-weight: bold; color: #9ca3af;")
        left_layout.addWidget(lbl_do_now)

        self.compass_summary_label = QLabel("")
        self.compass_summary_label.setWordWrap(True)
        self.compass_summary_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #6ee7b7;")
        left_layout.addWidget(self.compass_summary_label)

        self.actions_layout = QVBoxLayout()
        self.actions_layout.setSpacing(6)
        left_layout.addLayout(self.actions_layout)

        self.tell_box = QLabel("")
        self.tell_box.setWordWrap(True)
        self.tell_box.setStyleSheet(
            "background-color: #271705; color: #fde68a; border: 1px solid #d97706; "
            "border-radius: 8px; padding: 10px; font-size: 12px;"
        )
        left_layout.addWidget(self.tell_box)

        # Optional Extra Info Box (Hidden when all toggles are OFF)
        self.extra_info_layout = QVBoxLayout()
        self.extra_info_layout.setSpacing(6)
        left_layout.addLayout(self.extra_info_layout)

        left_layout.addStretch(1)
        grid_row.addWidget(left_card, stretch=4)

        # ---- Center Column (5/12): Large Vector Topology Schematic ----
        center_card = QFrame()
        center_card.setProperty("class", "Card")
        center_layout = QVBoxLayout(center_card)
        center_layout.setContentsMargins(14, 12, 14, 12)
        center_layout.setSpacing(8)

        map_header = QHBoxLayout()
        lbl_map_title = QLabel("SIMPLIFIED ZONE TOPOLOGY & EXPECTED EXITS")
        lbl_map_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #9ca3af;")
        map_header.addWidget(lbl_map_title)
        map_header.addStretch(1)
        self.compass_pill = QLabel("NE ↗")
        self.compass_pill.setStyleSheet(
            "background-color: #1f2937; color: #fbbf24; font-family: Consolas; "
            "font-size: 12px; font-weight: bold; padding: 2px 8px; border-radius: 4px;"
        )
        map_header.addWidget(self.compass_pill)
        center_layout.addLayout(map_header)

        self.map_canvas = TopologyMapWidget(compact=False, parent=center_card)
        center_layout.addWidget(self.map_canvas, stretch=1)

        # Color Legend Bar
        legend_lbl = QLabel(
            "🟢 Emerald = Primary Exit / Main Path    🟡 Amber = Quest / Trial / +1 Pt    "
            "🔵 Sky = Waypoint / Portal    🔴 Rose = Boss"
        )
        legend_lbl.setStyleSheet("font-size: 11px; color: #9ca3af; padding-top: 4px;")
        center_layout.addWidget(legend_lbl)

        self.variants_box = QLabel("")
        self.variants_box.setWordWrap(True)
        self.variants_box.setStyleSheet(
            "background-color: #0f131a; color: #d6d3d1; border: 1px solid #292524; "
            "border-radius: 6px; padding: 8px; font-size: 12px;"
        )
        self.variants_box.setVisible(False)
        center_layout.addWidget(self.variants_box)

        grid_row.addWidget(center_card, stretch=5)

        # ---- Right Column (3/12): Route Timeline & Manual Controls ----
        right_card = QFrame()
        right_card.setProperty("class", "Card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 12, 14, 12)
        right_layout.setSpacing(8)

        lbl_route = QLabel("CAMPAIGN ROUTE TIMELINE")
        lbl_route.setStyleSheet("font-size: 11px; font-weight: bold; color: #9ca3af;")
        right_layout.addWidget(lbl_route)

        self.route_list = QListWidget()
        self.route_list.setStyleSheet(
            """
            QListWidget {
                background-color: #0b0e14;
                border: 1px solid #1f2937;
                border-radius: 6px;
                padding: 4px;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #451a03;
                color: #fde68a;
                font-weight: bold;
            }
            """
        )
        for idx, s in enumerate(self.engine.steps):
            item = QListWidgetItem(f"A{s.act}.{s.step_number} — {s.zone_name}  [{s.compass}]")
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.route_list.addItem(item)
        self.route_list.currentRowChanged.connect(self.on_route_list_selected)
        right_layout.addWidget(self.route_list, stretch=1)

        nav_row = QHBoxLayout()
        btn_prev = QPushButton("← Prev (Alt+[)")
        btn_prev.clicked.connect(self.on_prev_step)
        btn_next = QPushButton("Next (Alt+]) →")
        btn_next.clicked.connect(self.on_next_step)
        nav_row.addWidget(btn_prev)
        nav_row.addWidget(btn_next)
        right_layout.addLayout(nav_row)

        grid_row.addWidget(right_card, stretch=3)
        root_layout.addLayout(grid_row, stretch=1)

    def poll_client_log(self) -> None:
        """Poll PoE's Client.txt for new zone transitions and update UI when changed."""
        events = self.tailer.poll_events()
        changed = False
        for evt in events:
            if self.engine.process_log_event(evt):
                changed = True
        if changed:
            self.refresh_ui()

        log_exists = self.tailer.log_path.exists()
        status_prefix = "🟢 Connected:" if log_exists else "🟡 Waiting for:"
        self.log_status_label.setText(f"{status_prefix} {self.tailer.log_path}")

    def refresh_ui(self) -> None:
        """Synchronize both DashboardWindow and OverlayWindow with current RouteStep & Settings."""
        step: RouteStep = self.engine.current_step
        cfg = self.settings_mgr.settings

        self.setWindowOpacity(cfg.opacity)
        self.overlay.render_step(step, cfg)

        self.act_header_label.setText(f"ACT {step.act} • STEP {step.step_number}")
        lvl_suffix = f" (Lvl {step.area_level})" if step.area_level else ""
        self.zone_header_label.setText(f"{step.zone_name}{lvl_suffix}")
        self.next_exit_label.setText(f"🎯 Primary Exit: {step.next_exit}")
        self.portal_tip_label.setText(f"⚡ Portal / Logout: {step.portal_tip}")

        self.compass_summary_label.setText(f"🧭 {step.summary}")
        self.compass_pill.setText(step.compass)
        self.tell_box.setText(f"⚡ Speedrunner Layout Tell:\n{step.layout_tell}")

        # Rebuild Action Pills
        self._clear_layout(self.actions_layout)
        for act in step.actions:
            bg, fg, border = TAG_STYLES.get(act.get("color", "emerald"), TAG_STYLES["emerald"])
            lbl = QLabel(f"[{act.get('tag', 'STEP')}]  {act.get('text', '')}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"background-color: {bg}; color: {fg}; border: 1px solid {border}; "
                "border-radius: 6px; padding: 6px 10px; font-size: 12px; font-weight: 600;"
            )
            self.actions_layout.addWidget(lbl)

        # Rebuild Optional Extra Info (OFF by default)
        self._clear_layout(self.extra_info_layout)
        if cfg.show_boss_info and step.boss_info:
            b_lbl = QLabel(f"🛡️ Boss & Resist Warning:\n{step.boss_info}")
            b_lbl.setWordWrap(True)
            b_lbl.setStyleSheet(
                "background-color: #4c0519; color: #fecdd3; border: 1px solid #f43f5e; "
                "border-radius: 6px; padding: 8px; font-size: 12px;"
            )
            self.extra_info_layout.addWidget(b_lbl)

        if cfg.show_gem_rewards and step.gem_reward:
            g_lbl = QLabel(f"💎 Quest Gem & Vendor Reward:\n{step.gem_reward}")
            g_lbl.setWordWrap(True)
            g_lbl.setStyleSheet(
                "background-color: #2e1065; color: #ddd6fe; border: 1px solid #8b5cf6; "
                "border-radius: 6px; padding: 8px; font-size: 12px;"
            )
            self.extra_info_layout.addWidget(g_lbl)

        if cfg.show_variants and step.variants:
            lines = [f"• {v.get('title')}: {v.get('desc')}" for v in step.variants]
            self.variants_box.setText("🗺️ Known Seed Layout Variations:\n" + "\n".join(lines))
            self.variants_box.setVisible(True)
        else:
            self.variants_box.setVisible(False)

        self.map_canvas.set_topology(step.topology, compass_label=step.compass)

        # Sync timeline selection without recursive signal loop
        self.route_list.blockSignals(True)
        self.route_list.setCurrentRow(self.engine.current_index)
        self.route_list.blockSignals(False)

    def on_opacity_changed(self, slider_value: int) -> None:
        opacity = self.settings_mgr.set_opacity(slider_value / 100.0)
        self.opacity_value_label.setText(f"{int(round(opacity * 100))}%")
        self.setWindowOpacity(opacity)
        self.overlay.set_overlay_opacity(opacity)

    def on_extra_toggle(self, field_name: str, enabled: bool) -> None:
        self.settings_mgr.set_extra_toggle(field_name, enabled)
        self.refresh_ui()

    def toggle_settings_drawer(self) -> None:
        self.settings_drawer.setVisible(not self.settings_drawer.isVisible())

    def toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self.overlay.hide()
            self.settings_mgr.settings.ui_mode = "dashboard"
        else:
            self.overlay.show()
            self.overlay.raise_()
            self.settings_mgr.settings.ui_mode = "both"
        self.settings_mgr.save()
        self._update_overlay_button_state()

    def _update_overlay_button_state(self) -> None:
        if self.overlay.isVisible():
            self.btn_toggle_overlay.setText("🟢 Hide In-Game Overlay (F9)")
        else:
            self.btn_toggle_overlay.setText("🖥️ Show In-Game Overlay (F9)")

    def on_next_step(self) -> None:
        self.engine.next_step()
        self.refresh_ui()

    def on_prev_step(self) -> None:
        self.engine.prev_step()
        self.refresh_ui()

    def on_route_list_selected(self, row: int) -> None:
        if row >= 0:
            self.engine.select_index(row)
            self.refresh_ui()

    def on_browse_log_path(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Path of Exile Client.txt",
            str(Path(self.settings_mgr.settings.client_log_path).parent),
            "Text Logs (Client.txt *.txt);;All Files (*)",
        )
        if file_path:
            self.settings_mgr.settings.client_log_path = file_path
            self.settings_mgr.save()
            self.tailer.set_log_path(file_path)
            self.poll_client_log()

    def closeEvent(self, event: object) -> None:
        self.overlay.close()
        super().closeEvent(event)  # type: ignore[arg-type]

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
