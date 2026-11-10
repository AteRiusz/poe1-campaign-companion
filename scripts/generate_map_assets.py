"""
Generates static embedded `.png` map graphics for all 103 campaign steps in:
- `assets/maps/<step_id>.png` (Dashboard resolution: 380x230 @ 2x HiDPI = 760x460)
- `assets/maps/compact/<step_id>.png` (Overlay resolution: 210x140 @ 2x HiDPI = 420x280)

Because PoE1 campaign layouts rarely change, the app loads these static `.png` files
directly at runtime (and you can inspect or hand-edit any `.png` file in `assets/maps/`).
Run this script whenever you want to regenerate the static map images from `data/acts/*.json`:
    .venv\\Scripts\\python.exe scripts\\generate_map_assets.py
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

from src.route_engine import RouteEngine
from src.ui.map_canvas import ASSETS_MAPS_DIR, TopologyMapWidget


def _ensure_windows_fonts_loaded() -> None:
    fonts_dir = Path(r"C:\Windows\Fonts")
    for font_file in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf", "consolab.ttf", "seguisym.ttf"):
        fp = fonts_dir / font_file
        if fp.exists():
            QFontDatabase.addApplicationFont(str(fp))


def generate_all_map_assets() -> int:
    app = QApplication.instance() or QApplication([])
    _ = app
    _ensure_windows_fonts_loaded()

    engine = RouteEngine()
    ASSETS_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    compact_dir = ASSETS_MAPS_DIR / "compact"
    compact_dir.mkdir(parents=True, exist_ok=True)

    full_canvas = TopologyMapWidget(compact=False)
    compact_canvas = TopologyMapWidget(compact=True)

    count = 0
    for step in engine.steps:
        full_canvas.set_topology(step.topology, compass_label=step.compass, step_id=step.step_id)
        full_img = full_canvas.render_to_image(380, 230, scale=2.0)
        full_out = ASSETS_MAPS_DIR / f"{step.step_id}.png"
        full_img.save(str(full_out), "PNG")

        compact_canvas.set_topology(step.topology, compass_label=step.compass, step_id=step.step_id)
        compact_img = compact_canvas.render_to_image(210, 140, scale=2.0)
        compact_out = compact_dir / f"{step.step_id}.png"
        compact_img.save(str(compact_out), "PNG")
        count += 1

    return count


if __name__ == "__main__":
    total = generate_all_map_assets()
    print(f"Generated {total} full-size and {total} compact static PNG maps in {ASSETS_MAPS_DIR}")
