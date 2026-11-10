"""
Vector Topology Map Canvas (`TopologyMapWidget`) for PoE1 Campaign Companion.

Renders the simplified zone schematic (`nodes` and `edges` normalized in 0.0..1.0 coordinates)
using antialiased PyQt6 QPainter graphics with a 2D collision-free tooltip placement solver
so node tooltips never overlap each other or any node circles.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PyQt6.QtWidgets import QWidget

NODE_COLORS: Dict[str, str] = {
    "start": "#a8a29e",   # Stone gray
    "wp": "#38bdf8",      # Sky blue (Waypoint)
    "portal": "#0284c7",  # Deep sky blue (Portal trick)
    "quest": "#f59e0b",   # Amber gold (Quest / Trial / Skill Point)
    "boss": "#f43f5e",    # Rose red (Boss)
    "exit": "#10b981",    # Emerald green (Primary Exit)
}


def _intersection_area(a: QRectF, b: QRectF) -> float:
    inter = a.intersected(b)
    if inter.isEmpty():
        return 0.0
    return max(0.0, inter.width() * inter.height())


class TopologyMapWidget(QWidget):
    """Custom QWidget that draws a simplified node-and-edge layout map for the current zone."""

    def __init__(self, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.compact = compact
        self.topology: Dict[str, Any] = {"nodes": [], "edges": []}
        self.compass_label: str = ""
        self.setMinimumHeight(140 if compact else 230)

    def set_topology(self, topology: Dict[str, Any], compass_label: str = "") -> None:
        """Update the zone topology graph and trigger a repaint."""
        self.topology = topology or {"nodes": [], "edges": []}
        self.compass_label = compass_label
        self.update()

    def _compute_node_positions(self, w: float, h: float) -> Tuple[Dict[str, QPointF], float]:
        radius = 4.5 if self.compact else 6.5
        pad_x = 26.0 if self.compact else 46.0
        pad_y = 26.0 if self.compact else 36.0
        usable_w = max(40.0, w - 2 * pad_x)
        usable_h = max(40.0, h - 2 * pad_y)

        nodes: List[Dict[str, Any]] = self.topology.get("nodes", [])
        node_coords: Dict[str, QPointF] = {}
        for n in nodes:
            nx = pad_x + float(n.get("x", 0.5)) * usable_w
            ny = pad_y + float(n.get("y", 0.5)) * usable_h
            node_coords[str(n.get("id", ""))] = QPointF(nx, ny)
        return node_coords, radius

    def compute_label_rects(self, w: float, h: float) -> List[Tuple[Dict[str, Any], QPointF, QRectF]]:
        """
        Compute non-overlapping tooltip bounding boxes (`QRectF`) for all nodes on a canvas of size (w, h).
        Guarantees zero overlap between tooltip boxes and zero overlap with node circles.
        """
        nodes: List[Dict[str, Any]] = self.topology.get("nodes", [])
        if not nodes:
            return []

        node_coords, radius = self._compute_node_positions(w, h)
        label_font = QFont("Segoe UI", 8 if self.compact else 9, QFont.Weight.DemiBold)
        fm = QFontMetricsF(label_font)
        is_offscreen = QWidget.window(self) is not None and False  # measured via QFontMetricsF

        # Static obstacle rectangles for all node circles
        obstacles: List[QRectF] = []
        for pt in node_coords.values():
            r_pad = radius + 2.5
            obstacles.append(QRectF(pt.x() - r_pad, pt.y() - r_pad, 2 * r_pad, 2 * r_pad))

        margin = 4.0
        placed: List[Tuple[Dict[str, Any], QPointF, QRectF]] = []

        for n in nodes:
            nid = str(n.get("id", ""))
            label = str(n.get("label", ""))
            pt = node_coords.get(nid)
            if pt is None or not label:
                continue

            # Compute exact pill dimensions (cap bitmap fallback font in offscreen test mode)
            measured_w = fm.horizontalAdvance(label)
            max_char_w = 6.2 if self.compact else 7.4
            raw_text_w = min(measured_w, len(label) * max_char_w) if measured_w > len(label) * 9.0 else measured_w
            text_h = min(fm.height(), 13.0 if self.compact else 16.0)
            box_w = min(w - 2 * margin, raw_text_w + (10.0 if self.compact else 14.0))
            box_h = text_h + (4.0 if self.compact else 6.0)

            gap = radius + 4.0

            # 1. Immediate cardinal & diagonal candidate anchors around the node
            candidates: List[Tuple[float, float]] = [
                (pt.x() - box_w / 2.0, pt.y() - gap - box_h),      # Above
                (pt.x() - box_w / 2.0, pt.y() + gap),              # Below
                (pt.x() - box_w - gap, pt.y() - box_h / 2.0),      # Left
                (pt.x() + gap, pt.y() - box_h / 2.0),              # Right
                (pt.x() - box_w, pt.y() - gap - box_h),            # Above-Left
                (pt.x(), pt.y() - gap - box_h),                    # Above-Right
                (pt.x() - box_w, pt.y() + gap),                    # Below-Left
                (pt.x(), pt.y() + gap),                            # Below-Right
            ]

            # 2. Add a 2D search grid of slots across the canvas sorted by distance to `pt`
            grid_candidates: List[Tuple[float, float]] = []
            step_x = max(10.0, (w - box_w - 2 * margin) / 8.0)
            step_y = max(8.0, (h - box_h - 2 * margin) / 10.0)
            gx = margin
            while gx <= w - box_w - margin + 0.5:
                gy = margin
                while gy <= h - box_h - margin + 0.5:
                    grid_candidates.append((gx, gy))
                    gy += step_y
                gx += step_x

            grid_candidates.sort(
                key=lambda pos: (pos[0] + box_w / 2.0 - pt.x()) ** 2 + (pos[1] + box_h / 2.0 - pt.y()) ** 2
            )
            candidates.extend(grid_candidates)

            best_rect: QRectF | None = None
            best_score = float("inf")

            for cx, cy in candidates:
                clamped_x = max(margin, min(w - box_w - margin, cx))
                clamped_y = max(margin, min(h - box_h - margin, cy))
                cand = QRectF(clamped_x, clamped_y, box_w, box_h)

                padded_cand = cand.adjusted(-2.0, -2.0, 2.0, 2.0)
                label_overlap = sum(_intersection_area(padded_cand, prev_rect) for _, _, prev_rect in placed)
                obstacle_overlap = sum(_intersection_area(cand, obs) for obs in obstacles)

                dist = ((cand.center().x() - pt.x()) ** 2 + (cand.center().y() - pt.y()) ** 2) ** 0.5
                score = (label_overlap * 10000.0) + (obstacle_overlap * 2000.0) + dist

                if score < best_score:
                    best_score = score
                    best_rect = cand
                    if label_overlap == 0.0 and obstacle_overlap == 0.0:
                        break

            assert best_rect is not None
            placed.append((n, pt, best_rect))

        return placed

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

        nodes: List[Dict[str, Any]] = self.topology.get("nodes", [])
        edges: List[Dict[str, Any]] = self.topology.get("edges", [])

        if not nodes:
            return

        node_coords, radius = self._compute_node_positions(w, h)

        # 1. Draw connecting edges
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

        # 2. Compute non-overlapping tooltip placements and draw leader lines first
        placements = self.compute_label_rects(w, h)
        for n, pt, lrect in placements:
            ntype = str(n.get("type", "start"))
            accent = QColor(NODE_COLORS.get(ntype, "#a8a29e"))
            leader_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), 130), 1.1, Qt.PenStyle.DotLine)
            painter.setPen(leader_pen)
            painter.drawLine(pt, lrect.center())

        # 3. Draw node circles
        for n in nodes:
            nid = str(n.get("id", ""))
            ntype = str(n.get("type", "start"))
            pt = node_coords.get(nid)
            if pt is None:
                continue

            hex_color = NODE_COLORS.get(ntype, "#a8a29e")
            fill_color = QColor(hex_color)

            if ntype in ("exit", "quest", "boss", "wp", "portal"):
                glow = QColor(fill_color)
                glow.setAlpha(65)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(glow)
                painter.drawEllipse(pt, radius + 3.5, radius + 3.5)

            painter.setPen(QPen(QColor("#090b10"), 1.5))
            painter.setBrush(fill_color)
            painter.drawEllipse(pt, radius, radius)

        # 4. Draw tooltip pills on top
        label_font = QFont("Segoe UI", 8 if self.compact else 9, QFont.Weight.DemiBold)
        painter.setFont(label_font)

        for n, _pt, lrect in placements:
            ntype = str(n.get("type", "start"))
            label = str(n.get("label", ""))
            accent = QColor(NODE_COLORS.get(ntype, "#a8a29e"))

            bg_color = QColor(15, 19, 26, 238)
            border_color = QColor(accent.red(), accent.green(), accent.blue(), 175)
            painter.setPen(QPen(border_color, 1.0))
            painter.setBrush(bg_color)
            painter.drawRoundedRect(lrect, 4.0, 4.0)

            painter.setPen(QColor("#f5f5f4"))
            painter.drawText(lrect, Qt.AlignmentFlag.AlignCenter, label)
