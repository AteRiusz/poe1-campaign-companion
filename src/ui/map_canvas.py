"""
Vector Topology Map Canvas (`TopologyMapWidget`) for PoE1 Campaign Companion.

Renders the simplified zone schematic (`nodes` and `edges` normalized in 0.0..1.0 coordinates)
using antialiased PyQt6 QPainter graphics.
"""

from __future__ import annotations

from typing import Any, Dict, List

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

NODE_COLORS: Dict[str, str] = {
    "start": "#a8a29e",   # Stone gray
    "wp": "#38bdf8",      # Sky blue (Waypoint)
    "portal": "#0284c7",  # Deep sky blue (Portal trick)
    "quest": "#f59e0b",   # Amber gold (Quest / Trial / Skill Point)
    "boss": "#f43f5e",    # Rose red (Boss)
    "exit": "#10b981",    # Emerald green (Primary Exit)
}


class TopologyMapWidget(QWidget):
    """Custom QWidget that draws a simplified node-and-edge layout map for the current zone."""

    def __init__(self, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.compact = compact
        self.topology: Dict[str, Any] = {"nodes": [], "edges": []}
        self.compass_label: str = ""
        self.setMinimumHeight(115 if compact else 210)

    def set_topology(self, topology: Dict[str, Any], compass_label: str = "") -> None:
        """Update the zone topology graph and trigger a repaint."""
        self.topology = topology or {"nodes": [], "edges": []}
        self.compass_label = compass_label
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect()
        w = float(rect.width())
        h = float(rect.height())

        # Dark slate-stone background with subtle border
        painter.fillRect(rect, QColor("#090b10"))
        border_pen = QPen(QColor("#292524"), 1.2)
        painter.setPen(border_pen)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8.0, 8.0)

        # Subtle compass rose watermark in top-right corner
        if self.compass_label:
            font_compass = QFont("Consolas", 9 if self.compact else 10, QFont.Weight.Bold)
            painter.setFont(font_compass)
            painter.setPen(QColor("#fbbf24"))
            painter.drawText(
                rect.adjusted(8, 6, -10, -6),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                self.compass_label,
            )

        nodes: List[Dict[str, Any]] = self.topology.get("nodes", [])
        edges: List[Dict[str, Any]] = self.topology.get("edges", [])

        if not nodes:
            return

        pad_x = 34.0 if self.compact else 48.0
        pad_y = 24.0 if self.compact else 34.0
        usable_w = max(40.0, w - 2 * pad_x)
        usable_h = max(40.0, h - 2 * pad_y)

        node_coords: Dict[str, QPointF] = {}
        for n in nodes:
            nx = pad_x + float(n.get("x", 0.5)) * usable_w
            ny = pad_y + float(n.get("y", 0.5)) * usable_h
            node_coords[str(n.get("id", ""))] = QPointF(nx, ny)

        # Draw edges first
        for edge in edges:
            src_id = str(edge.get("from", ""))
            dst_id = str(edge.get("to", ""))
            style = str(edge.get("style", "main"))
            if src_id not in node_coords or dst_id not in node_coords:
                continue

            p1 = node_coords[src_id]
            p2 = node_coords[dst_id]

            if style == "river":
                river_pen = QPen(QColor(56, 189, 248, 95), 5.0 if not self.compact else 3.5)
                painter.setPen(river_pen)
                painter.drawLine(p1, p2)
                dash_pen = QPen(QColor("#fbbf24"), 2.0, Qt.PenStyle.DashLine)
                painter.setPen(dash_pen)
                painter.drawLine(p1, p2)
            elif style == "branch":
                branch_pen = QPen(QColor("#f59e0b"), 2.0, Qt.PenStyle.DotLine)
                painter.setPen(branch_pen)
                painter.drawLine(p1, p2)
            else:
                main_pen = QPen(QColor("#34d399"), 2.8 if not self.compact else 2.2, Qt.PenStyle.DashLine)
                painter.setPen(main_pen)
                painter.drawLine(p1, p2)

        # Draw nodes and labels
        label_font = QFont("Segoe UI", 8 if self.compact else 9, QFont.Weight.DemiBold)
        painter.setFont(label_font)
        radius = 5.5 if self.compact else 7.5

        for n in nodes:
            nid = str(n.get("id", ""))
            ntype = str(n.get("type", "start"))
            label = str(n.get("label", ""))
            pt = node_coords.get(nid)
            if pt is None:
                continue

            hex_color = NODE_COLORS.get(ntype, "#a8a29e")
            fill_color = QColor(hex_color)

            # Outer glow ring for active objectives
            if ntype in ("exit", "quest", "boss", "wp", "portal"):
                glow = QColor(fill_color)
                glow.setAlpha(65)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(glow)
                painter.drawEllipse(pt, radius + 4.0, radius + 4.0)

            painter.setPen(QPen(QColor("#090b10"), 1.5))
            painter.setBrush(fill_color)
            painter.drawEllipse(pt, radius, radius)

            # Node label
            painter.setPen(QColor("#f5f5f4"))
            text_offset_y = -radius - 5.0 if pt.y() > h * 0.32 else radius + 13.0
            painter.drawText(
                QPointF(max(4.0, min(w - 75.0, pt.x() - 28.0)), pt.y() + text_offset_y),
                label,
            )
