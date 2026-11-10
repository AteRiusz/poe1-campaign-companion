"""
In-Game Click-Through HUD Overlay (`OverlayWindow`) for PoE1 Speedrun Companion.

Uses Qt's `FramelessWindowHint`, `WindowStaysOnTopHint`, and `WindowTransparentForInput`
so mouse clicks pass directly through to Path of Exile while displaying the current
zone's simplified topology map, action pills, and layout tell.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.route_engine import RouteStep
from src.settings_manager import AppSettings, SettingsManager
from src.ui.map_canvas import TopologyMapWidget

TAG_STYLES = {
    "emerald": ("#064e3b", "#6ee7b7", "#10b981"),
    "amber": ("#451a03", "#fde68a", "#f59e0b"),
    "sky": ("#0c4a6e", "#7dd3fc", "#38bdf8"),
    "rose": ("#4c0519", "#fda4af", "#f43f5e"),
}


class OverlayWindow(QWidget):
    """Topmost, frameless HUD overlay window that updates automatically on zone change."""

    def __init__(self, settings_mgr: SettingsManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings_mgr = settings_mgr
        self._drag_offset: Optional[QPoint] = None

        self.setWindowTitle("PoE1 Speedrun HUD Overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._apply_window_flags(self.settings_mgr.settings.overlay_click_through)

        self.resize(560, 250)
        self.move(
            self.settings_mgr.settings.overlay_x,
            self.settings_mgr.settings.overlay_y,
        )
        self.setWindowOpacity(self.settings_mgr.settings.opacity)

        self._build_ui()

    def _apply_window_flags(self, click_through: bool) -> None:
        was_visible = self.isVisible()
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        if click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

    def set_click_through(self, enabled: bool) -> None:
        """Enable or disable mouse click-through (disable temporarily to drag overlay)."""
        self.settings_mgr.settings.overlay_click_through = bool(enabled)
        self.settings_mgr.save()
        self._apply_window_flags(bool(enabled))
        self.drag_hint_label.setVisible(not enabled)

    def set_overlay_opacity(self, opacity: float) -> None:
        """Update window opacity in real time (0.25 to 1.00)."""
        clamped = max(0.25, min(1.0, float(opacity)))
        self.setWindowOpacity(clamped)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame(self)
        self.card.setObjectName("OverlayCard")
        self.card.setStyleSheet(
            """
            QFrame#OverlayCard {
                background-color: #0c0a09;
                border: 1.5px solid #d97706;
                border-radius: 10px;
            }
            QLabel {
                color: #f5f5f4;
                font-family: 'Segoe UI', sans-serif;
            }
            """
        )
        outer.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        # Top Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.act_badge = QLabel("ACT 1 • STEP 1")
        self.act_badge.setStyleSheet(
            "background-color: #451a03; color: #fcd34d; border: 1px solid #d97706; "
            "border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: bold;"
        )
        header_row.addWidget(self.act_badge)

        self.zone_title = QLabel("The Twilight Strand")
        self.zone_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #fef3c7;")
        header_row.addWidget(self.zone_title)

        self.level_label = QLabel("(Lvl 1)")
        self.level_label.setStyleSheet("font-size: 11px; color: #a8a29e; font-family: Consolas;")
        header_row.addWidget(self.level_label)

        header_row.addStretch(1)

        self.compass_badge = QLabel("NE ↗")
        self.compass_badge.setStyleSheet(
            "background-color: #064e3b; color: #6ee7b7; border: 1px solid #10b981; "
            "border-radius: 4px; padding: 2px 8px; font-size: 12px; font-weight: bold;"
        )
        header_row.addWidget(self.compass_badge)

        card_layout.addLayout(header_row)

        # Drag hint banner when unlocked
        self.drag_hint_label = QLabel("🔓 Drag Mode Active — Drag this HUD anywhere, then re-lock Click-Through in Dashboard")
        self.drag_hint_label.setStyleSheet(
            "background-color: #1e3a8a; color: #bfdbfe; border-radius: 4px; padding: 3px 6px; font-size: 11px; font-weight: bold;"
        )
        self.drag_hint_label.setVisible(not self.settings_mgr.settings.overlay_click_through)
        card_layout.addWidget(self.drag_hint_label)

        # Compass 1-line summary
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 12px; color: #6ee7b7; font-weight: 600;")
        card_layout.addWidget(self.summary_label)

        # Main Body: Left = Action Steps + Tell, Right = Compact Vector Map
        body_row = QHBoxLayout()
        body_row.setSpacing(10)

        left_col = QVBoxLayout()
        left_col.setSpacing(5)

        self.actions_container = QVBoxLayout()
        self.actions_container.setSpacing(4)
        left_col.addLayout(self.actions_container)

        self.tell_label = QLabel("")
        self.tell_label.setWordWrap(True)
        self.tell_label.setStyleSheet(
            "background-color: #1c1917; color: #fde68a; border-left: 3px solid #f59e0b; "
            "padding: 4px 6px; font-size: 11px; border-radius: 3px;"
        )
        left_col.addWidget(self.tell_label)

        # Extra Info Container (OFF by default, controlled via Settings)
        self.extra_container = QVBoxLayout()
        self.extra_container.setSpacing(4)
        left_col.addLayout(self.extra_container)

        left_col.addStretch(1)
        body_row.addLayout(left_col, stretch=7)

        self.map_widget = TopologyMapWidget(compact=True, parent=self.card)
        self.map_widget.setMinimumWidth(195)
        body_row.addWidget(self.map_widget, stretch=5)

        card_layout.addLayout(body_row)

    def render_step(self, step: RouteStep, settings: Optional[AppSettings] = None) -> None:
        """Update the HUD overlay contents for the given RouteStep and AppSettings."""
        cfg = settings or self.settings_mgr.settings
        self.set_overlay_opacity(cfg.opacity)

        self.act_badge.setText(f"ACT {step.act} • STEP {step.step_number}")
        self.zone_title.setText(step.zone_name)
        self.level_label.setText(f"(Lvl {step.area_level})" if step.area_level else "")
        self.compass_badge.setText(step.compass)
        self.summary_label.setText(f"🧭 {step.summary}")
        self.tell_label.setText(f"⚡ Tell: {step.layout_tell}")

        # Rebuild Action Pills
        self._clear_layout(self.actions_container)
        for act in step.actions:
            bg, fg, border = TAG_STYLES.get(act.get("color", "emerald"), TAG_STYLES["emerald"])
            pill = QLabel(f"[{act.get('tag', 'STEP')}]  {act.get('text', '')}")
            pill.setWordWrap(True)
            pill.setStyleSheet(
                f"background-color: {bg}; color: {fg}; border: 1px solid {border}; "
                "border-radius: 5px; padding: 3px 7px; font-size: 11px; font-weight: 600;"
            )
            self.actions_container.addWidget(pill)

        # Rebuild Optional Extra Info (Only shown when corresponding setting is True)
        self._clear_layout(self.extra_container)
        if cfg.show_boss_info and step.boss_info:
            boss_lbl = QLabel(f"🛡️ Boss: {step.boss_info}")
            boss_lbl.setWordWrap(True)
            boss_lbl.setStyleSheet(
                "background-color: #4c0519; color: #fecdd3; border: 1px solid #f43f5e; "
                "border-radius: 4px; padding: 3px 6px; font-size: 11px;"
            )
            self.extra_container.addWidget(boss_lbl)

        if cfg.show_gem_rewards and step.gem_reward:
            gem_lbl = QLabel(f"💎 Gems: {step.gem_reward}")
            gem_lbl.setWordWrap(True)
            gem_lbl.setStyleSheet(
                "background-color: #2e1065; color: #ddd6fe; border: 1px solid #8b5cf6; "
                "border-radius: 4px; padding: 3px 6px; font-size: 11px;"
            )
            self.extra_container.addWidget(gem_lbl)

        if cfg.show_variants and step.variants:
            var_text = " | ".join(f"{v.get('title')}: {v.get('desc')}" for v in step.variants)
            var_lbl = QLabel(f"🗺️ Variants: {var_text}")
            var_lbl.setWordWrap(True)
            var_lbl.setStyleSheet(
                "background-color: #1c1917; color: #d6d3d1; border: 1px solid #44403c; "
                "border-radius: 4px; padding: 3px 6px; font-size: 11px;"
            )
            self.extra_container.addWidget(var_lbl)

        self.map_widget.set_topology(step.topology, compass_label=step.compass, step_id=step.step_id)
        self.adjustSize()

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    # Allow dragging the HUD when Click-Through is temporarily unlocked
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.settings_mgr.settings.overlay_click_through and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and not self.settings_mgr.settings.overlay_click_through:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            pos = self.pos()
            self.settings_mgr.settings.overlay_x = pos.x()
            self.settings_mgr.settings.overlay_y = pos.y()
            self.settings_mgr.save()
            event.accept()
