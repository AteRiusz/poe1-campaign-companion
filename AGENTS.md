# AGENTS.md — Codebase Map & AI Agent Guide (`poe1-campaign-companion`)

This repository is structured specifically so AI agents can add zones, modify campaign routes, adjust visual schematics, or tweak UI behavior with zero friction.

> [!IMPORTANT]
> **Git Commit & Push Policy:** NEVER run `git commit` or `git push` on your own. Always leave code changes in the working tree and wait for the user to explicitly decide when to commit and push.

---

## 1. Directory & File Map

```text
C:\Projects\poe1-campaign-companion\
├── AGENTS.md                     # This Agent Codebase Map & Schema Reference
├── pyproject.toml                # Pytest & project configuration
├── main.py                       # App entry point (initializes SettingsManager, RouteEngine, DashboardWindow)
├── run_companion.bat             # Double-click launcher (runs main.py via .venv\Scripts\pythonw.exe)
├── config\
│   └── user_settings.json        # Auto-generated user preferences (opacity, extra info toggles, trial states)
├── data\
│   ├── acts\
│   │   ├── act1.json             # Act 1 zone-by-zone route & topology maps (16 steps)
│   │   ├── act2.json             # Act 2 zone-by-zone route & topology maps (13 steps)
│   │   ├── act3.json             # Act 3 zone-by-zone route & topology maps (12 steps)
│   │   ├── act4.json             # Act 4 zone-by-zone route & topology maps (11 steps)
│   │   ├── act5.json             # Act 5 zone-by-zone route & topology maps (9 steps)
│   │   ├── act6.json             # Act 6 zone-by-zone route & topology maps (11 steps)
│   │   ├── act7.json             # Act 7 zone-by-zone route & topology maps (9 steps)
│   │   ├── act8.json             # Act 8 zone-by-zone route & topology maps (9 steps)
│   │   ├── act9.json             # Act 9 zone-by-zone route & topology maps (6 steps)
│   │   └── act10.json            # Act 10 zone-by-zone route & topology maps (7 steps)
│   └── labyrinth_trials.json     # All 12 Campaign Labyrinth Trials (6 Normal, 3 Cruel, 3 Merciless)
├── src\
│   ├── __init__.py
│   ├── settings_manager.py       # AppSettings dataclass & SettingsManager JSON persistence
│   ├── log_watcher.py            # Regex parser & non-blocking ClientLogTailer for PoE's Client.txt
│   ├── route_engine.py           # Stateful RouteEngine & RouteStep model with forward-lookahead matching
│   └── ui\
│       ├── __init__.py
│       ├── map_canvas.py         # TopologyMapWidget (antialiased QPainter schematic renderer)
│       ├── overlay_window.py     # OverlayWindow (Frameless, topmost, click-through in-game HUD)
│       └── dashboard_window.py   # DashboardWindow (Second-screen Mission Control + Settings & Opacity bar)
└── tests\
    └── test_companion.py         # Headless unit + PyQt6 integration tests
```

---

## 2. How to Run & Test (For Agents)

* **Run Unit & UI Test Suite (0.15s, runs headless via `QT_QPA_PLATFORM=offscreen`):**
  ```powershell
  C:\Projects\poe1-campaign-companion\.venv\Scripts\pytest.exe -c C:\Projects\poe1-campaign-companion\pyproject.toml C:\Projects\poe1-campaign-companion\tests -v
  ```
* **Launch the Application:**
  ```powershell
  C:\Projects\poe1-campaign-companion\.venv\Scripts\python.exe C:\Projects\poe1-campaign-companion\main.py
  ```
  Or double-click `C:\Projects\poe1-campaign-companion\run_companion.bat`.

---

## 3. Core Architecture & Module Responsibilities

### A. `src/log_watcher.py`
* **`parse_client_log_line(line: str) -> Optional[LogEvent]`**:
  Parses a single line from Path of Exile's `logs/Client.txt`:
  * `ZONE_ENTERED`: Matches `: You have entered <Zone>.`
  * `WINDOW_FOCUS`: Matches `[WINDOW] Gained focus` / `[WINDOW] Lost focus`
  * `LEVEL_UP`: Matches `: <Name> (<Class>) is now level <N>`
* **`ClientLogTailer`**:
  Polls `Client.txt` every `150ms` via `QTimer` without locking the file. On first poll, scans the last `64 KB` of `Client.txt` so the app immediately synchronizes to the player's current zone even if opened mid-session.

### B. `src/settings_manager.py`
* **`AppSettings`**:
  * `opacity: float = 0.92` (`0.25` to `1.00`, controlled by the live Overlay Opacity Slider; applies **only** to `OverlayWindow`, while `DashboardWindow` is always locked at `1.0` / 100% opacity, and the opacity slider widget `self.opacity_group` is only visible when `OverlayWindow` is active)
  * `ui_mode: str = "dashboard"` (`"dashboard"` | `"overlay"` | `"both"`)
  * `overlay_click_through: bool = True` (uses `Qt.WindowType.WindowTransparentForInput`)
  * **Optional Extra Info Flags (Must default to `False` / OFF):**
    * `show_boss_info: bool = False`
    * `show_gem_rewards: bool = False`
    * `show_variants: bool = False`
  * **Labyrinth Trial Tracking:**
    * `unlocked_trials: List[str]` and `completed_trials: List[str]` persist across sessions via `mark_trial_unlocked()` and `set_trial_completed()`.

### C. `src/route_engine.py`
* Loads all per-Act JSON files (`data/acts/act1.json` .. `act10.json`, `103` steps total) in numerical Act order and all 12 Labyrinth Trials (`data/labyrinth_trials.json`).
* **`RouteEngine.on_zone_entered(zone_name: str) -> RouteStep`**:
  1. Searches forward up to 8 steps from `current_index` first (so revisiting hubs like `The Submerged Passage` or `The Crossroads` advances to the next logical pass).
  2. Falls back to the nearest matching step across the campaign.
  3. If the player enters an unmapped zone or Endgame Map (e.g., `Dunes`), sets `active_fallback` via `build_fallback_step()` without losing `current_index`.
* **`RouteEngine.get_trial_status(trial, unlocked_ids, completed_ids) -> str`**:
  Computes `'locked' | 'unlocked' | 'completed'` for each of the 12 Labyrinth Trials (`6` Normal, `3` Cruel, `3` Merciless), automatically unlocking trials when the player reaches their `unlock_zone` or progresses past their Act.

### D. `src/ui/map_canvas.py` (`TopologyMapWidget`)
* Renders normalized `0.0 .. 1.0` coordinates from `step.topology` (`nodes` and `edges`) using `QPainter`.
* **`compute_label_rects(w: float, h: float)`**: 2D collision-avoiding tooltip placement solver that checks immediate cardinal/diagonal offsets around each node first, then searches a distance-sorted 2D grid across the canvas to guarantee **0.0px overlap** between any two tooltip pills and **0.0px overlap** with any node circle.
* Supported `node["type"]` values and colors:
  * `"start"` (`#a8a29e` Stone)
  * `"wp"` (`#38bdf8` Sky Blue)
  * `"portal"` (`#0284c7` Deep Sky)
  * `"quest"` (`#f59e0b` Amber Gold)
  * `"boss"` (`#f43f5e` Rose Red)
  * `"exit"` (`#10b981` Emerald Green)
* Supported `edge["style"]` values:
  * `"main"` (Emerald dashed path)
  * `"branch"` (Amber dotted side-quest path)
  * `"river"` (Translucent blue stream + amber dashed line)

---

## 4. How to Add or Edit Campaign Zones (`data/acts/act1.json` .. `act10.json`)

To add a new step or modify an existing zone, edit the corresponding Act file in `data/acts/actN.json` (or `data/labyrinth_trials.json` for Labyrinth Trials). No Python code changes are required.

```json
{
  "step_id": "a1_s05_mud_flats",
  "act": 1,
  "step_number": 5,
  "zone_name": "The Mud Flats",
  "area_level": 4,
  "compass": "NE ↗",
  "summary": "Collect 3 Glyphs (follow water streams between nests) → Open Glyph Wall NE",
  "layout_tell": "The 3 Rhoa Nests are ALWAYS connected by shallow water streams on the ground!",
  "next_exit": "Touch Strange Glyph Wall → Enter The Submerged Passage",
  "portal_tip": "Ignore Fetid Pool during speed leveling",
  "badges": [
    { "label": "3 GLYPHS (STREAMS)", "color": "amber" }
  ],
  "actions": [
    { "tag": "QUEST", "color": "amber", "text": "Click 3 Rhoa Nests (follow the connecting water streams)" },
    { "tag": "EXIT", "color": "emerald", "text": "Enter The Submerged Passage" }
  ],
  "boss_info": "Charging Rhoas: High stun risk at Lvl 4.",
  "gem_reward": "Breaking Some Eggs (Tarkleigh): Lvl 4 Movement & Guard gems.",
  "variants": [
    { "title": "Triangle Streams", "desc": "Nests form a triangle in the middle." }
  ],
  "topology": {
    "nodes": [
      { "id": "start", "label": "Start", "x": 0.14, "y": 0.82, "type": "start" },
      { "id": "exit", "label": "→ Submerged", "x": 0.84, "y": 0.22, "type": "exit" }
    ],
    "edges": [
      { "from": "start", "to": "exit", "style": "main" }
    ]
  }
}
```
