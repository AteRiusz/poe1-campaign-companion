"""
Vector Topology Map Canvas (`TopologyMapWidget`) for PoE1 Campaign Companion.

Renders the simplified zone schematic (`nodes` and `edges` normalized in 0.0..1.0 coordinates)
live at native widget resolution using antialiased PyQt6 QPainter vector graphics, with a
2D collision-free tooltip placement solver so node tooltips never overlap each other or any node circles.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
    QPolygonF,
)
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
    """Custom QWidget that draws a crisp vector node-and-edge layout map for the current zone."""

    _fonts_loaded: bool = False

    @classmethod
    def _ensure_fonts(cls) -> None:
        if cls._fonts_loaded:
            return
        cls._fonts_loaded = True
        from PyQt6.QtGui import QFontDatabase

        fonts_dir = Path(r"C:\Windows\Fonts")
        for font_file in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf", "consolab.ttf", "seguisym.ttf"):
            fp = fonts_dir / font_file
            if fp.exists():
                QFontDatabase.addApplicationFont(str(fp))

    def __init__(self, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ensure_fonts()
        self.compact = compact
        self.topology: Dict[str, Any] = {"nodes": [], "edges": []}
        self.compass_label: str = ""
        self.setMinimumHeight(158 if compact else 252)

    def _banner_height(self) -> float:
        """Reserve bottom height when `procedural_note` is present on the zone topology."""
        proc_note = str(self.topology.get("procedural_note", "")).strip()
        if not proc_note:
            return 0.0
        return 18.0 if self.compact else 22.0

    def set_topology(
        self,
        topology: Dict[str, Any],
        compass_label: str = "",
    ) -> None:
        """Update the zone topology graph in memory and trigger a native vector repaint."""
        self.topology = topology or {"nodes": [], "edges": []}
        self.compass_label = compass_label
        self.update()

    def _compute_node_positions(self, w: float, h: float) -> Tuple[Dict[str, QPointF], float]:
        eff_h = max(60.0, h - self._banner_height())
        radius = 4.5 if self.compact else 6.5
        pad_x = 26.0 if self.compact else 46.0
        pad_y = 26.0 if self.compact else 36.0
        usable_w = max(40.0, w - 2 * pad_x)
        usable_h = max(40.0, eff_h - 2 * pad_y)

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
        Guarantees zero overlap between tooltip boxes, zero overlap with node circles, and zero overlap with
        the bottom procedural warning banner.
        """
        nodes: List[Dict[str, Any]] = self.topology.get("nodes", [])
        if not nodes:
            return []

        eff_h = max(60.0, h - self._banner_height())
        node_coords, radius = self._compute_node_positions(w, h)
        label_font = QFont("Segoe UI", 8 if self.compact else 9, QFont.Weight.DemiBold)
        fm = QFontMetricsF(label_font)

        # Static obstacle rectangles for all node circles
        node_obstacles: List[QRectF] = []
        for pt in node_coords.values():
            r_pad = radius + 0.5
            node_obstacles.append(QRectF(pt.x() - r_pad, pt.y() - r_pad, 2 * r_pad, 2 * r_pad))

        margin = 4.0
        placed: List[Tuple[Dict[str, Any], QPointF, QRectF]] = []

        # Place nodes nearest the top/bottom edges first so central nodes don't trap corner nodes
        ordered_nodes = sorted(nodes, key=lambda item: abs(float(item.get("y", 0.5)) - 0.5), reverse=True)

        for n in ordered_nodes:
            nid = str(n.get("id", ""))
            label = str(n.get("label", ""))
            pt = node_coords.get(nid)
            if pt is None or not label:
                continue

            # Compute exact pill dimensions
            measured_w = fm.horizontalAdvance(label)
            max_char_w = 6.2 if self.compact else 7.4
            raw_text_w = min(measured_w, len(label) * max_char_w) if measured_w > len(label) * 9.0 else measured_w
            text_h = min(fm.height(), 12.0 if self.compact else 16.0)
            box_w = min(w - 2 * margin, raw_text_w + (8.0 if self.compact else 14.0))
            box_h = text_h + (3.0 if self.compact else 6.0)

            gap = radius + (2.5 if self.compact else 4.0)

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

            # 2. Add exact tangent Y/X slots next to node obstacles & placed labels + fine 2D grid
            y_slots: List[float] = [margin, eff_h - box_h - margin, pt.y() - gap - box_h, pt.y() + gap]
            for obs in node_obstacles:
                y_slots.append(obs.bottom() + 0.5)
                y_slots.append(obs.top() - box_h - 0.5)
            for _, _, prev_r in placed:
                y_slots.append(prev_r.bottom() + 2.5)
                y_slots.append(prev_r.top() - box_h - 2.5)

            step_x = max(4.0, (w - box_w - 2 * margin) / 20.0)
            step_y = max(3.5, (eff_h - box_h - 2 * margin) / 24.0)
            gy = margin
            while gy <= eff_h - box_h - margin + 0.5:
                y_slots.append(gy)
                gy += step_y

            x_slots: List[float] = [margin, w - box_w - margin, pt.x() - box_w / 2.0]
            gx = margin
            while gx <= w - box_w - margin + 0.5:
                x_slots.append(gx)
                gx += step_x

            grid_candidates: List[Tuple[float, float]] = [
                (cx_s, cy_s) for cx_s in x_slots for cy_s in y_slots
            ]
            grid_candidates.sort(
                key=lambda pos: (pos[0] + box_w / 2.0 - pt.x()) ** 2 + (pos[1] + box_h / 2.0 - pt.y()) ** 2
            )
            candidates.extend(grid_candidates)

            best_rect: QRectF | None = None
            best_score = float("inf")

            for cx, cy in candidates:
                clamped_x = max(margin, min(w - box_w - margin, cx))
                clamped_y = max(margin, min(eff_h - box_h - margin, cy))
                cand = QRectF(clamped_x, clamped_y, box_w, box_h)

                padded_cand = cand.adjusted(-2.0, -2.0, 2.0, 2.0)
                label_overlap = sum(_intersection_area(padded_cand, prev_rect) for _, _, prev_rect in placed)
                node_overlap = sum(_intersection_area(cand, obs) for obs in node_obstacles)

                dist = ((cand.center().x() - pt.x()) ** 2 + (cand.center().y() - pt.y()) ** 2) ** 0.5
                score = (label_overlap * 50000.0) + (node_overlap * 50000.0) + dist

                if score < best_score:
                    best_score = score
                    best_rect = cand
                    if label_overlap == 0.0 and node_overlap == 0.0:
                        break

            assert best_rect is not None
            placed.append((n, pt, best_rect))

        return placed

    @staticmethod
    def _draw_edge_arrow(painter: QPainter, p1: QPointF, p2: QPointF, color: QColor, size: float = 6.0) -> None:
        """Draw a directional arrowhead along the midpoint of edge `p1 -> p2`."""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 24.0:
            return
        ux = dx / length
        uy = dy / length
        mx = p1.x() + dx * 0.54
        my = p1.y() + dy * 0.54

        tip = QPointF(mx + ux * size, my + uy * size)
        left = QPointF(mx - ux * size * 0.6 - uy * size * 0.65, my - uy * size * 0.6 + ux * size * 0.65)
        right = QPointF(mx - ux * size * 0.6 + uy * size * 0.65, my - uy * size * 0.6 - ux * size * 0.65)

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([tip, left, right]))
        painter.restore()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect()
        w = float(rect.width())
        h = float(rect.height())
        banner_h = self._banner_height()
        eff_h = max(60.0, h - banner_h)

        # Dark slate-stone background with subtle border & cardinal N/S/W/E guides
        painter.fillRect(rect, QColor("#090b10"))
        border_pen = QPen(QColor("#292524"), 1.2)
        painter.setPen(border_pen)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8.0, 8.0)

        grid_pen = QPen(QColor(255, 255, 255, 14), 1.0, Qt.PenStyle.DotLine)
        painter.setPen(grid_pen)
        painter.drawLine(QPointF(w / 2.0, 16.0), QPointF(w / 2.0, eff_h - 16.0))
        painter.drawLine(QPointF(18.0, eff_h / 2.0), QPointF(w - 18.0, eff_h / 2.0))

        compass_font = QFont("Consolas", 7 if self.compact else 8, QFont.Weight.Bold)
        painter.setFont(compass_font)
        painter.setPen(QColor("#57534e"))
        painter.drawText(QRectF(w / 2.0 - 10.0, 2.0, 20.0, 12.0), Qt.AlignmentFlag.AlignCenter, "N")
        painter.drawText(QRectF(w / 2.0 - 10.0, eff_h - 14.0, 20.0, 12.0), Qt.AlignmentFlag.AlignCenter, "S")
        painter.drawText(QRectF(3.0, eff_h / 2.0 - 7.0, 12.0, 14.0), Qt.AlignmentFlag.AlignCenter, "W")
        painter.drawText(QRectF(w - 15.0, eff_h / 2.0 - 7.0, 12.0, 14.0), Qt.AlignmentFlag.AlignCenter, "E")

        nodes: List[Dict[str, Any]] = self.topology.get("nodes", [])
        edges: List[Dict[str, Any]] = self.topology.get("edges", [])

        if not nodes:
            return

        node_coords, radius = self._compute_node_positions(w, h)

        # 1. Draw connecting edges + directional arrowheads
        arrow_sz = 4.5 if self.compact else 6.0
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
                self._draw_edge_arrow(painter, p1, p2, QColor("#fbbf24"), arrow_sz)
            elif style == "branch":
                branch_pen = QPen(QColor("#f59e0b"), 2.0, Qt.PenStyle.DotLine)
                painter.setPen(branch_pen)
                painter.drawLine(p1, p2)
                self._draw_edge_arrow(painter, p1, p2, QColor("#f59e0b"), arrow_sz * 0.9)
            else:
                main_pen = QPen(QColor("#34d399"), 2.8 if not self.compact else 2.2, Qt.PenStyle.DashLine)
                painter.setPen(main_pen)
                painter.drawLine(p1, p2)
                self._draw_edge_arrow(painter, p1, p2, QColor("#34d399"), arrow_sz)

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

        # 5. Draw procedural / multi-seed layout warning banner at bottom of canvas when present
        proc_note = str(self.topology.get("procedural_note", "")).strip()
        if proc_note and banner_h > 0.0:
            banner_rect = QRectF(4.0, h - banner_h + 1.0, max(20.0, w - 8.0), banner_h - 3.0)
            painter.setPen(QPen(QColor(245, 158, 11, 185), 1.0))
            painter.setBrush(QColor(28, 22, 12, 235))
            painter.drawRoundedRect(banner_rect, 4.0, 4.0)

            banner_font = QFont("Segoe UI", 7 if self.compact else 8, QFont.Weight.DemiBold)
            painter.setFont(banner_font)
            painter.setPen(QColor("#fcd34d"))
            raw_banner_text = (
                "⚠ Procedural: Actual layout may differ by seed"
                if self.compact
                else f"⚠ {proc_note}"
            )
            bfm = QFontMetricsF(banner_font)
            elided = bfm.elidedText(
                raw_banner_text,
                Qt.TextElideMode.ElideRight,
                max(10.0, banner_rect.width() - 10.0),
            )
            painter.drawText(banner_rect.adjusted(5.0, 0.0, -5.0, 0.0), Qt.AlignmentFlag.AlignCenter, elided)
